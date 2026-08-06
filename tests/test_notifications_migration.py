from __future__ import annotations

from importlib import import_module


def test_notifications_migration_metadata():
    migration = import_module("migrations.versions.c3f6eab94210_add_notifications_module_tables")
    assert migration.revision == "c3f6eab94210"
    assert migration.down_revision == "b2f4a61c9d3e"
    assert callable(migration.upgrade)
    assert callable(migration.downgrade)


def test_notifications_repair_migration_metadata():
    migration = import_module("migrations.versions.e9a24f3d7c11_notifications_logs_queue_repair")
    assert migration.revision == "e9a24f3d7c11"
    assert migration.down_revision == "c3f6eab94210"
    assert callable(migration.upgrade)
    assert callable(migration.downgrade)
