"""add inventory reservation tracking

Revision ID: 6d4c8d3c9f10
Revises: 1d6c9b0d2e6f
Create Date: 2026-08-18 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "6d4c8d3c9f10"
down_revision = "1d6c9b0d2e6f"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("inventory_parts"):
        columns = {col["name"] for col in inspector.get_columns("inventory_parts")}
        if "quantity_total" not in columns:
            op.add_column("inventory_parts", sa.Column("quantity_total", sa.Numeric(precision=12, scale=3), nullable=False, server_default="0"))
        if "quantity_reserved" not in columns:
            op.add_column("inventory_parts", sa.Column("quantity_reserved", sa.Numeric(precision=12, scale=3), nullable=False, server_default="0"))

        op.execute("UPDATE inventory_parts SET quantity_total = current_stock WHERE quantity_total IS NULL OR quantity_total = 0")
        op.execute("UPDATE inventory_parts SET quantity_reserved = 0 WHERE quantity_reserved IS NULL")
        op.alter_column("inventory_parts", "quantity_total", server_default=None)
        op.alter_column("inventory_parts", "quantity_reserved", server_default=None)

    if not inspector.has_table("inventory_reservations"):
        op.create_table(
            "inventory_reservations",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("inventory_item_id", sa.Integer(), nullable=False),
            sa.Column("service_order_id", sa.Integer(), nullable=False),
            sa.Column("quantity", sa.Numeric(precision=12, scale=3), nullable=False),
            sa.Column("reserved_by", sa.Integer(), nullable=True),
            sa.Column("reserved_at", sa.DateTime(), nullable=False),
            sa.Column("released_at", sa.DateTime(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False),
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
            sa.ForeignKeyConstraint(["inventory_item_id"], ["inventory_parts.id"]),
            sa.ForeignKeyConstraint(["service_order_id"], ["service_orders.id"]),
            sa.ForeignKeyConstraint(["reserved_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid"),
        )

    inspector = sa.inspect(bind)
    for index_name, columns in [
        ("ix_inventory_reservations_company_id", ["company_id"]),
        ("ix_inventory_reservations_branch_id", ["branch_id"]),
        ("ix_inventory_reservations_item_id", ["inventory_item_id"]),
        ("ix_inventory_reservations_order_id", ["service_order_id"]),
        ("ix_inventory_reservations_status", ["status"]),
    ]:
        if inspector.has_table("inventory_reservations") and index_name not in {item["name"] for item in inspector.get_indexes("inventory_reservations")}:
            op.create_index(index_name, "inventory_reservations", columns, unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("inventory_reservations"):
        indexes = {item["name"] for item in inspector.get_indexes("inventory_reservations")}
        for index_name in [
            "ix_inventory_reservations_status",
            "ix_inventory_reservations_order_id",
            "ix_inventory_reservations_item_id",
            "ix_inventory_reservations_branch_id",
            "ix_inventory_reservations_company_id",
        ]:
            if index_name in indexes:
                op.drop_index(index_name, table_name="inventory_reservations")
        op.drop_table("inventory_reservations")

    if inspector.has_table("inventory_parts"):
        columns = {col["name"] for col in inspector.get_columns("inventory_parts")}
        if "quantity_reserved" in columns:
            op.drop_column("inventory_parts", "quantity_reserved")
        if "quantity_total" in columns:
            op.drop_column("inventory_parts", "quantity_total")
