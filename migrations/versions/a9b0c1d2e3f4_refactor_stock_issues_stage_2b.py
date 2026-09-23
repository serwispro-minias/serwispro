"""refactor RW for Stage 2B

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
"""

from alembic import op
import sqlalchemy as sa

revision = "a9b0c1d2e3f4"
down_revision = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None


def _columns(inspector, table):
    return {column["name"] for column in inspector.get_columns(table)} if inspector.has_table(table) else set()


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("stock_issues"):
        columns = _columns(inspector, "stock_issues")
        if "service_order_id" in columns:
            column = next(column for column in inspector.get_columns("stock_issues") if column["name"] == "service_order_id")
            op.alter_column("stock_issues", "service_order_id", existing_type=column["type"], nullable=True)
        op.execute(sa.text("UPDATE stock_issues SET status = 'POSTED' WHERE status = 'ISSUED'"))
    if inspector.has_table("stock_issue_items"):
        columns = _columns(inspector, "stock_issue_items")
        if "inventory_item_id" not in columns:
            op.add_column("stock_issue_items", sa.Column("inventory_item_id", sa.Integer(), nullable=True))
            op.create_foreign_key("fk_stock_issue_items_inventory_item", "stock_issue_items", "inventory_items", ["inventory_item_id"], ["id"])
            if "part_id" in columns:
                op.execute(sa.text("UPDATE stock_issue_items SET inventory_item_id = part_id WHERE inventory_item_id IS NULL"))
        item_column = next(column for column in sa.inspect(bind).get_columns("stock_issue_items") if column["name"] == "inventory_item_id")
        op.alter_column("stock_issue_items", "inventory_item_id", existing_type=item_column["type"], nullable=False)
        quantity_column = next(column for column in sa.inspect(bind).get_columns("stock_issue_items") if column["name"] == "quantity_issued")
        op.alter_column("stock_issue_items", "quantity_issued", existing_type=quantity_column["type"], type_=sa.Integer(), nullable=False)
        reservation_column = next(column for column in sa.inspect(bind).get_columns("stock_issue_items") if column["name"] == "reservation_id")
        op.alter_column("stock_issue_items", "reservation_id", existing_type=reservation_column["type"], nullable=True)


def downgrade():
    pass
