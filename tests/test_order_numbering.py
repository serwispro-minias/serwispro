from __future__ import annotations

from datetime import date

import pytest

from app.extensions import db
from app.models.company import Company
from app.models.customer import Customer
from app.models.device import Device
from app.models.role import Role
from app.models.service_order import ServiceOrder
from app.models.service_order_number_counter import ServiceOrderNumberCounter
from app.models.service_order_status_history import ServiceOrderStatusHistory
from app.models.user_role import UserRole
from app.service_orders.exceptions import ServiceOrderValidationError
from app.service_orders.repository import ServiceOrderRepository
from app.service_orders.service import ServiceOrderService


@pytest.fixture()
def numbering_schema(app):
    tables = [
        Customer.__table__, Device.__table__, ServiceOrder.__table__,
        ServiceOrderStatusHistory.__table__, ServiceOrderNumberCounter.__table__,
        Role.__table__, UserRole.__table__,
    ]
    with app.app_context():
        db.Model.metadata.create_all(bind=db.engine, tables=tables)
    yield
    with app.app_context():
        db.session.remove()
        db.Model.metadata.drop_all(bind=db.engine, tables=list(reversed(tables)))


def _new_customer_device(company_id: int, *, unassigned: bool = True):
    customer = Customer(customer_type="PERSON", full_name="Numerowanie klient", company_id=company_id)
    db.session.add(customer)
    db.session.flush()
    device = Device(
        customer_id=None if unassigned else customer.id,
        manufacturer="Test",
        model="Unit",
        serial_number=f"NUM-{customer.id}",
        company_id=company_id,
    )
    db.session.add(device)
    db.session.flush()
    return customer, device


def _order_payload(customer_id: int, device_id: int, *, forged_number: str = "MANUAL-FORGED"):
    return {
        "customer_id": customer_id,
        "device_id": device_id,
        "order_number": forged_number,
        "status": "RECEIVED",
        "priority": "NORMAL",
        "intake_date": date(2026, 10, 24),
        "issue_description": "Test automatycznego numerowania",
    }


def test_order_numbers_are_generated_per_company_and_ignore_forged_form_values(app, company_id, numbering_schema):
    service = ServiceOrderService(ServiceOrderRepository())
    with app.app_context():
        company = db.session.get(Company, company_id)
        assert company is not None
        company.service_order_prefix = "SRV"
        company.service_order_include_year = True
        company.service_order_number_digits = 6
        customer_a, device_a = _new_customer_device(company_id)
        customer_b, device_b = _new_customer_device(company_id)
        db.session.commit()

        first = service.create_service_order(_order_payload(customer_a.id, device_a.id), company_id=company_id, branch_id=None)
        second = service.create_service_order(_order_payload(customer_b.id, device_b.id), company_id=company_id, branch_id=None)
        assert first.order_number == "SRV/2026/000001"
        assert second.order_number == "SRV/2026/000002"
        assert db.session.query(ServiceOrder.order_number).filter_by(company_id=company_id).count() == 2


def test_number_configuration_changes_do_not_modify_existing_numbers(app, company_id, numbering_schema):
    service = ServiceOrderService(ServiceOrderRepository())
    with app.app_context():
        customer, device = _new_customer_device(company_id)
        db.session.commit()
        existing = service.create_service_order(_order_payload(customer.id, device.id), company_id=company_id, branch_id=None)
        original_number = existing.order_number
        company = db.session.get(Company, company_id)
        company.service_order_prefix = "NEW"
        company.service_order_include_year = False
        company.service_order_number_digits = 4
        db.session.commit()

        second_customer, second_device = _new_customer_device(company_id)
        db.session.commit()
        second = service.create_service_order(_order_payload(second_customer.id, second_device.id), company_id=company_id, branch_id=None)
        db.session.refresh(existing)
        assert existing.order_number == original_number == "ZL/2026/000001"
        assert second.order_number == "NEW/0001"


def test_failed_order_creation_rolls_back_device_assignment_and_sequence(app, company_id, numbering_schema, monkeypatch):
    service = ServiceOrderService(ServiceOrderRepository())
    with app.app_context():
        customer, device = _new_customer_device(company_id)
        db.session.commit()
        device_id = device.id

        def fail_history(**kwargs):
            raise RuntimeError("simulated history persistence error")

        monkeypatch.setattr(service.repository, "create_status_history", fail_history)
        with pytest.raises(RuntimeError, match="simulated history persistence error"):
            service.create_service_order(_order_payload(customer.id, device.id), company_id=company_id, branch_id=None)

        persisted = db.session.get(Device, device_id)
        assert persisted is not None and persisted.customer_id is None
        assert db.session.query(ServiceOrder).filter_by(company_id=company_id).count() == 0
        assert db.session.query(ServiceOrderNumberCounter).filter_by(company_id=company_id).count() == 0


def test_unprivileged_user_cannot_view_or_change_numbering_settings(auth_client, app, company_id, numbering_schema):
    response = auth_client.get("/settings/order-numbering")
    assert response.status_code == 403
    response = auth_client.post("/settings/order-numbering", data={"prefix": "HACK", "digits": "3"})
    assert response.status_code == 403


def test_company_administrator_can_change_only_own_numbering_settings(auth_client, app, company_id, numbering_schema):
    with app.app_context():
        role = Role(name="Administrator", company_id=company_id)
        db.session.add(role)
        db.session.flush()
        db.session.add(UserRole(user_id=app.config["TEST_USER_ID"], role_id=role.id, company_id=company_id))
        db.session.commit()

    response = auth_client.get("/settings/order-numbering")
    assert response.status_code == 200
    response = auth_client.post(
        "/settings/order-numbering",
        data={"prefix": "CUSTOM", "include_year": "y", "digits": "4", "submit": "1"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    with app.app_context():
        company = db.session.get(Company, company_id)
        assert company.service_order_prefix == "CUSTOM"
        assert company.service_order_include_year is True
        assert company.service_order_number_digits == 4
