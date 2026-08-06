from __future__ import annotations

from importlib import import_module

import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext


def test_service_order_items_migration_metadata():
    migration = import_module("migrations.versions.b1f3c2d4a901_add_service_order_items_table")
    assert migration.revision == "b1f3c2d4a901"
    assert migration.down_revision == "a7c9d3e4f801"
    assert callable(migration.upgrade)
    assert callable(migration.downgrade)


def test_service_order_items_migration_creates_table_and_is_idempotent(tmp_path):
    migration = import_module("migrations.versions.b1f3c2d4a901_add_service_order_items_table")

    engine = sa.create_engine(f"sqlite:///{tmp_path / 'migration_service_order_items.sqlite'}")
    metadata = sa.MetaData()

    sa.Table("companies", metadata, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table("branches", metadata, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table("service_orders", metadata, sa.Column("id", sa.Integer, primary_key=True))

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
        assert inspector.has_table("service_order_items")

        columns = {item["name"] for item in inspector.get_columns("service_order_items")}
        expected_columns = {
            "id",
            "service_order_id",
            "item_type",
            "item_id",
            "quantity",
            "reserved_quantity",
            "used_quantity",
            "returned_quantity",
            "unit_price_net",
            "discount_percent",
            "vat_rate",
            "total_net",
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
        assert expected_columns.issubset(columns)
