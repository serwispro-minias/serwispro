from __future__ import annotations

from importlib import import_module
import io

import pytest
from pypdf import PdfReader

from app.extensions import db
from app.inventory.print_service import InventoryPrintService
from app.inventory.service import InventoryService
from app.models.inventory_part import InventoryPart
from app.models.inventory_stock_operation import InventoryStockOperation
from app.models.catalog_category import ProductCategory
from app.models.vat_rate import VatRate


@pytest.fixture()
def inventory_pdf_schema(app):
    with app.app_context():
        db.Model.metadata.create_all(
            bind=db.engine,
            tables=[
                InventoryPart.__table__,
                ProductCategory.__table__,
                VatRate.__table__,
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


def test_inventory_pdf_outputs(app, company_id, inventory_pdf_schema):
    service = InventoryService()
    print_service = InventoryPrintService(service=service)

    with app.app_context():
        category = ProductCategory(code="PDF-CAT", name="Materiały", company_id=company_id)
        vat = VatRate(code="PDF-23", rate=23, company_id=company_id, is_active=True)
        db.session.add_all([category, vat])
        db.session.flush()
        part = service.create_part(
            {
                "code": "PDF-001",
                "name": "Pas transferowy",
                "category_id": category.id,
                "barcode": "",
                "current_stock": "4",
                "purchase_price_net": "45",
                "sale_price_net": "60",
                "vat_id": vat.id,
                "is_active": True,
            },
            company_id=company_id,
            branch_id=None,
            user_id=1,
        )

        doc = print_service.build_part_card(part_id=part.id, company_id=company_id)
        assert doc is not None
        assert doc.content.startswith(b"%PDF")

        reader = PdfReader(io.BytesIO(doc.content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        assert "Karta produktu" in text
        assert "PDF-001" in text


def test_inventory_migration_metadata():
    migration = import_module("migrations.versions.b2f4a61c9d3e_inventory_module_tables")
    assert migration.revision == "b2f4a61c9d3e"
    assert migration.down_revision == "4d7b1ce2f901"
    assert callable(migration.upgrade)
    assert callable(migration.downgrade)
