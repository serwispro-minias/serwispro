"""add preferred supplier to catalog parts

Revision ID: 8f9a0b1c2d3e
Revises: 7e8f9a0b1c2d
"""

from alembic import op
import sqlalchemy as sa

revision = "8f9a0b1c2d3e"
down_revision = "7e8f9a0b1c2d"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("catalog_parts"):
        return
    columns = {column["name"] for column in inspector.get_columns("catalog_parts")}
    if "preferred_supplier_id" not in columns:
        op.add_column("catalog_parts", sa.Column("preferred_supplier_id", sa.Integer(), nullable=True))
        op.create_foreign_key("fk_catalog_parts_preferred_supplier_id", "catalog_parts", "catalog_suppliers", ["preferred_supplier_id"], ["id"])
    indexes = {item["name"] for item in inspector.get_indexes("catalog_parts")}
    if "ix_catalog_parts_preferred_supplier_id" not in indexes:
        op.create_index("ix_catalog_parts_preferred_supplier_id", "catalog_parts", ["preferred_supplier_id"], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("catalog_parts"):
        return
    indexes = {item["name"] for item in inspector.get_indexes("catalog_parts")}
    if "ix_catalog_parts_preferred_supplier_id" in indexes:
        op.drop_index("ix_catalog_parts_preferred_supplier_id", table_name="catalog_parts")
    columns = {column["name"] for column in inspector.get_columns("catalog_parts")}
    if "preferred_supplier_id" in columns:
        op.drop_constraint("fk_catalog_parts_preferred_supplier_id", "catalog_parts", type_="foreignkey")
        op.drop_column("catalog_parts", "preferred_supplier_id")
