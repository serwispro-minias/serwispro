"""Demand allocation regressions against the settlement fixture's isolated SQLite DB.

Historical corruption is deliberately inserted directly; valid demands always go
through PartDemandService. No production connection or stock adjustment API is used.
"""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.catalog_material import CatalogMaterial
from app.models.catalog_part import CatalogPart
from app.models.catalog_stock_movement import CatalogStockMovement
from app.models.inventory_reservation import InventoryReservation
from app.models.part_demand import PartDemand
from app.models.service_order import ServiceOrder
from app.models.service_order_item import ServiceOrderItem
from app.models.service_order_part_reservation import ServiceOrderPartReservation
from app.models.stock_issue import StockIssue
from app.models.stock_issue_item import StockIssueItem
from app.orders.item_service import ServiceOrderItemValidationError
from app.part_demands.exceptions import PartDemandValidationError
from app.part_demands.service import PartDemandService
from app.stock_issues.exceptions import StockIssueValidationError
from tests.test_order_parts_settlement import (
    _add,
    _post,
    _return,
    _scope,
    _use,
    app,
    settlement,
)


def _demand_scope(data):
    scope = _scope(data)
    return {
        "company_id": scope["company_id"],
        "branch_scope_id": scope["branch_id"],
        "actor": data.warehouse,
    }


def _payload(data, item=None, **overrides):
    payload = {
        "service_order_id": data.order_id,
        "service_order_item_id": item.id if item is not None else None,
        "inventory_item_id": data.part_id,
        "requested_quantity": "5",
        "reserved_quantity": "0",
        "status": "TO_ORDER",
        "priority": "NORMAL",
        "expected_date": None,
        "notes": "Consistency regression",
    }
    payload.update(overrides)
    return payload


def _create_demand(data, item=None, **overrides):
    return PartDemandService().create_demand(
        data=_payload(data, item, **overrides), **_demand_scope(data)
    )


def _snapshot():
    """Read every column, including versions/audit fields, bypassing ORM caches.

    Flush first so an uncommitted mutation is not hidden by a read or by a test
    rollback. Callers commit their setup before taking the baseline.
    """
    db.session.flush()
    db.session.expire_all()
    models = (
        CatalogPart, CatalogMaterial, ServiceOrder, ServiceOrderItem,
        ServiceOrderPartReservation, InventoryReservation, PartDemand,
        StockIssue, StockIssueItem, CatalogStockMovement, AuditLog,
    )
    return {
        model.__tablename__: tuple(
            tuple(row) for row in db.session.execute(
                select(table).order_by(table.c.id)
            )
        )
        for model in models
        for table in (db.Model.metadata.tables[model.__tablename__],)
    }


def _part(data):
    part = db.session.get(CatalogPart, data.part_id)
    assert part is not None
    return part


def _other_part(data):
    original = _part(data)
    part = CatalogPart(**{
        "code": "CONSISTENCY-OTHER", "name": "Different consistency part",
        "category_id": original.category_id, "vat_id": original.vat_id,
        "current_stock": 10, "purchase_price_net": Decimal("10"),
        "sale_price_net": Decimal("20"), **_scope(data),
    })
    db.session.add(part)
    db.session.commit()
    return part


def test_item_quantity_alone_is_not_reservation_evidence(app, settlement):
    with app.app_context():
        item = _add(settlement, reserve=False)
        item.reserved_quantity = Decimal("5")
        db.session.commit()
        before = _snapshot()
        with pytest.raises(PartDemandValidationError, match="potwierdzenia"):
            _create_demand(settlement, item, reserved_quantity="5")
        assert _snapshot() == before


def test_genuine_excess_reservation_is_not_rejected_by_requested_limit(app, settlement):
    with app.app_context():
        item = _add(settlement, "5")
        demand = _create_demand(settlement, item, requested_quantity="3", reserved_quantity="5", status="DELIVERED")
        assert demand.reserved_quantity == 5
        assert demand.missing_quantity == 0
        assert _part(settlement).current_stock == 10


def test_legacy_physical_reservation_requires_reconciliation(app, settlement):
    with app.app_context():
        item = _add(settlement, "5")
        db.session.add(CatalogStockMovement(item_type="PART", part_id=settlement.part_id,
            service_order_id=settlement.order_id, movement_type="RESERVATION", quantity=1,
            stock_before=11, stock_after=10, reference_type="SERVICE_ORDER",
            reference_id=str(settlement.order_id), **_scope(settlement)))
        db.session.commit()
        before = _snapshot()
        with pytest.raises(PartDemandValidationError, match="Historyczna"):
            _create_demand(settlement, item, reserved_quantity="5")
        assert _snapshot() == before


def test_fulfillment_retry_cannot_repeat_completed_allocation(app, settlement):
    with app.app_context():
        demand = _create_demand(settlement)
        service = PartDemandService()
        service.fulfill_demand(demand_id=demand.id, reserve_quantity=Decimal("5"), **_demand_scope(settlement))
        before = _snapshot()
        with pytest.raises(PartDemandValidationError):
            service.fulfill_demand(demand_id=demand.id, reserve_quantity=Decimal("5"), **_demand_scope(settlement))
        assert _snapshot() == before


@pytest.mark.parametrize(
    "defect",
    ["order", "product", "company", "branch", "type", "inactive", "missing"],
)
def test_create_rejects_inconsistent_order_item(app, settlement, defect):
    with app.app_context():
        item = _add(settlement, reserve=False)
        item_id = item.id
        if defect == "order":
            item.service_order_id = settlement.other_order_id
        elif defect == "product":
            item.item_id = _other_part(settlement).id
        elif defect == "company":
            item.company_id = settlement.other_company_id
        elif defect == "branch":
            item.branch_id = settlement.other_branch_id
        elif defect == "type":
            item.item_type = "MATERIAL"
        elif defect == "inactive":
            item.is_active = False
        else:
            item_id = 999999
        db.session.commit()
        before = _snapshot()

        with pytest.raises(PartDemandValidationError):
            _create_demand(settlement, service_order_item_id=item_id)

        assert _snapshot() == before
        assert db.session.query(PartDemand).count() == 0


@pytest.mark.parametrize("entity", ["order", "product"])
@pytest.mark.parametrize("defect", ["company", "branch", "inactive", "missing"])
def test_create_rejects_invalid_order_or_product_context(app, settlement, entity, defect):
    with app.app_context():
        model = ServiceOrder if entity == "order" else CatalogPart
        row_id = settlement.order_id if entity == "order" else settlement.part_id
        row = db.session.get(model, row_id)
        assert row is not None
        overrides = {}
        if defect == "company":
            row.company_id = settlement.other_company_id
        elif defect == "branch":
            row.branch_id = settlement.other_branch_id
        elif defect == "inactive":
            row.is_active = False
        else:
            key = "service_order_id" if entity == "order" else "inventory_item_id"
            overrides[key] = 999999
        db.session.commit()
        before = _snapshot()

        with pytest.raises(PartDemandValidationError):
            _create_demand(settlement, **overrides)

        assert _snapshot() == before


@pytest.mark.parametrize("invent_item_reservation", [False, True], ids=["demand-only", "item-only"])
def test_manual_reserved_amount_requires_an_actual_hold(app, settlement, invent_item_reservation):
    with app.app_context():
        item = _add(settlement, reserve=False)
        if invent_item_reservation:
            item.reserved_quantity = Decimal("5")
            db.session.commit()
        before = _snapshot()

        with pytest.raises(PartDemandValidationError):
            _create_demand(
                settlement, item,
                reserved_quantity="0" if invent_item_reservation else "5",
            )

        assert _snapshot() == before
        assert db.session.query(ServiceOrderPartReservation).count() == 0


def test_create_rejects_multiple_active_demands_for_one_allocation(app, settlement):
    with app.app_context():
        item = _add(settlement, reserve=False)
        first = _create_demand(settlement, item)
        assert first.missing_quantity == Decimal("5")
        before = _snapshot()

        with pytest.raises(PartDemandValidationError, match="kilka zapotrzebowań"):
            _create_demand(settlement, item)

        assert _snapshot() == before
        assert db.session.query(PartDemand).count() == 1


@pytest.mark.parametrize("kind", ["legacy", "multiple-canonical"])
def test_create_rejects_ambiguous_hold_records(app, settlement, kind):
    with app.app_context():
        item = _add(settlement)
        if kind == "legacy":
            row = InventoryReservation(**{
                "service_order_id": settlement.order_id,
                "inventory_item_id": settlement.part_id, "quantity": Decimal("5"),
                "status": "RESERVED", "reserved_by": settlement.user_id,
                **_scope(settlement),
            })
        else:
            # Equal rows must not be silently collapsed using MAX(quantity).
            row = ServiceOrderPartReservation(**{
                "service_order_id": settlement.order_id, "part_id": settlement.part_id,
                "quantity": Decimal("5"), "status": "RESERVED", **_scope(settlement),
            })
        db.session.add(row)
        db.session.commit()
        before = _snapshot()

        with pytest.raises(PartDemandValidationError, match="alokacja rezerwacji"):
            _create_demand(settlement, item, reserved_quantity="5")

        assert _snapshot() == before


def test_create_requires_explicit_item_link_when_matching_item_exists(app, settlement):
    with app.app_context():
        _add(settlement, reserve=False)
        before = _snapshot()
        with pytest.raises(PartDemandValidationError, match="alokacja pozycji"):
            _create_demand(settlement)
        assert _snapshot() == before


@pytest.mark.parametrize("endpoint", ["create", "edit", "status"])
def test_http_rejects_delivered_without_real_allocation(app, auth_client, settlement, endpoint):
    # Do not keep an application context across client requests.
    with app.app_context():
        item = _add(settlement, reserve=False)
        payload = _payload(settlement, item, status="DELIVERED", expected_date="")
        if endpoint == "create":
            url = "/part-demands/new"
        else:
            demand = _create_demand(settlement, item)
            url = f"/part-demands/{demand.id}/{endpoint}"
        before = _snapshot()

    response = auth_client.post(url, data=payload)

    assert response.status_code == (302 if endpoint == "status" else 200)
    if endpoint == "status":
        with auth_client.session_transaction() as session:
            assert any(
                category == "danger" and "Zaspokojone wymaga braku 0" in message
                for category, message in session.get("_flashes", [])
            )
    else:
        # Rendering the form consumes flashed messages; inspect the response.
        assert "Zaspokojone wymaga braku 0" in response.get_data(as_text=True)
    with app.app_context():
        assert _snapshot() == before
        if endpoint == "create":
            assert db.session.query(PartDemand).count() == 0
        else:
            demand = db.session.query(PartDemand).one()
            assert demand.status == "TO_ORDER"
            assert demand.missing_quantity == Decimal("5")


def test_delivered_is_allowed_with_an_actual_linked_hold(app, settlement):
    with app.app_context():
        item = _add(settlement)
        demand = _create_demand(
            settlement, item, requested_quantity="5", reserved_quantity="5",
            status="DELIVERED",
        )
        db.session.expire_all()
        assert demand.service_order_item_id == item.id
        assert demand.status == "DELIVERED"
        assert demand.requested_quantity == Decimal("5")
        assert demand.reserved_quantity == Decimal("5")
        assert demand.missing_quantity == 0
        hold = db.session.query(ServiceOrderPartReservation).one()
        assert hold.quantity == item.reserved_quantity == Decimal("5")
        assert hold.status == "RESERVED" and hold.is_active
        assert _part(settlement).current_stock == 10


def test_release_five_reopens_delivered_demand_with_missing_five(app, settlement):
    with app.app_context():
        item = _add(settlement)
        demand = _create_demand(settlement, item, reserved_quantity="5", status="DELIVERED")
        _return(settlement, item, "5")
        db.session.expire_all()
        assert demand.status == "TO_ORDER"
        assert demand.reserved_quantity == item.reserved_quantity == 0
        assert demand.missing_quantity == Decimal("5")
        assert item.returned_quantity == Decimal("5")
        assert item.used_quantity == 0
        hold = db.session.query(ServiceOrderPartReservation).one()
        assert hold.quantity == 0 and not hold.is_active and hold.status == "RELEASED"
        assert _part(settlement).current_stock == 10
        assert db.session.query(CatalogStockMovement).one().movement_type == "RELEASE"


def test_use_three_releases_two_and_note_edit_keeps_missing_two(app, settlement):
    with app.app_context():
        item = _add(settlement)
        demand = _create_demand(settlement, item, reserved_quantity="5", status="DELIVERED")
        issue = _use(settlement, item, "3")
        assert issue.status == "DRAFT"
        assert demand.status == "DELIVERED"
        assert demand.reserved_quantity == Decimal("5")
        _post(settlement, issue)
        db.session.expire_all()
        assert issue.status == "POSTED"
        assert item.used_quantity == Decimal("3")
        assert item.returned_quantity == Decimal("2")
        assert item.reserved_quantity == demand.reserved_quantity == 0
        assert demand.missing_quantity == Decimal("2")
        assert demand.status == "TO_ORDER"
        assert _part(settlement).current_stock == 7
        hold = db.session.query(ServiceOrderPartReservation).one()
        assert hold.quantity == 0 and not hold.is_active and hold.status == "RELEASED"
        release = db.session.query(CatalogStockMovement).filter_by(movement_type="RELEASE").one()
        assert release.quantity == Decimal("2")
        before = _snapshot()

        updated = PartDemandService().update_demand(
            demand_id=demand.id,
            data=_payload(settlement, item, notes="Only the note changed"),
            **_demand_scope(settlement),
        )

        assert updated.notes == "Only the note changed"
        assert updated.missing_quantity == Decimal("2")
        assert updated.reserved_quantity == 0
        assert updated.status == "TO_ORDER"
        after = _snapshot()
        assert {key: value for key, value in after.items() if key != "part_demands"} == {
            key: value for key, value in before.items() if key != "part_demands"
        }


def _historical_wrong_backlink(data, item, defect):
    """Bypass validation only to model already-persisted historical corruption."""
    payload = _payload(data, item, reserved_quantity=Decimal("5"))
    payload.update(company_id=data.company_id, branch_id=data.branch_id, missing_quantity=0)
    if defect == "order":
        payload["service_order_id"] = data.other_order_id
    elif defect == "product":
        payload["inventory_item_id"] = _other_part(data).id
    elif defect == "company":
        payload["company_id"] = data.other_company_id
    else:
        payload["branch_id"] = data.other_branch_id
    row = PartDemand(**payload)
    db.session.add(row)
    db.session.commit()
    return row


@pytest.mark.parametrize("defect", ["order", "product", "company", "branch"])
@pytest.mark.parametrize("operation", ["return", "use", "post"])
def test_historical_wrong_backlinks_fail_without_mutating_key_rows(
    app, settlement, defect, operation,
):
    with app.app_context():
        item = _add(settlement)
        # A posting test needs an otherwise valid, already-committed draft.
        issue = _use(settlement, item, "3") if operation == "post" else None
        _historical_wrong_backlink(settlement, item, defect)
        before = _snapshot()
        error = StockIssueValidationError if operation == "post" else ServiceOrderItemValidationError

        with pytest.raises(error):
            if operation == "return":
                _return(settlement, item, "2")
            elif operation == "use":
                _use(settlement, item, "3")
            else:
                _post(settlement, issue)

        assert _snapshot() == before


def _shortage_then_restock_for_test(data):
    # Direct stock assignment is fixture setup, not a production correction/PZ.
    part = _part(data)
    part.current_stock = 0
    db.session.commit()
    item = _add(data)
    demand = db.session.query(PartDemand).one()
    assert demand.service_order_item_id == item.id
    assert demand.reserved_quantity == item.reserved_quantity == 0
    assert demand.missing_quantity == Decimal("5")
    assert demand.status == "TO_ORDER"
    part.current_stock = 5
    db.session.commit()
    return item, demand


def test_fulfill_atomic_rolls_back_failure_after_reservation_writes(app, settlement, monkeypatch):
    with app.app_context():
        item, demand = _shortage_then_restock_for_test(settlement)
        service = PartDemandService()
        before = _snapshot()
        demand_version, item_version = demand.version, item.version
        reached_update = []

        def fail_after_reservation(row, payload):
            # Prove the failure occurs after real writes, not at an early guard.
            db.session.flush()
            hold = db.session.query(ServiceOrderPartReservation).one()
            movement = db.session.query(CatalogStockMovement).one()
            assert hold.quantity == Decimal("5") and hold.status == "RESERVED"
            assert movement.movement_type == "RESERVATION"
            assert movement.quantity == Decimal("5")
            assert item.reserved_quantity == Decimal("5")
            assert item.version == item_version + 1
            assert row.version == demand_version + 1
            assert payload["reserved_quantity"] == Decimal("5")
            assert payload["missing_quantity"] == 0
            reached_update.append(row.id)
            raise RuntimeError("injected demand update failure")

        monkeypatch.setattr(service.repository, "update", fail_after_reservation)
        with pytest.raises(RuntimeError, match="injected demand update failure"):
            service.fulfill_demand(
                demand_id=demand.id, reserve_quantity=Decimal("5"),
                **_demand_scope(settlement),
            )

        assert reached_update == [demand.id]
        assert _snapshot() == before
        assert item.version == item_version
        assert demand.version == demand_version


def test_fulfill_from_shortage_reserves_actual_stock_and_satisfies_demand(app, settlement):
    with app.app_context():
        item, demand = _shortage_then_restock_for_test(settlement)
        demand_version, item_version = demand.version, item.version
        fulfilled = PartDemandService().fulfill_demand(
            demand_id=demand.id, reserve_quantity=Decimal("5"),
            **_demand_scope(settlement),
        )
        db.session.expire_all()
        assert fulfilled.id == demand.id
        assert fulfilled.status == "DELIVERED"
        assert fulfilled.reserved_quantity == item.reserved_quantity == Decimal("5")
        assert fulfilled.missing_quantity == 0
        assert fulfilled.version == demand_version + 1
        assert item.version == item_version + 1
        assert item.used_quantity == item.returned_quantity == 0
        assert _part(settlement).current_stock == 5
        hold = db.session.query(ServiceOrderPartReservation).one()
        assert hold.service_order_id == settlement.order_id
        assert hold.part_id == settlement.part_id
        assert hold.company_id == settlement.company_id
        assert hold.branch_id == settlement.branch_id
        assert hold.quantity == Decimal("5") and hold.status == "RESERVED" and hold.is_active
        movement = db.session.query(CatalogStockMovement).one()
        assert movement.movement_type == "RESERVATION"
        assert movement.quantity == Decimal("5")
        assert movement.stock_before == movement.stock_after == Decimal("5")
        assert db.session.query(InventoryReservation).count() == 0
        assert db.session.query(StockIssue).count() == 0
        assert db.session.query(StockIssueItem).count() == 0