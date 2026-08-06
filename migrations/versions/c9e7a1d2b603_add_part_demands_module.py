"""add part demands module

Revision ID: c9e7a1d2b603
Revises: b6d4e1a2c903
Create Date: 2026-08-06 20:30:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c9e7a1d2b603"
down_revision = "b6d4e1a2c903"
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

    if not inspector.has_table("part_demands"):
        op.create_table(
            "part_demands",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("service_order_id", sa.Integer(), nullable=False),
            sa.Column("service_order_item_id", sa.Integer(), nullable=True),
            sa.Column("inventory_item_id", sa.Integer(), nullable=False),
            sa.Column("requested_quantity", sa.Numeric(12, 3), nullable=False),
            sa.Column("reserved_quantity", sa.Numeric(12, 3), nullable=False),
            sa.Column("missing_quantity", sa.Numeric(12, 3), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("priority", sa.String(length=20), nullable=False),
            sa.Column("expected_date", sa.Date(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            *_base_columns(),
            sa.ForeignKeyConstraint(["service_order_id"], ["service_orders.id"]),
            sa.ForeignKeyConstraint(["service_order_item_id"], ["service_order_items.id"]),
            sa.ForeignKeyConstraint(["inventory_item_id"], ["catalog_parts.id"]),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid"),
        )

    inspector = sa.inspect(bind)
    index_specs = [
        ("ix_part_demands_company_id", ["company_id"]),
        ("ix_part_demands_branch_id", ["branch_id"]),
        ("ix_part_demands_order_id", ["service_order_id"]),
        ("ix_part_demands_order_item_id", ["service_order_item_id"]),
        ("ix_part_demands_inventory_item_id", ["inventory_item_id"]),
        ("ix_part_demands_status", ["status"]),
        ("ix_part_demands_priority", ["priority"]),
        ("ix_part_demands_expected_date", ["expected_date"]),
    ]
    for index_name, columns in index_specs:
        if not _has_index(inspector, "part_demands", index_name):
            op.create_index(index_name, "part_demands", columns, unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("part_demands"):
        existing_indexes = {item["name"] for item in inspector.get_indexes("part_demands")}
        for index_name in [
            "ix_part_demands_expected_date",
            "ix_part_demands_priority",
            "ix_part_demands_status",
            "ix_part_demands_inventory_item_id",
            "ix_part_demands_order_item_id",
            "ix_part_demands_order_id",
            "ix_part_demands_branch_id",
            "ix_part_demands_company_id",
        ]:
            if index_name in existing_indexes:
                op.drop_index(index_name, table_name="part_demands")
        op.drop_table("part_demands")
