"""add purchase requests module

Revision ID: 1d6c9b0d2e6f
Revises: e31a2b7d9f10
Create Date: 2026-08-18 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "1d6c9b0d2e6f"
down_revision = "e31a2b7d9f10"
branch_labels = None
depends_on = None


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return index_name in {item["name"] for item in inspector.get_indexes(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("purchase_requests"):
        op.create_table(
            "purchase_requests",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("service_order_id", sa.Integer(), nullable=False),
            sa.Column("part_id", sa.Integer(), nullable=False),
            sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("priority", sa.String(length=20), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("requested_by", sa.Integer(), nullable=True),
            sa.Column("ordered_at", sa.DateTime(), nullable=True),
            sa.Column("received_at", sa.DateTime(), nullable=True),
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
            sa.ForeignKeyConstraint(["service_order_id"], ["service_orders.id"]),
            sa.ForeignKeyConstraint(["part_id"], ["catalog_parts.id"]),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid"),
        )

    inspector = sa.inspect(bind)
    for index_name, columns in [
        ("ix_purchase_requests_company_id", ["company_id"]),
        ("ix_purchase_requests_branch_id", ["branch_id"]),
        ("ix_purchase_requests_service_order_id", ["service_order_id"]),
        ("ix_purchase_requests_part_id", ["part_id"]),
        ("ix_purchase_requests_status", ["status"]),
        ("ix_purchase_requests_priority", ["priority"]),
    ]:
        if not _has_index(inspector, "purchase_requests", index_name):
            op.create_index(index_name, "purchase_requests", columns, unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("purchase_requests"):
        existing_indexes = {item["name"] for item in inspector.get_indexes("purchase_requests")}
        for index_name in [
            "ix_purchase_requests_priority",
            "ix_purchase_requests_status",
            "ix_purchase_requests_part_id",
            "ix_purchase_requests_service_order_id",
            "ix_purchase_requests_branch_id",
            "ix_purchase_requests_company_id",
        ]:
            if index_name in existing_indexes:
                op.drop_index(index_name, table_name="purchase_requests")
        op.drop_table("purchase_requests")
