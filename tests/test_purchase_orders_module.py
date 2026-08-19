from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.extensions import db
from app.models.catalog_part import CatalogPart
from app.models.catalog_supplier import CatalogSupplier
from app.models.customer import Customer
from app.models.device import Device
from app.models.part_demand import PartDemand
from app.models.purchase_order import PurchaseOrder, PurchaseOrderStatusEnum
from app.models.purchase_order_demand_link import PurchaseOrderDemandLink
from app.models.purchase_order_history import PurchaseOrderHistory
from app.models.purchase_order_item import PurchaseOrderItem
from app.models.service_order import ServiceOrder
from app.catalog.repository import PartsRepository
from app.purchase_orders.exceptions import PurchaseOrderPermissionError, PurchaseOrderValidationError
from app.purchase_orders.service import PurchaseOrderService


@pytest.fixture()
def purchase_order_schema(app):
    tables = [
        Device.__table__,
        ServiceOrder.__table__,
        CatalogSupplier.__table__,
        CatalogPart.__table__,
        PartDemand.__table__,
        PurchaseOrder.__table__,
        PurchaseOrderItem.__table__,
        PurchaseOrderDemandLink.__table__,
        PurchaseOrderHistory.__table__,
    ]
    with app.app_context():
        db.Model.metadata.create_all(bind=db.engine, tables=tables)
    yield
    with app.app_context():
        db.session.remove()
        db.Model.metadata.drop_all(bind=db.engine, tables=list(reversed(tables)))


def _actor(*roles: str):
    return SimpleNamespace(id=1, roles=[SimpleNamespace(name=role) for role in roles])


def _data(company_id: int):
    customer = Customer(customer_type="PERSON", full_name="PO Test", company_id=company_id)
    db.session.add(customer)
    db.session.flush()
    device = Device(customer_id=customer.id, manufacturer="HP", model="M1", serial_number="PO-SN", company_id=company_id)
    db.session.add(device)
    db.session.flush()
    order = ServiceOrder(customer_id=customer.id, device_id=device.id, order_number="PO-SO-1", status="RECEIVED", priority="NORMAL", intake_date=date.today(), issue_description="Test", company_id=company_id)
    db.session.add(order)
    supplier = CatalogSupplier(code="SUP-PO", name="Dostawca PO", company_id=company_id, is_supplier_active=True)
    db.session.add(supplier)
    db.session.flush()
    part = CatalogPart(code="PART-PO", name="Łożysko 6203", unit="szt.", current_stock=Decimal("0"), minimum_stock=Decimal("0"), purchase_price_net=Decimal("10"), sale_price_net=Decimal("20"), vat_rate=Decimal("23"), supplier_id=supplier.id, company_id=company_id)
    db.session.add(part)
    db.session.flush()
    demands = [
        PartDemand(service_order_id=order.id, inventory_item_id=part.id, requested_quantity=Decimal("2"), reserved_quantity=Decimal("0"), missing_quantity=Decimal("2"), status="TO_ORDER", priority="NORMAL", company_id=company_id),
        PartDemand(service_order_id=order.id, inventory_item_id=part.id, requested_quantity=Decimal("3"), reserved_quantity=Decimal("0"), missing_quantity=Decimal("3"), status="TO_ORDER", priority="NORMAL", company_id=company_id),
    ]
    db.session.add_all(demands)
    db.session.commit()
    return supplier, part, demands


def test_create_order_groups_demands_and_writes_history(app, purchase_order_schema):
    with app.app_context():
        company_id = int(app.config["TEST_COMPANY_ID"])
        supplier, _, demands = _data(company_id)
        order = PurchaseOrderService().create_from_demands(demand_ids=[d.id for d in demands], supplier_id=supplier.id, company_id=company_id, branch_id=None, actor=_actor("Magazynier"))

        assert order.po_number.startswith(f"PO/{date.today().year}/")
        assert order.status == PurchaseOrderStatusEnum.DRAFT.value
        assert len(order.items) == 1
        assert order.items[0].quantity_ordered == Decimal("5.000")
        assert order.total_net == Decimal("50.00")
        assert order.total_vat == Decimal("11.50")
        assert order.total_gross == Decimal("61.50")
        assert db.session.query(PurchaseOrderDemandLink).filter_by(purchase_order_item_id=order.items[0].id).count() == 2
        assert all(d.status == "IN_PURCHASE" for d in demands)
        assert len(order.history) == 1
        assert order.history[0].event_type == "CREATED"


def test_order_status_permissions_and_history(app, purchase_order_schema):
    with app.app_context():
        company_id = int(app.config["TEST_COMPANY_ID"])
        supplier, _, demands = _data(company_id)
        service = PurchaseOrderService()
        order = service.create_from_demands(demand_ids=[demands[0].id], supplier_id=supplier.id, company_id=company_id, branch_id=None, actor=_actor("Magazynier"))

        updated = service.update_status(order_id=order.id, status="SENT", company_id=company_id, branch_id=None, actor=_actor("Magazynier"))
        assert updated.status == PurchaseOrderStatusEnum.SENT.value
        with pytest.raises(PurchaseOrderPermissionError):
            service.update_status(order_id=order.id, status="CONFIRMED", company_id=company_id, branch_id=None, actor=_actor("Magazynier"))
        updated = service.update_status(order_id=order.id, status="CONFIRMED", company_id=company_id, branch_id=None, actor=_actor("Kierownik"))
        assert updated.status == PurchaseOrderStatusEnum.CONFIRMED.value
        assert len(updated.history) == 3

        for status in ("PARTIAL", "COMPLETED"):
            updated = service.update_status(order_id=order.id, status=status, company_id=company_id, branch_id=None, actor=_actor("Magazynier"))
        assert updated.status == PurchaseOrderStatusEnum.COMPLETED.value


def test_order_rejects_mixed_supplier_demands(app, purchase_order_schema):
    with app.app_context():
        company_id = int(app.config["TEST_COMPANY_ID"])
        supplier, part, demands = _data(company_id)
        other = CatalogSupplier(code="SUP-OTHER", name="Inny", company_id=company_id, is_supplier_active=True)
        db.session.add(other)
        db.session.flush()
        part.supplier_id = other.id
        db.session.commit()
        with pytest.raises(PurchaseOrderValidationError):
            PurchaseOrderService().create_from_demands(demand_ids=[demands[0].id], supplier_id=supplier.id, company_id=company_id, branch_id=None, actor=_actor("Magazynier"))


def test_preferred_supplier_is_saved_filtered_and_suggested(app, purchase_order_schema):
    with app.app_context():
        company_id = int(app.config["TEST_COMPANY_ID"])
        supplier, part, demands = _data(company_id)
        part.preferred_supplier_id = supplier.id
        db.session.commit()

        filtered = PartsRepository().list_paginated(page=1, per_page=20, company_id=company_id, query_text=None, supplier_id=supplier.id)
        assert [row.id for row in filtered["items"]] == [part.id]
        suggestions = PurchaseOrderService().preferred_supplier_suggestions(demand_ids=[demands[0].id], company_id=company_id, branch_id=None)
        assert suggestions["single_supplier_id"] == supplier.id

        part.preferred_supplier_id = None
        db.session.commit()
        assert PurchaseOrderService().preferred_supplier_suggestions(demand_ids=[demands[0].id], company_id=company_id, branch_id=None)["supplier_ids"] == []
