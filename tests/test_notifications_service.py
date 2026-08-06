from __future__ import annotations

from datetime import date

import pytest

from app.extensions import db
from app.models.customer import Customer
from app.models.device import Device
from app.models.notification_message import NotificationMessage
from app.models.notification_template import NotificationTemplate
from app.models.service_order import ServiceOrder
from app.models.setting import Setting
from app.notifications.constants import (
    CHANNEL_EMAIL,
    CHANNEL_SMS,
    NOTIFICATION_STATUS_CANCELLED,
    NOTIFICATION_STATUS_ERROR,
    NOTIFICATION_STATUS_SENT,
)
from app.notifications.providers import EmailProvider, ProviderFactory, ProviderResult, SmsProvider
from app.notifications.service import NotificationService


class FakeEmailProvider(EmailProvider):
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.calls: list[dict[str, str]] = []

    def send(self, *, recipient: str, subject: str | None, content: str, config: dict[str, str]) -> ProviderResult:
        self.calls.append({"recipient": recipient, "subject": subject or "", "content": content})
        if self.ok:
            return ProviderResult(ok=True, provider_name="fake_email", server_response="queued")
        return ProviderResult(ok=False, provider_name="fake_email", error_message="fail")


class FakeSmsProvider(SmsProvider):
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.calls: list[dict[str, str]] = []

    def send(self, *, recipient: str, content: str, config: dict[str, str]) -> ProviderResult:
        self.calls.append({"recipient": recipient, "content": content})
        if self.ok:
            return ProviderResult(ok=True, provider_name="fake_sms", server_response="queued")
        return ProviderResult(ok=False, provider_name="fake_sms", error_message="fail")


@pytest.fixture()
def notifications_schema(app):
    with app.app_context():
        db.Model.metadata.create_all(
            bind=db.engine,
            tables=[
                Device.__table__,
                ServiceOrder.__table__,
                Setting.__table__,
                NotificationTemplate.__table__,
                NotificationMessage.__table__,
            ],
        )

    yield

    with app.app_context():
        db.session.remove()
        db.Model.metadata.drop_all(
            bind=db.engine,
            tables=[
                NotificationMessage.__table__,
                NotificationTemplate.__table__,
                Setting.__table__,
                ServiceOrder.__table__,
                Device.__table__,
            ],
        )


def _create_order(company_id: int) -> int:
    customer = Customer(
        customer_type="PERSON",
        full_name="Jan Kowalski",
        email="jan@example.com",
        phone="500600700",
        company_id=company_id,
    )
    db.session.add(customer)
    db.session.flush()

    device = Device(
        customer_id=customer.id,
        manufacturer="Brother",
        model="DCP-1110",
        serial_number="SER-NOTIF-1",
        company_id=company_id,
    )
    db.session.add(device)
    db.session.flush()

    order = ServiceOrder(
        customer_id=customer.id,
        device_id=device.id,
        order_number="SO-NOTIF-1",
        status="RECEIVED",
        priority="NORMAL",
        intake_date=date.today(),
        issue_description="Test",
        estimated_cost=120,
        company_id=company_id,
    )
    db.session.add(order)
    db.session.flush()
    return int(order.id)


def _seed_notification_settings(company_id: int) -> None:
    for key, value in {
        "notifications.email_enabled": "1",
        "notifications.sms_enabled": "1",
        "notifications.default_sender_email": "serwis@example.com",
        "notifications.smtp.host": "smtp.example.com",
        "notifications.smtp.port": "587",
        "notifications.smtp.login": "user",
        "notifications.smtp.password": "pass",
        "notifications.smtp.use_tls": "1",
        "notifications.smtp.use_ssl": "0",
        "notifications.sms.provider_name": "fake",
        "notifications.sms.api_url": "https://sms.example.com",
        "notifications.sms.api_token": "token",
        "notifications.sms.sender": "SERWIS",
        "company_name": "SerwisPRO Test",
        "company_phone": "+48 123 123 123",
    }.items():
        db.session.add(Setting(company_id=company_id, key=key, value=value))
    db.session.commit()


def test_template_rendering_and_variables(app, company_id, notifications_schema):
    service = NotificationService(
        providers=ProviderFactory(email_provider=FakeEmailProvider(), sms_provider=FakeSmsProvider())
    )

    with app.app_context():
        order_id = _create_order(company_id)
        _seed_notification_settings(company_id)

        context = service.build_context_for_order(order_id=order_id, company_id=company_id, branch_id=None)
        rendered = service.render_with_context(
            "Zlecenie {{order_number}} dla {{customer_name}} {{device_name}} {{status}} {{pickup_amount}} {{company_name}} {{company_phone}}",
            context,
        )

        assert "SO-NOTIF-1" in rendered
        assert "Jan Kowalski" in rendered
        assert "Brother DCP-1110" in rendered
        assert "RECEIVED" in rendered
        assert "120.00 PLN" in rendered
        assert "SerwisPRO Test" in rendered


def test_history_and_provider_mechanism(app, company_id, notifications_schema):
    email_provider = FakeEmailProvider(ok=True)
    sms_provider = FakeSmsProvider(ok=False)
    service = NotificationService(providers=ProviderFactory(email_provider=email_provider, sms_provider=sms_provider))

    with app.app_context():
        order_id = _create_order(company_id)
        _seed_notification_settings(company_id)

        sent = service.send_draft(
            order_id=order_id,
            company_id=company_id,
            branch_id=None,
            user_id=1,
            channel=CHANNEL_EMAIL,
            recipient="jan@example.com",
            subject="Temat",
            content="Treść",
            event_key="RECEIVED",
            template_id=None,
        )
        failed = service.send_draft(
            order_id=order_id,
            company_id=company_id,
            branch_id=None,
            user_id=1,
            channel=CHANNEL_SMS,
            recipient="500600700",
            subject=None,
            content="Treść SMS",
            event_key="RECEIVED",
            template_id=None,
        )
        cancelled = service.cancel_draft(
            order_id=order_id,
            company_id=company_id,
            branch_id=None,
            user_id=1,
            channel=CHANNEL_SMS,
            recipient="500600700",
            subject=None,
            content="Anulowane",
            event_key="RECEIVED",
            template_id=None,
        )

        assert sent.status == NOTIFICATION_STATUS_SENT
        assert failed.status == NOTIFICATION_STATUS_ERROR
        assert cancelled.status == NOTIFICATION_STATUS_CANCELLED

        history = service.list_messages_for_order(order_id=order_id, company_id=company_id, branch_id=None)
        assert len(history) == 3
        assert email_provider.calls
        assert sms_provider.calls

        statuses = {item.status for item in history}
        assert NOTIFICATION_STATUS_SENT in statuses
        assert NOTIFICATION_STATUS_ERROR in statuses
        assert NOTIFICATION_STATUS_CANCELLED in statuses
