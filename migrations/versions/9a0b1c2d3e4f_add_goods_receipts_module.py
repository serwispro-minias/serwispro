"""add goods receipts module

Revision ID: 9a0b1c2d3e4f
Revises: 8f9a0b1c2d3e
"""

from alembic import op
import sqlalchemy as sa

revision = "9a0b1c2d3e4f"
down_revision = "8f9a0b1c2d3e"
branch_labels = None
depends_on = None


def _common():
    return [
        sa.Column("uuid", sa.String(36), nullable=False),
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
    if not inspector.has_table("goods_receipts"):
        op.create_table(
            "goods_receipts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("receipt_number", sa.String(60), nullable=False, unique=True),
            sa.Column("receipt_date", sa.Date(), nullable=False),
            sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("catalog_suppliers.id"), nullable=False),
            sa.Column("purchase_order_id", sa.Integer(), sa.ForeignKey("purchase_orders.id"), nullable=False),
            sa.Column("received_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
            sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id"), nullable=True),
            *_common(),
        )
    if not inspector.has_table("goods_receipt_items"):
        op.create_table(
            "goods_receipt_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("goods_receipt_id", sa.Integer(), sa.ForeignKey("goods_receipts.id"), nullable=False),
            sa.Column("purchase_order_item_id", sa.Integer(), sa.ForeignKey("purchase_order_items.id"), nullable=False),
            sa.Column("part_id", sa.Integer(), sa.ForeignKey("catalog_parts.id"), nullable=False),
            sa.Column("quantity_ordered", sa.Numeric(12, 3), nullable=False),
            sa.Column("quantity_received", sa.Numeric(12, 3), nullable=False),
            sa.Column("purchase_price_net", sa.Numeric(12, 2), nullable=False),
            sa.Column("batch_number", sa.String(120), nullable=True),
            sa.Column("serial_number", sa.String(180), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            *_common(),
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("goods_receipt_items"):
        op.drop_table("goods_receipt_items")
    if inspector.has_table("goods_receipts"):
        op.drop_table("goods_receipts")
