"""inventory module tables

Revision ID: b2f4a61c9d3e
Revises: 4d7b1ce2f901
Create Date: 2026-08-03 18:30:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b2f4a61c9d3e"
down_revision = "4d7b1ce2f901"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("inventory_parts"):
        op.create_table(
            "inventory_parts",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("part_code", sa.String(length=80), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("category", sa.String(length=120), nullable=True),
            sa.Column("manufacturer", sa.String(length=120), nullable=True),
            sa.Column("catalog_number", sa.String(length=120), nullable=True),
            sa.Column("barcode", sa.String(length=120), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("unit", sa.String(length=40), nullable=False),
            sa.Column("minimum_stock", sa.Numeric(precision=12, scale=3), nullable=False),
            sa.Column("current_stock", sa.Numeric(precision=12, scale=3), nullable=False),
            sa.Column("location", sa.String(length=120), nullable=True),
            sa.Column("purchase_price_net", sa.Numeric(precision=12, scale=2), nullable=False),
            sa.Column("sale_price_net", sa.Numeric(precision=12, scale=2), nullable=False),
            sa.Column("vat_rate", sa.Numeric(precision=5, scale=2), nullable=False),
            sa.Column("supplier", sa.String(length=180), nullable=True),
            sa.Column("image_path", sa.String(length=500), nullable=True),
            sa.Column("is_record_active", sa.Boolean(), nullable=False),
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
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid"),
            sa.UniqueConstraint("company_id", "part_code", name="uq_inventory_parts_company_code"),
        )

    inspector = sa.inspect(bind)
    part_indexes = set()
    if inspector.has_table("inventory_parts"):
        part_indexes = {index["name"] for index in inspector.get_indexes("inventory_parts")}

    for index_name, columns in [
        ("ix_inventory_parts_company_id", ["company_id"]),
        ("ix_inventory_parts_branch_id", ["branch_id"]),
        ("ix_inventory_parts_code", ["part_code"]),
        ("ix_inventory_parts_name", ["name"]),
        ("ix_inventory_parts_catalog_number", ["catalog_number"]),
        ("ix_inventory_parts_barcode", ["barcode"]),
        ("ix_inventory_parts_manufacturer", ["manufacturer"]),
    ]:
        if index_name not in part_indexes:
            op.create_index(index_name, "inventory_parts", columns, unique=False)

    inspector = sa.inspect(bind)
    if not inspector.has_table("inventory_stock_operations"):
        op.create_table(
            "inventory_stock_operations",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("part_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("service_order_id", sa.Integer(), nullable=True),
            sa.Column("operation_type", sa.String(length=40), nullable=False),
            sa.Column("operation_at", sa.DateTime(), nullable=False),
            sa.Column("quantity", sa.Numeric(precision=12, scale=3), nullable=False),
            sa.Column("stock_before", sa.Numeric(precision=12, scale=3), nullable=False),
            sa.Column("stock_after", sa.Numeric(precision=12, scale=3), nullable=False),
            sa.Column("document_number", sa.String(length=120), nullable=True),
            sa.Column("comment", sa.Text(), nullable=True),
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
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(["part_id"], ["inventory_parts.id"]),
            sa.ForeignKeyConstraint(["service_order_id"], ["service_orders.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid"),
        )

    inspector = sa.inspect(bind)
    operation_indexes = set()
    if inspector.has_table("inventory_stock_operations"):
        operation_indexes = {index["name"] for index in inspector.get_indexes("inventory_stock_operations")}

    for index_name, columns in [
        ("ix_inv_ops_company_id", ["company_id"]),
        ("ix_inv_ops_branch_id", ["branch_id"]),
        ("ix_inv_ops_part_id", ["part_id"]),
        ("ix_inv_ops_order_id", ["service_order_id"]),
        ("ix_inv_ops_operation_at", ["operation_at"]),
    ]:
        if index_name not in operation_indexes:
            op.create_index(index_name, "inventory_stock_operations", columns, unique=False)

    inspector = sa.inspect(bind)
    if not inspector.has_table("service_order_part_usages"):
        op.create_table(
            "service_order_part_usages",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("service_order_id", sa.Integer(), nullable=False),
            sa.Column("part_id", sa.Integer(), nullable=False),
            sa.Column("stock_operation_id", sa.Integer(), nullable=True),
            sa.Column("quantity", sa.Numeric(precision=12, scale=3), nullable=False),
            sa.Column("unit_net_price", sa.Numeric(precision=12, scale=2), nullable=False),
            sa.Column("vat_rate", sa.Numeric(precision=5, scale=2), nullable=False),
            sa.Column("net_value", sa.Numeric(precision=12, scale=2), nullable=False),
            sa.Column("vat_value", sa.Numeric(precision=12, scale=2), nullable=False),
            sa.Column("gross_value", sa.Numeric(precision=12, scale=2), nullable=False),
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
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(["part_id"], ["inventory_parts.id"]),
            sa.ForeignKeyConstraint(["service_order_id"], ["service_orders.id"]),
            sa.ForeignKeyConstraint(["stock_operation_id"], ["inventory_stock_operations.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid"),
        )

    inspector = sa.inspect(bind)
    usage_indexes = set()
    if inspector.has_table("service_order_part_usages"):
        usage_indexes = {index["name"] for index in inspector.get_indexes("service_order_part_usages")}

    for index_name, columns in [
        ("ix_so_part_usage_company_id", ["company_id"]),
        ("ix_so_part_usage_branch_id", ["branch_id"]),
        ("ix_so_part_usage_order_id", ["service_order_id"]),
        ("ix_so_part_usage_part_id", ["part_id"]),
    ]:
        if index_name not in usage_indexes:
            op.create_index(index_name, "service_order_part_usages", columns, unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("service_order_part_usages"):
        indexes = {index["name"] for index in inspector.get_indexes("service_order_part_usages")}
        for index_name in [
            "ix_so_part_usage_part_id",
            "ix_so_part_usage_order_id",
            "ix_so_part_usage_branch_id",
            "ix_so_part_usage_company_id",
        ]:
            if index_name in indexes:
                op.drop_index(index_name, table_name="service_order_part_usages")
        op.drop_table("service_order_part_usages")

    inspector = sa.inspect(bind)
    if inspector.has_table("inventory_stock_operations"):
        indexes = {index["name"] for index in inspector.get_indexes("inventory_stock_operations")}
        for index_name in [
            "ix_inv_ops_operation_at",
            "ix_inv_ops_order_id",
            "ix_inv_ops_part_id",
            "ix_inv_ops_branch_id",
            "ix_inv_ops_company_id",
        ]:
            if index_name in indexes:
                op.drop_index(index_name, table_name="inventory_stock_operations")
        op.drop_table("inventory_stock_operations")

    inspector = sa.inspect(bind)
    if inspector.has_table("inventory_parts"):
        indexes = {index["name"] for index in inspector.get_indexes("inventory_parts")}
        for index_name in [
            "ix_inventory_parts_manufacturer",
            "ix_inventory_parts_barcode",
            "ix_inventory_parts_catalog_number",
            "ix_inventory_parts_name",
            "ix_inventory_parts_code",
            "ix_inventory_parts_branch_id",
            "ix_inventory_parts_company_id",
        ]:
            if index_name in indexes:
                op.drop_index(index_name, table_name="inventory_parts")
        op.drop_table("inventory_parts")
