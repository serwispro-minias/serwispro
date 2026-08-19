"""add purchase orders module

Revision ID: 7e8f9a0b1c2d
Revises: 6d4c8d3c9f10, a91d4ef62c70
"""

from alembic import op
import sqlalchemy as sa

revision = "7e8f9a0b1c2d"
down_revision = ("6d4c8d3c9f10", "a91d4ef62c70")
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    supplier_columns = {
        "tax_id": sa.Column("tax_id", sa.String(20), nullable=True),
        "contact_person": sa.Column("contact_person", sa.String(180), nullable=True),
        "website": sa.Column("website", sa.String(255), nullable=True),
        "default_lead_time_days": sa.Column("default_lead_time_days", sa.Integer(), nullable=True),
        "notes": sa.Column("notes", sa.Text(), nullable=True),
        "is_supplier_active": sa.Column("is_supplier_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    }
    if inspector.has_table("catalog_suppliers"):
        existing = {column["name"] for column in inspector.get_columns("catalog_suppliers")}
        for name, column in supplier_columns.items():
            if name not in existing:
                op.add_column("catalog_suppliers", column)
        op.alter_column("catalog_suppliers", "is_supplier_active", server_default=None)

    common = [
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
    if not inspector.has_table("purchase_orders"):
        op.create_table(
            "purchase_orders",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("po_number", sa.String(60), nullable=False, unique=True),
            sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("catalog_suppliers.id"), nullable=False),
            sa.Column("status", sa.String(24), nullable=False),
            sa.Column("order_date", sa.Date(), nullable=False),
            sa.Column("expected_delivery_date", sa.Date(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("total_net", sa.Numeric(14, 2), nullable=False),
            sa.Column("total_vat", sa.Numeric(14, 2), nullable=False),
            sa.Column("total_gross", sa.Numeric(14, 2), nullable=False),
            sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
            sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id"), nullable=True),
            *common,
        )
    if not inspector.has_table("purchase_order_items"):
        op.create_table(
            "purchase_order_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("purchase_order_id", sa.Integer(), sa.ForeignKey("purchase_orders.id"), nullable=False),
            sa.Column("part_id", sa.Integer(), sa.ForeignKey("catalog_parts.id"), nullable=False),
            sa.Column("code_snapshot", sa.String(80), nullable=False),
            sa.Column("manufacturer_snapshot", sa.String(180), nullable=True),
            sa.Column("quantity_ordered", sa.Numeric(12, 3), nullable=False),
            sa.Column("quantity_received", sa.Numeric(12, 3), nullable=False),
            sa.Column("unit", sa.String(40), nullable=False),
            sa.Column("unit_price_net", sa.Numeric(12, 2), nullable=False),
            sa.Column("vat_rate", sa.Numeric(5, 2), nullable=False),
            sa.Column("total_net", sa.Numeric(14, 2), nullable=False),
            sa.Column("total_vat", sa.Numeric(14, 2), nullable=False),
            sa.Column("total_gross", sa.Numeric(14, 2), nullable=False),
            sa.Column("expected_delivery_date", sa.Date(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            *common,
        )
    if not inspector.has_table("purchase_order_demand_links"):
        op.create_table(
            "purchase_order_demand_links",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("purchase_order_item_id", sa.Integer(), sa.ForeignKey("purchase_order_items.id"), nullable=False),
            sa.Column("part_demand_id", sa.Integer(), sa.ForeignKey("part_demands.id"), nullable=False),
            sa.Column("allocated_quantity", sa.Numeric(12, 3), nullable=False),
            sa.Column("received_quantity", sa.Numeric(12, 3), nullable=False),
            *common,
        )
    if not inspector.has_table("purchase_order_history"):
        op.create_table(
            "purchase_order_history",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("purchase_order_id", sa.Integer(), sa.ForeignKey("purchase_orders.id"), nullable=False),
            sa.Column("event_type", sa.String(30), nullable=False),
            sa.Column("old_status", sa.String(24), nullable=True),
            sa.Column("new_status", sa.String(24), nullable=True),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("changed_at", sa.DateTime(), nullable=False),
            sa.Column("changed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            *common,
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in ("purchase_order_history", "purchase_order_demand_links", "purchase_order_items", "purchase_orders"):
        if inspector.has_table(table):
            op.drop_table(table)
    if inspector.has_table("catalog_suppliers"):
        existing = {column["name"] for column in inspector.get_columns("catalog_suppliers")}
        for name in ("is_supplier_active", "notes", "default_lead_time_days", "website", "contact_person", "tax_id"):
            if name in existing:
                op.drop_column("catalog_suppliers", name)
