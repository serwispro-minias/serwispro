from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.extensions import db
from app.estimate_approval.service import EstimateApprovalService, EstimateApprovalValidationError
from app.models.branch import Branch
from app.models.company import Company
from app.models.customer import Customer, CustomerTypeEnum
from app.models.device import Device
from app.models.estimate_approval_token import EstimateApprovalToken
from app.models.service_estimate import ServiceEstimate
from app.models.service_estimate_item import ServiceEstimateItem
from app.models.service_order import ServiceOrder
from app.models.service_order_action import ServiceOrderAction
from app.models.service_order_status_history import ServiceOrderStatusHistory
from app.models.setting import Setting


class _NotificationResult:
    def __init__(self, status: str = "SENT") -> None:
        self.status = status


class _NotificationStub:
    def __init__(self) -> None:
        self.sent_payloads: list[dict[str, object]] = []

    def send_draft(self, **kwargs):
        self.sent_payloads.append(kwargs)
        return _NotificationResult(status="SENT")


def _ensure_tables() -> None:
    db.Model.metadata.create_all(
        bind=db.engine,
        tables=[
            Branch.__table__,
            Customer.__table__,
            Device.__table__,
            ServiceOrder.__table__,
            ServiceEstimate.__table__,
            ServiceEstimateItem.__table__,
            EstimateApprovalToken.__table__,
            ServiceOrderAction.__table__,
            ServiceOrderStatusHistory.__table__,
            Setting.__table__,
        ],
    )


def _seed_estimate_graph(*, company_id: int, branch_id: int, estimate_status: str = "SENT") -> tuple[ServiceOrder, ServiceEstimate, EstimateApprovalToken]:
    customer = Customer(
        company_id=company_id,
        branch_id=branch_id,
        customer_type=CustomerTypeEnum.PERSON,
        full_name="Jan Test",
        email="jan.test@example.com",
        phone="111222333",
    )
    db.session.add(customer)
    db.session.flush()

    device = Device(
        company_id=company_id,
        branch_id=branch_id,
        customer_id=customer.id,
        manufacturer="Dell",
        model="Latitude",
    )
    db.session.add(device)
    db.session.flush()

    order = ServiceOrder(
        company_id=company_id,
        branch_id=branch_id,
        customer_id=customer.id,
        device_id=device.id,
        order_number="SER-0001",
        status="WAITING_CUSTOMER_DECISION",
        issue_description="Nie uruchamia sie",
    )
    db.session.add(order)
    db.session.flush()

    estimate = ServiceEstimate(
        company_id=company_id,
        branch_id=branch_id,
        service_order_id=order.id,
        version_number=1,
        status=estimate_status,
        title="Kosztorys testowy",
        gross_total=Decimal("123.45"),
        net_total=Decimal("100.37"),
        vat_total=Decimal("23.08"),
        parts_net=Decimal("80.00"),
        materials_net=Decimal("10.00"),
        services_net=Decimal("10.37"),
        discount_total=Decimal("0.00"),
    )
    db.session.add(estimate)
    db.session.flush()

    token = EstimateApprovalToken(
        company_id=company_id,
        branch_id=branch_id,
        estimate_id=estimate.id,
        token="token-test-123",
        status="PENDING",
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    db.session.add(token)
    db.session.commit()

    return order, estimate, token


def test_process_customer_accepts_estimate(app):
    with app.app_context():
        _ensure_tables()

        company = db.session.get(Company, app.config["TEST_COMPANY_ID"])
        assert company is not None
        company.email = "serwis@example.com"

        branch = Branch(
            company_id=company.id,
            name="Main",
            code="TST-MAIN",
        )
        db.session.add(branch)
        db.session.commit()

        order, estimate, token = _seed_estimate_graph(company_id=company.id, branch_id=branch.id)

        service = EstimateApprovalService(notification_service=_NotificationStub())
        service.process_customer_decision(
            token_value=token.token,
            decision="ACCEPT",
            customer_note="Prosze realizowac.",
            ip_address="127.0.0.1",
            user_agent="pytest",
        )

        refreshed_token = db.session.get(EstimateApprovalToken, token.id)
        refreshed_estimate = db.session.get(ServiceEstimate, estimate.id)
        refreshed_order = db.session.get(ServiceOrder, order.id)

        assert refreshed_token is not None
        assert refreshed_token.status == "ACCEPTED"
        assert refreshed_token.used_at is not None
        assert refreshed_estimate is not None
        assert refreshed_estimate.status == "ACCEPTED"
        assert refreshed_order is not None
        assert refreshed_order.status == "READY_FOR_REPAIR"

        actions = db.session.query(ServiceOrderAction).filter_by(service_order_id=order.id).all()
        assert len(actions) == 1
        assert "Klient zaakceptował kosztorys" in actions[0].description
        status_events = db.session.query(ServiceOrderStatusHistory).filter_by(service_order_id=order.id).all()
        assert len(status_events) == 1
        assert status_events[0].new_status == "READY_FOR_REPAIR"


def test_process_customer_rejects_estimate(app):
    with app.app_context():
        _ensure_tables()

        company = db.session.get(Company, app.config["TEST_COMPANY_ID"])
        assert company is not None
        company.email = "serwis@example.com"

        branch = db.session.query(Branch).filter_by(code="TST-MAIN").one_or_none()
        if branch is None:
            branch = Branch(company_id=company.id, name="Main", code="TST-MAIN")
            db.session.add(branch)
            db.session.commit()

        order, estimate, token = _seed_estimate_graph(company_id=company.id, branch_id=branch.id)

        service = EstimateApprovalService(notification_service=_NotificationStub())
        service.process_customer_decision(
            token_value=token.token,
            decision="REJECT",
            customer_note="Za drogo.",
            ip_address="127.0.0.1",
            user_agent="pytest",
        )

        refreshed_token = db.session.get(EstimateApprovalToken, token.id)
        refreshed_estimate = db.session.get(ServiceEstimate, estimate.id)
        refreshed_order = db.session.get(ServiceOrder, order.id)

        assert refreshed_token is not None
        assert refreshed_token.status == "REJECTED"
        assert refreshed_estimate is not None
        assert refreshed_estimate.status == "REJECTED"
        assert refreshed_order is not None
        assert refreshed_order.status == "WAITING_CUSTOMER_DECISION"

        actions = db.session.query(ServiceOrderAction).filter_by(service_order_id=order.id).all()
        assert len(actions) == 1
        assert "Klient odrzucił kosztorys" in actions[0].description


def test_token_cannot_be_reused(app):
    with app.app_context():
        _ensure_tables()

        company = db.session.get(Company, app.config["TEST_COMPANY_ID"])
        assert company is not None
        company.email = "serwis@example.com"

        branch = db.session.query(Branch).filter_by(code="TST-MAIN").one_or_none()
        if branch is None:
            branch = Branch(company_id=company.id, name="Main", code="TST-MAIN")
            db.session.add(branch)
            db.session.commit()

        _, _, token = _seed_estimate_graph(company_id=company.id, branch_id=branch.id)

        service = EstimateApprovalService(notification_service=_NotificationStub())
        service.process_customer_decision(
            token_value=token.token,
            decision="ACCEPT",
            customer_note="ok",
            ip_address="127.0.0.1",
            user_agent="pytest",
        )

        with pytest.raises(EstimateApprovalValidationError) as exc_info:
            service.process_customer_decision(
                token_value=token.token,
                decision="REJECT",
                customer_note="druga proba",
                ip_address="127.0.0.1",
                user_agent="pytest",
            )
        assert "wykorzystany" in str(exc_info.value)
