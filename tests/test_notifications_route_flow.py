from __future__ import annotations

from datetime import date

import pytest

from app.extensions import db
from app.models.customer import Customer
from app.models.device import Device
from app.models.notification_message import NotificationMessage
from app.models.notification_queue import NotificationQueue
from app.models.notification_template import NotificationTemplate
from app.models.service_order_action import ServiceOrderAction
from app.models.service_order import ServiceOrder
from app.models.service_order_status_history import ServiceOrderStatusHistory
from app.models.setting import Setting
from app.models.purchase_request import PurchaseRequest


@pytest.fixture()
def notifications_route_schema(app):
    with app.app_context():
        db.Model.metadata.create_all(
            bind=db.engine,
            tables=[
                Device.__table__,
                ServiceOrder.__table__,
                ServiceOrderAction.__table__,
                ServiceOrderStatusHistory.__table__,
                Setting.__table__,
                NotificationTemplate.__table__,
                NotificationMessage.__table__,
                NotificationQueue.__table__,
                PurchaseRequest.__table__,
            ],
        )

    yield

    with app.app_context():
        db.session.remove()
        db.Model.metadata.drop_all(
            bind=db.engine,
            tables=[
                NotificationMessage.__table__,
                NotificationQueue.__table__,
                NotificationTemplate.__table__,
                Setting.__table__,
                ServiceOrderStatusHistory.__table__,
                ServiceOrderAction.__table__,
                PurchaseRequest.__table__,
                ServiceOrder.__table__,
                Device.__table__,
            ],
        )


def _create_order_with_templates(company_id: int) -> int:
    customer = Customer(
        customer_type="PERSON",
        full_name="Ala Test",
        email="ala@example.com",
        phone="501501501",
        company_id=company_id,
    )
    db.session.add(customer)
    db.session.flush()

    device = Device(
        customer_id=customer.id,
        manufacturer="HP",
        model="LaserJet",
        serial_number="ROUTE-NOTIF-1",
        company_id=company_id,
    )
    db.session.add(device)
    db.session.flush()

    order = ServiceOrder(
        customer_id=customer.id,
        device_id=device.id,
        order_number="SO-ROUTE-1",
        status="RECEIVED",
        priority="NORMAL",
        intake_date=date.today(),
        issue_description="Test",
        company_id=company_id,
    )
    db.session.add(order)
    db.session.flush()

    settings = {
        "notifications.email_enabled": "1",
        "notifications.sms_enabled": "1",
        "notifications.default_sender_email": "serwis@example.com",
        "notifications.smtp.host": "smtp.example.com",
        "notifications.smtp.port": "587",
        "notifications.smtp.login": "u",
        "notifications.smtp.password": "p",
        "notifications.smtp.use_tls": "1",
        "notifications.smtp.use_ssl": "0",
        "notifications.sms.provider_name": "generic_api",
        "notifications.sms.api_url": "",
        "notifications.sms.api_token": "",
        "notifications.sms.sender": "SERWIS",
        "company_name": "SerwisPRO Test",
        "company_phone": "+48 111 222 333",
    }
    for key, value in settings.items():
        db.session.add(Setting(company_id=company_id, key=key, value=value))

    db.session.add(
        NotificationTemplate(
            company_id=company_id,
            name="RECEIVED EMAIL",
            event_key="RECEIVED",
            channel="EMAIL",
            subject="Przyjęcie {{order_number}}",
            body="Witaj {{customer_name}}",
            is_enabled=True,
        )
    )
    db.session.commit()
    return int(order.id)


def test_status_change_proposes_notification(auth_client, app, company_id, notifications_route_schema):
    with app.app_context():
        order_id = _create_order_with_templates(company_id)

    response = auth_client.post(
        f"/orders/{order_id}/status",
        data={"new_status": "RECEIVED", "note": "test"},
        follow_redirects=True,
    )
    assert response.status_code == 200

    # same status is invalid; now valid transition to diagnosis should succeed but no template, so no proposal
    response = auth_client.post(
        f"/orders/{order_id}/status",
        data={"new_status": "DIAGNOSIS", "note": "diag"},
        follow_redirects=False,
    )
    assert response.status_code == 302


def test_settings_notifications_page_loads(auth_client, app, company_id, notifications_route_schema):
    with app.app_context():
        _create_order_with_templates(company_id)

    response = auth_client.get("/settings/notifications")
    assert response.status_code == 200


@pytest.mark.parametrize("channel", ["EMAIL", "SMS"])
def test_compose_notification_modal_loads(auth_client, app, company_id, notifications_route_schema, channel):
    with app.app_context():
        order_id = _create_order_with_templates(company_id)

    response = auth_client.get(f"/orders/{order_id}/communication/compose?channel={channel}")
    assert response.status_code == 200
