"""add stock issues module

Revision ID: ab1c2d3e4f50
Revises: 9a0b1c2d3e4f
"""

from alembic import op
import sqlalchemy as sa

revision = "ab1c2d3e4f50"
down_revision = "9a0b1c2d3e4f"
branch_labels = None
depends_on = None


def common():
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
    if not inspector.has_table("stock_issues"):
        op.create_table(
            "stock_issues",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("issue_number", sa.String(60), nullable=False, unique=True),
            sa.Column("issue_date", sa.Date(), nullable=False),
            sa.Column("service_order_id", sa.Integer(), sa.ForeignKey("service_orders.id"), nullable=False),
            sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id"), nullable=True),
            sa.Column("issued_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
            *common(),
        )
    if not inspector.has_table("stock_issue_items"):
        op.create_table(
            "stock_issue_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("stock_issue_id", sa.Integer(), sa.ForeignKey("stock_issues.id"), nullable=False),
            sa.Column("part_id", sa.Integer(), sa.ForeignKey("catalog_parts.id"), nullable=False),
            sa.Column("part_demand_id", sa.Integer(), sa.ForeignKey("part_demands.id"), nullable=True),
            sa.Column("reservation_id", sa.Integer(), sa.ForeignKey("service_order_part_reservations.id"), nullable=False),
            sa.Column("quantity_issued", sa.Numeric(12, 3), nullable=False),
            *common(),
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("stock_issue_items"):
        op.drop_table("stock_issue_items")
    if inspector.has_table("stock_issues"):
        op.drop_table("stock_issues")
