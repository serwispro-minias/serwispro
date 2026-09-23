"""add Stage 2A PZ and BO documents

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
"""

from alembic import op
import sqlalchemy as sa

revision = "e7f8a9b0c1d2"
down_revision = "d6e7f8a9b0c1"
branch_labels = None
depends_on = None


def _columns(inspector, table):
    return {column["name"] for column in inspector.get_columns(table)} if inspector.has_table(table) else set()


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("goods_receipts"):
        columns = _columns(inspector, "goods_receipts")
        if "notes" not in columns:
            op.add_column("goods_receipts", sa.Column("notes", sa.String(2000), nullable=True))
        if "supplier_id" in columns:
            supplier_type = next(column["type"] for column in inspector.get_columns("goods_receipts") if column["name"] == "supplier_id")
            op.alter_column("goods_receipts", "supplier_id", existing_type=supplier_type, nullable=True)
        if "purchase_order_id" in columns:
            order_type = next(column["type"] for column in inspector.get_columns("goods_receipts") if column["name"] == "purchase_order_id")
            op.alter_column("goods_receipts", "purchase_order_id", existing_type=order_type, nullable=True)
        op.execute(sa.text("UPDATE goods_receipts SET status = 'DRAFT' WHERE status = 'NEW'"))
        op.execute(sa.text("UPDATE goods_receipts SET status = 'POSTED' WHERE status = 'ACCEPTED'"))

    if inspector.has_table("goods_receipt_items"):
        columns = _columns(inspector, "goods_receipt_items")
        if "inventory_item_id" not in columns:
            op.add_column("goods_receipt_items", sa.Column("inventory_item_id", sa.Integer(), nullable=True))
            op.create_foreign_key("fk_goods_receipt_items_inventory_item", "goods_receipt_items", "inventory_items", ["inventory_item_id"], ["id"])
            if "part_id" in columns:
                op.execute(sa.text("UPDATE goods_receipt_items SET inventory_item_id = part_id WHERE inventory_item_id IS NULL"))
        if "vat_id" not in columns:
            op.add_column("goods_receipt_items", sa.Column("vat_id", sa.Integer(), nullable=True))
        if "demand_id" not in columns:
            op.add_column("goods_receipt_items", sa.Column("demand_id", sa.Integer(), nullable=True))
        inspector = sa.inspect(bind)
        po_item_type = next(column["type"] for column in inspector.get_columns("goods_receipt_items") if column["name"] == "purchase_order_item_id")
        op.alter_column("goods_receipt_items", "purchase_order_item_id", existing_type=po_item_type, nullable=True)
        item_type = next(column["type"] for column in inspector.get_columns("goods_receipt_items") if column["name"] == "inventory_item_id")
        op.alter_column("goods_receipt_items", "inventory_item_id", existing_type=item_type, nullable=False)

    if not inspector.has_table("opening_balances"):
        op.create_table(
            "opening_balances",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("document_number", sa.String(60), nullable=False, unique=True),
            sa.Column("document_date", sa.Date(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("notes", sa.String(2000), nullable=True),
            sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
            sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id"), nullable=True),
            sa.Column("uuid", sa.String(36), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("created_by", sa.Integer()),
            sa.Column("updated_by", sa.Integer()),
            sa.Column("deleted_at", sa.DateTime()),
            sa.Column("deleted_by", sa.Integer()),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
        )
    if not inspector.has_table("opening_balance_items"):
        op.create_table(
            "opening_balance_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("opening_balance_id", sa.Integer(), sa.ForeignKey("opening_balances.id"), nullable=False),
            sa.Column("inventory_item_id", sa.Integer(), sa.ForeignKey("inventory_items.id"), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("purchase_price_net", sa.Numeric(12, 2), nullable=False),
            sa.Column("vat_id", sa.Integer(), sa.ForeignKey("vat_rates.id"), nullable=True),
            sa.Column("net_value", sa.Numeric(14, 2), nullable=False),
            sa.Column("vat_value", sa.Numeric(14, 2), nullable=False),
            sa.Column("gross_value", sa.Numeric(14, 2), nullable=False),
            sa.Column("uuid", sa.String(36), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("created_by", sa.Integer()),
            sa.Column("updated_by", sa.Integer()),
            sa.Column("deleted_at", sa.DateTime()),
            sa.Column("deleted_by", sa.Integer()),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("opening_balance_items"):
        op.drop_table("opening_balance_items")
    if inspector.has_table("opening_balances"):
        op.drop_table("opening_balances")
