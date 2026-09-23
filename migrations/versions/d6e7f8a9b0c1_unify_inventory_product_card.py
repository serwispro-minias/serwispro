"""unify warehouse products, categories, VAT and suppliers

Revision ID: d6e7f8a9b0c1
Revises: ab1c2d3e4f50
"""

from alembic import op
import sqlalchemy as sa

revision = "d6e7f8a9b0c1"
down_revision = "ab1c2d3e4f50"
branch_labels = None
depends_on = None


def _columns(inspector, table_name):
    return {column["name"] for column in inspector.get_columns(table_name)} if inspector.has_table(table_name) else set()


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("catalog_categories") and not inspector.has_table("product_categories"):
        op.rename_table("catalog_categories", "product_categories")
    inspector = sa.inspect(bind)
    if inspector.has_table("product_categories") and "is_active" not in _columns(inspector, "product_categories"):
        op.add_column("product_categories", sa.Column("is_active", sa.Boolean(), nullable=True))
        op.execute(sa.text("UPDATE product_categories SET is_active = 1 WHERE is_active IS NULL"))
        op.alter_column("product_categories", "is_active", nullable=False)

    if inspector.has_table("catalog_suppliers") and not inspector.has_table("suppliers"):
        op.rename_table("catalog_suppliers", "suppliers")
    inspector = sa.inspect(bind)
    if inspector.has_table("suppliers") and "is_active" not in _columns(inspector, "suppliers"):
        op.add_column("suppliers", sa.Column("is_active", sa.Boolean(), nullable=True))
        active_column = "is_supplier_active" if "is_supplier_active" in _columns(inspector, "suppliers") else "is_active"
        op.execute(sa.text(f"UPDATE suppliers SET is_active = COALESCE({active_column}, 1) WHERE is_active IS NULL"))
        op.alter_column("suppliers", "is_active", nullable=False)

    inspector = sa.inspect(bind)
    if inspector.has_table("catalog_parts") and not inspector.has_table("inventory_items"):
        op.rename_table("catalog_parts", "inventory_items")
    inspector = sa.inspect(bind)
    if not inspector.has_table("inventory_items"):
        op.create_table(
            "inventory_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("code", sa.String(80), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("barcode", sa.String(64)),
            sa.Column("current_stock", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("purchase_price_net", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("sale_price_net", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("category_id", sa.Integer(), nullable=False),
            sa.Column("vat_id", sa.Integer(), nullable=False),
            sa.Column("company_id", sa.Integer(), nullable=False),
            sa.Column("branch_id", sa.Integer()),
            sa.Column("uuid", sa.String(36), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("created_by", sa.Integer()),
            sa.Column("updated_by", sa.Integer()),
            sa.Column("deleted_at", sa.DateTime()),
            sa.Column("deleted_by", sa.Integer()),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        )

    inspector = sa.inspect(bind)
    if not inspector.has_table("vat_rates"):
        op.create_table(
            "vat_rates",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("code", sa.String(20), nullable=False),
            sa.Column("rate", sa.Numeric(5, 2), nullable=False),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("company_id", sa.Integer(), nullable=False),
            sa.Column("branch_id", sa.Integer()),
            sa.Column("uuid", sa.String(36), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("created_by", sa.Integer()),
            sa.Column("updated_by", sa.Integer()),
            sa.Column("deleted_at", sa.DateTime()),
            sa.Column("deleted_by", sa.Integer()),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        )
        op.execute(sa.text("INSERT INTO vat_rates (code, rate, is_default, is_active, company_id, uuid, created_at, updated_at, version) SELECT '23', 23, 1, 1, id, lower(hex(randomblob(16))), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1 FROM companies"))
    else:
        existing = _columns(inspector, "vat_rates")
        if "is_default" not in existing:
            op.add_column("vat_rates", sa.Column("is_default", sa.Boolean(), nullable=True))
            op.execute(sa.text("UPDATE vat_rates SET is_default = 0 WHERE is_default IS NULL"))
        if "is_active" not in existing:
            op.add_column("vat_rates", sa.Column("is_active", sa.Boolean(), nullable=True))
            op.execute(sa.text("UPDATE vat_rates SET is_active = 1 WHERE is_active IS NULL"))

    inspector = sa.inspect(bind)
    item_columns = _columns(inspector, "inventory_items")
    if "barcode" not in item_columns:
        op.add_column("inventory_items", sa.Column("barcode", sa.String(64), nullable=True))
        item_columns = _columns(sa.inspect(bind), "inventory_items")
    if "vat_id" not in item_columns:
        op.add_column("inventory_items", sa.Column("vat_id", sa.Integer(), nullable=True))
    op.execute(sa.text("UPDATE inventory_items SET vat_id = (SELECT MIN(v.id) FROM vat_rates v WHERE v.company_id = inventory_items.company_id AND v.is_active = 1) WHERE vat_id IS NULL"))
    op.execute(sa.text("UPDATE inventory_items SET vat_id = (SELECT MIN(v.id) FROM vat_rates v WHERE v.is_active = 1) WHERE vat_id IS NULL"))
    op.execute(sa.text("UPDATE inventory_items SET category_id = (SELECT MIN(c.id) FROM product_categories c WHERE c.company_id = inventory_items.company_id) WHERE category_id IS NULL"))

    inspector = sa.inspect(bind)
    if inspector.has_table("inventory_parts"):
        op.execute(sa.text("INSERT INTO inventory_items (code, name, barcode, description, unit, current_stock, minimum_stock, purchase_price_net, sale_price_net, vat_rate, is_sellable, is_reservable, category_id, vat_id, company_id, branch_id, uuid, created_at, updated_at, is_active, version) SELECT p.part_code, p.name, p.barcode, p.description, 'szt.', CAST(p.current_stock AS INTEGER), 0, p.purchase_price_net, p.sale_price_net, p.vat_rate, 1, 1, (SELECT MIN(c.id) FROM product_categories c WHERE c.company_id = p.company_id), (SELECT MIN(v.id) FROM vat_rates v WHERE v.company_id = p.company_id AND v.is_active = 1), p.company_id, p.branch_id, p.uuid, p.created_at, p.updated_at, p.is_active, p.version FROM inventory_parts p WHERE NOT EXISTS (SELECT 1 FROM inventory_items i WHERE i.code = p.part_code AND i.company_id = p.company_id)"))

    op.execute(sa.text("UPDATE inventory_items SET current_stock = 0 WHERE current_stock IS NULL"))
    op.execute(sa.text("UPDATE inventory_items SET purchase_price_net = 0 WHERE purchase_price_net IS NULL"))
    op.execute(sa.text("UPDATE inventory_items SET sale_price_net = 0 WHERE sale_price_net IS NULL"))


def downgrade():
    pass
