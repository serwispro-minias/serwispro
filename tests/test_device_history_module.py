from __future__ import annotations

import re
from datetime import date, datetime

import pytest

from app.devices.repository import DeviceRepository
from app.devices.service import DeviceService
from app.extensions import db
from app.models.branch import Branch
from app.models.customer import Customer
from app.models.device import Device
from app.models.purchase_request import PurchaseRequest
from app.models.service_estimate import ServiceEstimate
from app.models.service_estimate_item import ServiceEstimateItem
from app.models.service_order import ServiceOrder
from app.models.service_order_action import ServiceOrderAction
from app.models.service_order_number_counter import ServiceOrderNumberCounter
from app.models.service_order_status_history import ServiceOrderStatusHistory
from app.models.user import User


@pytest.fixture()
def device_history_schema(app):
    with app.app_context():
        db.Model.metadata.create_all(
            bind=db.engine,
            tables=[
                Device.__table__,
                ServiceOrder.__table__,
                ServiceOrderAction.__table__,
                ServiceOrderStatusHistory.__table__,
                ServiceOrderNumberCounter.__table__,
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
                ServiceOrderStatusHistory.__table__,
                ServiceOrderNumberCounter.__table__,
                ServiceOrder.__table__,
                Device.__table__,
                ServiceEstimateItem.__table__,
                ServiceEstimate.__table__,
                PurchaseRequest.__table__,
            ],
        )


def _create_customer_and_device(*, company_id: int, branch_id: int | None = None, serial: str = "SN-DEV-1") -> tuple[int, int]:
    customer = Customer(
        customer_type="PERSON",
        full_name="Historia Klient",
        email=f"{serial.lower()}@example.com",
        phone="123456789",
        company_id=company_id,
        branch_id=branch_id,
    )
    db.session.add(customer)
    db.session.flush()

    device = Device(
        customer_id=customer.id,
        manufacturer="HP",
        model="LaserJet",
        serial_number=serial,
        company_id=company_id,
        branch_id=branch_id,
    )
    db.session.add(device)
    db.session.flush()
    return customer.id, device.id


def _create_order(
    *,
    company_id: int,
    customer_id: int,
    device_id: int,
    order_number: str,
    status: str,
    intake_date: date,
    issue_description: str,
    repair_description: str,
    branch_id: int | None = None,
    created_by: int | None = None,
) -> int:
    order = ServiceOrder(
        customer_id=customer_id,
        device_id=device_id,
        order_number=order_number,
        status=status,
        priority="NORMAL",
        intake_date=intake_date,
        issue_description=issue_description,
        repair_description=repair_description,
        finished_at=datetime(2024, 4, 1, 12, 0, 0),
        company_id=company_id,
        branch_id=branch_id,
        created_by=created_by,
    )
    db.session.add(order)
    db.session.flush()
    return int(order.id)


def test_device_service_history_summary_counts(app, company_id, device_history_schema):
    service = DeviceService(DeviceRepository())

    with app.app_context():
        customer_id, device_id = _create_customer_and_device(company_id=company_id, serial="SN-HIST-1")

        _create_order(
            company_id=company_id,
            customer_id=customer_id,
            device_id=device_id,
            order_number="SO-H-001",
            status="RECEIVED",
            intake_date=date(2024, 1, 10),
            issue_description="Brak zasilania",
            repair_description="Diagnostyka",
        )
        _create_order(
            company_id=company_id,
            customer_id=customer_id,
            device_id=device_id,
            order_number="SO-H-002",
            status="ISSUED",
            intake_date=date(2024, 2, 10),
            issue_description="Uszkodzona matryca",
            repair_description="Wymieniono matryce",
        )
        _create_order(
            company_id=company_id,
            customer_id=customer_id,
            device_id=device_id,
            order_number="SO-H-003",
            status="CANCELLED",
            intake_date=date(2024, 3, 10),
            issue_description="Peknieta obudowa",
            repair_description="Klient anulowal",
        )
        db.session.commit()

        history = service.get_repair_history_context(
            device_id=device_id,
            company_id=company_id,
            branch_id=None,
            query_text=None,
        )

    assert history["summary"]["total_repairs"] == 3
    assert history["summary"]["first_repair"] == date(2024, 1, 10)
    assert history["summary"]["last_repair"] == date(2024, 3, 10)
    assert history["summary"]["completed_count"] == 1
    assert history["summary"]["cancelled_count"] == 1
    assert [item.order_number for item in history["rows"]] == ["SO-H-003", "SO-H-002", "SO-H-001"]


def test_device_history_tab_renders_summary_and_rows(auth_client, app, company_id, device_history_schema):
    with app.app_context():
        user = db.session.get(User, app.config["TEST_USER_ID"])
        assert user is not None
        user.first_name = "Jan"
        user.last_name = "Tester"

        customer_id, device_id = _create_customer_and_device(company_id=company_id, serial="SN-HIST-2")
        _create_order(
            company_id=company_id,
            customer_id=customer_id,
            device_id=device_id,
            order_number="SO-H-101",
            status="ISSUED",
            intake_date=date(2024, 1, 1),
            issue_description="Paski na ekranie",
            repair_description="Wymieniono tasme",
            created_by=user.id,
        )
        _create_order(
            company_id=company_id,
            customer_id=customer_id,
            device_id=device_id,
            order_number="SO-H-102",
            status="RECEIVED",
            intake_date=date(2024, 2, 1),
            issue_description="Nie drukuje",
            repair_description="Czyszczenie",
            created_by=user.id,
        )
        db.session.commit()

    response = auth_client.get(f"/devices/{device_id}?tab=history")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Historia napraw" in body
    assert "Liczba napraw" in body
    assert "SO-H-102" in body
    assert "SO-H-101" in body
    assert "Jan Tester" in body
    assert "Otworz zlecenie" in body
    assert body.index("SO-H-102") < body.index("SO-H-101")


def test_device_history_search_filters_results(auth_client, app, company_id, device_history_schema):
    with app.app_context():
        customer_id, device_id = _create_customer_and_device(company_id=company_id, serial="SN-HIST-3")

        _create_order(
            company_id=company_id,
            customer_id=customer_id,
            device_id=device_id,
            order_number="SO-H-201",
            status="RECEIVED",
            intake_date=date(2024, 1, 1),
            issue_description="Niedzialajaca klawiatura",
            repair_description="Wyczyszczono",
        )
        _create_order(
            company_id=company_id,
            customer_id=customer_id,
            device_id=device_id,
            order_number="SO-H-202",
            status="RECEIVED",
            intake_date=date(2024, 2, 1),
            issue_description="Martwe piksele",
            repair_description="Wymieniono matryce",
        )
        db.session.commit()

    response = auth_client.get(f"/devices/{device_id}?tab=history&history_q=matryce")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "SO-H-202" in body
    assert "SO-H-201" not in body


def test_device_history_empty_state_message(auth_client, app, company_id, device_history_schema):
    with app.app_context():
        _, device_id = _create_customer_and_device(company_id=company_id, serial="SN-HIST-4")
        db.session.commit()

    response = auth_client.get(f"/devices/{device_id}?tab=history")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "To pierwsza naprawa tego urządzenia." in body


def test_device_history_respects_branch_scope(auth_client, app, company_id, device_history_schema):
    with app.app_context():
        branch_a = Branch(name="Serwis A", code="SER-A", company_id=company_id)
        branch_b = Branch(name="Serwis B", code="SER-B", company_id=company_id)
        db.session.add_all([branch_a, branch_b])
        db.session.flush()

        user = db.session.get(User, app.config["TEST_USER_ID"])
        assert user is not None
        user.branch_id = branch_a.id

        customer_id, device_id = _create_customer_and_device(company_id=company_id, branch_id=branch_a.id, serial="SN-HIST-5")
        _create_order(
            company_id=company_id,
            customer_id=customer_id,
            device_id=device_id,
            order_number="SO-H-301",
            status="RECEIVED",
            intake_date=date(2024, 1, 1),
            issue_description="Naprawa A",
            repair_description="Gałąź A",
            branch_id=branch_a.id,
        )
        _create_order(
            company_id=company_id,
            customer_id=customer_id,
            device_id=device_id,
            order_number="SO-H-302",
            status="RECEIVED",
            intake_date=date(2024, 2, 1),
            issue_description="Naprawa B",
            repair_description="Gałąź B",
            branch_id=branch_b.id,
        )
        db.session.commit()

    response = auth_client.get(f"/devices/{device_id}?tab=history")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "SO-H-301" in body
    assert "SO-H-302" not in body
    assert "Liczba napraw" in body
    assert ">1<" in body


def test_order_details_contains_device_history_link(auth_client, app, company_id, device_history_schema, monkeypatch):
    with app.app_context():
        customer_id, device_id = _create_customer_and_device(company_id=company_id, serial="SN-HIST-6")
        order_id = _create_order(
            company_id=company_id,
            customer_id=customer_id,
            device_id=device_id,
            order_number="SO-H-401",
            status="RECEIVED",
            intake_date=date(2024, 1, 1),
            issue_description="Test linku",
            repair_description="Test",
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
    assert "Historia tego urządzenia" in " ".join(body.split())
    assert f"/devices/{device_id}?tab=history" in body


def test_create_order_auto_numbers_assigns_device_and_queues_one_time_print_prompt(auth_client, app, company_id, device_history_schema, monkeypatch):
    with app.app_context():
        customer_id, device_id = _create_customer_and_device(company_id=company_id, serial="SN-NEW-ORDER")
        device = db.session.get(Device, device_id)
        assert device is not None
        device.customer_id = None
        db.session.commit()

    from app.orders import routes as orders_routes

    monkeypatch.setattr(orders_routes, "_ensure_workflow_seed", lambda **kwargs: False)
    monkeypatch.setattr(orders_routes.service, "get_status_history", lambda order_id, company_id: [])
    monkeypatch.setattr(orders_routes.notification_service, "list_messages_for_order", lambda order_id, company_id, branch_id: [])

    response = auth_client.post(
        "/orders/new",
        data={
            "customer_id": str(customer_id),
            "device_id": str(device_id),
            "intake_serial_number": "INTAKE-SERIAL-42",
            "order_number": "FORGED-MANUAL-NUMBER",
            "order_type": "STANDARD",
            "intake_date": "2026-10-24",
            "status": "RECEIVED",
            "priority": "NORMAL",
            "issue_description": "Test order creation",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/orders/1")
    with auth_client.session_transaction() as session:
        assert session["order_print_prompts"] == [1]

    with app.app_context():
        created = db.session.get(ServiceOrder, 1)
        assigned = db.session.get(Device, device_id)
        assert created is not None
        assert created.order_number == "ZL/2026/000001"
        assert created.order_number != "FORGED-MANUAL-NUMBER"
        assert created.intake_serial_number == "INTAKE-SERIAL-42"
        assert assigned is not None and assigned.customer_id is None
        assert assigned.serial_number == "SN-NEW-ORDER"

    details = auth_client.get("/orders/1")
    body = details.get_data(as_text=True)
    assert "Drukować dokument przyjęcia?" in body
    assert "INTAKE-SERIAL-42" in body
    assert 'data-print-intake-action="print"' in body
    assert 'data-action-url="/orders/1/print/intake?mode=inline"' in body
    assert 'data-print-intake-action="print-photos"' in body
    assert 'data-action-url="/orders/1/print/intake?mode=inline&amp;include_photos=1"' in body
    assert 'data-print-intake-action="skip"' in body
    assert 'data-action-url="/orders/"' in body
    refreshed = auth_client.get("/orders/1")
    assert "Drukować dokument przyjęcia?" not in refreshed.get_data(as_text=True)


def test_invalid_new_order_preserves_date_and_optional_blank_serial(auth_client, app, company_id, device_history_schema, monkeypatch):
    with app.app_context():
        customer_id, device_id = _create_customer_and_device(company_id=company_id, serial="SN-INVALID-ORDER")
        device = db.session.get(Device, device_id)
        device.customer_id = None
        db.session.commit()
    from app.orders import routes as orders_routes
    monkeypatch.setattr(orders_routes, "_ensure_workflow_seed", lambda **kwargs: False)

    response = auth_client.post("/orders/new", data={
        "customer_id": str(customer_id),
        "device_id": str(device_id),
        "intake_serial_number": "",
        "intake_date": "2026-09-17",
    })
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'name="intake_serial_number"' in body
    assert re.search(r'<input(?=[^>]*\bid="intake_serial_number")(?=[^>]*\bvalue="")[^>]*>', body)
    assert re.search(r'<input(?=[^>]*\bid="intake_date")(?=[^>]*\bvalue="2026-09-17")[^>]*>', body)
    with auth_client.session_transaction() as session:
        assert "order_print_prompts" not in session
    with app.app_context():
        assert db.session.get(Device, device_id).customer_id is None


def test_new_order_print_prompt_is_one_time_and_uses_existing_intake_route(auth_client, app, company_id, device_history_schema, monkeypatch):
    with app.app_context():
        customer_id, device_id = _create_customer_and_device(company_id=company_id, serial="SN-PRINT-PROMPT")
        order_id = _create_order(
            company_id=company_id,
            customer_id=customer_id,
            device_id=device_id,
            order_number="SO-PRINT-PROMPT",
            status="RECEIVED",
            intake_date=date(2026, 10, 24),
            issue_description="Test print prompt",
            repair_description="Test",
        )
        db.session.commit()

    from app.orders import routes as orders_routes

    monkeypatch.setattr(orders_routes.service, "get_status_history", lambda order_id, company_id: [])
    monkeypatch.setattr(orders_routes.notification_service, "list_messages_for_order", lambda order_id, company_id, branch_id: [])
    with auth_client.session_transaction() as session:
        session["order_print_prompts"] = [order_id]

    first = auth_client.get(f"/orders/{order_id}")
    body = first.get_data(as_text=True)
    assert "Drukować dokument przyjęcia?" in body
    assert 'data-print-intake-action="print"' in body
    assert f'data-action-url="/orders/{order_id}/print/intake?mode=inline"' in body
    assert 'data-print-intake-action="print-photos"' in body
    assert 'data-print-intake-action="skip"' in body
    assert 'data-action-url="/orders/"' in body

    refreshed = auth_client.get(f"/orders/{order_id}")
    assert "Drukować dokument przyjęcia?" not in refreshed.get_data(as_text=True)
