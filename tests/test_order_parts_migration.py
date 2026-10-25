"""Exercise the RW settlement migration against the pre-upgrade SQLite schema."""

from datetime import datetime
from decimal import Decimal
from importlib import import_module

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext


@pytest.fixture()
def migration_db(monkeypatch):
    migration = import_module("migrations.versions.8b3d0e5f2c91_order_item_rw_settlement")
    engine = sa.create_engine("sqlite:///:memory:")
    metadata = sa.MetaData()
    # Only referenced IDs are needed; deliberately do not use current ORM metadata.
    references = [
        sa.Table(name, metadata, sa.Column("id", sa.Integer(), primary_key=True))
        for name in (
            "stock_issues", "inventory_items", "part_demands",
            "service_order_part_reservations", "catalog_materials", "service_order_items",
        )
    ]
    old_items = sa.Table(
        "stock_issue_items", metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stock_issue_id", sa.Integer(), sa.ForeignKey("stock_issues.id"), nullable=False),
        sa.Column("inventory_item_id", sa.Integer(), sa.ForeignKey("inventory_items.id"), nullable=False),
        sa.Column("part_demand_id", sa.Integer(), sa.ForeignKey("part_demands.id")),
        sa.Column("reservation_id", sa.Integer(), sa.ForeignKey("service_order_part_reservations.id")),
        sa.Column("quantity_issued", sa.Integer(), nullable=False),
        sa.Column("uuid", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer()),
        sa.Column("updated_by", sa.Integer()),
        sa.Column("deleted_at", sa.DateTime()),
        sa.Column("deleted_by", sa.Integer()),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
    )
    now = datetime(2026, 10, 25, 12, 0)
    legacy = dict(
        id=1, stock_issue_id=1, inventory_item_id=1, part_demand_id=1,
        reservation_id=1, quantity_issued=3,
        uuid="00000000-0000-0000-0000-000000000001",
        created_at=now, updated_at=now, created_by=7, updated_by=8,
        deleted_at=None, deleted_by=None, is_active=True, version=4,
    )
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()
            with connection.begin():
                metadata.create_all(connection)
                for table in references:
                    connection.execute(table.insert().values(id=1))
                connection.execute(old_items.insert().values(**legacy))
                operations = Operations(MigrationContext.configure(connection))
                with monkeypatch.context() as patch:
                    patch.setattr(migration, "op", operations)
                    yield migration, connection, legacy
    finally:
        engine.dispose()


def _items(connection):
    return sa.Table("stock_issue_items", sa.MetaData(), autoload_with=connection)


def _insert_linked(connection, legacy, *, material_id, service_order_item_id):
    items = _items(connection)
    payload = dict(legacy)
    payload.update(
        id=2, uuid="00000000-0000-0000-0000-000000000002",
        inventory_item_id=None if material_id else 1,
        material_id=material_id, service_order_item_id=service_order_item_id,
        settlement_version=9,
        quantity_issued=Decimal("1.125") if material_id else Decimal("2.000"),
        part_demand_id=None, reservation_id=None,
    )
    connection.execute(items.insert().values(**payload))
    return payload


def test_upgrade_preserves_integer_row_and_accepts_fractional_linked_material(migration_db):
    migration, connection, legacy = migration_db
    assert migration.revision == "8b3d0e5f2c91"
    assert migration.down_revision == "7a2c9f4e1b80"
    old_columns = {column["name"]: column for column in sa.inspect(connection).get_columns("stock_issue_items")}
    assert isinstance(old_columns["quantity_issued"]["type"], sa.Integer)
    assert old_columns["inventory_item_id"]["nullable"] is False

    migration.upgrade()

    inspector = sa.inspect(connection)
    columns = {column["name"]: column for column in inspector.get_columns("stock_issue_items")}
    assert columns["inventory_item_id"]["nullable"] is True
    assert columns["quantity_issued"]["nullable"] is False
    quantity_type = columns["quantity_issued"]["type"]
    assert isinstance(quantity_type, sa.Numeric)
    assert (quantity_type.precision, quantity_type.scale) == (12, 3)
    for name in ("material_id", "service_order_item_id", "settlement_version"):
        assert columns[name]["nullable"] is True
        assert isinstance(columns[name]["type"], sa.Integer)
    foreign_keys = {fk["name"]: fk for fk in inspector.get_foreign_keys("stock_issue_items")}
    for name, column, target in (
        ("fk_rw_material", "material_id", "catalog_materials"),
        ("fk_rw_order_item", "service_order_item_id", "service_order_items"),
    ):
        assert foreign_keys[name]["constrained_columns"] == [column]
        assert foreign_keys[name]["referred_table"] == target
        assert foreign_keys[name]["referred_columns"] == ["id"]

    items = _items(connection)
    preserved = connection.execute(sa.select(items).where(items.c.id == 1)).mappings().one()
    assert {name: preserved[name] for name in legacy} == legacy
    assert preserved["quantity_issued"] == Decimal("3.000")
    assert all(preserved[name] is None for name in ("material_id", "service_order_item_id", "settlement_version"))

    payload = _insert_linked(connection, legacy, material_id=1, service_order_item_id=1)
    linked = connection.execute(sa.select(items).where(items.c.id == 2)).mappings().one()
    assert dict(linked) == payload
    assert linked["quantity_issued"] == Decimal("1.125")
    assert linked["inventory_item_id"] is None
    assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []


def test_downgrade_restores_old_schema_when_only_legacy_integer_data_exists(migration_db):
    migration, connection, legacy = migration_db
    migration.upgrade()
    migration.downgrade()

    columns = {column["name"]: column for column in sa.inspect(connection).get_columns("stock_issue_items")}
    assert set(columns) == set(legacy)
    assert columns["inventory_item_id"]["nullable"] is False
    assert columns["quantity_issued"]["nullable"] is False
    assert isinstance(columns["quantity_issued"]["type"], sa.Integer)
    assert dict(connection.execute(sa.select(_items(connection))).mappings().one()) == legacy
    assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []


@pytest.mark.parametrize(
    "material_id,service_order_item_id", [(1, None), (None, 1), (1, 1)],
    ids=["material-only", "order-item-only", "material-and-order-item"],
)
def test_downgrade_refuses_linked_data_without_changing_schema_or_rows(
    migration_db, material_id, service_order_item_id,
):
    migration, connection, legacy = migration_db
    migration.upgrade()
    _insert_linked(
        connection, legacy, material_id=material_id,
        service_order_item_id=service_order_item_id,
    )
    items = _items(connection)
    before_rows = connection.execute(sa.select(items).order_by(items.c.id)).mappings().all()
    before_columns = sa.inspect(connection).get_columns("stock_issue_items")
    before_fks = sa.inspect(connection).get_foreign_keys("stock_issue_items")

    with pytest.raises(RuntimeError, match="Nie można usunąć powiązań istniejących rozliczeń RW"):
        migration.downgrade()

    columns = sa.inspect(connection).get_columns("stock_issue_items")
    assert [(c["name"], str(c["type"]), c["nullable"]) for c in columns] == [
        (c["name"], str(c["type"]), c["nullable"]) for c in before_columns
    ]
    assert sa.inspect(connection).get_foreign_keys("stock_issue_items") == before_fks
    assert connection.execute(sa.select(_items(connection)).order_by(sa.column("id"))).mappings().all() == before_rows
    assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []


@pytest.mark.parametrize("quantity", [1000000000, -1000000000, 2147483647])
def test_upgrade_refuses_decimal_overflow_before_ddl(migration_db, quantity):
    migration, connection, _ = migration_db
    connection.execute(sa.text("UPDATE stock_issue_items SET quantity_issued=:qty"), {"qty": quantity})
    with pytest.raises(RuntimeError, match="DECIMAL"):
        migration.upgrade()
    columns = {col["name"] for col in sa.inspect(connection).get_columns("stock_issue_items")}
    assert "material_id" not in columns
    assert connection.scalar(sa.text("SELECT quantity_issued FROM stock_issue_items")) == quantity


@pytest.mark.parametrize("field,value", [
    ("quantity_issued", Decimal("1.125")),
    ("inventory_item_id", None),
    ("settlement_version", 3),
])
def test_downgrade_refuses_other_lossy_data_before_ddl(migration_db, field, value):
    migration, connection, _ = migration_db
    migration.upgrade()
    items = _items(connection)
    connection.execute(items.update().values(**{field: value}))
    before = dict(connection.execute(sa.select(items)).mappings().one())
    with pytest.raises(RuntimeError, match="Nie można"):
        migration.downgrade()
    assert "settlement_version" in {col["name"] for col in sa.inspect(connection).get_columns("stock_issue_items")}
    assert dict(connection.execute(sa.select(_items(connection))).mappings().one()) == before


def test_upgrade_refuses_partial_schema_without_further_changes(migration_db):
    migration, connection, _ = migration_db
    connection.exec_driver_sql("ALTER TABLE stock_issue_items ADD COLUMN material_id INTEGER NULL")
    with pytest.raises(RuntimeError, match="częściowo"):
        migration.upgrade()
    assert "service_order_item_id" not in {c["name"] for c in sa.inspect(connection).get_columns("stock_issue_items")}


@pytest.mark.parametrize("quantity", [-999999999, 999999999])
def test_upgrade_accepts_representable_integer_boundaries(migration_db, quantity):
    migration, connection, _ = migration_db
    connection.execute(sa.text("UPDATE stock_issue_items SET quantity_issued=:qty"), {"qty": quantity})
    migration.upgrade()
    assert connection.scalar(sa.select(_items(connection).c.quantity_issued)) == Decimal(quantity)


def test_mysql_upgrade_sql_is_preview_only_and_has_no_data_mutation(monkeypatch):
    from io import StringIO

    migration = import_module("migrations.versions.8b3d0e5f2c91_order_item_rw_settlement")
    output = StringIO()
    context = MigrationContext.configure(dialect_name="mysql", opts={"as_sql": True, "output_buffer": output})
    monkeypatch.setattr(migration, "op", Operations(context))
    migration.upgrade()
    sql = output.getvalue()
    assert "PREVIEW ONLY" in sql
    assert "MODIFY inventory_item_id INTEGER NULL" in sql
    assert "quantity_issued NUMERIC(12, 3) NOT NULL" in sql
    assert "ADD CONSTRAINT fk_rw_material" in sql
    assert "ADD CONSTRAINT fk_rw_order_item" in sql
    assert "UPDATE " not in sql and "DELETE " not in sql and "DROP " not in sql
    assert "DEFAULT " not in sql
    with pytest.raises(RuntimeError, match="downgrade"):
        migration.downgrade()


def test_revision_is_single_next_step_after_database_revision():
    from pathlib import Path

    from alembic.script import ScriptDirectory

    scripts = ScriptDirectory(str(Path(__file__).resolve().parents[1] / "migrations"))
    assert scripts.get_heads() == ["8b3d0e5f2c91"]
    assert scripts.get_revision("8b3d0e5f2c91").down_revision == "7a2c9f4e1b80"