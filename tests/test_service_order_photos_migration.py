from __future__ import annotations

from importlib import import_module

import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext


def test_service_order_photos_migration_metadata():
    migration = import_module("migrations.versions.d2a1b8c4f905_add_service_order_photos_module")
    assert migration.revision == "d2a1b8c4f905"
    assert migration.down_revision == "c9e7a1d2b603"
    assert callable(migration.upgrade)
    assert callable(migration.downgrade)


def test_service_order_photos_migration_creates_table_and_is_idempotent(tmp_path):
    migration = import_module("migrations.versions.d2a1b8c4f905_add_service_order_photos_module")

    engine = sa.create_engine(f"sqlite:///{tmp_path / 'migration_service_order_photos.sqlite'}")
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
        assert inspector.has_table("service_order_photos")

        columns = {item["name"] for item in inspector.get_columns("service_order_photos")}
        expected_columns = {
            "id",
            "service_order_id",
            "photo_type",
            "title",
            "description",
            "file_name",
            "original_file_name",
            "mime_type",
            "file_size",
            "width",
            "height",
            "taken_at",
            "sort_order",
            "is_visible_for_customer",
            "company_id",
            "branch_id",
            "uuid",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "deleted_at",
            "deleted_by",
            "is_active",
            "version",
        }
        assert expected_columns.issubset(columns)


def test_terminal_photo_retention_migration_backfills_current_terminal_period(tmp_path):
    from datetime import datetime

    migration = import_module("migrations.versions.7a2c9f4e1b80_add_terminal_photo_retention_timestamp")
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'migration_terminal_photo_retention.sqlite'}")
    metadata = sa.MetaData()
    sa.Table(
        "service_orders", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("status", sa.String(40), nullable=False),
    )
    sa.Table(
        "service_order_status_history", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("service_order_id", sa.Integer, nullable=False),
        sa.Column("old_status", sa.String(40)),
        sa.Column("new_status", sa.String(40), nullable=False),
        sa.Column("changed_at", sa.DateTime, nullable=False),
    )

    with engine.begin() as connection:
        metadata.create_all(connection)
        connection.execute(sa.text("INSERT INTO service_orders (id, status) VALUES (1, 'CLOSED'), (2, 'CLOSED'), (3, 'ISSUED')"))
        connection.execute(
            sa.Table("service_order_status_history", metadata, autoload_with=connection).insert(),
            [
                {"service_order_id": 1, "old_status": "RECEIVED", "new_status": "ISSUED", "changed_at": datetime(2026, 1, 1, 10)},
                {"service_order_id": 1, "old_status": "ISSUED", "new_status": "CLOSED", "changed_at": datetime(2026, 1, 10, 10)},
                {"service_order_id": 2, "old_status": "RECEIVED", "new_status": "CLOSED", "changed_at": datetime(2026, 1, 1, 10)},
                {"service_order_id": 2, "old_status": "CLOSED", "new_status": "IN_REPAIR", "changed_at": datetime(2026, 1, 10, 10)},
                {"service_order_id": 2, "old_status": "IN_REPAIR", "new_status": "CLOSED", "changed_at": datetime(2026, 2, 1, 10)},
            ],
        )
        context = MigrationContext.configure(connection)
        operations = Operations(context)
        old_op = migration.op
        migration.op = operations
        try:
            migration.upgrade()
        finally:
            migration.op = old_op

        rows = connection.execute(sa.text("SELECT id, terminal_status_entered_at FROM service_orders ORDER BY id")).all()
        assert datetime.fromisoformat(rows[0].terminal_status_entered_at) == datetime(2026, 1, 1, 10)
        assert datetime.fromisoformat(rows[1].terminal_status_entered_at) == datetime(2026, 2, 1, 10)
        assert rows[2].terminal_status_entered_at is None
