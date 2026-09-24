from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from alembic import op

from app.extensions import db
from app.goods_receipts.exceptions import GoodsReceiptValidationError
from app.goods_receipts.service import GoodsReceiptService
from app.models.catalog_category import ProductCategory
from app.models.catalog_part import CatalogPart
from app.models.catalog_stock_movement import CatalogStockMovement
from app.models.catalog_supplier import CatalogSupplier
from app.models.company import Company
from app.models.goods_receipt import GoodsReceipt
from app.models.goods_receipt_item import GoodsReceiptItem
from app.models.vat_rate import VatRate
from migrations.versions import e3f4a5b6c7d8_seed_standard_vat_rates as vat_seed


@pytest.fixture()
def vat_schema(app):
    tables = [Company.__table__, ProductCategory.__table__, VatRate.__table__, CatalogPart.__table__, CatalogSupplier.__table__, GoodsReceipt.__table__, GoodsReceiptItem.__table__, CatalogStockMovement.__table__]
    with app.app_context():
        db.Model.metadata.create_all(bind=db.engine, tables=tables)
    yield
    with app.app_context():
        db.session.remove()
        db.Model.metadata.drop_all(bind=db.engine, tables=list(reversed(tables)))


def actor():
    return SimpleNamespace(id=1, roles=[SimpleNamespace(name="Magazynier")])


def seed_standard_rates(engine):
    original_get_bind = op.get_bind
    with engine.begin() as connection:
        op.get_bind = lambda: connection
        try:
            vat_seed.upgrade()
        finally:
            op.get_bind = original_get_bind


def test_standard_vat_rates_seeded_once_and_distinguish_zero_from_exempt(app, company_id, vat_schema):
    with app.app_context():
        seed_standard_rates(db.engine)
        seed_standard_rates(db.engine)
        rows = VatRate.query.filter_by(company_id=company_id).order_by(VatRate.code.asc()).all()
        codes = [row.code for row in rows]
        assert sorted(codes) == ["0%", "23%", "5%", "8%", "zw."]
        assert len(rows) == 5
        zero = VatRate.query.filter_by(company_id=company_id, code="0%").one()
        exempt = VatRate.query.filter_by(company_id=company_id, code="zw.").one()
        assert zero.id != exempt.id
        assert zero.rate == exempt.rate == Decimal("0.00")
        assert VatRate.query.filter_by(company_id=company_id, code="23%").one().is_default is True


def test_vat_choices_are_company_scoped_and_active_only(app, company_id, vat_schema):
    with app.app_context():
        other = Company(name="Other", prefix="OTH")
        db.session.add(other)
        db.session.flush()
        active = VatRate(code="23%", rate=Decimal("23"), company_id=company_id, is_active=True)
        inactive = VatRate(code="8%", rate=Decimal("8"), company_id=company_id, is_active=False)
        foreign = VatRate(code="5%", rate=Decimal("5"), company_id=other.id, is_active=True)
        db.session.add_all([active, inactive, foreign])
        db.session.commit()

        from app.catalog.service import CatalogService

        choices = CatalogService().vat_rate_choices(company_id=company_id)
        assert choices == [(active.id, "23% (23.00%)")]


def test_product_and_receipt_keep_vat_id_after_deactivation(app, company_id, vat_schema):
    with app.app_context():
        vat = VatRate(code="zw.", rate=Decimal("0"), company_id=company_id, is_active=True)
        category = ProductCategory(code="VAT-CAT", name="VAT", company_id=company_id)
        supplier = CatalogSupplier(code="VAT-SUP", name="Dostawca VAT", company_id=company_id, is_active=True)
        db.session.add_all([vat, category, supplier])
        db.session.flush()
        product = CatalogPart(code="VAT-PROD", name="Produkt VAT", category_id=category.id, vat_id=vat.id, current_stock=0, purchase_price_net=Decimal("10"), sale_price_net=Decimal("20"), company_id=company_id)
        db.session.add(product)
        db.session.commit()

        service = GoodsReceiptService()
        receipt = service.create_receipt(items=[{"inventory_item_id": product.id, "quantity_received": "1", "purchase_price_net": "10", "sale_price_net": "20", "vat_id": vat.id}], supplier_id=supplier.id, company_id=company_id, branch_id=None, actor=actor())
        item = db.session.query(GoodsReceiptItem).filter_by(goods_receipt_id=receipt.id).one()
        assert item.vat_id == vat.id
        vat.is_active = False
        db.session.commit()
        db.session.refresh(product)
        db.session.refresh(item)
        assert product.vat_id == vat.id
        assert item.vat_id == vat.id


def test_receipt_rejects_inactive_product_vat_with_clear_message(app, company_id, vat_schema):
    with app.app_context():
        category = ProductCategory(code="NO-VAT", name="NO VAT", company_id=company_id)
        supplier = CatalogSupplier(code="NO-VAT-SUP", name="Supplier", company_id=company_id, is_active=True)
        vat = VatRate(code="NO-ACTIVE", rate=Decimal("23"), company_id=company_id, is_active=False)
        db.session.add_all([category, supplier, vat])
        db.session.flush()
        product = CatalogPart(code="NO-VAT-PROD", name="No VAT", category_id=category.id, vat_id=vat.id, current_stock=0, company_id=company_id)
        db.session.add(product)
        db.session.commit()
        with pytest.raises(GoodsReceiptValidationError, match="Nieprawidłowa stawka VAT"):
            GoodsReceiptService().create_receipt(items=[{"inventory_item_id": product.id, "quantity_received": "1"}], supplier_id=supplier.id, company_id=company_id, branch_id=None, actor=actor())
