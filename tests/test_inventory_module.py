from __future__ import annotations

from decimal import Decimal

import pytest

from app.extensions import db
from app.inventory.service import InventoryService
from app.models.inventory_part import InventoryPart
from app.models.inventory_stock_operation import InventoryStockOperation


@pytest.fixture()
def inventory_schema(app):
    with app.app_context():
        db.Model.metadata.create_all(
            bind=db.engine,
            tables=[
                InventoryPart.__table__,
                InventoryStockOperation.__table__,
            ],
        )

    yield

    with app.app_context():
        db.session.remove()
        db.Model.metadata.drop_all(
            bind=db.engine,
            tables=[
                InventoryStockOperation.__table__,
                InventoryPart.__table__,
            ],
        )


def test_create_and_edit_part_inventory_card(app, company_id, inventory_schema):
    service = InventoryService()

    with app.app_context():
        part = service.create_part(
            {
                "part_code": "P-001",
                "name": "Rolka poboru",
                "category": "Mechanika",
                "manufacturer": "Brother",
                "catalog_number": "BR-RP-01",
                "barcode": "1234567890123",
                "description": "Rolka do podajnika papieru",
                "unit": "szt.",
                "minimum_stock": "2",
                "current_stock": "5",
                "location": "A1-02",
                "purchase_price_net": "12.50",
                "sale_price_net": "24.99",
                "vat_rate": "23",
                "supplier": "ABC Parts",
                "image_path": "",
                "is_record_active": "1",
            },
            company_id=company_id,
            branch_id=None,
            user_id=1,
        )

        assert part.id is not None
        assert part.part_code == "P-001"
        assert Decimal(part.current_stock) == Decimal("5.000")

        updated = service.update_part(
            part.id,
            {
                "part_code": "P-001",
                "name": "Rolka poboru papieru",
                "category": "Mechanika",
                "manufacturer": "Brother",
                "catalog_number": "BR-RP-01",
                "barcode": "1234567890123",
                "description": "Aktualizacja opisu",
                "unit": "szt.",
                "minimum_stock": "4",
                "current_stock": "3",
                "location": "A1-03",
                "purchase_price_net": "12.50",
                "sale_price_net": "24.99",
                "vat_rate": "23",
                "supplier": "ABC Parts",
                "image_path": "",
                "is_record_active": "1",
            },
            company_id=company_id,
            branch_id=None,
            user_id=1,
        )

        assert updated.name == "Rolka poboru papieru"
        assert Decimal(updated.current_stock) == Decimal("3.000")


def test_stock_operations_and_low_stock_warning(app, company_id, inventory_schema, auth_client):
    service = InventoryService()

    with app.app_context():
        part = service.create_part(
            {
                "part_code": "P-LOW",
                "name": "Toner",
                "category": "Materiały",
                "manufacturer": "HP",
                "catalog_number": "HP-TN-1",
                "barcode": "",
                "description": "",
                "unit": "szt.",
                "minimum_stock": "3",
                "current_stock": "3",
                "location": "B2",
                "purchase_price_net": "100",
                "sale_price_net": "150",
                "vat_rate": "23",
                "supplier": "",
                "image_path": "",
                "is_record_active": "1",
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
        assert Decimal(refreshed.current_stock) == Decimal("2.000")

        operations = service.list_part_operations(part.id, company_id=company_id)
        assert len(operations) >= 2
        assert any(op.document_number == "RW-1" for op in operations)

    response = auth_client.get("/inventory/")
    assert response.status_code == 200
    assert "Stan poniżej minimum" in response.get_data(as_text=True)
