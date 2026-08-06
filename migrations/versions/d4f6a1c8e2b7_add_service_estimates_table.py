"""add service estimates table

Revision ID: d4f6a1c8e2b7
Revises: f1b2c3d4e5f6
Create Date: 2026-08-06 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d4f6a1c8e2b7"
down_revision = "f1b2c3d4e5f6"
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


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return index_name in {item["name"] for item in inspector.get_indexes(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("service_estimates"):
        op.create_table(
            "service_estimates",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("service_order_id", sa.Integer(), nullable=False),
            sa.Column("parent_estimate_id", sa.Integer(), nullable=True),
            sa.Column("version_number", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("valid_until", sa.Date(), nullable=True),
            sa.Column("sent_at", sa.DateTime(), nullable=True),
            sa.Column("approved_at", sa.DateTime(), nullable=True),
            sa.Column("rejected_at", sa.DateTime(), nullable=True),
            sa.Column("discount_total", sa.Numeric(12, 2), nullable=False),
            sa.Column("parts_net", sa.Numeric(12, 2), nullable=False),
            sa.Column("materials_net", sa.Numeric(12, 2), nullable=False),
            sa.Column("services_net", sa.Numeric(12, 2), nullable=False),
            sa.Column("net_total", sa.Numeric(12, 2), nullable=False),
            sa.Column("vat_total", sa.Numeric(12, 2), nullable=False),
            sa.Column("gross_total", sa.Numeric(12, 2), nullable=False),
            *_base_columns(),
            sa.ForeignKeyConstraint(["parent_estimate_id"], ["service_estimates.id"]),
            sa.ForeignKeyConstraint(["service_order_id"], ["service_orders.id"]),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid"),
            sa.UniqueConstraint("service_order_id", "version_number", name="uq_service_estimates_order_version"),
        )

    if not inspector.has_table("service_estimate_items"):
        op.create_table(
            "service_estimate_items",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("estimate_id", sa.Integer(), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False),
            sa.Column("source_type", sa.String(length=20), nullable=False),
            sa.Column("source_id", sa.Integer(), nullable=True),
            sa.Column("code", sa.String(length=80), nullable=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
            sa.Column("unit", sa.String(length=40), nullable=False),
            sa.Column("unit_net_price", sa.Numeric(12, 2), nullable=False),
            sa.Column("discount_percent", sa.Numeric(5, 2), nullable=False),
            sa.Column("vat_rate", sa.Numeric(5, 2), nullable=False),
            sa.Column("net_value", sa.Numeric(12, 2), nullable=False),
            sa.Column("vat_value", sa.Numeric(12, 2), nullable=False),
            sa.Column("gross_value", sa.Numeric(12, 2), nullable=False),
            sa.Column("is_manual", sa.Boolean(), nullable=False),
            *_base_columns(),
            sa.ForeignKeyConstraint(["estimate_id"], ["service_estimates.id"]),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid"),
        )

    inspector = sa.inspect(bind)
    if inspector.has_table("service_estimates"):
        for index_name, columns in [
            ("ix_service_estimates_company_id", ["company_id"]),
            ("ix_service_estimates_branch_id", ["branch_id"]),
            ("ix_service_estimates_order_id", ["service_order_id"]),
            ("ix_service_estimates_version_number", ["version_number"]),
            ("ix_service_estimates_status", ["status"]),
        ]:
            if not _has_index(inspector, "service_estimates", index_name):
                op.create_index(index_name, "service_estimates", columns, unique=False)

    if inspector.has_table("service_estimate_items"):
        for index_name, columns in [
            ("ix_service_estimate_items_company_id", ["company_id"]),
            ("ix_service_estimate_items_branch_id", ["branch_id"]),
            ("ix_service_estimate_items_estimate_id", ["estimate_id"]),
            ("ix_service_estimate_items_source_type", ["source_type"]),
            ("ix_service_estimate_items_sort_order", ["sort_order"]),
        ]:
            if not _has_index(inspector, "service_estimate_items", index_name):
                op.create_index(index_name, "service_estimate_items", columns, unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("service_estimate_items"):
        for index_name in ["ix_service_estimate_items_sort_order", "ix_service_estimate_items_source_type", "ix_service_estimate_items_estimate_id", "ix_service_estimate_items_branch_id", "ix_service_estimate_items_company_id"]:
            if _has_index(inspector, "service_estimate_items", index_name):
                op.drop_index(index_name, table_name="service_estimate_items")
        op.drop_table("service_estimate_items")

    if inspector.has_table("service_estimates"):
        for index_name in ["ix_service_estimates_status", "ix_service_estimates_version_number", "ix_service_estimates_order_id", "ix_service_estimates_branch_id", "ix_service_estimates_company_id"]:
            if _has_index(inspector, "service_estimates", index_name):
                op.drop_index(index_name, table_name="service_estimates")
        op.drop_table("service_estimates")