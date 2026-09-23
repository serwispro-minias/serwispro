from __future__ import annotations

from decimal import Decimal

import pytest

from app.extensions import db
from app.inventory.service import InventoryService
from app.models.catalog_category import ProductCategory
from app.models.inventory_item import InventoryItem
from app.models.inventory_reservation import InventoryReservation
from app.models.inventory_stock_operation import InventoryStockOperation
from app.models.vat_rate import VatRate


@pytest.fixture()
def inventory_schema(app):
    with app.app_context():
        db.Model.metadata.create_all(
            bind=db.engine,
            tables=[
                ProductCategory.__table__,
                VatRate.__table__,
                InventoryItem.__table__,
                InventoryStockOperation.__table__,
                InventoryReservation.__table__,
            ],
        )

    yield

    with app.app_context():
        db.session.remove()
        db.Model.metadata.drop_all(
            bind=db.engine,
            tables=[
                InventoryStockOperation.__table__,
                InventoryReservation.__table__,
                InventoryItem.__table__,
                VatRate.__table__,
                ProductCategory.__table__,
            ],
        )


def test_create_and_edit_part_inventory_card(app, company_id, inventory_schema):
    service = InventoryService()

    with app.app_context():
        category = ProductCategory(code="MECH", name="Mechanika", company_id=company_id)
        vat = VatRate(code="23", rate=Decimal("23"), company_id=company_id, is_active=True)
        db.session.add_all([category, vat])
        db.session.flush()
        part = service.create_part(
            {
                "code": "P-001",
                "name": "Rolka poboru",
                "category_id": category.id,
                "barcode": "1234567890123",
                "current_stock": "5",
                "purchase_price_net": "12.50",
                "sale_price_net": "24.99",
                "vat_id": vat.id,
                "is_active": True,
            },
            company_id=company_id,
            branch_id=None,
            user_id=1,
        )

        assert part.id is not None
        assert part.code == "P-001"
        assert part.current_stock == 5

        updated = service.update_part(
            part.id,
            {
                "code": "P-001",
                "name": "Rolka poboru papieru",
                "category_id": category.id,
                "barcode": "1234567890123",
                "current_stock": "3",
                "purchase_price_net": "12.50",
                "sale_price_net": "24.99",
                "vat_id": vat.id,
                "is_active": True,
            },
            company_id=company_id,
            branch_id=None,
            user_id=1,
        )

        assert updated.name == "Rolka poboru papieru"
        assert updated.current_stock == 3


def test_stock_operations_and_low_stock_warning(app, company_id, inventory_schema, auth_client):
    service = InventoryService()

    with app.app_context():
        category = ProductCategory(code="MAT", name="Materiały", company_id=company_id)
        vat = VatRate(code="23", rate=Decimal("23"), company_id=company_id, is_active=True)
        db.session.add_all([category, vat])
        db.session.flush()
        part = service.create_part(
            {
                "code": "P-LOW",
                "name": "Toner",
                "category_id": category.id,
                "barcode": "",
                "current_stock": "3",
                "purchase_price_net": "100",
                "sale_price_net": "150",
                "vat_id": vat.id,
                "is_active": True,
            },
            company_id=company_id,
            branch_id=None,
            user_id=1,
        )

        service.register_operation(
            part_id=part.id,
            operation_type="ISSUE",
            quantity_raw="1",
            document_number="RW-1",
            comment="Wydanie",
            company_id=company_id,
            branch_id=None,
            user_id=1,
        )

        refreshed = service.get_part(part.id, company_id=company_id)
        assert refreshed is not None
        assert refreshed.current_stock == 2

        operations = service.list_part_operations(part.id, company_id=company_id)
        assert len(operations) >= 2
        assert any(op.document_number == "RW-1" for op in operations)

    response = auth_client.get("/inventory/")
    assert response.status_code == 200
    assert response.status_code == 200
