from __future__ import annotations

from datetime import datetime
from importlib import import_module

import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext


def test_terminal_photo_retention_migration_backfills_current_terminal_period(tmp_path):
    migration = import_module("migrations.versions.7a2c9f4e1b80_add_terminal_photo_retention_timestamp")
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'photo_retention.sqlite'}")
    metadata = sa.MetaData()
    orders = sa.Table(
        "service_orders", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("status", sa.String(40), nullable=False),
    )
    history = sa.Table(
        "service_order_status_history", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("service_order_id", sa.Integer, nullable=False),
        sa.Column("old_status", sa.String(40)),
        sa.Column("new_status", sa.String(40), nullable=False),
        sa.Column("changed_at", sa.DateTime, nullable=False),
    )

    with engine.begin() as connection:
        metadata.create_all(connection)
        connection.execute(orders.insert(), [
            {"id": 1, "status": "CLOSED"},
            {"id": 2, "status": "CLOSED"},
            {"id": 3, "status": "ISSUED"},
        ])
        connection.execute(history.insert(), [
            {"service_order_id": 1, "old_status": "RECEIVED", "new_status": "ISSUED", "changed_at": datetime(2026, 1, 1, 10)},
            {"service_order_id": 1, "old_status": "ISSUED", "new_status": "CLOSED", "changed_at": datetime(2026, 1, 10, 10)},
            {"service_order_id": 2, "old_status": "RECEIVED", "new_status": "CLOSED", "changed_at": datetime(2026, 1, 1, 10)},
            {"service_order_id": 2, "old_status": "CLOSED", "new_status": "IN_REPAIR", "changed_at": datetime(2026, 1, 10, 10)},
            {"service_order_id": 2, "old_status": "IN_REPAIR", "new_status": "CLOSED", "changed_at": datetime(2026, 2, 1, 10)},
        ])
        context = MigrationContext.configure(connection)
        ops = Operations(context)
        original = migration.op
        migration.op = ops
        try:
            migration.upgrade()
        finally:
            migration.op = original

        rows = connection.execute(sa.text("SELECT id, terminal_status_entered_at FROM service_orders ORDER BY id")).all()
        assert datetime.fromisoformat(rows[0].terminal_status_entered_at) == datetime(2026, 1, 1, 10)
        assert datetime.fromisoformat(rows[1].terminal_status_entered_at) == datetime(2026, 2, 1, 10)
        assert rows[2].terminal_status_entered_at is None
        assert "ix_service_orders_photo_retention" in {item["name"] for item in sa.inspect(connection).get_indexes("service_orders")}
