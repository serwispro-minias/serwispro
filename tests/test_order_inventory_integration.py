from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.inventory.service import InventoryService
from app.models.customer import Customer
from app.models.device import Device
from app.models.inventory_part import InventoryPart
from app.models.inventory_stock_operation import InventoryStockOperation
from app.models.catalog_category import ProductCategory
from app.models.vat_rate import VatRate
from app.models.service_order import ServiceOrder
from app.models.service_order_part_usage import ServiceOrderPartUsage


@pytest.fixture()
def order_inventory_schema(app):
    with app.app_context():
        db.Model.metadata.create_all(
            bind=db.engine,
            tables=[
                Device.__table__,
                ServiceOrder.__table__,
                InventoryPart.__table__,
                ProductCategory.__table__,
                VatRate.__table__,
                InventoryStockOperation.__table__,
                ServiceOrderPartUsage.__table__,
            ],
        )

    yield

    with app.app_context():
        db.session.remove()
        db.Model.metadata.drop_all(
            bind=db.engine,
            tables=[
                ServiceOrderPartUsage.__table__,
                InventoryStockOperation.__table__,
                InventoryPart.__table__,
                VatRate.__table__,
                ProductCategory.__table__,
                ServiceOrder.__table__,
                Device.__table__,
            ],
        )


def _create_order(company_id: int) -> int:
    customer = Customer(
        customer_type="PERSON",
        full_name="Integracja Magazynu",
        company_id=company_id,
    )
    db.session.add(customer)
    db.session.flush()

    device = Device(
        customer_id=customer.id,
        manufacturer="Brother",
        model="DCP",
        serial_number="SO-INV-001",
        company_id=company_id,
    )
    db.session.add(device)
    db.session.flush()

    order = ServiceOrder(
        customer_id=customer.id,
        device_id=device.id,
        order_number="SO-INV-001",
        status="RECEIVED",
        priority="NORMAL",
        intake_date=date.today(),
        issue_description="Usterka testowa",
        company_id=company_id,
    )
    db.session.add(order)
    db.session.commit()
    return int(order.id)


def test_consume_part_decrements_stock_and_creates_usage(app, company_id, order_inventory_schema):
    service = InventoryService()

    with app.app_context():
        order_id = _create_order(company_id)
        category = ProductCategory(code="INV-CAT", name="Mechanika", company_id=company_id)
        vat = VatRate(code="INV-23", rate=23, company_id=company_id, is_active=True)
        db.session.add_all([category, vat])
        db.session.flush()
        part = service.create_part(
            {
                "code": "INV-001",
                "name": "Rolka",
                "category_id": category.id,
                "barcode": "",
                "current_stock": "10",
                "purchase_price_net": "10",
                "sale_price_net": "20",
                "vat_id": vat.id,
                "is_active": True,
            },
            company_id=company_id,
            branch_id=None,
            user_id=1,
        )

        usage = service.consume_for_order(
            order_id=order_id,
            part_id=part.id,
            quantity_raw="2",
            unit_net_price_raw="20",
            company_id=company_id,
            branch_id=None,
            user_id=1,
        )

        assert Decimal(usage.net_value) == Decimal("40.00")
        assert Decimal(usage.vat_value) == Decimal("9.20")
        assert Decimal(usage.gross_value) == Decimal("49.20")

        refreshed = service.get_part(part.id, company_id=company_id)
        assert refreshed is not None
        assert Decimal(refreshed.current_stock) == Decimal("8.000")

        usages = service.list_order_usages(order_id=order_id, company_id=company_id, branch_id=None)
        totals = service.compute_order_usage_totals(usages)
        assert totals.net == Decimal("40.00")
        assert totals.vat == Decimal("9.20")
        assert totals.gross == Decimal("49.20")

        operation = db.session.query(InventoryStockOperation).filter_by(service_order_id=order_id).first()
        assert operation is not None
        assert operation.operation_type == "ISSUE"
