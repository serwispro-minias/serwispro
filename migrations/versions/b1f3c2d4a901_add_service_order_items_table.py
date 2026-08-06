"""add service order items table

Revision ID: b1f3c2d4a901
Revises: a7c9d3e4f801
Create Date: 2026-08-06 10:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b1f3c2d4a901"
down_revision = "a7c9d3e4f801"
branch_labels = None
depends_on = None


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("branch_id", sa.Integer(), nullable=True),
        sa.Column("uuid", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_by", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
    ]


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("service_order_items"):
        op.create_table(
            "service_order_items",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("service_order_id", sa.Integer(), nullable=False),
            sa.Column("item_type", sa.String(length=20), nullable=False),
            sa.Column("item_id", sa.Integer(), nullable=False),
            sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
            sa.Column("reserved_quantity", sa.Numeric(12, 3), nullable=False),
            sa.Column("used_quantity", sa.Numeric(12, 3), nullable=False),
            sa.Column("returned_quantity", sa.Numeric(12, 3), nullable=False),
            sa.Column("unit_price_net", sa.Numeric(12, 2), nullable=False),
            sa.Column("discount_percent", sa.Numeric(5, 2), nullable=False),
            sa.Column("vat_rate", sa.Numeric(5, 2), nullable=False),
            sa.Column("total_net", sa.Numeric(12, 2), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            *_base_columns(),
            sa.ForeignKeyConstraint(["service_order_id"], ["service_orders.id"]),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid"),
        )

    inspector = sa.inspect(bind)
    indexes = {item["name"] for item in inspector.get_indexes("service_order_items")} if inspector.has_table("service_order_items") else set()
    if "ix_service_order_items_company_id" not in indexes:
        op.create_index("ix_service_order_items_company_id", "service_order_items", ["company_id"], unique=False)
    if "ix_service_order_items_branch_id" not in indexes:
        op.create_index("ix_service_order_items_branch_id", "service_order_items", ["branch_id"], unique=False)
    if "ix_service_order_items_order_id" not in indexes:
        op.create_index("ix_service_order_items_order_id", "service_order_items", ["service_order_id"], unique=False)
    if "ix_service_order_items_type" not in indexes:
        op.create_index("ix_service_order_items_type", "service_order_items", ["item_type"], unique=False)
    if "ix_service_order_items_item_id" not in indexes:
        op.create_index("ix_service_order_items_item_id", "service_order_items", ["item_id"], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("service_order_items"):
        for index_name in [
            "ix_service_order_items_item_id",
            "ix_service_order_items_type",
            "ix_service_order_items_order_id",
            "ix_service_order_items_branch_id",
            "ix_service_order_items_company_id",
        ]:
            if index_name in {item["name"] for item in inspector.get_indexes("service_order_items")}:
                op.drop_index(index_name, table_name="service_order_items")
        op.drop_table("service_order_items")
