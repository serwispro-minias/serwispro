from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.models.branch import Branch
from app.models.customer import Customer, CustomerTypeEnum
from app.models.device import Device
from app.models.role import Role
from app.models.service_estimate import ServiceEstimate
from app.models.service_order import ServiceOrder
from app.models.service_order_action import ServiceOrderAction
from app.models.service_order_part_reservation import ServiceOrderPartReservation
from app.models.service_order_status_history import ServiceOrderStatusHistory
from app.models.user import User
from app.models.user_role import UserRole
from app.models.workflow_status import WorkflowStatus
from app.models.workflow_transition import WorkflowTransition
from app.workflow.exceptions import WorkflowValidationError
from app.workflow.service import WorkflowService


def _ensure_tables() -> None:
    db.Model.metadata.create_all(
        bind=db.engine,
        tables=[
            Branch.__table__,
            Role.__table__,
            UserRole.__table__,
            Customer.__table__,
            Device.__table__,
            ServiceOrder.__table__,
            ServiceEstimate.__table__,
            ServiceOrderAction.__table__,
            ServiceOrderPartReservation.__table__,
            ServiceOrderStatusHistory.__table__,
            WorkflowStatus.__table__,
            WorkflowTransition.__table__,
        ],
    )


def _make_branch(*, company_id: int, suffix: str) -> Branch:
    branch = Branch(company_id=company_id, name=f"Main {suffix}", code=f"WF-{suffix}")
    db.session.add(branch)
    db.session.commit()
    return branch


def _make_order_graph(*, company_id: int, branch_id: int) -> ServiceOrder:
    customer = Customer(
        company_id=company_id,
        branch_id=branch_id,
        customer_type=CustomerTypeEnum.PERSON,
        full_name="Workflow Klient",
        email="workflow@example.com",
        phone="123123123",
    )
    db.session.add(customer)
    db.session.flush()

    device = Device(
        company_id=company_id,
        branch_id=branch_id,
        customer_id=customer.id,
        manufacturer="HP",
        model="ProBook",
    )
    db.session.add(device)
    db.session.flush()

    order = ServiceOrder(
        company_id=company_id,
        branch_id=branch_id,
        customer_id=customer.id,
        device_id=device.id,
        order_number=f"WF-{branch_id}-001",
        status="READY_FOR_REPAIR",
        issue_description="Test workflow",
    )
    db.session.add(order)
    db.session.commit()
    return order


def _assign_admin_role(*, user: User, company_id: int, branch_id: int) -> None:
    role = Role(company_id=company_id, branch_id=branch_id, name="Administrator")
    db.session.add(role)
    db.session.flush()
    db.session.add(UserRole(company_id=company_id, branch_id=branch_id, user_id=user.id, role_id=role.id))
    db.session.commit()


def test_default_workflow_seed(app):
    with app.app_context():
        _ensure_tables()
        company_id = int(app.config["TEST_COMPANY_ID"])
        user_id = int(app.config["TEST_USER_ID"])
        branch = _make_branch(company_id=company_id, suffix="SEED")

        service = WorkflowService()
        service.ensure_default_workflow(company_id=company_id, branch_id=branch.id, user_id=user_id)

        statuses = service.repository.list_statuses(company_id=company_id, branch_id=branch.id)
        transitions = service.repository.list_transitions(company_id=company_id, branch_id=branch.id)

        assert len(statuses) >= 9
        assert any(status.code == "RECEIVED" for status in statuses)
        assert any(transition.from_status.code == "READY_FOR_PICKUP" and transition.to_status.code == "ISSUED" for transition in transitions)


def test_cannot_start_repair_without_technician_action(app):
    with app.app_context():
        _ensure_tables()
        company_id = int(app.config["TEST_COMPANY_ID"])
        user = db.session.get(User, int(app.config["TEST_USER_ID"]))
        assert user is not None
        branch = _make_branch(company_id=company_id, suffix="NTECH")

        service = WorkflowService()
        service.ensure_default_workflow(company_id=company_id, branch_id=branch.id, user_id=user.id)

        order = _make_order_graph(company_id=company_id, branch_id=branch.id)

        with pytest.raises(WorkflowValidationError) as exc_info:
            service.change_order_status(
                order_id=order.id,
                target_status_code="IN_REPAIR",
                company_id=company_id,
                branch_id=branch.id,
                actor=user,
                note="test",
                ip_address="127.0.0.1",
                force=False,
            )

        assert "technika" in str(exc_info.value)


def test_cannot_release_without_accepted_estimate(app):
    with app.app_context():
        _ensure_tables()
        company_id = int(app.config["TEST_COMPANY_ID"])
        user = db.session.get(User, int(app.config["TEST_USER_ID"]))
        assert user is not None
        branch = _make_branch(company_id=company_id, suffix="NOEST")

        service = WorkflowService()
        service.ensure_default_workflow(company_id=company_id, branch_id=branch.id, user_id=user.id)

        order = _make_order_graph(company_id=company_id, branch_id=branch.id)
        order.status = "IN_REPAIR"
        db.session.add(order)
        db.session.flush()

        db.session.add(
            ServiceOrderAction(
                company_id=company_id,
                branch_id=branch.id,
                service_order_id=order.id,
                action_date=date.today(),
                technician_id=user.id,
                action_type="REPAIR",
                description="Naprawa zakończona",
                is_visible_for_customer=False,
            )
        )
        db.session.add(
            ServiceEstimate(
                company_id=company_id,
                branch_id=branch.id,
                service_order_id=order.id,
                version_number=1,
                status="SENT",
                title="Kosztorys",
                net_total=Decimal("100.00"),
                vat_total=Decimal("23.00"),
                gross_total=Decimal("123.00"),
                parts_net=Decimal("80.00"),
                materials_net=Decimal("10.00"),
                services_net=Decimal("10.00"),
                discount_total=Decimal("0.00"),
            )
        )
        db.session.commit()

        with pytest.raises(WorkflowValidationError) as exc_info:
            service.change_order_status(
                order_id=order.id,
                target_status_code="READY_FOR_PICKUP",
                company_id=company_id,
                branch_id=branch.id,
                actor=user,
                note="test",
                ip_address="127.0.0.1",
                force=False,
            )

        assert "zaakceptowanego kosztorysu" in str(exc_info.value)


def test_admin_force_transition_writes_history_ip(app):
    with app.app_context():
        _ensure_tables()
        company_id = int(app.config["TEST_COMPANY_ID"])
        user = db.session.get(User, int(app.config["TEST_USER_ID"]))
        assert user is not None
        branch = _make_branch(company_id=company_id, suffix="FORCE")
        _assign_admin_role(user=user, company_id=company_id, branch_id=branch.id)

        service = WorkflowService()
        service.ensure_default_workflow(company_id=company_id, branch_id=branch.id, user_id=user.id)

        order = _make_order_graph(company_id=company_id, branch_id=branch.id)
        order.status = "RECEIVED"
        db.session.add(order)
        db.session.commit()

        result = service.change_order_status(
            order_id=order.id,
            target_status_code="CLOSED",
            company_id=company_id,
            branch_id=branch.id,
            actor=user,
            note="tryb awaryjny",
            ip_address="10.10.10.10",
            force=True,
        )

        assert result.forced is True
        assert result.order.status == "CLOSED"

        events = db.session.query(ServiceOrderStatusHistory).filter_by(service_order_id=order.id).all()
        assert len(events) == 1
        assert events[0].ip_address == "10.10.10.10"
        assert "FORCE" in (events[0].note or "")
