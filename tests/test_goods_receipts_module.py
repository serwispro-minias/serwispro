from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.extensions import db
from app.goods_receipts.exceptions import GoodsReceiptValidationError
from app.goods_receipts.service import GoodsReceiptService
from app.models.catalog_category import ProductCategory
from app.models.catalog_manufacturer import CatalogManufacturer
from app.models.catalog_part import CatalogPart
from app.models.catalog_stock_movement import CatalogStockMovement
from app.models.catalog_supplier import CatalogSupplier
from app.models.customer import Customer
from app.models.device import Device
from app.models.goods_receipt import GoodsReceipt, GoodsReceiptStatusEnum
from app.models.goods_receipt_item import GoodsReceiptItem
from app.models.part_demand import PartDemand
from app.models.purchase_order import PurchaseOrder, PurchaseOrderStatusEnum
from app.models.purchase_order_demand_link import PurchaseOrderDemandLink
from app.models.purchase_order_history import PurchaseOrderHistory
from app.models.purchase_order_item import PurchaseOrderItem
from app.models.service_order import ServiceOrder
from app.models.service_order_part_reservation import ServiceOrderPartReservation
from app.models.supplier import Supplier
from app.models.vat_rate import VatRate


@pytest.fixture()
def goods_receipt_schema(app):
    tables = [
        Device.__table__, ServiceOrder.__table__, CatalogSupplier.__table__, ProductCategory.__table__, VatRate.__table__, CatalogPart.__table__,
        PartDemand.__table__, PurchaseOrder.__table__, PurchaseOrderItem.__table__,
        PurchaseOrderDemandLink.__table__, PurchaseOrderHistory.__table__, CatalogStockMovement.__table__,
        ServiceOrderPartReservation.__table__, GoodsReceipt.__table__, GoodsReceiptItem.__table__,
    ]
    with app.app_context():
        db.Model.metadata.create_all(bind=db.engine, tables=tables)
    yield
    with app.app_context():
        db.session.remove()
        db.Model.metadata.drop_all(bind=db.engine, tables=list(reversed(tables)))


@pytest.fixture()
def receipt_route_schema(app):
    tables = [ProductCategory.__table__, CatalogManufacturer.__table__, VatRate.__table__, CatalogPart.__table__, Supplier.__table__]
    with app.app_context():
        db.Model.metadata.create_all(bind=db.engine, tables=tables)
    yield
    with app.app_context():
        db.session.remove()
        db.Model.metadata.drop_all(bind=db.engine, tables=list(reversed(tables)))


def actor():
    return SimpleNamespace(id=1, roles=[SimpleNamespace(name="Magazynier")])


def test_manual_receipt_form_uses_flask_wtf_csrf(app, auth_client, company_id, receipt_route_schema, monkeypatch):
    with app.app_context():
        category = ProductCategory(code="PZ-ROUTE-CAT", name="PZ", company_id=company_id)
        vat = VatRate(code="PZ-ROUTE-23", rate=Decimal("23"), company_id=company_id, is_active=True)
        supplier = Supplier(code="PZ-ROUTE-SUP", name="PZ Supplier", company_id=company_id, is_active=True)
        db.session.add_all([category, vat, supplier])
        db.session.flush()
        db.session.add(CatalogPart(code="PZ-ROUTE-ITEM", name="PZ Item", category_id=category.id, vat_id=vat.id, company_id=company_id, current_stock=0))
        db.session.commit()

    app.config["WTF_CSRF_ENABLED"] = True
    response = auth_client.get("/goods-receipts/new")
    assert response.status_code == 200
    assert b"csrf_token" in response.data
    assert b"+ Dodaj asortyment" in response.data
    assert b"PZ-ROUTE-ITEM" not in response.data

    called = False

    def fail_create(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("PZ service must not run without a valid CSRF token")

    from app.goods_receipts import routes

    monkeypatch.setattr(routes.goods_receipt_service, "create_receipt", fail_create)
    invalid = auth_client.post("/goods-receipts/new", data={"supplier_id": "1"})
    assert invalid.status_code == 200
    assert called is False


def test_product_search_matches_code_name_barcode_and_fragments(auth_client, app, company_id, receipt_route_schema):
    with app.app_context():
        category = ProductCategory(code="CPU", name="Procesory", company_id=company_id)
        vat = VatRate(code="23-SEARCH", rate=Decimal("23"), company_id=company_id, is_active=True)
        product = CatalogPart(code="CPU-I5", name="Procesor Intel Core i5", barcode="HP652EAN", category=category, vat=vat, company_id=company_id, current_stock=7, purchase_price_net=Decimal("100"), sale_price_net=Decimal("130"))
        db.session.add(product)
        db.session.commit()

    assert "CPU-I5" in auth_client.get("/catalog/parts/search?q=CPU").get_data(as_text=True)
    assert "CPU-I5" in auth_client.get("/catalog/parts/search?q=procesor").get_data(as_text=True).lower().upper()
    assert "CPU-I5" in auth_client.get("/catalog/parts/search?q=HP652").get_data(as_text=True)
    assert "CPU-I5" in auth_client.get("/catalog/parts/search?q=proc int").get_data(as_text=True)


def test_product_created_from_receipt_returns_to_receipt_with_new_item(app, auth_client, company_id, receipt_route_schema):
    with app.app_context():
        category = ProductCategory(code="PZ-NEW-CAT", name="Nowe", company_id=company_id)
        vat = VatRate(code="PZ-NEW-23", rate=Decimal("23"), company_id=company_id, is_active=True)
        db.session.add_all([category, vat])
        db.session.commit()
        category_id = category.id
        vat_id = vat.id

    response = auth_client.post(
        "/catalog/parts/create?return_to=goods_receipt",
        data={
            "code": "PZ-NEW-PROD",
            "name": "Produkt z PZ",
            "category_id": str(category_id),
            "barcode": "PZNEW123",
            "current_stock": "9",
            "purchase_price_net": "10.00",
            "sale_price_net": "15.00",
            "vat_id": str(vat_id),
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/goods-receipts/new?new_item_id=" in response.headers["Location"]
    with app.app_context():
        product = db.session.query(CatalogPart).filter_by(code="PZ-NEW-PROD").one()
        assert product.current_stock == 0


def test_rw_list_links_to_existing_create_endpoint(auth_client, monkeypatch):
    from app.stock_issues import routes

    monkeypatch.setattr(routes.stock_issue_service, "list_issues", lambda **kwargs: [])
    response = auth_client.get("/stock-issues/")
    assert response.status_code == 200
    assert b"Nowy RW" in response.data
    assert b"/stock-issues/new" in response.data


def setup_data(company_id: int):
    customer = Customer(customer_type="PERSON", full_name="PZ Klient", company_id=company_id)
    db.session.add(customer)
    db.session.flush()
    device = Device(customer_id=customer.id, manufacturer="HP", model="M1", serial_number="PZ-SN", company_id=company_id)
    db.session.add(device)
    db.session.flush()
    order = ServiceOrder(customer_id=customer.id, device_id=device.id, order_number="PZ-SO", status="RECEIVED", priority="NORMAL", intake_date=date.today(), issue_description="PZ", company_id=company_id)
    supplier = CatalogSupplier(code="PZ-SUP", name="Dostawca PZ", company_id=company_id, is_active=True)
    db.session.add_all([order, supplier])
    db.session.flush()
    category = ProductCategory(code="PZ-CAT", name="Części PZ", company_id=company_id)
    vat = VatRate(code="PZ-23", rate=Decimal("23"), company_id=company_id, is_active=True)
    db.session.add_all([category, vat])
    db.session.flush()
    part = CatalogPart(code="PZ-PART", name="Część PZ", category_id=category.id, vat_id=vat.id, current_stock=0, purchase_price_net=Decimal("10"), sale_price_net=Decimal("12"), company_id=company_id)
    db.session.add(part)
    db.session.flush()
    demand = PartDemand(service_order_id=order.id, inventory_item_id=part.id, requested_quantity=Decimal("5"), reserved_quantity=Decimal("0"), missing_quantity=Decimal("5"), status="IN_PURCHASE", priority="NORMAL", company_id=company_id)
    db.session.add(demand)
    po_number = f"PO/PZ/{(db.session.query(PurchaseOrder).count() + 1):06d}"
    po = PurchaseOrder(po_number=po_number, supplier_id=supplier.id, status=PurchaseOrderStatusEnum.CONFIRMED.value, order_date=date.today(), total_net=Decimal("50"), total_vat=Decimal("11.50"), total_gross=Decimal("61.50"), company_id=company_id)
    db.session.add(po)
    db.session.flush()
    po_item = PurchaseOrderItem(purchase_order_id=po.id, part_id=part.id, code_snapshot=part.code, quantity_ordered=Decimal("5"), quantity_received=Decimal("0"), unit="szt.", unit_price_net=Decimal("10"), vat_rate=Decimal("23"), total_net=Decimal("50"), total_vat=Decimal("11.50"), total_gross=Decimal("61.50"))
    db.session.add(po_item)
    db.session.flush()
    db.session.add(PurchaseOrderDemandLink(purchase_order_item_id=po_item.id, part_demand_id=demand.id, allocated_quantity=Decimal("5")))
    db.session.commit()
    return po, po_item, part, demand


def test_accept_receipt_updates_stock_reservation_demand_order_and_history(app, goods_receipt_schema):
    with app.app_context():
        company_id = int(app.config["TEST_COMPANY_ID"])
        po, po_item, part, demand = setup_data(company_id)
        service = GoodsReceiptService()
        receipt = service.create_receipt(purchase_order_id=po.id, items=[{"purchase_order_item_id": po_item.id, "quantity_received": "5"}], company_id=company_id, branch_id=None, actor=actor())
        service.accept_receipt(receipt_id=receipt.id, company_id=company_id, branch_id=None, actor=actor())

        db.session.refresh(part)
        db.session.refresh(demand)
        db.session.refresh(po)
        assert part.current_stock == 5
        assert part.purchase_price_net == Decimal("10.00")
        assert part.sale_price_net == Decimal("12.00")
        assert demand.status == "IN_PURCHASE"
        assert demand.reserved_quantity == Decimal("0")
        assert db.session.query(ServiceOrderPartReservation).filter_by(service_order_id=demand.service_order_id).count() == 0
        assert po.status == PurchaseOrderStatusEnum.COMPLETED.value
        movement = db.session.query(CatalogStockMovement).filter_by(reference_id=receipt.receipt_number).one()
        assert movement.movement_type == "RECEIPT"
        assert movement.note == f"Przyjęcie PZ nr {receipt.receipt_number}"
        service.accept_receipt(receipt_id=receipt.id, company_id=company_id, branch_id=None, actor=actor())
        db.session.refresh(part)
        assert part.current_stock == 5


def test_manual_receipt_updates_purchase_and_sale_price_on_post(app, goods_receipt_schema):
    with app.app_context():
        company_id = int(app.config["TEST_COMPANY_ID"])
        _, _, part, _ = setup_data(company_id)
        supplier = db.session.query(CatalogSupplier).filter_by(company_id=company_id).first()
        service = GoodsReceiptService()
        receipt = service.create_receipt(items=[{"inventory_item_id": part.id, "quantity_received": "2", "purchase_price_net": "120", "sale_price_net": "159", "vat_id": part.vat_id}], supplier_id=supplier.id, company_id=company_id, branch_id=None, actor=actor())
        db.session.refresh(part)
        assert part.current_stock == 0
        service.accept_receipt(receipt_id=receipt.id, company_id=company_id, branch_id=None, actor=actor())
        db.session.refresh(part)
        assert part.current_stock == 2
        assert part.purchase_price_net == Decimal("120.00")
        assert part.sale_price_net == Decimal("159.00")
        item = db.session.query(GoodsReceiptItem).filter_by(goods_receipt_id=receipt.id).one()
        assert item.sale_price_net == Decimal("159.00")


def test_partial_receipt_and_validation(app, goods_receipt_schema):
    with app.app_context():
        company_id = int(app.config["TEST_COMPANY_ID"])
        po, po_item, _, _ = setup_data(company_id)
        service = GoodsReceiptService()
        receipt = service.create_receipt(purchase_order_id=po.id, items=[{"purchase_order_item_id": po_item.id, "quantity_received": "2"}], company_id=company_id, branch_id=None, actor=actor())
        service.accept_receipt(receipt_id=receipt.id, company_id=company_id, branch_id=None, actor=actor())
        db.session.refresh(po)
        assert po.status == PurchaseOrderStatusEnum.PARTIAL.value

        po2, item2, _, _ = setup_data(company_id)
        with pytest.raises(GoodsReceiptValidationError):
            service.create_receipt(purchase_order_id=po2.id, items=[{"purchase_order_item_id": item2.id, "quantity_received": "0"}], company_id=company_id, branch_id=None, actor=actor())
        with pytest.raises(GoodsReceiptValidationError):
            service.create_receipt(purchase_order_id=po2.id, items=[{"purchase_order_item_id": item2.id, "quantity_received": "1"}, {"purchase_order_item_id": item2.id, "quantity_received": "1"}], company_id=company_id, branch_id=None, actor=actor())
