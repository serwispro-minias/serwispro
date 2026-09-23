"""add sale price to goods receipt items

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
"""

from alembic import op
import sqlalchemy as sa

revision = "d2e3f4a5b6c7"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def _columns(inspector, table):
    return {column["name"] for column in inspector.get_columns(table)} if inspector.has_table(table) else set()


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("goods_receipt_items"):
        return
    columns = _columns(inspector, "goods_receipt_items")
    if "sale_price_net" not in columns:
        op.add_column("goods_receipt_items", sa.Column("sale_price_net", sa.Numeric(12, 2), nullable=True))
        columns = _columns(sa.inspect(bind), "goods_receipt_items")
    if "inventory_item_id" in columns:
        op.execute(sa.text("""
            UPDATE goods_receipt_items gri
            LEFT JOIN inventory_items ii ON ii.id = gri.inventory_item_id
            SET gri.sale_price_net = COALESCE(ii.sale_price_net, gri.purchase_price_net, 0)
            WHERE gri.sale_price_net IS NULL
        """))
    else:
        op.execute(sa.text("UPDATE goods_receipt_items SET sale_price_net = COALESCE(purchase_price_net, 0) WHERE sale_price_net IS NULL"))
    sale_type = next(column["type"] for column in sa.inspect(bind).get_columns("goods_receipt_items") if column["name"] == "sale_price_net")
    op.alter_column("goods_receipt_items", "sale_price_net", existing_type=sale_type, nullable=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("goods_receipt_items") and "sale_price_net" in _columns(inspector, "goods_receipt_items"):
        op.drop_column("goods_receipt_items", "sale_price_net")
