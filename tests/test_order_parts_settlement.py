"""Order-item settlement through draft/posted RW, with an isolated SQLite schema."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from flask_wtf.csrf import generate_csrf

import app as app_package
from app.extensions import db
from app.goods_receipts.service import GoodsReceiptService
from app.inventory.reservation_service import reserved_stock
from app.models.audit_log import AuditLog
from app.models.branch import Branch
from app.models.catalog_category import ProductCategory
from app.models.catalog_material import CatalogMaterial
from app.models.catalog_part import CatalogPart
from app.models.catalog_stock_movement import CatalogStockMovement
from app.models.catalog_supplier import CatalogSupplier
from app.models.company import Company
from app.models.customer import Customer
from app.models.device import Device
from app.models.part_demand import PartDemand
from app.models.purchase_order_demand_link import PurchaseOrderDemandLink
from app.models.role import Role
from app.models.service_order import ServiceOrder
from app.models.service_order_item import ServiceOrderItem
from app.models.service_order_part_reservation import ServiceOrderPartReservation
from app.models.stock_issue import StockIssue
from app.models.stock_issue_item import StockIssueItem
from app.models.user import User
from app.models.user_role import UserRole
from app.models.vat_rate import VatRate
from app.orders.item_service import (
    ServiceOrderItemNotFoundError,
    ServiceOrderItemService,
    ServiceOrderItemValidationError,
)
from app.purchase_orders.service import PurchaseOrderService
from app.stock_issues.exceptions import (
    StockIssueNotFoundError,
    StockIssuePermissionError,
    StockIssueValidationError,
)
from app.stock_issues.service import StockIssueService


@pytest.fixture()
def app(monkeypatch):
    """Override the shared partial-schema fixture only for this test module.

    Override configuration BEFORE SQLAlchemy initialization: changing the URI
    afterwards would not replace an engine loaded from the instance config.
    Never keep an application context open across yield/HTTP requests.
    """
    register_extensions = app_package.register_extensions

    def initialize_sqlite(test_app):
        test_app.config.update(
            TESTING=True,
            SECRET_KEY="order-parts-settlement-tests",
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_BINDS={},
            SQLALCHEMY_ENGINE_OPTIONS={},
            WTF_CSRF_ENABLED=False,
            SESSION_COOKIE_SECURE=False,
        )
        register_extensions(test_app)

    with monkeypatch.context() as patch:
        patch.setattr(app_package, "register_extensions", initialize_sqlite)
        test_app = app_package.create_app("testing")

    @test_app.get("/_test/order-parts/csrf")
    def csrf_token():
        # Use the actual session/token machinery without rendering order details.
        return {"csrf_token": generate_csrf()}

    with test_app.app_context():
        assert db.engine.url.drivername == "sqlite"
        assert db.engine.url.database == ":memory:"
        db.Model.metadata.create_all(bind=db.engine)
        company = Company(name="Settlement company", prefix="SET")
        db.session.add(company)
        db.session.flush()
        branch = Branch(name="Settlement branch", code="SET-A", company_id=company.id)
        db.session.add(branch)
        db.session.flush()
        user = User(
            login="settlement-warehouse",
            password_hash="not-used-in-tests",
            company_id=company.id,
            branch_id=branch.id,
        )
        role = Role(name="Magazynier", company_id=company.id)
        db.session.add_all([user, role])
        db.session.flush()
        db.session.add(UserRole(user_id=user.id, role_id=role.id, company_id=company.id))
        db.session.commit()
        test_app.config.update(
            TEST_COMPANY_ID=company.id,
            TEST_USER_ID=user.id,
            TEST_BRANCH_ID=branch.id,
        )

    try:
        yield test_app
    finally:
        with test_app.app_context():
            db.session.remove()
            db.Model.metadata.drop_all(bind=db.engine)
            db.engine.dispose()


def _create_order(company_id, branch_id, suffix):
    customer = Customer(
        customer_type="PERSON",
        full_name=f"Settlement customer {suffix}",
        company_id=company_id,
        branch_id=branch_id,
    )
    db.session.add(customer)
    db.session.flush()
    device = Device(
        customer_id=customer.id,
        manufacturer="Canon",
        model="Settlement device",
        serial_number=f"SET-SN-{suffix}",
        company_id=company_id,
        branch_id=branch_id,
    )
    db.session.add(device)
    db.session.flush()
    order = ServiceOrder(
        customer_id=customer.id,
        device_id=device.id,
        order_number=f"SET-SO-{suffix}",
        status="RECEIVED",
        priority="NORMAL",
        intake_date=date(2026, 10, 25),
        issue_description="Parts settlement regression",
        company_id=company_id,
        branch_id=branch_id,
    )
    db.session.add(order)
    db.session.flush()
    return order


@pytest.fixture()
def settlement(app):
    """Return IDs, not ORM objects tied to a context that has already closed."""
    with app.app_context():
        company_id = app.config["TEST_COMPANY_ID"]
        branch_id = app.config["TEST_BRANCH_ID"]
        order = _create_order(company_id, branch_id, "ONE")
        other_order = _create_order(company_id, branch_id, "TWO")
        other_branch = Branch(name="Other branch", code="SET-B", company_id=company_id)
        other_company = Company(name="Other company", prefix="OTHER")
        category = ProductCategory(code="SET-CAT", name="Settlement parts", company_id=company_id)
        vat = VatRate(code="SET-23", rate=Decimal("23"), company_id=company_id)
        db.session.add_all([other_branch, other_company, category, vat])
        db.session.flush()
        part = CatalogPart(
            code="SET-PART",
            name="Settlement part",
            category_id=category.id,
            vat_id=vat.id,
            current_stock=10,
            purchase_price_net=Decimal("10"),
            sale_price_net=Decimal("20"),
            company_id=company_id,
            branch_id=branch_id,
        )
        material = CatalogMaterial(
            code="SET-MATERIAL",
            name="Settlement liquid",
            unit="l",
            current_stock=Decimal("5"),
            purchase_price_net=Decimal("8"),
            vat_rate=Decimal("23"),
            company_id=company_id,
            branch_id=branch_id,
        )
        db.session.add_all([part, material])
        db.session.commit()
        return SimpleNamespace(
            company_id=company_id,
            branch_id=branch_id,
            user_id=app.config["TEST_USER_ID"],
            order_id=order.id,
            other_order_id=other_order.id,
            other_company_id=other_company.id,
            other_branch_id=other_branch.id,
            part_id=part.id,
            material_id=material.id,
            warehouse=SimpleNamespace(
                id=app.config["TEST_USER_ID"],
                roles=[SimpleNamespace(name="Magazynier")],
            ),
        )


def _scope(data):
    return {"company_id": data.company_id, "branch_id": data.branch_id}


def _add(data, quantity="5", *, item_type="PART", **overrides):
    arguments = dict(
        order_id=data.order_id,
        **_scope(data),
        user_id=data.user_id,
        item_type=item_type,
        item_id=data.part_id if item_type == "PART" else data.material_id,
        quantity_raw=quantity,
        unit_price_net_raw=None,
        discount_percent_raw=None,
        notes=None,
    )
    arguments.update(overrides)
    return ServiceOrderItemService().add_item(**arguments)


def _use(data, item, quantity="3", **overrides):
    arguments = dict(
        order_id=item.service_order_id,
        item_id=item.id,
        quantity_raw=quantity,
        **_scope(data),
        user_id=data.user_id,
        actor=data.warehouse,
        expected_version=item.version,
    )
    arguments.update(overrides)
    return ServiceOrderItemService().mark_used(**arguments)


def _return(data, item, quantity="2", **overrides):
    arguments = dict(
        order_id=item.service_order_id,
        item_id=item.id,
        quantity_raw=quantity,
        **_scope(data),
        user_id=data.user_id,
        expected_version=item.version,
        reserve=False,
    )
    arguments.update(overrides)
    return ServiceOrderItemService().return_item(**arguments)


def _post(data, issue, **overrides):
    arguments = dict(issue_id=issue.id, **_scope(data), actor=data.warehouse)
    arguments.update(overrides)
    return StockIssueService().post_issue(**arguments)


def _held(data, item_type="PART"):
    return reserved_stock(
        item_type=item_type,
        item_id=data.part_id if item_type == "PART" else data.material_id,
        company_id=data.company_id,
    )


def test_duplicate_rw_lines_validate_cumulative_quantity(app, settlement):
    with app.app_context():
        service = StockIssueService()
        issue = service.create_issue(items=[
            {"inventory_item_id": settlement.part_id, "quantity": "6"},
            {"inventory_item_id": settlement.part_id, "quantity": "6"},
        ], **_scope(settlement), actor=settlement.warehouse)
        with pytest.raises(StockIssueValidationError):
            _post(settlement, issue)
        assert db.session.get(CatalogPart, settlement.part_id).current_stock == 10
        assert db.session.get(StockIssue, issue.id).status == "DRAFT"
        assert db.session.query(CatalogStockMovement).count() == 0


def test_stale_draft_rw_does_not_post_twice(app, settlement):
    from sqlalchemy import update
    with app.app_context():
        item = _add(settlement, reserve=False)
        issue = _use(settlement, item)
        assert issue.status == "DRAFT"
        db.session.execute(update(StockIssue).where(StockIssue.id == issue.id)
            .values(status="POSTED").execution_options(synchronize_session=False))
        _post(settlement, issue)
        assert db.session.get(CatalogPart, settlement.part_id).current_stock == 10
        assert db.session.query(CatalogStockMovement).count() == 0


def test_failed_rw_creation_does_not_leave_partial_document(app, settlement):
    with app.app_context():
        with pytest.raises(StockIssueValidationError):
            StockIssueService().create_issue(items=[
                {"inventory_item_id": settlement.part_id, "quantity": "1"},
                {"inventory_item_id": 999999, "quantity": "1"},
            ], **_scope(settlement), actor=settlement.warehouse)
        db.session.commit()
        assert db.session.query(StockIssue).count() == 0
        assert db.session.query(StockIssueItem).count() == 0


def test_product_search_matches_ean_and_excludes_other_branch(app, settlement):
    with app.app_context():
        part = db.session.get(CatalogPart, settlement.part_id)
        part.barcode = "5901234567890"
        db.session.commit()
        service = ServiceOrderItemService()
        rows = service.search_catalog_items(query_text="5901234567890", **_scope(settlement))
        assert rows[0]["item_id"] == part.id
        assert rows[0]["barcode"] == part.barcode
        assert Decimal(rows[0]["available_stock"]) == 10
        part.branch_id = settlement.other_branch_id
        db.session.commit()
        assert service.search_catalog_items(query_text="5901234567890", **_scope(settlement)) == []
        with pytest.raises(ServiceOrderItemValidationError):
            _add(settlement)


def test_legacy_consume_route_cannot_bypass_rw(app, auth_client, settlement):
    response = auth_client.post(f"/orders/{settlement.order_id}/parts/consume", data={
        "part_id": str(settlement.part_id), "quantity": "2", "unit_net_price": "10",
    })
    assert response.status_code == 409
    with app.app_context():
        assert db.session.get(CatalogPart, settlement.part_id).current_stock == 10
        assert db.session.query(CatalogStockMovement).count() == 0


def test_catalog_material_action_prepares_rw_without_stock_change(app, auth_client, settlement):
    response = auth_client.post(f"/catalog/orders/{settlement.order_id}/issue-material", data={
        "material_id": str(settlement.material_id), "quantity": "1.125",
    })
    assert response.status_code == 302
    assert "/stock-issues/" in response.headers["Location"]
    with app.app_context():
        assert db.session.get(CatalogMaterial, settlement.material_id).current_stock == 5
        assert db.session.query(StockIssue).one().status == "DRAFT"


def test_catalog_auto_issue_does_not_bypass_rw(app, auth_client, settlement):
    response = auth_client.post(f"/catalog/orders/{settlement.order_id}/auto-issue-materials")
    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(CatalogMaterial, settlement.material_id).current_stock == 5
        assert db.session.query(CatalogStockMovement).count() == 0


def test_catalog_reservation_is_visible_as_order_item(app, auth_client, settlement):
    response = auth_client.post(f"/catalog/orders/{settlement.order_id}/reserve-part", data={
        "part_id": str(settlement.part_id), "quantity": "4",
    })
    assert response.status_code == 302
    with app.app_context():
        item = db.session.query(ServiceOrderItem).one()
        assert item.reserved_quantity == 4
        assert db.session.get(CatalogPart, settlement.part_id).current_stock == 10
        assert _held(settlement) == 4


def _assert_state(data, item, *, stock, reserved, used, returned):
    db.session.refresh(item)
    model = CatalogPart if item.item_type == "PART" else CatalogMaterial
    product = db.session.get(model, item.item_id)
    db.session.refresh(product)
    assert Decimal(product.current_stock) == Decimal(stock)
    assert item.reserved_quantity == Decimal(reserved)
    assert item.used_quantity == Decimal(used)
    assert item.returned_quantity == Decimal(returned)


@pytest.mark.parametrize(
    "reserve,used,stock,returned",
    [(False, "3", "7", "0"), (True, "3", "7", "2"), (True, "7", "3", "0")],
    ids=["direct-use", "reserve-five-settle-three", "reserve-five-settle-seven"],
)
def test_usage_is_draft_until_rw_posting(app, settlement, reserve, used, stock, returned):
    with app.app_context():
        item = _add(settlement, reserve=reserve)
        held = "5" if reserve else "0"
        _assert_state(settlement, item, stock="10", reserved=held, used="0", returned="0")
        assert _held(settlement) == Decimal(held)
        issue = _use(settlement, item, used)
        assert issue.status == "DRAFT"
        assert issue.service_order_id == settlement.order_id
        assert len(issue.items) == 1
        line = issue.items[0]
        assert line.service_order_item_id == item.id
        assert line.inventory_item_id == settlement.part_id
        assert line.material_id is None
        assert line.quantity_issued == Decimal(used)
        assert line.settlement_version == item.version
        _assert_state(settlement, item, stock="10", reserved=held, used="0", returned="0")
        assert db.session.query(CatalogStockMovement).count() == 0

        posted = _post(settlement, issue)
        assert posted.status == "POSTED"
        _assert_state(settlement, item, stock=stock, reserved="0", used=used, returned=returned)
        assert _held(settlement) == 0
        holds = db.session.query(ServiceOrderPartReservation).filter_by(service_order_id=item.service_order_id).all()
        assert all(not row.is_active and row.status == "RELEASED" and row.quantity == 0 for row in holds)
        movement = db.session.query(CatalogStockMovement).filter_by(movement_type="ISSUE").one()
        assert movement.movement_type == "ISSUE"
        assert movement.reference_type == "STOCK_ISSUE"
        assert movement.reference_id == issue.issue_number
        assert movement.quantity == Decimal(used)
        assert movement.stock_before == Decimal("10")
        assert movement.stock_after == Decimal(stock)


def test_default_add_reserves_without_reducing_physical_stock(app, settlement):
    with app.app_context():
        item = _add(settlement)
        _assert_state(settlement, item, stock="10", reserved="5", used="0", returned="0")
        assert _held(settlement) == Decimal("5")  # Item + legacy hold must not be counted twice.
        assert db.session.query(StockIssue).count() == 0


@pytest.mark.parametrize("attach_other_order", [False, True], ids=["manual-rw", "other-order-rw"])
def test_ordinary_rw_cannot_spend_another_orders_hold(app, settlement, attach_other_order):
    with app.app_context():
        item = _add(settlement, "8")
        issue = StockIssueService().create_issue(
            items=[{"inventory_item_id": settlement.part_id, "quantity": "3"}],
            **_scope(settlement),
            actor=settlement.warehouse,
            service_order_id=settlement.other_order_id if attach_other_order else None,
        )
        with pytest.raises(StockIssueValidationError, match="Niewystarczająca dostępność"):
            _post(settlement, issue)
        db.session.refresh(issue)
        assert issue.status == "DRAFT"
        _assert_state(settlement, item, stock="10", reserved="8", used="0", returned="0")
        assert _held(settlement) == Decimal("8")
        assert db.session.query(CatalogStockMovement).count() == 0
        assert db.session.query(AuditLog).filter_by(action="STOCK_ISSUE").count() == 0


def test_second_order_reserves_only_available_stock_and_creates_shortage(app, settlement):
    with app.app_context():
        first = _add(settlement, "8")
        second = _add(settlement, "5", order_id=settlement.other_order_id)
        _assert_state(settlement, first, stock="10", reserved="8", used="0", returned="0")
        _assert_state(settlement, second, stock="10", reserved="2", used="0", returned="0")
        assert _held(settlement) == Decimal("10")
        demand = db.session.query(PartDemand).one()
        assert demand.service_order_id == settlement.other_order_id
        assert demand.service_order_item_id == second.id
        assert demand.inventory_item_id == settlement.part_id
        assert demand.requested_quantity == Decimal("5")
        assert demand.missing_quantity == Decimal("3")
        assert demand.status == "TO_ORDER"
        assert demand.company_id == settlement.company_id
        assert demand.branch_id == settlement.branch_id


def test_posting_same_rw_twice_does_not_repeat_stock_or_settlement(app, settlement):
    with app.app_context():
        item = _add(settlement)
        issue = _use(settlement, item)
        _post(settlement, issue)
        version = item.version
        _post(settlement, issue)
        _assert_state(settlement, item, stock="7", reserved="0", used="3", returned="2")
        assert item.version == version
        assert db.session.query(StockIssue).count() == 1
        assert db.session.query(StockIssueItem).count() == 1
        assert db.session.query(CatalogStockMovement).filter_by(movement_type="ISSUE").count() == 1
        assert db.session.query(AuditLog).filter_by(action="STOCK_ISSUE", object_id=str(issue.id)).count() == 1


def test_same_stale_version_cannot_create_second_rw(app, settlement):
    with app.app_context():
        item = _add(settlement)
        stale_version = item.version
        issue = _use(settlement, item, expected_version=stale_version)
        with pytest.raises(ServiceOrderItemValidationError, match="Pozycja została zmieniona"):
            _use(settlement, item, expected_version=stale_version)
        assert db.session.query(StockIssue).count() == 1
        assert db.session.query(StockIssueItem).count() == 1
        assert db.session.get(StockIssue, issue.id).status == "DRAFT"
        _assert_state(settlement, item, stock="10", reserved="5", used="0", returned="0")


def test_current_version_retry_reuses_existing_draft(app, settlement):
    with app.app_context():
        item = _add(settlement)
        issue = _use(settlement, item)
        version = item.version
        retry = _use(settlement, item)
        assert retry.id == issue.id
        db.session.refresh(item)
        assert item.version == version
        assert db.session.query(StockIssue).count() == 1
        _post(settlement, retry)
        _assert_state(settlement, item, stock="7", reserved="0", used="3", returned="2")


def test_release_changes_holds_not_physical_stock_and_rejects_stale_retry(app, settlement):
    with app.app_context():
        item = _add(settlement)
        stale_version = item.version
        _return(settlement, item, expected_version=stale_version, reserve=False)
        _assert_state(settlement, item, stock="10", reserved="3", used="0", returned="2")
        assert _held(settlement) == Decimal("3")
        movement = db.session.query(CatalogStockMovement).one()
        assert movement.movement_type == "RELEASE"
        assert movement.quantity == Decimal("2")
        assert movement.stock_before == movement.stock_after == Decimal("10")
        with pytest.raises(ServiceOrderItemValidationError, match="Pozycja została zmieniona"):
            _return(settlement, item, expected_version=stale_version, reserve=False)
        _assert_state(settlement, item, stock="10", reserved="3", used="0", returned="2")
        assert db.session.query(CatalogStockMovement).count() == 1
        assert db.session.query(StockIssue).count() == 0


def test_reserve_operation_on_direct_item_can_later_be_settled(app, settlement):
    with app.app_context():
        item = _add(settlement, reserve=False)
        _return(settlement, item, "5", reserve=True)
        _assert_state(settlement, item, stock="10", reserved="5", used="0", returned="0")
        assert _held(settlement) == Decimal("5")
        _post(settlement, _use(settlement, item))
        _assert_state(settlement, item, stock="7", reserved="0", used="3", returned="2")


@pytest.mark.parametrize("reserve,quantity", [(False, "6"), (True, "6")], ids=["over-release", "over-reserve"])
def test_invalid_hold_changes_roll_back_version_and_stock(app, settlement, reserve, quantity):
    with app.app_context():
        item = _add(settlement)
        version = item.version
        with pytest.raises(ServiceOrderItemValidationError):
            _return(settlement, item, quantity, reserve=reserve)
        _assert_state(settlement, item, stock="10", reserved="5", used="0", returned="0")
        assert item.version == version
        assert _held(settlement) == Decimal("5")
        assert db.session.query(CatalogStockMovement).count() == 0


@pytest.mark.parametrize("reserve", [False, True], ids=["release", "reserve"])
def test_pending_rw_blocks_hold_changes(app, settlement, reserve):
    with app.app_context():
        item = _add(settlement)
        issue = _use(settlement, item)
        version = item.version
        with pytest.raises(ServiceOrderItemValidationError, match="roboczy RW"):
            _return(settlement, item, "1", reserve=reserve)
        _assert_state(settlement, item, stock="10", reserved="5", used="0", returned="0")
        assert item.version == version
        _post(settlement, issue)
        _assert_state(settlement, item, stock="7", reserved="0", used="3", returned="2")


@pytest.mark.parametrize("reserve", [False, True], ids=["direct", "reserved"])
def test_fractional_material_settlement_uses_rw(app, settlement, reserve):
    with app.app_context():
        item = _add(settlement, "1.750", item_type="MATERIAL", reserve=reserve)
        issue = _use(settlement, item, "1.125")
        assert issue.status == "DRAFT"
        assert issue.items[0].material_id == settlement.material_id
        assert issue.items[0].inventory_item_id is None
        assert issue.items[0].quantity_issued == Decimal("1.125")
        held = "1.750" if reserve else "0"
        _assert_state(settlement, item, stock="5", reserved=held, used="0", returned="0")
        assert _held(settlement, "MATERIAL") == Decimal(held)
        _post(settlement, issue)
        _assert_state(
            settlement, item, stock="3.875", reserved="0", used="1.125",
            returned="0.625" if reserve else "0",
        )
        assert _held(settlement, "MATERIAL") == 0
        movement = db.session.query(CatalogStockMovement).filter_by(movement_type="ISSUE").one()
        assert movement.item_type == "MATERIAL"
        assert movement.movement_type == "ISSUE"
        assert movement.quantity == Decimal("1.125")
        assert movement.stock_before == Decimal("5")
        assert movement.stock_after == Decimal("3.875")


@pytest.mark.parametrize("operation", ["add", "use", "return"])
@pytest.mark.parametrize("scope_name", ["company", "branch"])
def test_item_services_reject_wrong_tenant_or_branch(app, settlement, operation, scope_name):
    with app.app_context():
        item = _add(settlement)
        scope = {f"{scope_name}_id": getattr(settlement, f"other_{scope_name}_id")}
        version = item.version
        with pytest.raises(ServiceOrderItemNotFoundError):
            if operation == "add":
                _add(settlement, **scope)
            elif operation == "use":
                _use(settlement, item, **scope)
            else:
                _return(settlement, item, **scope)
        _assert_state(settlement, item, stock="10", reserved="5", used="0", returned="0")
        assert item.version == version
        assert db.session.query(ServiceOrderItem).count() == 1
        assert db.session.query(StockIssue).count() == 0


@pytest.mark.parametrize("scope_name", ["company", "branch"])
def test_rw_post_rejects_wrong_tenant_or_branch(app, settlement, scope_name):
    with app.app_context():
        item = _add(settlement)
        issue = _use(settlement, item)
        scope = {f"{scope_name}_id": getattr(settlement, f"other_{scope_name}_id")}
        with pytest.raises(StockIssueNotFoundError):
            _post(settlement, issue, **scope)
        db.session.refresh(issue)
        assert issue.status == "DRAFT"
        _assert_state(settlement, item, stock="10", reserved="5", used="0", returned="0")
        assert db.session.query(CatalogStockMovement).count() == 0


@pytest.mark.parametrize("role", [None, "Mechanik", "Kierownik"])
def test_settlement_and_rw_post_require_warehouse_permission(app, settlement, role):
    with app.app_context():
        item = _add(settlement)
        denied = SimpleNamespace(
            id=settlement.user_id,
            roles=[] if role is None else [SimpleNamespace(name=role)],
        )
        version = item.version
        with pytest.raises(ServiceOrderItemValidationError, match="magazynier"):
            _use(settlement, item, actor=denied)
        assert item.version == version
        assert db.session.query(StockIssue).count() == 0
        issue = _use(settlement, item)
        with pytest.raises(StockIssuePermissionError):
            _post(settlement, issue, actor=denied)
        _assert_state(settlement, item, stock="10", reserved="5", used="0", returned="0")
        assert issue.status == "DRAFT"


def test_settlement_requires_actor(app, settlement):
    with app.app_context():
        item = _add(settlement)
        with pytest.raises(ServiceOrderItemValidationError, match="Brak użytkownika"):
            _use(settlement, item, actor=None)
        assert db.session.query(StockIssue).count() == 0


@pytest.mark.parametrize("operation", ["add", "use", "return"])
def test_http_csrf_rejects_missing_token_then_accepts_session_token(auth_client, app, settlement, operation):
    app.config["WTF_CSRF_ENABLED"] = True
    with app.app_context():
        item = _add(settlement) if operation != "add" else None
        item_id = item.id if item is not None else None
        version = item.version if item is not None else None
    if operation == "add":
        url = f"/orders/{settlement.order_id}/items"
        payload = {
            "item_type": "PART", "item_id": str(settlement.part_id),
            "quantity": "5", "allocation_mode": "direct",
            "unit_price_net": "20.00", "discount_percent": "0",
        }
    else:
        url = f"/orders/{settlement.order_id}/items/{item_id}/{operation}"
        payload = {
            "item_id": str(item_id), "version": str(version), "quantity": "2",
            "operation": "release", f"submit_{operation}": "1",
        }

    rejected = auth_client.post(url, data=payload)
    assert rejected.status_code == 400
    assert rejected.get_json()["ok"] is False
    with app.app_context():
        assert db.session.query(StockIssue).count() == 0
        assert db.session.query(CatalogStockMovement).count() == 0
        if item_id is None:
            assert db.session.query(ServiceOrderItem).count() == 0
        else:
            unchanged = db.session.get(ServiceOrderItem, item_id)
            _assert_state(settlement, unchanged, stock="10", reserved="5", used="0", returned="0")
            assert unchanged.version == version

    token_response = auth_client.get("/_test/order-parts/csrf")
    assert token_response.status_code == 200
    payload["csrf_token"] = token_response.get_json()["csrf_token"]
    accepted = auth_client.post(url, data=payload)
    assert accepted.status_code == (302 if operation == "use" else 200)
    if operation != "use":
        assert accepted.get_json()["ok"] is True
    with app.app_context():
        saved = db.session.query(ServiceOrderItem).one()
        if operation == "add":
            _assert_state(settlement, saved, stock="10", reserved="0", used="0", returned="0")
        elif operation == "return":
            _assert_state(settlement, saved, stock="10", reserved="3", used="0", returned="2")
        else:
            issue = db.session.query(StockIssue).one()
            assert issue.status == "DRAFT"
            assert accepted.headers["Location"].endswith(f"/stock-issues/{issue.id}")
            _assert_state(settlement, saved, stock="10", reserved="5", used="0", returned="0")


@pytest.mark.parametrize("operation", ["add", "use", "return"])
def test_http_without_allowed_role_is_forbidden_even_with_csrf(auth_client, app, settlement, operation):
    app.config["WTF_CSRF_ENABLED"] = True
    with app.app_context():
        item = _add(settlement)
        item_id, version = item.id, item.version
        db.session.query(UserRole).filter_by(user_id=settlement.user_id).delete()
        db.session.commit()
    token = auth_client.get("/_test/order-parts/csrf").get_json()["csrf_token"]
    url = f"/orders/{settlement.order_id}/items"
    if operation != "add":
        url += f"/{item_id}/{operation}"
    response = auth_client.post(url, data={
        "csrf_token": token, "item_type": "PART", "item_id": str(settlement.part_id),
        "quantity": "1", "version": str(version), "operation": "release",
    })
    assert response.status_code == 403
    with app.app_context():
        item = db.session.get(ServiceOrderItem, item_id)
        _assert_state(settlement, item, stock="10", reserved="5", used="0", returned="0")
        assert item.version == version
        assert db.session.query(ServiceOrderItem).count() == 1
        assert db.session.query(StockIssue).count() == 0
        assert db.session.query(CatalogStockMovement).count() == 0


def test_pz_from_shortage_requires_explicit_reservation_and_rw_settlement(app, settlement):
    with app.app_context():
        part = db.session.get(CatalogPart, settlement.part_id)
        part.current_stock = 0
        supplier = CatalogSupplier(
            code="SET-PZ-SUP", name="Settlement PZ supplier",
            company_id=settlement.company_id, branch_id=settlement.branch_id,
            is_active=True,
        )
        db.session.add(supplier)
        db.session.commit()

        item = _add(settlement, "5")
        item_id, initial_version = item.id, item.version
        _assert_state(settlement, item, stock="0", reserved="0", used="0", returned="0")
        assert _held(settlement) == 0
        demand = db.session.query(PartDemand).one()
        assert demand.service_order_item_id == item_id
        assert demand.service_order_id == settlement.order_id
        assert demand.inventory_item_id == settlement.part_id
        assert demand.requested_quantity == Decimal("5")
        assert demand.missing_quantity == Decimal("5")
        assert demand.reserved_quantity == 0
        assert demand.status == "TO_ORDER"

        purchases = PurchaseOrderService()
        po = purchases.create_from_demands(
            demand_ids=[demand.id], supplier_id=supplier.id,
            **_scope(settlement), actor=settlement.warehouse,
        )
        assert po.status == "DRAFT"
        assert len(po.items) == 1
        po_item = po.items[0]
        assert po_item.part_id == settlement.part_id
        assert po_item.quantity_ordered == Decimal("5")
        link = db.session.query(PurchaseOrderDemandLink).one()
        assert link.purchase_order_item_id == po_item.id
        assert link.part_demand_id == demand.id
        assert link.allocated_quantity == Decimal("5")
        assert link.received_quantity == 0
        po = purchases.update_status(
            order_id=po.id, status="SENT", **_scope(settlement),
            actor=settlement.warehouse,
        )
        assert po.status == "SENT"
        manager = SimpleNamespace(
            id=settlement.user_id, roles=[SimpleNamespace(name="Kierownik")],
        )
        po = purchases.update_status(
            order_id=po.id, status="CONFIRMED", **_scope(settlement), actor=manager,
        )
        assert po.status == "CONFIRMED"
        db.session.refresh(demand)
        assert demand.status == "IN_PURCHASE"

        receipts = GoodsReceiptService()
        receipt = receipts.create_receipt(
            purchase_order_id=po.id,
            items=[{
                "purchase_order_item_id": po_item.id,
                "quantity_received": "5", "demand_id": demand.id,
            }],
            **_scope(settlement), actor=settlement.warehouse,
        )
        assert receipt.status == "DRAFT"
        _assert_state(settlement, item, stock="0", reserved="0", used="0", returned="0")
        assert db.session.query(CatalogStockMovement).count() == 0
        receipt = receipts.accept_receipt(
            receipt_id=receipt.id, **_scope(settlement), actor=settlement.warehouse,
        )
        assert receipt.status == "POSTED"
        _assert_state(settlement, item, stock="5", reserved="0", used="0", returned="0")
        assert item.version == initial_version
        assert _held(settlement) == 0
        assert db.session.query(ServiceOrderPartReservation).count() == 0
        assert db.session.query(StockIssue).count() == 0
        assert db.session.query(StockIssueItem).count() == 0
        db.session.refresh(demand)
        assert demand.status == "IN_PURCHASE"
        assert demand.reserved_quantity == 0
        assert demand.missing_quantity == Decimal("5")
        db.session.refresh(po)
        db.session.refresh(po_item)
        db.session.refresh(link)
        assert po.status == "COMPLETED"
        assert po_item.quantity_received == Decimal("5")
        assert link.received_quantity == Decimal("5")
        receipt_movement = db.session.query(CatalogStockMovement).one()
        assert receipt_movement.movement_type == "RECEIPT"
        assert receipt_movement.reference_type == "GOODS_RECEIPT"
        assert receipt_movement.reference_id == receipt.receipt_number
        assert receipt_movement.quantity == Decimal("5")
        assert receipt_movement.stock_before == 0
        assert receipt_movement.stock_after == Decimal("5")

        # Reserve the existing shortage item, not a duplicate order line.
        item = _return(settlement, item, "5", reserve=True, expected_version=initial_version)
        assert item.id == item_id
        assert item.version == initial_version + 1
        assert item.quantity == Decimal("5")
        assert db.session.query(ServiceOrderItem).count() == 1
        _assert_state(settlement, item, stock="5", reserved="5", used="0", returned="0")
        assert _held(settlement) == Decimal("5")
        hold = db.session.query(ServiceOrderPartReservation).one()
        assert hold.service_order_id == settlement.order_id
        assert hold.part_id == settlement.part_id
        assert hold.quantity == Decimal("5")
        assert hold.status == "RESERVED" and hold.is_active
        assert db.session.query(CatalogStockMovement).count() == 1

        issue = _use(settlement, item, "3", expected_version=item.version)
        assert issue.status == "DRAFT"
        assert issue.items[0].service_order_item_id == item_id
        assert issue.items[0].quantity_issued == Decimal("3")
        _assert_state(settlement, item, stock="5", reserved="5", used="0", returned="0")
        assert _held(settlement) == Decimal("5")
        assert db.session.query(CatalogStockMovement).count() == 1

        posted = _post(settlement, issue)
        assert posted.status == "POSTED"
        _assert_state(settlement, item, stock="2", reserved="0", used="3", returned="2")
        assert _held(settlement) == 0
        db.session.refresh(hold)
        assert hold.quantity == 0
        assert hold.status == "RELEASED" and not hold.is_active
        assert db.session.query(ServiceOrderItem).count() == 1
        assert db.session.query(CatalogStockMovement).filter_by(movement_type="ISSUE").count() == 1
        issue_movement = db.session.query(CatalogStockMovement).filter_by(movement_type="ISSUE").one()
        assert issue_movement.reference_type == "STOCK_ISSUE"
        assert issue_movement.reference_id == issue.issue_number
        assert issue_movement.quantity == Decimal("3")
        assert issue_movement.stock_before == Decimal("5")
        assert issue_movement.stock_after == Decimal("2")