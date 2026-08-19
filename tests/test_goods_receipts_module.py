from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.extensions import db
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
from app.goods_receipts.exceptions import GoodsReceiptValidationError
from app.goods_receipts.service import GoodsReceiptService


@pytest.fixture()
def goods_receipt_schema(app):
    tables = [
        Device.__table__, ServiceOrder.__table__, CatalogSupplier.__table__, CatalogPart.__table__,
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


def actor():
    return SimpleNamespace(id=1, roles=[SimpleNamespace(name="Magazynier")])


def setup_data(company_id: int):
    customer = Customer(customer_type="PERSON", full_name="PZ Klient", company_id=company_id)
    db.session.add(customer)
    db.session.flush()
    device = Device(customer_id=customer.id, manufacturer="HP", model="M1", serial_number="PZ-SN", company_id=company_id)
    db.session.add(device)
    db.session.flush()
    order = ServiceOrder(customer_id=customer.id, device_id=device.id, order_number="PZ-SO", status="RECEIVED", priority="NORMAL", intake_date=date.today(), issue_description="PZ", company_id=company_id)
    supplier = CatalogSupplier(code="PZ-SUP", name="Dostawca PZ", company_id=company_id, is_supplier_active=True)
    db.session.add_all([order, supplier])
    db.session.flush()
    part = CatalogPart(code="PZ-PART", name="Część PZ", unit="szt.", current_stock=Decimal("0"), minimum_stock=Decimal("0"), purchase_price_net=Decimal("10"), sale_price_net=Decimal("12"), vat_rate=Decimal("23"), supplier_id=supplier.id, company_id=company_id)
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
        assert part.current_stock == Decimal("0.000")
        assert demand.status == "DELIVERED"
        assert demand.reserved_quantity == Decimal("5.000")
        assert db.session.query(ServiceOrderPartReservation).filter_by(service_order_id=demand.service_order_id).count() == 1
        assert po.status == PurchaseOrderStatusEnum.COMPLETED.value
        movement = db.session.query(CatalogStockMovement).filter_by(reference_id=receipt.receipt_number).one()
        assert movement.movement_type == "IN"
        assert movement.note == f"Przyjęcie PZ nr {receipt.receipt_number}"


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
