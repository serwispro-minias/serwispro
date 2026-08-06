"""add service order status history

Revision ID: 3a9d2f4e7b1c
Revises: 8c16f851bbd8
Create Date: 2026-08-02 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "3a9d2f4e7b1c"
down_revision = "8c16f851bbd8"
branch_labels = None
depends_on = None


def upgrade():
    """Create service order status history table."""

    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("service_order_status_history"):
        op.create_table(
            "service_order_status_history",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("service_order_id", sa.Integer(), nullable=False),
            sa.Column("old_status", sa.String(length=40), nullable=True),
            sa.Column("new_status", sa.String(length=40), nullable=False),
            sa.Column("changed_at", sa.DateTime(), nullable=False),
            sa.Column("changed_by", sa.Integer(), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("uuid", sa.String(length=36), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("updated_by", sa.Integer(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
            sa.Column("deleted_by", sa.Integer(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["changed_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["service_order_id"], ["service_orders.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid"),
        )

    inspector = sa.inspect(bind)
    existing_indexes = set()
    if inspector.has_table("service_order_status_history"):
        existing_indexes = {index["name"] for index in inspector.get_indexes("service_order_status_history")}

    if "ix_service_order_status_history_service_order_id" not in existing_indexes:
        op.create_index(
            "ix_service_order_status_history_service_order_id",
            "service_order_status_history",
            ["service_order_id"],
            unique=False,
        )
    if "ix_service_order_status_history_changed_at" not in existing_indexes:
        op.create_index(
            "ix_service_order_status_history_changed_at",
            "service_order_status_history",
            ["changed_at"],
            unique=False,
        )


def downgrade():
    """Drop service order status history table."""

    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("service_order_status_history"):
        existing_indexes = {index["name"] for index in inspector.get_indexes("service_order_status_history")}
        if "ix_service_order_status_history_changed_at" in existing_indexes:
            op.drop_index("ix_service_order_status_history_changed_at", table_name="service_order_status_history")
        if "ix_service_order_status_history_service_order_id" in existing_indexes:
            op.drop_index("ix_service_order_status_history_service_order_id", table_name="service_order_status_history")
        op.drop_table("service_order_status_history")
