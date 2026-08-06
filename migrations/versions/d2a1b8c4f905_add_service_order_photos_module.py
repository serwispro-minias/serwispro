"""add service order photos module

Revision ID: d2a1b8c4f905
Revises: c9e7a1d2b603
Create Date: 2026-08-06 22:10:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d2a1b8c4f905"
down_revision = "c9e7a1d2b603"
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

    if not inspector.has_table("service_order_photos"):
        op.create_table(
            "service_order_photos",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("service_order_id", sa.Integer(), nullable=False),
            sa.Column("photo_type", sa.String(length=24), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("file_name", sa.String(length=255), nullable=False),
            sa.Column("original_file_name", sa.String(length=255), nullable=False),
            sa.Column("mime_type", sa.String(length=120), nullable=False),
            sa.Column("file_size", sa.Integer(), nullable=False),
            sa.Column("width", sa.Integer(), nullable=False),
            sa.Column("height", sa.Integer(), nullable=False),
            sa.Column("taken_at", sa.DateTime(), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False),
            sa.Column("is_visible_for_customer", sa.Boolean(), nullable=False),
            *_base_columns(),
            sa.ForeignKeyConstraint(["service_order_id"], ["service_orders.id"]),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid"),
        )

    inspector = sa.inspect(bind)
    for index_name, columns in [
        ("ix_so_photos_company_id", ["company_id"]),
        ("ix_so_photos_branch_id", ["branch_id"]),
        ("ix_so_photos_order_id", ["service_order_id"]),
        ("ix_so_photos_type", ["photo_type"]),
        ("ix_so_photos_taken_at", ["taken_at"]),
        ("ix_so_photos_created_by", ["created_by"]),
        ("ix_so_photos_sort_order", ["sort_order"]),
    ]:
        if not _has_index(inspector, "service_order_photos", index_name):
            op.create_index(index_name, "service_order_photos", columns, unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("service_order_photos"):
        existing_indexes = {item["name"] for item in inspector.get_indexes("service_order_photos")}
        for index_name in [
            "ix_so_photos_sort_order",
            "ix_so_photos_created_by",
            "ix_so_photos_taken_at",
            "ix_so_photos_type",
            "ix_so_photos_order_id",
            "ix_so_photos_branch_id",
            "ix_so_photos_company_id",
        ]:
            if index_name in existing_indexes:
                op.drop_index(index_name, table_name="service_order_photos")
        op.drop_table("service_order_photos")
