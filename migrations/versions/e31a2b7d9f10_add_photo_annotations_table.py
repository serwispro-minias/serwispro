"""add photo annotations table

Revision ID: e31a2b7d9f10
Revises: d2a1b8c4f905
Create Date: 2026-08-06 23:20:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e31a2b7d9f10"
down_revision = "d2a1b8c4f905"
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

    if not inspector.has_table("service_order_photo_annotations"):
        op.create_table(
            "service_order_photo_annotations",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("photo_id", sa.Integer(), nullable=False),
            sa.Column("annotation_type", sa.String(length=24), nullable=False),
            sa.Column("x", sa.Numeric(10, 6), nullable=False),
            sa.Column("y", sa.Numeric(10, 6), nullable=False),
            sa.Column("width", sa.Numeric(10, 6), nullable=False),
            sa.Column("height", sa.Numeric(10, 6), nullable=False),
            sa.Column("rotation", sa.Numeric(10, 3), nullable=False),
            sa.Column("color", sa.String(length=16), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("priority", sa.String(length=20), nullable=False),
            sa.Column("is_visible_for_customer", sa.Boolean(), nullable=False),
            sa.Column("points_json", sa.Text(), nullable=True),
            *_base_columns(),
            sa.ForeignKeyConstraint(["photo_id"], ["service_order_photos.id"]),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid"),
        )

    inspector = sa.inspect(bind)
    for index_name, columns in [
        ("ix_photo_annotations_company_id", ["company_id"]),
        ("ix_photo_annotations_branch_id", ["branch_id"]),
        ("ix_photo_annotations_photo_id", ["photo_id"]),
        ("ix_photo_annotations_type", ["annotation_type"]),
        ("ix_photo_annotations_priority", ["priority"]),
        ("ix_photo_annotations_visible", ["is_visible_for_customer"]),
    ]:
        if not _has_index(inspector, "service_order_photo_annotations", index_name):
            op.create_index(index_name, "service_order_photo_annotations", columns, unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("service_order_photo_annotations"):
        existing_indexes = {item["name"] for item in inspector.get_indexes("service_order_photo_annotations")}
        for index_name in [
            "ix_photo_annotations_visible",
            "ix_photo_annotations_priority",
            "ix_photo_annotations_type",
            "ix_photo_annotations_photo_id",
            "ix_photo_annotations_branch_id",
            "ix_photo_annotations_company_id",
        ]:
            if index_name in existing_indexes:
                op.drop_index(index_name, table_name="service_order_photo_annotations")
        op.drop_table("service_order_photo_annotations")
