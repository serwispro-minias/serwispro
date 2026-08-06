from importlib import import_module

import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext


def test_service_order_actions_migration_metadata():
    migration = import_module("migrations.versions.f1b2c3d4e5f6_add_service_order_actions")
    assert migration.revision == "f1b2c3d4e5f6"
    assert migration.down_revision == "e9a24f3d7c11"
    assert callable(migration.upgrade)
    assert callable(migration.downgrade)


def test_service_order_actions_migration_creates_table_and_is_idempotent(tmp_path):
    migration = import_module("migrations.versions.f1b2c3d4e5f6_add_service_order_actions")

    engine = sa.create_engine(f"sqlite:///{tmp_path / 'migration_actions.sqlite'}")
    metadata = sa.MetaData()

    sa.Table("companies", metadata, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table("branches", metadata, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table("users", metadata, sa.Column("id", sa.Integer, primary_key=True))
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
        assert inspector.has_table("service_order_actions")

        columns = {item["name"] for item in inspector.get_columns("service_order_actions")}
        expected_columns = {
            "id",
            "service_order_id",
            "action_date",
            "technician_id",
            "action_type",
            "description",
            "work_time_minutes",
            "cost",
            "is_visible_for_customer",
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
