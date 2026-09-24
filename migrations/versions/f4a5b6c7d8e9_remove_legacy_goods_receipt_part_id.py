"""remove legacy PZ part_id after InventoryItem migration

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
"""

from alembic import op
import sqlalchemy as sa

revision = "f4a5b6c7d8e9"
down_revision = "e3f4a5b6c7d8"
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
    if "part_id" not in columns:
        return
    if "inventory_item_id" not in columns:
        raise RuntimeError("Cannot drop goods_receipt_items.part_id: inventory_item_id column is missing.")

    null_count = bind.execute(sa.text("SELECT COUNT(*) FROM goods_receipt_items WHERE inventory_item_id IS NULL")).scalar()
    if int(null_count or 0) > 0:
        raise RuntimeError(
            "Cannot drop goods_receipt_items.part_id: some rows have inventory_item_id IS NULL. "
            "Fill inventory_item_id explicitly before running this migration."
        )

    for foreign_key in inspector.get_foreign_keys("goods_receipt_items"):
        if "part_id" in (foreign_key.get("constrained_columns") or []):
            op.drop_constraint(foreign_key["name"], "goods_receipt_items", type_="foreignkey")
    for index in inspector.get_indexes("goods_receipt_items"):
        if "part_id" in (index.get("column_names") or []):
            op.drop_index(index["name"], table_name="goods_receipt_items")
    op.drop_column("goods_receipt_items", "part_id")


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("goods_receipt_items") and "part_id" not in _columns(inspector, "goods_receipt_items"):
        op.add_column("goods_receipt_items", sa.Column("part_id", sa.Integer(), nullable=True))
