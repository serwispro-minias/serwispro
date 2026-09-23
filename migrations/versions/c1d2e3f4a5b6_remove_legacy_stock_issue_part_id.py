"""remove legacy RW part_id after InventoryItem migration

Revision ID: c1d2e3f4a5b6
Revises: a9b0c1d2e3f4
"""

from alembic import op
import sqlalchemy as sa

revision = "c1d2e3f4a5b6"
down_revision = "a9b0c1d2e3f4"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("stock_issue_items"):
        return
    columns = {column["name"] for column in inspector.get_columns("stock_issue_items")}
    if "part_id" not in columns:
        return
    for foreign_key in inspector.get_foreign_keys("stock_issue_items"):
        if "part_id" in (foreign_key.get("constrained_columns") or []):
            op.drop_constraint(foreign_key["name"], "stock_issue_items", type_="foreignkey")
    for index in inspector.get_indexes("stock_issue_items"):
        if "part_id" in (index.get("column_names") or []):
            op.drop_index(index["name"], table_name="stock_issue_items")
    op.drop_column("stock_issue_items", "part_id")


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("stock_issue_items") and "part_id" not in {column["name"] for column in inspector.get_columns("stock_issue_items")}:
        op.add_column("stock_issue_items", sa.Column("part_id", sa.Integer(), nullable=True))
