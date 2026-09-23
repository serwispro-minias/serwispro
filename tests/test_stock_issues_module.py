from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.catalog_category import ProductCategory
from app.models.catalog_part import CatalogPart
from app.models.catalog_stock_movement import CatalogStockMovement
from app.models.catalog_supplier import CatalogSupplier
from app.models.customer import Customer
from app.models.device import Device
from app.models.part_demand import PartDemand
from app.models.service_order import ServiceOrder
from app.models.service_order_part_reservation import ServiceOrderPartReservation
from app.models.stock_issue import StockIssue, StockIssueStatusEnum
from app.models.stock_issue_item import StockIssueItem
from app.models.vat_rate import VatRate
from app.stock_issues.exceptions import StockIssueValidationError
from app.stock_issues.service import StockIssueService


@pytest.fixture()
def stock_issue_schema(app):
    tables = [Device.__table__, ServiceOrder.__table__, CatalogSupplier.__table__, ProductCategory.__table__, VatRate.__table__, CatalogPart.__table__, PartDemand.__table__, ServiceOrderPartReservation.__table__, CatalogStockMovement.__table__, AuditLog.__table__, StockIssue.__table__, StockIssueItem.__table__]
    with app.app_context():
        db.Model.metadata.create_all(bind=db.engine, tables=tables)
    yield
    with app.app_context():
        db.session.remove()
        db.Model.metadata.drop_all(bind=db.engine, tables=list(reversed(tables)))


def actor():
    return SimpleNamespace(id=1, roles=[SimpleNamespace(name="Magazynier")])


def data(company_id: int, quantity: str = "5"):
    customer = Customer(customer_type="PERSON", full_name="RW Klient", company_id=company_id)
    db.session.add(customer)
    db.session.flush()
    device = Device(customer_id=customer.id, manufacturer="HP", model="M1", serial_number="RW-SN", company_id=company_id)
    db.session.add(device)
    db.session.flush()
    order = ServiceOrder(customer_id=customer.id, device_id=device.id, order_number="RW-SO", status="RECEIVED", priority="NORMAL", intake_date=date.today(), issue_description="RW", company_id=company_id)
    category = ProductCategory(code="RW-CAT", name="Części RW", company_id=company_id)
    vat = VatRate(code="RW-23", rate=Decimal("23"), company_id=company_id, is_active=True)
    part = CatalogPart(code="RW-PART", name="Część RW", category=category, vat=vat, current_stock=int(quantity), purchase_price_net=Decimal("10"), sale_price_net=Decimal("12"), company_id=company_id)
    db.session.add_all([order, part])
    db.session.flush()
    demand = PartDemand(service_order_id=order.id, inventory_item_id=part.id, requested_quantity=Decimal(quantity), reserved_quantity=Decimal(quantity), missing_quantity=Decimal("0"), status="ORDERED", priority="NORMAL", company_id=company_id)
    reservation = ServiceOrderPartReservation(service_order_id=order.id, part_id=part.id, quantity=Decimal(quantity), status="RESERVED", company_id=company_id)
    db.session.add_all([demand, reservation])
    db.session.commit()
    return order, part, demand, reservation


def test_issue_reserved_parts_updates_stock_reservation_demand_and_audit(app, stock_issue_schema):
    with app.app_context():
        company_id = int(app.config["TEST_COMPANY_ID"])
        order, part, demand, reservation = data(company_id)
        issue = StockIssueService().issue_reserved_parts(service_order_id=order.id, company_id=company_id, branch_id=None, actor=actor())
        db.session.refresh(part)
        db.session.refresh(reservation)
        db.session.refresh(demand)
        assert issue.issue_number.startswith(f"RW/{date.today().year}/")
        assert issue.status == StockIssueStatusEnum.ISSUED.value
        assert part.current_stock == Decimal("0.000")
        assert reservation.is_active is False
        assert reservation.status == "RELEASED"
        assert demand.status == "ORDERED"
        movement = db.session.query(CatalogStockMovement).filter_by(reference_id=issue.issue_number).one()
        assert movement.movement_type == "ISSUE"
        assert db.session.query(AuditLog).filter_by(object_id=str(issue.id), action="STOCK_ISSUE").count() == 1


def test_partial_issue_keeps_remaining_reservation(app, stock_issue_schema):
    with app.app_context():
        company_id = int(app.config["TEST_COMPANY_ID"])
        order, part, demand, reservation = data(company_id)
        issue = StockIssueService().issue_reserved_parts(service_order_id=order.id, company_id=company_id, branch_id=None, actor=actor(), quantities={reservation.id: Decimal("2")})
        db.session.refresh(part)
        db.session.refresh(reservation)
        db.session.refresh(demand)
        assert issue.status == "POSTED"
        assert part.current_stock == 3
        assert reservation.is_active is True
        assert reservation.quantity == Decimal("3.000")
        assert demand.status == "ORDERED"
        assert demand.reserved_quantity == Decimal("3.000")


def test_issue_rejects_over_reservation_and_insufficient_stock(app, stock_issue_schema):
    with app.app_context():
        company_id = int(app.config["TEST_COMPANY_ID"])
        order, part, _, reservation = data(company_id)
        service = StockIssueService()
        with pytest.raises(StockIssueValidationError):
            service.issue_reserved_parts(service_order_id=order.id, company_id=company_id, branch_id=None, actor=actor(), quantities={reservation.id: Decimal("6")})
        part.current_stock = 1
        db.session.commit()
        with pytest.raises(StockIssueValidationError):
            service.issue_reserved_parts(service_order_id=order.id, company_id=company_id, branch_id=None, actor=actor())


def test_branchless_issue_is_visible_to_branch_scoped_user(app, stock_issue_schema):
    """Regression test: a StockIssue created with branch_id=None must remain visible
    on the RW list for users scoped to a specific branch, not just admins."""
    with app.app_context():
        company_id = int(app.config["TEST_COMPANY_ID"])
        order, _, _, _ = data(company_id)
        service = StockIssueService()
        issue = service.issue_reserved_parts(service_order_id=order.id, company_id=company_id, branch_id=None, actor=actor())
        assert issue.branch_id is None

        branch_scoped_actor = SimpleNamespace(id=2, roles=[SimpleNamespace(name="Magazynier")])
        issues = service.list_issues(company_id=company_id, branch_id=999, actor=branch_scoped_actor)
        assert [row.id for row in issues] == [issue.id]

        fetched = service.get_issue(issue_id=issue.id, company_id=company_id, branch_id=999, actor=branch_scoped_actor)
        assert fetched.id == issue.id


def test_manual_rw_draft_posts_once_without_service_order(app, stock_issue_schema):
    with app.app_context():
        company_id = int(app.config["TEST_COMPANY_ID"])
        _, part, _, _ = data(company_id)
        service = StockIssueService()
        issue = service.create_issue(items=[{"inventory_item_id": part.id, "quantity": 2}], company_id=company_id, branch_id=None, actor=actor())
        assert issue.service_order_id is None
        assert issue.status == StockIssueStatusEnum.DRAFT.value
        db.session.refresh(part)
        assert part.current_stock == 5

        service.post_issue(issue_id=issue.id, company_id=company_id, branch_id=None, actor=actor())
        service.post_issue(issue_id=issue.id, company_id=company_id, branch_id=None, actor=actor())
        db.session.refresh(part)
        assert part.current_stock == 3
        assert db.session.query(CatalogStockMovement).filter_by(reference_id=issue.issue_number, movement_type="ISSUE").count() == 1


def test_rw_multi_item_post_rolls_back_when_one_item_lacks_stock(app, stock_issue_schema):
    with app.app_context():
        company_id = int(app.config["TEST_COMPANY_ID"])
        _, first, _, _ = data(company_id)
        second = CatalogPart(code="RW-EMPTY", name="Brak stanu", category=first.category, vat=first.vat, current_stock=0, purchase_price_net=Decimal("1"), sale_price_net=Decimal("2"), company_id=company_id)
        db.session.add(second)
        db.session.commit()
        service = StockIssueService()
        issue = service.create_issue(items=[{"inventory_item_id": first.id, "quantity": 1}, {"inventory_item_id": second.id, "quantity": 1}], company_id=company_id, branch_id=None, actor=actor())
        with pytest.raises(StockIssueValidationError):
            service.post_issue(issue_id=issue.id, company_id=company_id, branch_id=None, actor=actor())
        db.session.refresh(first)
        db.session.refresh(issue)
        assert first.current_stock == 5
        assert issue.status == StockIssueStatusEnum.DRAFT.value
        assert db.session.query(CatalogStockMovement).filter_by(reference_id=issue.issue_number).count() == 0


def test_rw_create_form_route_renders(auth_client, stock_issue_schema):
    with auth_client.application.app_context():
        company_id = int(auth_client.application.config["TEST_COMPANY_ID"])
        _, part, _, _ = data(company_id)
        code = part.code.encode()
    response = auth_client.get("/stock-issues/new")
    assert response.status_code == 200
    assert b"Nowe RW" in response.data
    assert b"+ Dodaj asortyment" in response.data
    assert code not in response.data

