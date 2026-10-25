"""Track the current terminal-status entry time for service-order photo retention.

Revision ID: 7a2c9f4e1b80
Revises: 6a8c2e4f1b90
"""

from alembic import op
import sqlalchemy as sa


revision = "7a2c9f4e1b80"
down_revision = "6a8c2e4f1b90"
branch_labels = None
depends_on = None

_TERMINAL = {"ISSUED", "CLOSED", "CANCELLED"}


def upgrade():
    op.add_column("service_orders", sa.Column("terminal_status_entered_at", sa.DateTime(), nullable=True))
    op.create_index(
        "ix_service_orders_photo_retention",
        "service_orders",
        ["status", "terminal_status_entered_at"],
        unique=False,
    )

    bind = op.get_bind()
    current_orders = {
        int(row.id): row.status
        for row in bind.execute(
            sa.text("SELECT id, status FROM service_orders WHERE status IN ('ISSUED', 'CLOSED', 'CANCELLED')")
        ).fetchall()
    }
    if not current_orders:
        return

    history_rows = bind.execute(
        sa.text(
            "SELECT service_order_id, old_status, new_status, changed_at "
            "FROM service_order_status_history "
            "WHERE service_order_id IN :order_ids "
            "ORDER BY service_order_id ASC, changed_at ASC, id ASC"
        ).bindparams(sa.bindparam("order_ids", expanding=True)),
        {"order_ids": list(current_orders)},
    ).fetchall()
    entry_by_order = {}
    for row in history_rows:
        order_id = int(row.service_order_id)
        if row.new_status in _TERMINAL:
            if row.old_status not in _TERMINAL:
                entry_by_order[order_id] = row.changed_at
        else:
            entry_by_order.pop(order_id, None)

    for order_id, current_status in current_orders.items():
        entered_at = entry_by_order.get(order_id)
        if current_status in _TERMINAL and entered_at is not None:
            bind.execute(
                sa.text("UPDATE service_orders SET terminal_status_entered_at = :entered_at WHERE id = :order_id")
                .bindparams(entered_at=entered_at, order_id=order_id)
            )


def downgrade():
    op.drop_index("ix_service_orders_photo_retention", table_name="service_orders")
    op.drop_column("service_orders", "terminal_status_entered_at")
