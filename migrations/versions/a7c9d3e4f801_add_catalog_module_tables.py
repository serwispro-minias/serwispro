"""add catalog module tables

Revision ID: a7c9d3e4f801
Revises: f1b2c3d4e5f6
Create Date: 2026-08-04 10:10:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a7c9d3e4f801"
down_revision = "f1b2c3d4e5f6"
branch_labels = None
depends_on = None


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return index_name in {item["name"] for item in inspector.get_indexes(table_name)}


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


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("catalog_categories"):
        op.create_table(
            "catalog_categories",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("code", sa.String(length=60), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("kind", sa.String(length=20), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            *_base_columns(),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid"),
        )

    if not inspector.has_table("catalog_suppliers"):
        op.create_table(
            "catalog_suppliers",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("code", sa.String(length=60), nullable=False),
            sa.Column("name", sa.String(length=180), nullable=False),
            sa.Column("email", sa.String(length=120), nullable=True),
            sa.Column("phone", sa.String(length=50), nullable=True),
            sa.Column("address", sa.Text(), nullable=True),
            *_base_columns(),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid"),
        )

    if not inspector.has_table("catalog_manufacturers"):
        op.create_table(
            "catalog_manufacturers",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("code", sa.String(length=60), nullable=False),
            sa.Column("name", sa.String(length=180), nullable=False),
            sa.Column("website", sa.String(length=255), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            *_base_columns(),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid"),
        )

    if not inspector.has_table("catalog_parts"):
        op.create_table(
            "catalog_parts",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("code", sa.String(length=80), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("unit", sa.String(length=40), nullable=False),
            sa.Column("current_stock", sa.Numeric(12, 3), nullable=False),
            sa.Column("minimum_stock", sa.Numeric(12, 3), nullable=False),
            sa.Column("purchase_price_net", sa.Numeric(12, 2), nullable=False),
            sa.Column("sale_price_net", sa.Numeric(12, 2), nullable=False),
            sa.Column("vat_rate", sa.Numeric(5, 2), nullable=False),
            sa.Column("location", sa.String(length=120), nullable=True),
            sa.Column("is_sellable", sa.Boolean(), nullable=False),
            sa.Column("is_reservable", sa.Boolean(), nullable=False),
            sa.Column("category_id", sa.Integer(), nullable=True),
            sa.Column("supplier_id", sa.Integer(), nullable=True),
            sa.Column("manufacturer_id", sa.Integer(), nullable=True),
            *_base_columns(),
            sa.ForeignKeyConstraint(["category_id"], ["catalog_categories.id"]),
            sa.ForeignKeyConstraint(["supplier_id"], ["catalog_suppliers.id"]),
            sa.ForeignKeyConstraint(["manufacturer_id"], ["catalog_manufacturers.id"]),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid"),
        )

    if not inspector.has_table("catalog_materials"):
        op.create_table(
            "catalog_materials",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("code", sa.String(length=80), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("unit", sa.String(length=40), nullable=False),
            sa.Column("current_stock", sa.Numeric(12, 3), nullable=False),
            sa.Column("minimum_stock", sa.Numeric(12, 3), nullable=False),
            sa.Column("purchase_price_net", sa.Numeric(12, 2), nullable=False),
            sa.Column("default_usage_qty", sa.Numeric(12, 3), nullable=False),
            sa.Column("vat_rate", sa.Numeric(5, 2), nullable=False),
            sa.Column("location", sa.String(length=120), nullable=True),
            sa.Column("auto_issue_on_order", sa.Boolean(), nullable=False),
            sa.Column("category_id", sa.Integer(), nullable=True),
            sa.Column("supplier_id", sa.Integer(), nullable=True),
            sa.Column("manufacturer_id", sa.Integer(), nullable=True),
            *_base_columns(),
            sa.ForeignKeyConstraint(["category_id"], ["catalog_categories.id"]),
            sa.ForeignKeyConstraint(["supplier_id"], ["catalog_suppliers.id"]),
            sa.ForeignKeyConstraint(["manufacturer_id"], ["catalog_manufacturers.id"]),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid"),
        )

    if not inspector.has_table("catalog_services"):
        op.create_table(
            "catalog_services",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("code", sa.String(length=80), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("default_price_net", sa.Numeric(12, 2), nullable=False),
            sa.Column("vat_rate", sa.Numeric(5, 2), nullable=False),
            sa.Column("standard_duration_minutes", sa.Integer(), nullable=False),
            sa.Column("is_sellable", sa.Boolean(), nullable=False),
            sa.Column("category_id", sa.Integer(), nullable=True),
            *_base_columns(),
            sa.ForeignKeyConstraint(["category_id"], ["catalog_categories.id"]),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid"),
        )

    if not inspector.has_table("catalog_stock_movements"):
        op.create_table(
            "catalog_stock_movements",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("item_type", sa.String(length=20), nullable=False),
            sa.Column("part_id", sa.Integer(), nullable=True),
            sa.Column("material_id", sa.Integer(), nullable=True),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("service_order_id", sa.Integer(), nullable=True),
            sa.Column("movement_type", sa.String(length=20), nullable=False),
            sa.Column("operation_at", sa.DateTime(), nullable=False),
            sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
            sa.Column("stock_before", sa.Numeric(12, 3), nullable=False),
            sa.Column("stock_after", sa.Numeric(12, 3), nullable=False),
            sa.Column("reference_type", sa.String(length=40), nullable=True),
            sa.Column("reference_id", sa.String(length=80), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            *_base_columns(),
            sa.ForeignKeyConstraint(["part_id"], ["catalog_parts.id"]),
            sa.ForeignKeyConstraint(["material_id"], ["catalog_materials.id"]),
            sa.ForeignKeyConstraint(["service_order_id"], ["service_orders.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid"),
        )

    if not inspector.has_table("service_order_part_reservations"):
        op.create_table(
            "service_order_part_reservations",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("service_order_id", sa.Integer(), nullable=False),
            sa.Column("part_id", sa.Integer(), nullable=False),
            sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            *_base_columns(),
            sa.ForeignKeyConstraint(["service_order_id"], ["service_orders.id"]),
            sa.ForeignKeyConstraint(["part_id"], ["catalog_parts.id"]),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid"),
        )

    if not inspector.has_table("service_order_material_usages"):
        op.create_table(
            "service_order_material_usages",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("service_order_id", sa.Integer(), nullable=False),
            sa.Column("material_id", sa.Integer(), nullable=False),
            sa.Column("stock_movement_id", sa.Integer(), nullable=True),
            sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
            sa.Column("unit_net_price", sa.Numeric(12, 2), nullable=False),
            sa.Column("vat_rate", sa.Numeric(5, 2), nullable=False),
            sa.Column("net_value", sa.Numeric(12, 2), nullable=False),
            sa.Column("vat_value", sa.Numeric(12, 2), nullable=False),
            sa.Column("gross_value", sa.Numeric(12, 2), nullable=False),
            *_base_columns(),
            sa.ForeignKeyConstraint(["service_order_id"], ["service_orders.id"]),
            sa.ForeignKeyConstraint(["material_id"], ["catalog_materials.id"]),
            sa.ForeignKeyConstraint(["stock_movement_id"], ["catalog_stock_movements.id"]),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid"),
        )

    if not inspector.has_table("service_order_service_lines"):
        op.create_table(
            "service_order_service_lines",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("service_order_id", sa.Integer(), nullable=False),
            sa.Column("service_item_id", sa.Integer(), nullable=False),
            sa.Column("quantity", sa.Numeric(10, 2), nullable=False),
            sa.Column("unit_net_price", sa.Numeric(12, 2), nullable=False),
            sa.Column("vat_rate", sa.Numeric(5, 2), nullable=False),
            sa.Column("net_value", sa.Numeric(12, 2), nullable=False),
            sa.Column("vat_value", sa.Numeric(12, 2), nullable=False),
            sa.Column("gross_value", sa.Numeric(12, 2), nullable=False),
            sa.Column("duration_minutes", sa.Integer(), nullable=False),
            *_base_columns(),
            sa.ForeignKeyConstraint(["service_order_id"], ["service_orders.id"]),
            sa.ForeignKeyConstraint(["service_item_id"], ["catalog_services.id"]),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid"),
        )

    inspector = sa.inspect(bind)
    indexes = [
        ("catalog_categories", "ix_catalog_categories_company_id", ["company_id"]),
        ("catalog_categories", "ix_catalog_categories_branch_id", ["branch_id"]),
        ("catalog_categories", "ix_catalog_categories_code", ["code"]),
        ("catalog_categories", "ix_catalog_categories_name", ["name"]),
        ("catalog_categories", "ix_catalog_categories_kind", ["kind"]),
        ("catalog_suppliers", "ix_catalog_suppliers_company_id", ["company_id"]),
        ("catalog_suppliers", "ix_catalog_suppliers_branch_id", ["branch_id"]),
        ("catalog_suppliers", "ix_catalog_suppliers_code", ["code"]),
        ("catalog_suppliers", "ix_catalog_suppliers_name", ["name"]),
        ("catalog_manufacturers", "ix_catalog_manufacturers_company_id", ["company_id"]),
        ("catalog_manufacturers", "ix_catalog_manufacturers_branch_id", ["branch_id"]),
        ("catalog_manufacturers", "ix_catalog_manufacturers_code", ["code"]),
        ("catalog_manufacturers", "ix_catalog_manufacturers_name", ["name"]),
        ("catalog_parts", "ix_catalog_parts_company_id", ["company_id"]),
        ("catalog_parts", "ix_catalog_parts_branch_id", ["branch_id"]),
        ("catalog_parts", "ix_catalog_parts_code", ["code"]),
        ("catalog_parts", "ix_catalog_parts_name", ["name"]),
        ("catalog_parts", "ix_catalog_parts_category_id", ["category_id"]),
        ("catalog_parts", "ix_catalog_parts_supplier_id", ["supplier_id"]),
        ("catalog_parts", "ix_catalog_parts_manufacturer_id", ["manufacturer_id"]),
        ("catalog_materials", "ix_catalog_materials_company_id", ["company_id"]),
        ("catalog_materials", "ix_catalog_materials_branch_id", ["branch_id"]),
        ("catalog_materials", "ix_catalog_materials_code", ["code"]),
        ("catalog_materials", "ix_catalog_materials_name", ["name"]),
        ("catalog_materials", "ix_catalog_materials_category_id", ["category_id"]),
        ("catalog_materials", "ix_catalog_materials_supplier_id", ["supplier_id"]),
        ("catalog_materials", "ix_catalog_materials_manufacturer_id", ["manufacturer_id"]),
        ("catalog_services", "ix_catalog_services_company_id", ["company_id"]),
        ("catalog_services", "ix_catalog_services_branch_id", ["branch_id"]),
        ("catalog_services", "ix_catalog_services_code", ["code"]),
        ("catalog_services", "ix_catalog_services_name", ["name"]),
        ("catalog_services", "ix_catalog_services_category_id", ["category_id"]),
        ("catalog_stock_movements", "ix_catalog_movements_company_id", ["company_id"]),
        ("catalog_stock_movements", "ix_catalog_movements_branch_id", ["branch_id"]),
        ("catalog_stock_movements", "ix_catalog_movements_item_type", ["item_type"]),
        ("catalog_stock_movements", "ix_catalog_movements_part_id", ["part_id"]),
        ("catalog_stock_movements", "ix_catalog_movements_material_id", ["material_id"]),
        ("catalog_stock_movements", "ix_catalog_movements_order_id", ["service_order_id"]),
        ("catalog_stock_movements", "ix_catalog_movements_created_at", ["operation_at"]),
        ("service_order_part_reservations", "ix_so_part_res_company_id", ["company_id"]),
        ("service_order_part_reservations", "ix_so_part_res_branch_id", ["branch_id"]),
        ("service_order_part_reservations", "ix_so_part_res_order_id", ["service_order_id"]),
        ("service_order_part_reservations", "ix_so_part_res_part_id", ["part_id"]),
        ("service_order_part_reservations", "ix_so_part_res_status", ["status"]),
        ("service_order_material_usages", "ix_so_mat_usage_company_id", ["company_id"]),
        ("service_order_material_usages", "ix_so_mat_usage_branch_id", ["branch_id"]),
        ("service_order_material_usages", "ix_so_mat_usage_order_id", ["service_order_id"]),
        ("service_order_material_usages", "ix_so_mat_usage_material_id", ["material_id"]),
        ("service_order_service_lines", "ix_so_service_line_company_id", ["company_id"]),
        ("service_order_service_lines", "ix_so_service_line_branch_id", ["branch_id"]),
        ("service_order_service_lines", "ix_so_service_line_order_id", ["service_order_id"]),
        ("service_order_service_lines", "ix_so_service_line_service_id", ["service_item_id"]),
    ]

    for table_name, index_name, columns in indexes:
        if not _has_index(inspector, table_name, index_name):
            op.create_index(index_name, table_name, columns, unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    drop_indexes_order = [
        ("service_order_service_lines", "ix_so_service_line_service_id"),
        ("service_order_service_lines", "ix_so_service_line_order_id"),
        ("service_order_service_lines", "ix_so_service_line_branch_id"),
        ("service_order_service_lines", "ix_so_service_line_company_id"),
        ("service_order_material_usages", "ix_so_mat_usage_material_id"),
        ("service_order_material_usages", "ix_so_mat_usage_order_id"),
        ("service_order_material_usages", "ix_so_mat_usage_branch_id"),
        ("service_order_material_usages", "ix_so_mat_usage_company_id"),
        ("service_order_part_reservations", "ix_so_part_res_status"),
        ("service_order_part_reservations", "ix_so_part_res_part_id"),
        ("service_order_part_reservations", "ix_so_part_res_order_id"),
        ("service_order_part_reservations", "ix_so_part_res_branch_id"),
        ("service_order_part_reservations", "ix_so_part_res_company_id"),
        ("catalog_stock_movements", "ix_catalog_movements_created_at"),
        ("catalog_stock_movements", "ix_catalog_movements_order_id"),
        ("catalog_stock_movements", "ix_catalog_movements_material_id"),
        ("catalog_stock_movements", "ix_catalog_movements_part_id"),
        ("catalog_stock_movements", "ix_catalog_movements_item_type"),
        ("catalog_stock_movements", "ix_catalog_movements_branch_id"),
        ("catalog_stock_movements", "ix_catalog_movements_company_id"),
        ("catalog_services", "ix_catalog_services_category_id"),
        ("catalog_services", "ix_catalog_services_name"),
        ("catalog_services", "ix_catalog_services_code"),
        ("catalog_services", "ix_catalog_services_branch_id"),
        ("catalog_services", "ix_catalog_services_company_id"),
        ("catalog_materials", "ix_catalog_materials_manufacturer_id"),
        ("catalog_materials", "ix_catalog_materials_supplier_id"),
        ("catalog_materials", "ix_catalog_materials_category_id"),
        ("catalog_materials", "ix_catalog_materials_name"),
        ("catalog_materials", "ix_catalog_materials_code"),
        ("catalog_materials", "ix_catalog_materials_branch_id"),
        ("catalog_materials", "ix_catalog_materials_company_id"),
        ("catalog_parts", "ix_catalog_parts_manufacturer_id"),
        ("catalog_parts", "ix_catalog_parts_supplier_id"),
        ("catalog_parts", "ix_catalog_parts_category_id"),
        ("catalog_parts", "ix_catalog_parts_name"),
        ("catalog_parts", "ix_catalog_parts_code"),
        ("catalog_parts", "ix_catalog_parts_branch_id"),
        ("catalog_parts", "ix_catalog_parts_company_id"),
        ("catalog_manufacturers", "ix_catalog_manufacturers_name"),
        ("catalog_manufacturers", "ix_catalog_manufacturers_code"),
        ("catalog_manufacturers", "ix_catalog_manufacturers_branch_id"),
        ("catalog_manufacturers", "ix_catalog_manufacturers_company_id"),
        ("catalog_suppliers", "ix_catalog_suppliers_name"),
        ("catalog_suppliers", "ix_catalog_suppliers_code"),
        ("catalog_suppliers", "ix_catalog_suppliers_branch_id"),
        ("catalog_suppliers", "ix_catalog_suppliers_company_id"),
        ("catalog_categories", "ix_catalog_categories_kind"),
        ("catalog_categories", "ix_catalog_categories_name"),
        ("catalog_categories", "ix_catalog_categories_code"),
        ("catalog_categories", "ix_catalog_categories_branch_id"),
        ("catalog_categories", "ix_catalog_categories_company_id"),
    ]

    for table_name, index_name in drop_indexes_order:
        if inspector.has_table(table_name):
            existing = {item["name"] for item in inspector.get_indexes(table_name)}
            if index_name in existing:
                op.drop_index(index_name, table_name=table_name)

    for table_name in [
        "service_order_service_lines",
        "service_order_material_usages",
        "service_order_part_reservations",
        "catalog_stock_movements",
        "catalog_services",
        "catalog_materials",
        "catalog_parts",
        "catalog_manufacturers",
        "catalog_suppliers",
        "catalog_categories",
    ]:
        if inspector.has_table(table_name):
            op.drop_table(table_name)
