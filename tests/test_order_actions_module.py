from __future__ import annotations

from datetime import date

import pytest

from app.extensions import db
from app.models.customer import Customer
from app.models.device import Device
from app.models.service_estimate import ServiceEstimate
from app.models.service_estimate_item import ServiceEstimateItem
from app.models.service_order import ServiceOrder
from app.models.service_order_action import ServiceOrderAction
from app.models.user import User
from app.models.purchase_request import PurchaseRequest


@pytest.fixture()
def order_actions_schema(app):
    with app.app_context():
        db.Model.metadata.create_all(
            bind=db.engine,
            tables=[
                Device.__table__,
                ServiceOrder.__table__,
                ServiceOrderAction.__table__,
                ServiceEstimate.__table__,
                ServiceEstimateItem.__table__,
                PurchaseRequest.__table__,
            ],
        )

    yield

    with app.app_context():
        db.session.remove()
        db.Model.metadata.drop_all(
            bind=db.engine,
            tables=[
                ServiceOrderAction.__table__,
                ServiceOrder.__table__,
                Device.__table__,
                ServiceEstimateItem.__table__,
                ServiceEstimate.__table__,
                PurchaseRequest.__table__,
            ],
        )


def _create_order(company_id: int) -> tuple[int, int]:
    customer = Customer(
        customer_type="PERSON",
        full_name="Order Action Customer",
        email="order-actions@example.com",
        phone="500500500",
        company_id=company_id,
    )
    db.session.add(customer)
    db.session.flush()

    device = Device(
        customer_id=customer.id,
        manufacturer="Canon",
        model="MG3650",
        serial_number="SN-ACTION-1",
        company_id=company_id,
    )
    db.session.add(device)
    db.session.flush()

    service_order = ServiceOrder(
        customer_id=customer.id,
        device_id=device.id,
        order_number="SO-ACT-001",
        status="RECEIVED",
        priority="NORMAL",
        intake_date=date(2026, 8, 3),
        issue_description="Nie pobiera papieru",
        company_id=company_id,
    )
    db.session.add(service_order)
    db.session.commit()
    return int(service_order.id), int(device.id)


def test_add_order_action_entry(auth_client, app, company_id, order_actions_schema):
    with app.app_context():
        order_id, _ = _create_order(company_id)

    response = auth_client.post(
        f"/orders/{order_id}/actions/new",
        data={
            "action_date": "2026-08-03",
            "technician_id": "0",
            "action_type": "DIAGNOSIS",
            "description": "Wykonano diagnozę układu poboru papieru.",
            "work_time_minutes": "25",
            "cost": "120.00",
            "is_visible_for_customer": "1",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/orders/{order_id}")

    with app.app_context():
        entries = db.session.query(ServiceOrderAction).filter_by(service_order_id=order_id).all()
        assert len(entries) == 1
        assert entries[0].action_type == "DIAGNOSIS"
        assert entries[0].description == "Wykonano diagnozę układu poboru papieru."
        assert entries[0].work_time_minutes == 25


def test_edit_order_action_entry(auth_client, app, company_id, order_actions_schema):
    with app.app_context():
        order_id, _ = _create_order(company_id)
        action = ServiceOrderAction(
            service_order_id=order_id,
            company_id=company_id,
            action_date=date(2026, 8, 2),
            action_type="DIAGNOSIS",
            description="Wstępna diagnoza.",
            work_time_minutes=10,
            cost=50,
            is_visible_for_customer=True,
        )
        db.session.add(action)
        db.session.commit()
        action_id = int(action.id)

    response = auth_client.post(
        f"/orders/{order_id}/actions/{action_id}/edit",
        data={
            "action_date": "2026-08-04",
            "technician_id": "0",
            "action_type": "REPAIR",
            "description": "Wymieniono rolki poboru.",
            "work_time_minutes": "40",
            "cost": "180.00",
            "is_visible_for_customer": "1",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/orders/{order_id}")

    with app.app_context():
        updated = db.session.get(ServiceOrderAction, action_id)
        assert updated is not None
        assert updated.action_type == "REPAIR"
        assert updated.description == "Wymieniono rolki poboru."
        assert updated.work_time_minutes == 40


def test_delete_order_action_entry(auth_client, app, company_id, order_actions_schema):
    with app.app_context():
        order_id, _ = _create_order(company_id)
        action = ServiceOrderAction(
            service_order_id=order_id,
            company_id=company_id,
            action_date=date(2026, 8, 2),
            action_type="OTHER",
            description="Wpis do usunięcia.",
            is_visible_for_customer=False,
        )
        db.session.add(action)
        db.session.commit()
        action_id = int(action.id)

    response = auth_client.post(f"/orders/{order_id}/actions/{action_id}/delete", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/orders/{order_id}")

    with app.app_context():
        assert db.session.get(ServiceOrderAction, action_id) is None


def test_order_actions_are_displayed_chronologically(auth_client, app, company_id, order_actions_schema, monkeypatch):
    with app.app_context():
        order_id, _ = _create_order(company_id)
        user = db.session.get(User, app.config["TEST_USER_ID"])
        assert user is not None
        user.first_name = "Jan"
        user.last_name = "Serwisant"

        db.session.add_all(
            [
                ServiceOrderAction(
                    service_order_id=order_id,
                    company_id=company_id,
                    action_date=date(2026, 8, 3),
                    technician_id=user.id,
                    action_type="REPAIR",
                    description="Naprawa końcowa.",
                    is_visible_for_customer=True,
                ),
                ServiceOrderAction(
                    service_order_id=order_id,
                    company_id=company_id,
                    action_date=date(2026, 8, 1),
                    technician_id=user.id,
                    action_type="DIAGNOSIS",
                    description="Diagnoza początkowa.",
                    is_visible_for_customer=True,
                ),
                ServiceOrderAction(
                    service_order_id=order_id,
                    company_id=company_id,
                    action_date=date(2026, 8, 2),
                    technician_id=user.id,
                    action_type="TESTS",
                    description="Test pośredni.",
                    is_visible_for_customer=True,
                ),
            ]
        )
        db.session.commit()

    from app.orders import routes as orders_routes

    monkeypatch.setattr(orders_routes.service, "get_status_history", lambda order_id, company_id: [])
    monkeypatch.setattr(
        orders_routes.notification_service,
        "list_messages_for_order",
        lambda order_id, company_id, branch_id: [],
    )

    response = auth_client.get(f"/orders/{order_id}")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Historia napraw" in body
    assert "Diagnoza początkowa." in body
    assert "Test pośredni." in body
    assert "Naprawa końcowa." in body
    assert body.index("Diagnoza początkowa.") < body.index("Test pośredni.") < body.index("Naprawa końcowa.")
