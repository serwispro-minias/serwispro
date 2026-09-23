"""complete Stage 2A receipt item foreign keys

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
"""

from alembic import op
import sqlalchemy as sa

revision = "f8a9b0c1d2e3"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def _foreign_keys(inspector):
    return {item.get("name") for item in inspector.get_foreign_keys("goods_receipt_items")} if inspector.has_table("goods_receipt_items") else set()


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("goods_receipt_items"):
        return
    foreign_keys = _foreign_keys(inspector)
    if "fk_goods_receipt_items_vat_rate" not in foreign_keys:
        op.create_foreign_key("fk_goods_receipt_items_vat_rate", "goods_receipt_items", "vat_rates", ["vat_id"], ["id"])
    if "fk_goods_receipt_items_part_demand" not in foreign_keys:
        op.create_foreign_key("fk_goods_receipt_items_part_demand", "goods_receipt_items", "part_demands", ["demand_id"], ["id"])


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("goods_receipt_items"):
        return
    foreign_keys = _foreign_keys(inspector)
    if "fk_goods_receipt_items_part_demand" in foreign_keys:
        op.drop_constraint("fk_goods_receipt_items_part_demand", "goods_receipt_items", type_="foreignkey")
    if "fk_goods_receipt_items_vat_rate" in foreign_keys:
        op.drop_constraint("fk_goods_receipt_items_vat_rate", "goods_receipt_items", type_="foreignkey")
