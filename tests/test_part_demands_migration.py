from __future__ import annotations

from importlib import import_module

import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext


def test_part_demands_migration_metadata():
    migration = import_module("migrations.versions.c9e7a1d2b603_add_part_demands_module")
    assert migration.revision == "c9e7a1d2b603"
    assert migration.down_revision == "b6d4e1a2c903"
    assert callable(migration.upgrade)
    assert callable(migration.downgrade)


def test_part_demands_migration_is_idempotent(tmp_path):
    migration = import_module("migrations.versions.c9e7a1d2b603_add_part_demands_module")

    engine = sa.create_engine(f"sqlite:///{tmp_path / 'part_demands_migration.sqlite'}")
    metadata = sa.MetaData()

    sa.Table("companies", metadata, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table("branches", metadata, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table("service_orders", metadata, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table("service_order_items", metadata, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table("catalog_parts", metadata, sa.Column("id", sa.Integer, primary_key=True))

    with engine.begin() as connection:
        metadata.create_all(connection)

        context = MigrationContext.configure(connection)
        operations = Operations(context)
        previous_op = migration.op
        migration.op = operations
        try:
            migration.upgrade()
            migration.upgrade()
        finally:
            migration.op = previous_op

        inspector = sa.inspect(connection)
        assert inspector.has_table("part_demands")

        columns = {item["name"] for item in inspector.get_columns("part_demands")}
        expected = {
            "id",
            "service_order_id",
            "service_order_item_id",
            "inventory_item_id",
            "requested_quantity",
            "reserved_quantity",
            "missing_quantity",
            "status",
            "priority",
            "expected_date",
            "notes",
            "uuid",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "deleted_at",
            "deleted_by",
            "is_active",
            "version",
            "company_id",
            "branch_id",
        }
        assert expected.issubset(columns)
