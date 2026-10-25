"""P7/P8 stock entry-point regressions using only the isolated SQLite fixtures.

Import the module-local app fixture explicitly: the shared conftest app does not
provide the same pre-initialization database isolation. No application is built
and no database is opened during collection of this module.
"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.catalog.exceptions import CatalogValidationError
from app.catalog.repository import StockRepository
from app.catalog.service import CatalogService
from app.extensions import db
from app.inventory.reservation_service import reserved_stock
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
from app.models.user import User
from app.models.user_role import UserRole
from app.orders import routes as order_routes
from tests.test_order_parts_settlement import (
    _add,
    _post,
    _return,
    _scope,
    _use,
    app,
    settlement,
)

BLOCKED_MOVEMENTS = (
    "ISSUE", "RESERVATION", "RELEASE", "AUTO_ISSUE", "SALE", "RECEIPT",
    "OPENING_BALANCE",
)
PRODUCT_TYPES = ("part", "material")


def test_adjustment_rolls_back_if_history_write_fails(app, settlement, monkeypatch):
    with app.app_context():
        service = CatalogService()
        before = _state(settlement)
        actor = db.session.get(User, settlement.user_id)
        def fail_history(payload):
            raise RuntimeError("history unavailable")
        monkeypatch.setattr(service.stock, "create_movement", fail_history)
        with pytest.raises(RuntimeError, match="history unavailable"):
            service.add_stock_movement(entity_type="part", entity_id=settlement.part_id,
                movement_type="ADJUSTMENT", quantity=Decimal("8"),
                reference_type="ADJUSTMENT", reference_id="SEC-ROLLBACK",
                note="Rollback test", user_id=settlement.user_id,
                **_scope(settlement), actor=actor)
        assert _state(settlement) == before


@pytest.mark.parametrize("movement", BLOCKED_MOVEMENTS)
def test_inventory_operation_cannot_bypass_rw(app, auth_client, settlement, movement):
    app.config["WTF_CSRF_ENABLED"] = True
    token = _token(auth_client)
    before = _snapshot(app, settlement)
    response = auth_client.post(f"/inventory/{settlement.part_id}/operations", data={
        "csrf_token": token, "operation_type": movement, "quantity": "1",
        "document_number": "SEC-LEGACY", "comment": "Must not bypass RW",
    })
    assert response.status_code == 302
    _assert_unchanged(app, settlement, before)


def test_inventory_correction_uses_shared_scoped_history(app, auth_client, settlement):
    app.config["WTF_CSRF_ENABLED"] = True
    token = _token(auth_client)
    response = auth_client.post(f"/inventory/{settlement.part_id}/operations", data={
        "csrf_token": token, "operation_type": "ADJUSTMENT", "quantity": "9",
        "document_number": "SEC-INVENTORY", "comment": "Documented physical count",
    })
    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(CatalogPart, settlement.part_id).current_stock == 9
        row = db.session.query(CatalogStockMovement).one()
        assert (row.stock_before, row.stock_after) == (10, 9)
        assert row.reference_id == "SEC-INVENTORY"
        assert row.user_id == settlement.user_id
        assert db.session.query(StockIssue).count() == 0


@pytest.mark.parametrize("product_type", PRODUCT_TYPES)
def test_card_edit_cannot_change_stock(app, auth_client, settlement, product_type):
    app.config["WTF_CSRF_ENABLED"] = True
    token = _token(auth_client)
    with app.app_context():
        model, product_id = _product(settlement, product_type)
        product = db.session.get(model, product_id)
        payload = {"csrf_token": token, "code": product.code, "name": product.name,
            "current_stock": "1", "purchase_price_net": "10", "sale_price_net": "20"}
        if product_type == "part":
            payload.update(category_id=str(product.category_id), vat_id=str(product.vat_id))
        else:
            payload.update(unit="l", minimum_stock="1", default_usage_qty="1", vat_rate="23")
    before = _snapshot(app, settlement)
    response = auth_client.post(f"/catalog/{product_type}s/{product_id}/edit", data=payload)
    assert response.status_code == 200
    assert "Edycja kartoteki nie zmienia stanu" in response.get_data(as_text=True)
    _assert_unchanged(app, settlement, before)
    if product_type == "part":
        payload["is_active"] = "1"
        response = auth_client.post(f"/inventory/{product_id}/edit", data=payload)
        assert response.status_code == 200
        _assert_unchanged(app, settlement, before)


@pytest.mark.parametrize("field", ["csrf", "role", "branch", "company"])
def test_inventory_correction_rejects_invalid_access(app, auth_client, settlement, field):
    app.config["WTF_CSRF_ENABLED"] = True
    token = _token(auth_client)
    with app.app_context():
        if field == "role":
            db.session.query(UserRole).filter_by(user_id=settlement.user_id).delete()
        elif field in {"branch", "company"}:
            product = db.session.get(CatalogPart, settlement.part_id)
            setattr(product, f"{field}_id", getattr(settlement, f"other_{field}_id"))
        db.session.commit()
    before = _snapshot(app, settlement)
    response = auth_client.post(f"/inventory/{settlement.part_id}/operations", data={
        "csrf_token": token if field != "csrf" else "", "operation_type": "ADJUSTMENT",
        "quantity": "1", "document_number": "SEC-DENY", "comment": "Denied adjustment",
    })
    assert response.status_code == (403 if field == "role" else 302)
    _assert_unchanged(app, settlement, before)
STATE_MODELS = (
    CatalogPart, CatalogMaterial, ServiceOrder, ServiceOrderItem,
    ServiceOrderPartReservation, InventoryReservation, PartDemand,
    CatalogStockMovement, StockIssue, StockIssueItem, AuditLog,
)


def _product(data, product_type):
    if product_type == "part":
        return CatalogPart, data.part_id
    return CatalogMaterial, data.material_id


def _state(data):
    """Compare persisted rows, counts and effective holds, not cached objects."""
    db.session.expire_all()
    rows = {
        model.__tablename__: tuple(
            tuple(row)
            for row in db.session.query(*model.__table__.columns)
            .order_by(model.__table__.c.id).all()
        )
        for model in STATE_MODELS
    }
    return {
        "rows": rows,
        "counts": {table: len(values) for table, values in rows.items()},
        "stock": (
            Decimal(db.session.get(CatalogPart, data.part_id).current_stock),
            Decimal(db.session.get(CatalogMaterial, data.material_id).current_stock),
        ),
        "holds": tuple(
            reserved_stock(
                item_type=kind, item_id=product_id, company_id=data.company_id,
            )
            for kind, product_id in (
                ("PART", data.part_id), ("MATERIAL", data.material_id),
            )
        ),
    }


def _snapshot(test_app, data):
    with test_app.app_context():
        return _state(data)


def _assert_unchanged(test_app, data, before):
    assert _snapshot(test_app, data) == before


def _token(client):
    response = client.get("/_test/order-parts/csrf")
    assert response.status_code == 200
    return response.get_json()["csrf_token"]


def _movement_url(data, product_type):
    _, product_id = _product(data, product_type)
    return f"/catalog/{product_type}s/{product_id}/movements"


def _adjustment(token, **overrides):
    payload = {
        "csrf_token": token,
        "movement_type": "ADJUSTMENT",
        "quantity": "8",
        "reference_type": "ADJUSTMENT",
        "reference_id": "SEC-CORRECTION-1",
        "note": "Physical count reconciled by warehouse",
    }
    payload.update(overrides)
    return payload


def _readiness_url(data):
    return f"/orders/{data.order_id}/readiness/reserve"


def _line(part_id, **overrides):
    line = {
        "part_id": part_id, "required": "3", "available": "10",
        "reserved": "0",
    }
    line.update(overrides)
    return line


def _mock_readiness(monkeypatch, lines):
    build = Mock(return_value={"lines": lines})
    monkeypatch.setattr(order_routes.readiness_service, "build", build)
    return build


def _move_out_of_scope(entity, data, scope):
    if scope == "company":
        entity.company_id = data.other_company_id
    else:
        entity.branch_id = data.other_branch_id
    db.session.commit()


@pytest.fixture()
def protected_state(app, settlement):
    """Rejections must preserve existing holds and an existing draft RW too."""
    with app.app_context():
        item = _add(settlement, "2")
        _add(settlement, "2", item_type="MATERIAL")
        issue = _use(settlement, item, "1")
        assert issue.status == "DRAFT"
        state = _state(settlement)
        assert state["stock"] == (Decimal("10"), Decimal("5"))
        assert state["holds"] == (Decimal("2"), Decimal("2"))
        assert state["counts"][StockIssue.__tablename__] == 1
        assert state["counts"][StockIssueItem.__tablename__] == 1
        return state


@pytest.mark.parametrize("product_type", PRODUCT_TYPES)
@pytest.mark.parametrize("movement_type", BLOCKED_MOVEMENTS)
def test_catalog_http_blocks_non_adjustment_movements(
    app, auth_client, settlement, protected_state, product_type, movement_type,
):
    app.config["WTF_CSRF_ENABLED"] = True
    response = auth_client.post(
        _movement_url(settlement, product_type),
        data=_adjustment(_token(auth_client), movement_type=movement_type),
    )
    assert response.status_code == 302
    _assert_unchanged(app, settlement, protected_state)


@pytest.mark.parametrize("product_type", PRODUCT_TYPES)
def test_catalog_http_requires_warehouse_role(
    app, auth_client, settlement, protected_state, product_type,
):
    app.config["WTF_CSRF_ENABLED"] = True
    with app.app_context():
        db.session.query(UserRole).filter_by(user_id=settlement.user_id).delete()
        db.session.commit()
    response = auth_client.post(
        _movement_url(settlement, product_type),
        data=_adjustment(_token(auth_client)),
    )
    assert response.status_code == 403
    _assert_unchanged(app, settlement, protected_state)


@pytest.mark.parametrize("product_type", PRODUCT_TYPES)
@pytest.mark.parametrize("scope", ("company", "branch"))
def test_catalog_http_rejects_foreign_product(
    app, auth_client, settlement, protected_state, product_type, scope,
):
    app.config["WTF_CSRF_ENABLED"] = True
    with app.app_context():
        model, product_id = _product(settlement, product_type)
        _move_out_of_scope(db.session.get(model, product_id), settlement, scope)
    before = _snapshot(app, settlement)
    response = auth_client.post(
        _movement_url(settlement, product_type),
        data=_adjustment(_token(auth_client)),
    )
    assert response.status_code == 302
    _assert_unchanged(app, settlement, before)


@pytest.mark.parametrize("product_type", PRODUCT_TYPES)
@pytest.mark.parametrize("csrf", ("missing", "bad"))
def test_catalog_http_rejects_invalid_csrf(
    app, auth_client, settlement, protected_state, product_type, csrf,
):
    app.config["WTF_CSRF_ENABLED"] = True
    payload = _adjustment(_token(auth_client))
    if csrf == "missing":
        payload.pop("csrf_token")
    else:
        payload["csrf_token"] = "invalid-session-signature"
    response = auth_client.post(_movement_url(settlement, product_type), data=payload)
    assert response.status_code == 302
    _assert_unchanged(app, settlement, protected_state)


@pytest.mark.parametrize("product_type", PRODUCT_TYPES)
@pytest.mark.parametrize("field", ("reference_id", "note"))
def test_catalog_http_adjustment_requires_document_and_reason(
    app, auth_client, settlement, protected_state, product_type, field,
):
    app.config["WTF_CSRF_ENABLED"] = True
    payload = _adjustment(_token(auth_client))
    payload[field] = ""
    response = auth_client.post(_movement_url(settlement, product_type), data=payload)
    assert response.status_code == 302
    _assert_unchanged(app, settlement, protected_state)


@pytest.mark.parametrize(
    "product_type,quantity",
    (("part", "12"), ("part", "0"), ("material", "6.125"),
     ("material", "0"), ("material", "5")),
)
def test_catalog_http_adjustment_records_full_history(
    app, auth_client, settlement, product_type, quantity,
):
    app.config["WTF_CSRF_ENABLED"] = True
    before = _snapshot(app, settlement)
    response = auth_client.post(
        _movement_url(settlement, product_type),
        data=_adjustment(
            _token(auth_client), quantity=quantity,
            reference_type="UNTRUSTED", reference_id="  SEC-COUNT-1  ",
            note="  Verified physical count  ",
        ),
    )
    assert response.status_code == 302
    with app.app_context():
        after = _state(settlement)
        model, product_id = _product(settlement, product_type)
        assert Decimal(db.session.get(model, product_id).current_stock) == Decimal(quantity)
        movement = db.session.query(CatalogStockMovement).one()
        assert movement.item_type == product_type.upper()
        assert movement.part_id == (product_id if product_type == "part" else None)
        assert movement.material_id == (product_id if product_type == "material" else None)
        assert movement.movement_type == "ADJUSTMENT"
        assert movement.quantity == movement.stock_after == Decimal(quantity)
        assert movement.stock_before == Decimal("10" if product_type == "part" else "5")
        assert movement.reference_type == "ADJUSTMENT"
        assert movement.reference_id == "SEC-COUNT-1"
        assert movement.note == "Verified physical count"
        assert movement.company_id == settlement.company_id
        assert movement.branch_id == settlement.branch_id
        assert movement.user_id == movement.created_by == movement.updated_by == settlement.user_id
        assert movement.service_order_id is None
        assert movement.operation_at is not None
        assert after["holds"] == before["holds"] == (Decimal("0"), Decimal("0"))
        for table, rows in before["rows"].items():
            if table not in {model.__tablename__, CatalogStockMovement.__tablename__}:
                assert after["rows"][table] == rows
        assert after["counts"][StockIssue.__tablename__] == 0
        assert after["counts"][StockIssueItem.__tablename__] == 0
        assert after["counts"][CatalogStockMovement.__tablename__] == 1


@pytest.mark.parametrize("product_type", PRODUCT_TYPES)
def test_catalog_http_cannot_correct_below_existing_holds(
    app, auth_client, settlement, protected_state, product_type,
):
    app.config["WTF_CSRF_ENABLED"] = True
    response = auth_client.post(
        _movement_url(settlement, product_type),
        data=_adjustment(_token(auth_client), quantity="1"),
    )
    assert response.status_code == 302
    _assert_unchanged(app, settlement, protected_state)


@pytest.mark.parametrize("product_type", PRODUCT_TYPES)
@pytest.mark.parametrize("operation", ("create", "update"))
def test_catalog_card_service_cannot_write_physical_stock(
    app, settlement, protected_state, product_type, operation,
):
    with app.app_context():
        service = CatalogService()
        repository = service.parts if product_type == "part" else service.materials
        _, product_id = _product(settlement, product_type)
        with pytest.raises(CatalogValidationError):
            if operation == "create":
                service.create_entity(
                    repository,
                    {"code": "SEC-NEW", "name": "Must not exist", "current_stock": "1"},
                    **_scope(settlement),
                )
            else:
                service.update_entity(
                    repository, product_id,
                    {"name": "Must not change", "current_stock": "1"},
                    **_scope(settlement),
                )
        assert _state(settlement) == protected_state


@pytest.mark.parametrize("csrf", ("missing", "bad"))
def test_readiness_rejects_csrf_before_build(
    app, auth_client, settlement, protected_state, monkeypatch, csrf,
):
    app.config["WTF_CSRF_ENABLED"] = True
    build = _mock_readiness(monkeypatch, [_line(settlement.part_id)])
    token = _token(auth_client)
    payload = {} if csrf == "missing" else {"csrf_token": token + "tampered"}
    response = auth_client.post(_readiness_url(settlement), data=payload)
    assert response.status_code == 400
    assert response.get_json()["ok"] is False
    build.assert_not_called()
    _assert_unchanged(app, settlement, protected_state)


def test_readiness_requires_role_even_with_valid_csrf(
    app, auth_client, settlement, protected_state, monkeypatch,
):
    app.config["WTF_CSRF_ENABLED"] = True
    build = _mock_readiness(monkeypatch, [_line(settlement.part_id)])
    with app.app_context():
        db.session.query(UserRole).filter_by(user_id=settlement.user_id).delete()
        db.session.commit()
    response = auth_client.post(
        _readiness_url(settlement), data={"csrf_token": _token(auth_client)},
    )
    assert response.status_code == 403
    build.assert_not_called()
    _assert_unchanged(app, settlement, protected_state)


@pytest.mark.parametrize("scope", ("company", "branch"))
def test_readiness_scopes_order_before_build(
    app, auth_client, settlement, protected_state, monkeypatch, scope,
):
    app.config["WTF_CSRF_ENABLED"] = True
    build = _mock_readiness(monkeypatch, [_line(settlement.part_id)])
    with app.app_context():
        _move_out_of_scope(
            db.session.get(ServiceOrder, settlement.order_id), settlement, scope,
        )
    before = _snapshot(app, settlement)
    response = auth_client.post(
        _readiness_url(settlement), data={"csrf_token": _token(auth_client)},
    )
    assert response.status_code == 404
    build.assert_not_called()
    _assert_unchanged(app, settlement, before)


@pytest.mark.parametrize("scope", ("company", "branch"))
def test_readiness_rechecks_product_scope_from_mocked_lines(
    app, auth_client, settlement, protected_state, monkeypatch, scope,
):
    app.config["WTF_CSRF_ENABLED"] = True
    build = _mock_readiness(monkeypatch, [_line(settlement.part_id)])
    with app.app_context():
        _move_out_of_scope(
            db.session.get(CatalogPart, settlement.part_id), settlement, scope,
        )
    before = _snapshot(app, settlement)
    response = auth_client.post(
        _readiness_url(settlement), data={"csrf_token": _token(auth_client)},
    )
    assert response.status_code == 400
    assert response.get_json()["ok"] is False
    build.assert_called_once_with(order_id=settlement.order_id, **_scope(settlement))
    _assert_unchanged(app, settlement, before)


def test_readiness_reserves_through_catalog_without_changing_physical_stock(
    app, auth_client, settlement, monkeypatch,
):
    app.config["WTF_CSRF_ENABLED"] = True
    build = _mock_readiness(monkeypatch, [_line(settlement.part_id)])
    original = CatalogService.reserve_part_for_order
    calls = []

    def reserve(service, **kwargs):
        calls.append(kwargs)
        return original(service, **kwargs)

    monkeypatch.setattr(CatalogService, "reserve_part_for_order", reserve)
    before = _snapshot(app, settlement)
    response = auth_client.post(
        _readiness_url(settlement), data={"csrf_token": _token(auth_client)},
    )
    assert response.status_code == 200
    assert response.get_json()["ok"] is True
    assert response.get_json()["reserved_count"] == 1
    assert calls == [{
        "order_id": settlement.order_id, "part_id": settlement.part_id,
        "quantity": Decimal("3"), "user_id": settlement.user_id,
        **_scope(settlement), "commit": False,
    }]
    assert build.call_count == 2
    for call in build.call_args_list:
        assert call.kwargs == {"order_id": settlement.order_id, **_scope(settlement)}
    with app.app_context():
        after = _state(settlement)
        assert after["stock"] == before["stock"]
        assert after["holds"] == (Decimal("3"), Decimal("0"))
        hold = db.session.query(ServiceOrderPartReservation).one()
        assert hold.quantity == Decimal("3")
        assert hold.status == "RESERVED" and hold.is_active
        assert hold.service_order_id == settlement.order_id
        assert hold.part_id == settlement.part_id
        assert hold.company_id == settlement.company_id
        assert hold.branch_id == settlement.branch_id
        movement = db.session.query(CatalogStockMovement).one()
        assert movement.movement_type == "RESERVATION"
        assert movement.quantity == Decimal("3")
        assert movement.stock_before == movement.stock_after == Decimal("10")
        assert movement.service_order_id == settlement.order_id
        assert movement.part_id == settlement.part_id
        assert movement.reference_type == "SERVICE_ORDER"
        assert movement.reference_id == str(settlement.order_id)
        for table, rows in before["rows"].items():
            if table not in {
                ServiceOrderPartReservation.__tablename__, CatalogStockMovement.__tablename__,
            }:
                assert after["rows"][table] == rows
        assert after["counts"][ServiceOrderPartReservation.__tablename__] == 1
        assert after["counts"][CatalogStockMovement.__tablename__] == 1
        assert after["counts"][StockIssue.__tablename__] == 0
        assert after["counts"][StockIssueItem.__tablename__] == 0


@pytest.mark.parametrize("invalid", ("missing", "company", "branch"))
def test_readiness_rolls_back_first_valid_line_when_next_part_is_invalid(
    app, auth_client, settlement, protected_state, monkeypatch, invalid,
):
    app.config["WTF_CSRF_ENABLED"] = True
    with app.app_context():
        if invalid == "missing":
            invalid_id = 999999
            assert db.session.get(CatalogPart, invalid_id) is None
        else:
            source = db.session.get(CatalogPart, settlement.part_id)
            foreign = CatalogPart(
                code="SEC-FOREIGN", name="Foreign readiness product",
                category_id=source.category_id, vat_id=source.vat_id,
                current_stock=10, purchase_price_net=Decimal("10"),
                sale_price_net=Decimal("20"), company_id=settlement.company_id,
                branch_id=settlement.branch_id,
            )
            db.session.add(foreign)
            db.session.flush()
            invalid_id = foreign.id
            _move_out_of_scope(foreign, settlement, invalid)
    before = _snapshot(app, settlement)
    build = _mock_readiness(
        monkeypatch, [_line(settlement.part_id), _line(invalid_id)],
    )
    original = CatalogService.reserve_part_for_order
    calls = []

    def reserve(service, **kwargs):
        assert kwargs["commit"] is False
        calls.append(kwargs["part_id"])
        if len(calls) == 2:
            # Prove the first line really wrote, rather than failing early.
            assert reserved_stock(
                item_type="PART", item_id=settlement.part_id,
                company_id=settlement.company_id,
            ) == Decimal("5")
            assert db.session.query(CatalogStockMovement).filter_by(
                movement_type="RESERVATION", part_id=settlement.part_id,
            ).count() == 1
        return original(service, **kwargs)

    monkeypatch.setattr(CatalogService, "reserve_part_for_order", reserve)
    response = auth_client.post(
        _readiness_url(settlement), data={"csrf_token": _token(auth_client)},
    )
    assert response.status_code == 400
    assert response.get_json()["ok"] is False
    assert calls == [settlement.part_id, invalid_id]
    build.assert_called_once_with(order_id=settlement.order_id, **_scope(settlement))
    _assert_unchanged(app, settlement, before)


@pytest.mark.parametrize("product_type", PRODUCT_TYPES)
@pytest.mark.parametrize("movement_type", BLOCKED_MOVEMENTS)
def test_catalog_service_blocks_non_adjustment_without_mutation(
    app, settlement, protected_state, product_type, movement_type,
):
    with app.app_context():
        _, product_id = _product(settlement, product_type)
        actor = db.session.get(User, settlement.user_id)
        with pytest.raises(CatalogValidationError, match="wyłącznie"):
            CatalogService().add_stock_movement(
                entity_type=product_type, entity_id=product_id,
                movement_type=movement_type, quantity=Decimal("1"),
                reference_type="ADJUSTMENT", reference_id="SEC-DIRECT",
                note="Must not bypass stock documents", user_id=settlement.user_id,
                **_scope(settlement), actor=actor,
            )
        assert _state(settlement) == protected_state


@pytest.mark.parametrize("product_type", PRODUCT_TYPES)
@pytest.mark.parametrize("actor_kind", ("missing", "no-role", "company", "branch"))
def test_catalog_service_adjustment_requires_authorized_scoped_actor(
    app, settlement, protected_state, product_type, actor_kind,
):
    with app.app_context():
        _, product_id = _product(settlement, product_type)
        actor = SimpleNamespace(
            id=settlement.user_id, company_id=settlement.company_id,
            branch_id=settlement.branch_id,
            roles=[SimpleNamespace(name="Magazynier")],
        )
        if actor_kind == "missing":
            actor = None
        elif actor_kind == "no-role":
            actor.roles = []
        elif actor_kind == "company":
            actor.company_id = settlement.other_company_id
        else:
            actor.branch_id = settlement.other_branch_id
        with pytest.raises(CatalogValidationError):
            CatalogService().add_stock_movement(
                entity_type=product_type, entity_id=product_id,
                movement_type="ADJUSTMENT", quantity=Decimal("8"),
                reference_type="ADJUSTMENT", reference_id="SEC-ACTOR",
                note="Denied correction", user_id=settlement.user_id,
                **_scope(settlement), actor=actor,
            )
        assert _state(settlement) == protected_state


@pytest.mark.parametrize("product_type", PRODUCT_TYPES)
@pytest.mark.parametrize("movement_type", BLOCKED_MOVEMENTS)
def test_stock_repository_rejects_non_adjustment_without_mutation(
    app, settlement, protected_state, product_type, movement_type,
):
    with app.app_context():
        model, product_id = _product(settlement, product_type)
        repository = StockRepository()
        update = (
            repository.update_part_stock if product_type == "part"
            else repository.update_material_stock
        )
        with pytest.raises(CatalogValidationError, match="korekty"):
            update(
                db.session.get(model, product_id), quantity=Decimal("1"),
                movement_type=movement_type,
            )
        # No caller rollback: the repository guard itself must precede writes.
        assert _state(settlement) == protected_state


@pytest.mark.parametrize("item_type", ("PART", "MATERIAL"))
def test_order_helpers_reserve_release_and_settle_only_through_posted_rw(
    app, settlement, item_type,
):
    with app.app_context():
        model, product_id = _product(settlement, item_type.lower())
        stock = Decimal("10" if item_type == "PART" else "5")
        item = _add(settlement, "4", item_type=item_type)
        assert Decimal(db.session.get(model, product_id).current_stock) == stock
        assert reserved_stock(
            item_type=item_type, item_id=product_id, company_id=settlement.company_id,
        ) == Decimal("4")
        assert db.session.query(ServiceOrderItem).count() == 1
        assert db.session.query(CatalogStockMovement).count() == 0
        assert db.session.query(StockIssue).count() == 0
        assert db.session.query(StockIssueItem).count() == 0

        item = _return(settlement, item, "1")
        assert item.reserved_quantity == Decimal("3")
        assert item.returned_quantity == Decimal("1")
        assert item.used_quantity == 0
        assert Decimal(db.session.get(model, product_id).current_stock) == stock
        release = db.session.query(CatalogStockMovement).one()
        assert release.movement_type == "RELEASE"
        assert release.quantity == Decimal("1")
        assert release.stock_before == release.stock_after == stock
        assert reserved_stock(
            item_type=item_type, item_id=product_id, company_id=settlement.company_id,
        ) == Decimal("3")

        issue = _use(settlement, item, "2")
        assert issue.status == "DRAFT"
        assert db.session.query(StockIssue).count() == 1
        assert db.session.query(StockIssueItem).count() == 1
        line = db.session.query(StockIssueItem).one()
        assert line.service_order_item_id == item.id
        assert line.quantity_issued == Decimal("2")
        assert line.inventory_item_id == (product_id if item_type == "PART" else None)
        assert line.material_id == (product_id if item_type == "MATERIAL" else None)
        assert Decimal(db.session.get(model, product_id).current_stock) == stock
        assert item.used_quantity == 0 and item.reserved_quantity == Decimal("3")
        assert db.session.query(CatalogStockMovement).count() == 1

        _post(settlement, issue)
        db.session.refresh(item)
        db.session.refresh(issue)
        assert issue.status == "POSTED"
        assert Decimal(db.session.get(model, product_id).current_stock) == stock - 2
        assert item.used_quantity == Decimal("2")
        assert item.reserved_quantity == 0
        assert item.returned_quantity == Decimal("2")
        assert reserved_stock(
            item_type=item_type, item_id=product_id, company_id=settlement.company_id,
        ) == 0
        movement = db.session.query(CatalogStockMovement).filter_by(movement_type="ISSUE").one()
        assert movement.quantity == Decimal("2")
        assert movement.stock_before == stock and movement.stock_after == stock - 2
        assert movement.reference_type == "STOCK_ISSUE"
        assert movement.reference_id == issue.issue_number
        releases = db.session.query(CatalogStockMovement).filter_by(movement_type="RELEASE").all()
        assert len(releases) == 2
        assert all(row.stock_before == row.stock_after for row in releases)
        assert sum((row.quantity for row in releases), Decimal("0")) == Decimal("2")
        assert db.session.query(CatalogStockMovement).count() == 3
        assert db.session.query(StockIssue).count() == 1
        assert db.session.query(StockIssueItem).count() == 1
        assert db.session.query(PartDemand).count() == 0
        if item_type == "PART":
            holds = db.session.query(ServiceOrderPartReservation).all()
            assert holds
            assert all(not hold.is_active and hold.status == "RELEASED" and hold.quantity == 0 for hold in holds)

        posted_state = _state(settlement)
        _post(settlement, issue)
        assert _state(settlement) == posted_state