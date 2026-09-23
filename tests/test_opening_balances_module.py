from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.extensions import db
from app.models.catalog_category import ProductCategory
from app.models.catalog_part import CatalogPart
from app.models.catalog_stock_movement import CatalogStockMovement
from app.models.opening_balance import OpeningBalance, OpeningBalanceStatusEnum
from app.models.opening_balance_item import OpeningBalanceItem
from app.models.vat_rate import VatRate
from app.opening_balances.service import opening_balance_service


@pytest.fixture()
def opening_balance_schema(app):
    tables = [ProductCategory.__table__, VatRate.__table__, CatalogPart.__table__, CatalogStockMovement.__table__, OpeningBalance.__table__, OpeningBalanceItem.__table__]
    with app.app_context():
        db.Model.metadata.create_all(bind=db.engine, tables=tables)
    yield
    with app.app_context():
        db.session.remove()
        db.Model.metadata.drop_all(bind=db.engine, tables=list(reversed(tables)))


def actor():
    return SimpleNamespace(id=1, roles=[SimpleNamespace(name="Magazynier")])


def setup_product(company_id):
    category = ProductCategory(code="BO-CAT", name="BO", company_id=company_id)
    vat = VatRate(code="BO-23", rate=Decimal("23"), company_id=company_id, is_active=True)
    db.session.add_all([category, vat])
    db.session.flush()
    product = CatalogPart(code="BO-001", name="Produkt BO", category_id=category.id, vat_id=vat.id, current_stock=0, purchase_price_net=Decimal("10"), sale_price_net=Decimal("20"), company_id=company_id)
    db.session.add(product)
    db.session.commit()
    return product, vat


def test_opening_balance_posts_once_and_creates_movement(app, company_id, opening_balance_schema):
    with app.app_context():
        product, vat = setup_product(company_id)
        balance = opening_balance_service.create(items=[{"inventory_item_id": product.id, "quantity": "4", "purchase_price_net": "11.50", "vat_id": vat.id}], company_id=company_id, branch_id=None, actor=actor())
        db.session.refresh(product)
        assert balance.status == OpeningBalanceStatusEnum.DRAFT.value
        assert product.current_stock == 0

        opening_balance_service.post(balance_id=balance.id, company_id=company_id, branch_id=None, actor=actor())
        opening_balance_service.post(balance_id=balance.id, company_id=company_id, branch_id=None, actor=actor())
        db.session.refresh(product)
        assert product.current_stock == 4
        assert db.session.query(CatalogStockMovement).filter_by(reference_id=balance.document_number, movement_type="OPENING_BALANCE").count() == 1
