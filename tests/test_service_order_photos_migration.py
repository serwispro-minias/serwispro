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
