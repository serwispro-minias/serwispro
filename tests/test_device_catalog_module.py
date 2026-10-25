from __future__ import annotations

import re
from datetime import date

import pytest

from app.devices.repository import DeviceRepository
from app.devices.service import DeviceService
from app.extensions import db
from app.models.company import Company
from app.models.customer import Customer
from app.models.device import Device
from app.models.service_order import ServiceOrder
from app.models.service_order_number_counter import ServiceOrderNumberCounter
from app.models.service_order_status_history import ServiceOrderStatusHistory
from app.service_orders.repository import ServiceOrderRepository
from app.service_orders.service import ServiceOrderService


@pytest.fixture()
def device_catalog_schema(app):
    tables = [
        Customer.__table__, Device.__table__, ServiceOrder.__table__,
        ServiceOrderStatusHistory.__table__, ServiceOrderNumberCounter.__table__,
    ]
    with app.app_context():
        db.Model.metadata.create_all(bind=db.engine, tables=tables)
    yield
    with app.app_context():
        db.session.remove()
        db.Model.metadata.drop_all(bind=db.engine, tables=list(reversed(tables)))


def _customer(company_id: int, name: str) -> Customer:
    customer = Customer(customer_type="PERSON", full_name=name, company_id=company_id)
    db.session.add(customer)
    db.session.flush()
    return customer


def _device(company_id: int, customer_id: int | None, serial: str) -> Device:
    device = Device(customer_id=customer_id, serial_number=serial, company_id=company_id)
    db.session.add(device)
    db.session.flush()
    return device


def test_device_catalog_lists_only_three_attributes_and_search_keeps_company_scope(app, auth_client, company_id, device_catalog_schema):
    with app.app_context():
        customer = _customer(company_id, "Assigned Customer")
        assigned = _device(company_id, customer.id, "CATALOG-ASSIGNED")
        unassigned = _device(company_id, None, "CATALOG-UNASSIGNED")
        assigned.manufacturer = "CatalogMaker"
        unassigned.manufacturer = "CatalogMaker"
        foreign_company = Company(name="Foreign Device Company", prefix="FDC")
        db.session.add(foreign_company)
        db.session.flush()
        _device(foreign_company.id, None, "CATALOG-FOREIGN")
        db.session.commit()
        unassigned_id = unassigned.id

    response = auth_client.get("/devices/?q=CatalogMaker")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    table_body = body.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    assert table_body.count("<tr>") == 2
    assert table_body.count("<td>") == 8
    assert "CatalogMaker" in table_body
    assert str(unassigned_id) in body
    assert "CATALOG-FOREIGN" not in body
    for heading in ("<th>Typ urządzenia</th>", "<th>Producent</th>", "<th>Model</th>", "<th>Akcje</th>"):
        assert heading in body
    for heading in ("<th>ID</th>", "<th>Klient</th>", "<th>Nr seryjny</th>", "<th>Numer seryjny</th>", "<th>Numer inwentarzowy</th>"):
        assert heading not in body
    assert f'href="/devices/{unassigned_id}/edit"' in body


def test_device_catalog_create_ignores_forged_customer_assignment(app, auth_client, company_id, device_catalog_schema):
    with app.app_context():
        customer = _customer(company_id, "Must Not Be Assigned")
        customer_id = customer.id
        db.session.commit()

    get_response = auth_client.get("/devices/create")
    assert get_response.status_code == 200
    for forbidden in (b'name="customer_id"', b'name="serial_number"', b'name="inventory_number"', b'name="purchase_date"', b'name="warranty_until"', b'name="password"', b'name="condition_description"', b'name="accessories"', b'name="notes"'):
        assert forbidden not in get_response.data
    for expected in (b'name="device_type"', b'name="manufacturer"', b'name="model"'):
        assert expected in get_response.data

    response = auth_client.post(
        "/devices/create",
        data={"customer_id": str(customer_id), "serial_number": "IGNORED-SERIAL", "device_type": "Printer", "manufacturer": "Maker", "model": "M1"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    with app.app_context():
        created = db.session.query(Device).filter_by(manufacturer="Maker", model="M1").one()
        assert created.customer_id is None
        assert created.device_type == "Printer"
        assert created.serial_number is None


def test_assigned_device_catalog_attributes_can_be_edited_but_legacy_assignment_and_history_data_remain(app, auth_client, company_id, device_catalog_schema):
    with app.app_context():
        customer = _customer(company_id, "Owner")
        device = _device(company_id, customer.id, "ASSIGNED-LOCKED")
        db.session.commit()
        device_id = device.id
        owner_id = customer.id

    edit_response = auth_client.get(f"/devices/{device_id}/edit", follow_redirects=False)
    assert edit_response.status_code == 200
    edit_response = auth_client.post(f"/devices/{device_id}/edit", data={
        "device_type": "Laptop",
        "manufacturer": "Updated maker",
        "model": "Updated model",
        "serial_number": "SHOULD-NOT-CHANGE",
    })
    assert edit_response.status_code == 302

    delete_response = auth_client.post(f"/devices/{device_id}/delete", follow_redirects=True)
    assert delete_response.status_code == 200
    with app.app_context():
        persisted = db.session.get(Device, device_id)
        assert persisted is not None
        assert persisted.customer_id == owner_id
        assert persisted.manufacturer == "Updated maker"
        assert persisted.model == "Updated model"
        assert persisted.device_type == "Laptop"
        assert persisted.serial_number == "ASSIGNED-LOCKED"
        assert persisted.is_active is True


def test_device_service_updates_only_catalog_attributes_for_assigned_and_unassigned_records(app, company_id, device_catalog_schema):
    service = DeviceService(DeviceRepository())
    with app.app_context():
        customer = _customer(company_id, "Owner")
        unassigned = _device(company_id, None, "UPDATE-UNASSIGNED")
        assigned = _device(company_id, customer.id, "UPDATE-ASSIGNED")
        db.session.commit()
        unassigned_id, assigned_id, customer_id = unassigned.id, assigned.id, customer.id

        service.update_device(
            unassigned_id,
            {"customer_id": customer_id, "serial_number": "FORGED-SERIAL", "device_type": "Scanner", "manufacturer": "New maker", "model": "New model"},
            company_id,
        )
        updated = db.session.get(Device, unassigned_id)
        assert updated is not None
        assert updated.customer_id is None
        assert updated.serial_number == "UPDATE-UNASSIGNED"
        assert (updated.device_type, updated.manufacturer, updated.model) == ("Scanner", "New maker", "New model")

        service.update_device(assigned_id, {"serial_number": "SHOULD-NOT-UPDATE", "model": "Updated"}, company_id)
        changed = db.session.get(Device, assigned_id)
        assert changed is not None
        assert changed.customer_id == customer_id
        assert changed.serial_number == "UPDATE-ASSIGNED"
        assert changed.model == "Updated"


def test_order_device_availability_is_a_bounded_unassigned_existence_check(app, auth_client, company_id, device_catalog_schema):
    with app.app_context():
        customer = _customer(company_id, "Order Customer")
        other_customer = _customer(company_id, "Other Customer")
        unassigned = _device(company_id, None, "ORDER-UNASSIGNED")
        owned = _device(company_id, customer.id, "ORDER-OWNED")
        foreign = _device(company_id, other_customer.id, "ORDER-FOREIGN")
        db.session.commit()
        customer_id = customer.id

    response = auth_client.get(f"/orders/devices/by-customer?customer_id={customer_id}")
    assert response.status_code == 200
    assert response.get_json() == {"devices": [], "has_devices": True}


def test_order_create_form_allows_independent_customer_and_device_search(auth_client, app, company_id, device_catalog_schema):
    with app.app_context():
        selected = _customer(company_id, "Selected Customer")
        other = _customer(company_id, "Other Customer")
        foreign_company = Company(name="Foreign Order Device Company", prefix="FOD")
        db.session.add(foreign_company)
        db.session.flush()
        assigned = _device(company_id, selected.id, "ORDER-FORM-ASSIGNED")
        unassigned = _device(company_id, None, "ORDER-FORM-UNASSIGNED")
        foreign = _device(company_id, other.id, "ORDER-FORM-FOREIGN")
        foreign_unassigned = _device(foreign_company.id, None, "ORDER-FORM-FOREIGN-TENANT")
        assigned.device_type = "ORDER-FORM"
        unassigned.device_type = "ORDER-FORM"
        foreign.device_type = "ORDER-FORM"
        foreign_unassigned.device_type = "ORDER-FORM"
        db.session.commit()
        selected_id = selected.id
        assigned_id, unassigned_id, foreign_id = assigned.id, unassigned.id, foreign.id
        foreign_unassigned_id = foreign_unassigned.id

    response = auth_client.get("/orders/new")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "data-live-search-url=\"/customers/search\"" in body
    assert 'name="customer_id" id="customer_id"' in body
    assert 'name="device_id" id="device_id"' in body
    assert 'id="order-device-search"' in body
    assert 'data-live-search-url="/orders/devices/search"' in body
    assert re.search(r'<input(?=[^>]*id="order-device-search")(?=[^>]*data-live-search-url="/orders/devices/search")(?![^>]*disabled)[^>]*>', body)
    result = auth_client.get("/orders/devices/search?q=ORDER-FORM")
    assert result.status_code == 200
    result_ids = {item["id"] for item in result.get_json()["items"]}
    assert unassigned_id in result_ids
    assert assigned_id in result_ids
    assert foreign_id in result_ids
    assert foreign_unassigned_id not in result_ids


def test_new_order_form_defaults_intake_date_and_renders_optional_intake_serial(auth_client, monkeypatch):
    from app.orders import routes as orders_routes

    monkeypatch.setattr(orders_routes, "_ensure_workflow_seed", lambda **kwargs: False)
    response = auth_client.get("/orders/new")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'name="intake_serial_number"' in body
    assert 'name="intake_date"' in body
    assert f'value="{date.today().isoformat()}"' in body


def test_customer_search_returns_real_company_scoped_records_and_usable_payload(auth_client, app, company_id, device_catalog_schema):
    with app.app_context():
        matching = Customer(
            customer_type="PERSON",
            first_name="Alicja",
            last_name="Nowak",
            nip="9876543210",
            company_id=company_id,
        )
        foreign_company = Company(name="Foreign Customer Company", prefix="FCC")
        db.session.add_all([matching, foreign_company])
        db.session.flush()
        foreign = Customer(full_name="Alicja Nowak Foreign", nip="9876543210", company_id=foreign_company.id)
        db.session.add(foreign)
        db.session.commit()
        matching_id = matching.id

    response = auth_client.get("/customers/search?q=9876543210")
    assert response.status_code == 200
    payload = response.get_json()
    assert set(payload) == {"items"}
    assert len(payload["items"]) == 1
    item = payload["items"][0]
    assert item["id"] == matching_id
    assert item["name"] == "Alicja Nowak"
    assert item["display"] == "Alicja Nowak"
    assert item["tax_id"] == "9876543210"
    name_response = auth_client.get("/customers/search?q=Alicja%20Nowak")
    assert name_response.status_code == 200
    assert [entry["id"] for entry in name_response.get_json()["items"]] == [matching_id]


def test_order_creation_uses_ids_returned_by_live_search_endpoints(auth_client, app, company_id, device_catalog_schema, monkeypatch):
    with app.app_context():
        customer = _customer(company_id, "Live Search Customer")
        legacy_owner = _customer(company_id, "Legacy Catalog Owner")
        device = _device(company_id, legacy_owner.id, "LIVE-SEARCH-DEVICE")
        device.device_type = "Live Search Printer"
        db.session.commit()
        expected_customer_id, expected_device_id = customer.id, device.id

    customer_response = auth_client.get("/customers/search?q=Live%20Search")
    assert customer_response.status_code == 200
    customer_item = next(item for item in customer_response.get_json()["items"] if item["id"] == expected_customer_id)
    device_response = auth_client.get(
        "/orders/devices/search?q=Live%20Search"
    )
    assert device_response.status_code == 200
    device_item = next(item for item in device_response.get_json()["items"] if item["id"] == expected_device_id)

    from app.orders import routes as orders_routes

    monkeypatch.setattr(orders_routes, "_ensure_workflow_seed", lambda **kwargs: False)
    response = auth_client.post(
        "/orders/new",
        data={
            "customer_id": str(customer_item["id"]),
            "device_id": str(device_item["id"]),
            "intake_serial_number": "INTAKE-LIVE-SEARCH-1",
            "order_type": "STANDARD",
            "intake_date": "2026-09-17",
            "status": "RECEIVED",
            "priority": "NORMAL",
            "issue_description": "Created using selected live-search records",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    with app.app_context():
        created = db.session.query(ServiceOrder).one()
        assigned = db.session.get(Device, expected_device_id)
        assert created.customer_id == expected_customer_id
        assert created.device_id == expected_device_id
        assert created.intake_date == date(2026, 9, 17)
        assert created.intake_serial_number == "INTAKE-LIVE-SEARCH-1"
        assert assigned is not None and assigned.customer_id is not None
        assert assigned.customer_id != expected_customer_id
        assert assigned.serial_number == "LIVE-SEARCH-DEVICE"


def test_order_parties_can_be_selected_in_either_sequence(auth_client, app, company_id, device_catalog_schema, monkeypatch):
    with app.app_context():
        customers = [_customer(company_id, "Sequence Customer Alpha"), _customer(company_id, "Sequence Customer Beta")]
        devices = [_device(company_id, None, "SEQUENCE-DEVICE-A"), _device(company_id, None, "SEQUENCE-DEVICE-B")]
        devices[0].manufacturer, devices[0].model = "Sequence", "Device Alpha"
        devices[1].manufacturer, devices[1].model = "Sequence", "Device Beta"
        db.session.commit()
        customer_ids = [row.id for row in customers]
        device_ids = [row.id for row in devices]

    from app.orders import routes as orders_routes

    monkeypatch.setattr(orders_routes, "_ensure_workflow_seed", lambda **kwargs: False)
    expected_pairs = [(customer_ids[0], device_ids[0]), (customer_ids[1], device_ids[1])]
    for (customer_id, device_id), serial in zip(expected_pairs, ("SEQUENCE-SERIAL-A", "SEQUENCE-SERIAL-B")):
        customer_results = auth_client.get(f"/customers/search?q=Sequence%20Customer").get_json()["items"]
        device_results = auth_client.get("/orders/devices/search?q=Sequence").get_json()["items"]
        assert customer_id in {row["id"] for row in customer_results}
        assert device_id in {row["id"] for row in device_results}
        response = auth_client.post("/orders/new", data={
            "customer_id": str(customer_id),
            "device_id": str(device_id),
            "intake_serial_number": serial,
            "order_type": "STANDARD",
            "intake_date": "2026-10-24",
            "status": "RECEIVED",
            "priority": "NORMAL",
            "issue_description": "Independent selection order",
        })
        assert response.status_code == 302

    with app.app_context():
        created = db.session.query(ServiceOrder).order_by(ServiceOrder.id).all()
        assert [(row.customer_id, row.device_id, row.intake_serial_number) for row in created] == [
            (customer_ids[0], device_ids[0], "SEQUENCE-SERIAL-A"),
            (customer_ids[1], device_ids[1], "SEQUENCE-SERIAL-B"),
        ]


def test_order_create_rejects_nonexistent_customer_id(auth_client, app, company_id, device_catalog_schema, monkeypatch):
    with app.app_context():
        device = _device(company_id, None, "INVALID-CUSTOMER-DEVICE")
        db.session.commit()
        device_id = device.id

    from app.orders import routes as orders_routes

    monkeypatch.setattr(orders_routes, "_ensure_workflow_seed", lambda **kwargs: False)
    response = auth_client.post(
        "/orders/new",
        data={
            "customer_id": "999999",
            "device_id": str(device_id),
            "order_type": "STANDARD",
            "intake_date": "2026-10-24",
            "status": "RECEIVED",
            "priority": "NORMAL",
            "issue_description": "Invalid customer must be rejected",
        },
    )
    assert response.status_code == 200
    with app.app_context():
        assert db.session.query(ServiceOrder).count() == 0
        persisted = db.session.get(Device, device_id)
        assert persisted is not None and persisted.customer_id is None


def test_order_create_rejects_foreign_company_customer_and_device(auth_client, app, company_id, device_catalog_schema, monkeypatch):
    with app.app_context():
        own_customer = _customer(company_id, "Tenant Customer")
        own_device = _device(company_id, None, "TENANT-DEVICE")
        foreign_company = Company(name="Order Foreign Company", prefix="OFC")
        db.session.add(foreign_company)
        db.session.flush()
        foreign_customer = _customer(foreign_company.id, "Foreign Tenant Customer")
        foreign_device = _device(foreign_company.id, None, "FOREIGN-TENANT-DEVICE")
        db.session.commit()
        own_customer_id, own_device_id = own_customer.id, own_device.id
        foreign_customer_id, foreign_device_id = foreign_customer.id, foreign_device.id

    from app.orders import routes as orders_routes

    monkeypatch.setattr(orders_routes, "_ensure_workflow_seed", lambda **kwargs: False)
    base_data = {
        "order_type": "STANDARD",
        "intake_date": "2026-10-24",
        "status": "RECEIVED",
        "priority": "NORMAL",
        "issue_description": "Cross-company ids must be rejected",
    }
    for customer_id, device_id in (
        (foreign_customer_id, own_device_id),
        (own_customer_id, foreign_device_id),
    ):
        response = auth_client.post(
            "/orders/new",
            data={**base_data, "customer_id": str(customer_id), "device_id": str(device_id)},
        )
        assert response.status_code == 200

    with app.app_context():
        assert db.session.query(ServiceOrder).count() == 0
        assert db.session.get(Device, own_device_id).customer_id is None
        assert db.session.get(Device, foreign_device_id).customer_id is None


def test_order_create_allows_legacy_assigned_device_without_mutating_catalog_owner(auth_client, app, company_id, device_catalog_schema, monkeypatch):
    with app.app_context():
        owner = _customer(company_id, "Existing Device Owner")
        requester = _customer(company_id, "Requesting Customer")
        assigned = _device(company_id, owner.id, "ALREADY-ASSIGNED")
        db.session.commit()
        owner_id, requester_id, device_id = owner.id, requester.id, assigned.id

    from app.orders import routes as orders_routes

    monkeypatch.setattr(orders_routes, "_ensure_workflow_seed", lambda **kwargs: False)
    response = auth_client.post(
        "/orders/new",
        data={
            "customer_id": str(requester_id),
            "device_id": str(device_id),
            "order_number": "IGNORED",
            "order_type": "STANDARD",
            "intake_date": "2026-10-24",
            "status": "RECEIVED",
            "priority": "NORMAL",
            "intake_serial_number": "PHYSICAL-UNIT-100",
            "issue_description": "Order ownership is independent of catalog legacy customer",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        persisted = db.session.get(Device, device_id)
        assert persisted is not None and persisted.customer_id == owner_id
        created = db.session.query(ServiceOrder).one()
        assert created.customer_id == requester_id
        assert created.device_id == device_id
        assert created.intake_serial_number == "PHYSICAL-UNIT-100"


def test_order_service_validates_order_parties_independently_without_device_mutation(app, company_id, device_catalog_schema):
    orders = ServiceOrderService(ServiceOrderRepository())
    with app.app_context():
        customer = _customer(company_id, "Order Customer")
        other_customer = _customer(company_id, "Other Customer")
        unassigned = _device(company_id, None, "ORDER-ASSIGN")
        foreign = _device(company_id, other_customer.id, "ORDER-FOREIGN-OWNED")
        db.session.commit()
        customer_id, other_customer_id = customer.id, other_customer.id
        unassigned_id, assigned_id = unassigned.id, foreign.id

        order_a = orders.create_service_order(
            {"customer_id": customer_id, "device_id": unassigned_id, "intake_serial_number": "SERIAL-A",
             "status": "RECEIVED", "priority": "NORMAL", "intake_date": date.today(),
             "issue_description": "Independent order association A"},
            company_id=company_id, branch_id=None,
        )
        order_b = orders.create_service_order(
            {"customer_id": other_customer_id, "device_id": assigned_id, "intake_serial_number": "SERIAL-B",
             "status": "RECEIVED", "priority": "NORMAL", "intake_date": date.today(),
             "issue_description": "Independent order association B"},
            company_id=company_id, branch_id=None,
        )
        assert (order_a.customer_id, order_a.device_id, order_a.intake_serial_number) == (customer_id, unassigned_id, "SERIAL-A")
        assert (order_b.customer_id, order_b.device_id, order_b.intake_serial_number) == (other_customer_id, assigned_id, "SERIAL-B")
        db.session.refresh(unassigned)
        db.session.refresh(foreign)
        assert unassigned.customer_id is None
        assert foreign.customer_id == other_customer_id


def test_order_validation_does_not_require_device_customer_to_match_order_customer(app, company_id, device_catalog_schema):
    orders = ServiceOrderService(ServiceOrderRepository())
    with app.app_context():
        original_customer = _customer(company_id, "Original Owner")
        requested_customer = _customer(company_id, "New Order Customer")
        device = _device(company_id, original_customer.id, "NO-IMPLICIT-TRANSFER")
        db.session.commit()

        orders._validate_customer_device(requested_customer.id, device.id, company_id)
        persisted = db.session.get(Device, device.id)
        assert persisted is not None
        assert persisted.customer_id == original_customer.id


def test_creating_service_order_keeps_device_catalog_separate_from_order_serial(app, company_id, device_catalog_schema):
    orders = ServiceOrderService(ServiceOrderRepository())
    with app.app_context():
        customer = _customer(company_id, "Order Transaction Customer")
        device = _device(company_id, None, "ORDER-TRANSACTION-DEVICE")
        db.session.commit()

        order = orders.create_service_order(
            {
                "customer_id": customer.id,
                "device_id": device.id,
                "intake_serial_number": "ORDER-SPECIFIC-SERIAL",
                "order_number": "ORD-ASSIGN-1",
                "status": "RECEIVED",
                "priority": "NORMAL",
                "intake_date": date.today(),
                "issue_description": "Test assignment in order",
            },
            company_id=company_id,
            branch_id=None,
        )
        db.session.refresh(device)
        assert order.device_id == device.id
        assert order.customer_id == customer.id
        assert order.intake_serial_number == "ORDER-SPECIFIC-SERIAL"
        assert device.customer_id is None
        assert device.serial_number == "ORDER-TRANSACTION-DEVICE"


def test_two_order_intakes_can_reference_same_catalog_type_without_racing_on_owner(app, company_id, device_catalog_schema):
    orders = ServiceOrderService(ServiceOrderRepository())
    with app.app_context():
        customer = _customer(company_id, "Concurrent Claim Customer")
        device = _device(company_id, None, "CONCURRENT-CLAIM")
        db.session.commit()
        customer_id, device_id = customer.id, device.id
        other_customer = _customer(company_id, "Second Concurrent Customer")
        db.session.commit()
        first = orders.create_service_order(
            {"customer_id": customer_id, "device_id": device_id, "intake_serial_number": "UNIT-1",
             "status": "RECEIVED", "priority": "NORMAL", "intake_date": date(2026, 10, 24),
             "issue_description": "First order"},
            company_id=company_id, branch_id=None,
        )
        second = orders.create_service_order(
            {"customer_id": other_customer.id, "device_id": device_id, "intake_serial_number": "UNIT-2",
             "status": "RECEIVED", "priority": "NORMAL", "intake_date": date(2026, 10, 24),
             "issue_description": "Second order"},
            company_id=company_id, branch_id=None,
        )
        assert first.device_id == second.device_id == device_id
        assert first.intake_serial_number != second.intake_serial_number
        persisted = db.session.get(Device, device_id)
        assert persisted is not None and persisted.customer_id is None
        assert db.session.query(ServiceOrder).count() == 2


def test_order_modal_creates_three_field_catalog_device_without_customer_context(auth_client, app, company_id, device_catalog_schema):
    response = auth_client.post(
        "/orders/modal/devices/new",
        data={"device_type": "Printer", "manufacturer": "Modal Maker", "model": "M-3", "serial_number": "SHOULD-IGNORE"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    with app.app_context():
        device = db.session.query(Device).filter_by(manufacturer="Modal Maker", model="M-3").one()
        assert device.customer_id is None
        assert device.device_type == "Printer"
        assert device.serial_number is None


def test_order_modal_edits_catalog_fields_without_mutating_legacy_owner_or_serial(auth_client, app, company_id, device_catalog_schema):
    with app.app_context():
        owner = _customer(company_id, "Existing Owner")
        other = _customer(company_id, "Other Customer")
        device = _device(company_id, owner.id, "MODAL-OWNED")
        db.session.commit()
        owner_id, other_id, device_id = owner.id, other.id, device.id

    response = auth_client.post(
        f"/orders/modal/devices/{device_id}/edit",
        data={"device_type": "Updated type", "manufacturer": "Updated maker", "model": "Updated model", "serial_number": "FORGED-TRANSFER"},
    )
    assert response.status_code == 200
    assert response.get_json()["ok"] is True
    with app.app_context():
        persisted = db.session.get(Device, device_id)
        assert persisted is not None
        assert persisted.customer_id == owner_id
        assert persisted.serial_number == "MODAL-OWNED"
        assert persisted.device_type == "Updated type"
        assert persisted.manufacturer == "Updated maker"
        assert persisted.model == "Updated model"
