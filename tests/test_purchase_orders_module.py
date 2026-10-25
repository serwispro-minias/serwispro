from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.catalog.repository import PartsRepository
from app.extensions import db
from app.models.catalog_category import ProductCategory
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
from app.models.vat_rate import VatRate
from app.purchase_orders.exceptions import (
    PurchaseOrderPermissionError,
    PurchaseOrderValidationError,
)
from app.purchase_orders.service import PurchaseOrderService


@pytest.fixture()
def purchase_order_schema(app):
    tables = [
        Device.__table__,
        ServiceOrder.__table__,
        CatalogSupplier.__table__,
        ProductCategory.__table__,
        VatRate.__table__,
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
    supplier = CatalogSupplier(code="SUP-PO", name="Dostawca PO", company_id=company_id, is_active=True)
    db.session.add(supplier)
    db.session.flush()
    category = ProductCategory(code="MECH-PO", name="Mechanika PO", company_id=company_id)
    vat = VatRate(code="23-PO", rate=Decimal("23"), company_id=company_id, is_active=True)
    db.session.add_all([category, vat])
    db.session.flush()
    part = CatalogPart(code="PART-PO", name="Łożysko 6203", category_id=category.id, vat_id=vat.id, current_stock=0, purchase_price_net=Decimal("10"), sale_price_net=Decimal("20"), company_id=company_id)
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


def test_create_order_from_catalog_does_not_change_stock(app, purchase_order_schema):
    with app.app_context():
        company_id = int(app.config["TEST_COMPANY_ID"])
        supplier, part, _ = _data(company_id)
        order = PurchaseOrderService().create_order(
            items=[{"part_id": part.id, "quantity_ordered": "4", "unit_price_net": "12.50"}],
            supplier_id=supplier.id,
            company_id=company_id,
            branch_id=None,
            actor=_actor("Magazynier"),
        )

        db.session.refresh(part)
        assert order.status == PurchaseOrderStatusEnum.DRAFT.value
        assert len(order.items) == 1
        assert order.items[0].quantity_ordered == Decimal("4.000")
        assert order.items[0].total_net == Decimal("50.00")
        assert order.items[0].total_vat == Decimal("11.50")
        assert order.total_gross == Decimal("61.50")
        assert part.current_stock == 0
        assert not order.items[0].demand_links


def test_create_order_rejects_invalid_catalog_quantity(app, purchase_order_schema):
    with app.app_context():
        company_id = int(app.config["TEST_COMPANY_ID"])
        supplier, part, _ = _data(company_id)
        with pytest.raises(PurchaseOrderValidationError):
            PurchaseOrderService().create_order(
                items=[{"part_id": part.id, "quantity_ordered": "0", "unit_price_net": "10"}],
                supplier_id=supplier.id,
                company_id=company_id,
                branch_id=None,
                actor=_actor("Magazynier"),
            )


def test_catalog_order_form_uses_existing_part_search(auth_client, monkeypatch):
    from app.purchase_orders import routes

    monkeypatch.setattr(routes.purchase_order_service, "get_suppliers", lambda **kwargs: [])
    response = auth_client.get("/purchase-orders/new/catalog")
    assert response.status_code == 200
    assert b"data-live-search-url=\"/catalog/parts/search\"" in response.data
    assert b"name=\"csrf_token\"" in response.data
    assert b"id=\"add-product\"" in response.data
    assert b"id=\"order-items\"" in response.data


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
        with pytest.raises(PurchaseOrderValidationError):
            service.update_status(order_id=order.id, status="COMPLETED", company_id=company_id, branch_id=None, actor=_actor("Magazynier"))
        with pytest.raises(PurchaseOrderValidationError):
            service.update_status(order_id=order.id, status="PARTIAL", company_id=company_id, branch_id=None, actor=_actor("Magazynier"))


def test_order_rejects_mixed_supplier_demands(app, purchase_order_schema):
    with app.app_context():
        company_id = int(app.config["TEST_COMPANY_ID"])
        supplier, part, demands = _data(company_id)
        other = CatalogSupplier(code="SUP-OTHER", name="Inny", company_id=company_id, is_active=True)
        db.session.add(other)
        db.session.flush()
        db.session.commit()


def test_catalog_order_post_requires_csrf(app, auth_client, monkeypatch):
    from app.purchase_orders import routes

    app.config["WTF_CSRF_ENABLED"] = True
    monkeypatch.setattr(routes.purchase_order_service, "get_suppliers", lambda **kw: [SimpleNamespace(id=1, name="Dostawca", code="SUP")])
    monkeypatch.setattr(routes, "current_user", SimpleNamespace(
        company_id=app.config["TEST_COMPANY_ID"], branch_id=None, **vars(_actor("Magazynier"))
    ))
    calls = []
    monkeypatch.setattr(routes.purchase_order_service, "create_order", lambda **kw: calls.append(kw) or SimpleNamespace(id=123))
    payload = {"supplier_id": "1", "order_date": "2026-10-25"}
    auth_client.post("/purchase-orders/new/catalog", data=payload)
    assert calls == []
    import re
    page = auth_client.get("/purchase-orders/new/catalog")
    token = re.search(r'name="csrf_token" value="([^"]+)"', page.get_data(as_text=True)).group(1)
    response = auth_client.post("/purchase-orders/new/catalog", data={**payload, "csrf_token": token})
    assert response.status_code == 302
    assert len(calls) == 1


def test_catalog_order_rejects_fractional_stock_quantity(app, purchase_order_schema):
    with app.app_context():
        company = app.config["TEST_COMPANY_ID"]
        supplier, part, _ = _data(company)
        with pytest.raises(PurchaseOrderValidationError):
            PurchaseOrderService().create_order(
                items=[{"part_id": part.id, "quantity_ordered": "1.5", "unit_price_net": "10"}],
                supplier_id=supplier.id, company_id=company, branch_id=None, actor=_actor("Magazynier"),
            )


def test_order_details_render_quantities(app, auth_client, purchase_order_schema, monkeypatch):
    from app.purchase_orders import routes
    company = app.config["TEST_COMPANY_ID"]
    monkeypatch.setattr(routes, "current_user", SimpleNamespace(company_id=company, branch_id=None, **vars(_actor("Magazynier"))))
    with app.app_context():
        supplier, part, _ = _data(company)
        po = PurchaseOrderService().create_order(
            items=[{"part_id": part.id, "quantity_ordered": "7", "unit_price_net": "10"}],
            supplier_id=supplier.id, company_id=company, branch_id=None, actor=_actor("Magazynier"),
        )
        po_id = po.id
    response = auth_client.get(f"/purchase-orders/{po_id}")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Przyjęto" in html and "Pozostało" in html
    assert "<td>7.000</td>" in html and "<td>0.000</td>" in html


def test_order_status_transition_cannot_skip_approval(app, purchase_order_schema):
    with app.app_context():
        company = app.config["TEST_COMPANY_ID"]
        supplier, part, _ = _data(company)
        service = PurchaseOrderService()
        po = service.create_order(items=[{"part_id": part.id, "quantity_ordered": "1"}], supplier_id=supplier.id, company_id=company, branch_id=None, actor=_actor("Magazynier"))
        with pytest.raises(PurchaseOrderValidationError):
            service.update_status(order_id=po.id, status="CONFIRMED", company_id=company, branch_id=None, actor=_actor("Administrator"))
        with pytest.raises(PurchaseOrderPermissionError):
            service.update_status(order_id=po.id, status="SENT", company_id=company, branch_id=None, actor=_actor("Mechanik"))
        assert po.status == "DRAFT"


@pytest.mark.parametrize("scope", ["company", "branch"])
def test_order_access_is_scoped(app, purchase_order_schema, scope):
    from app.models.branch import Branch
    from app.purchase_orders.exceptions import PurchaseOrderNotFoundError
    with app.app_context():
        company = app.config["TEST_COMPANY_ID"]
        supplier, part, _ = _data(company)
        service = PurchaseOrderService()
        po = service.create_order(items=[{"part_id": part.id, "quantity_ordered": "1"}], supplier_id=supplier.id, company_id=company, branch_id=None, actor=_actor("Magazynier"))
        branch = None
        if scope == "branch":
            branches = [Branch(name=code, code=code, company_id=company) for code in ("PO-OWN", "PO-OTHER")]
            db.session.add_all(branches)
            db.session.flush()
            branch = branches[0].id
            po.branch_id = branches[1].id
            db.session.commit()
        else:
            company += 999
        with pytest.raises(PurchaseOrderNotFoundError):
            service.get_order(order_id=po.id, company_id=company, branch_id=branch, actor=_actor("Magazynier"))
        with pytest.raises(PurchaseOrderNotFoundError):
            service.update_status(order_id=po.id, status="SENT", company_id=company, branch_id=branch, actor=_actor("Magazynier"))


def test_status_route_requires_csrf(app, auth_client, monkeypatch):
    from app.purchase_orders import routes
    app.config["WTF_CSRF_ENABLED"] = True
    calls = []
    monkeypatch.setattr(routes.purchase_order_service, "update_status", lambda **kw: calls.append(kw))
    response = auth_client.post("/purchase-orders/123/status", data={"status": "SENT"})
    assert response.status_code == 302
    assert calls == []
