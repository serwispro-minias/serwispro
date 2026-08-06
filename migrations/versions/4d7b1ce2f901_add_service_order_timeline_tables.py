"""add service order timeline tables

Revision ID: 4d7b1ce2f901
Revises: 3a9d2f4e7b1c
Create Date: 2026-08-03 15:10:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4d7b1ce2f901"
down_revision = "3a9d2f4e7b1c"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("service_order_timeline_entries"):
        op.create_table(
            "service_order_timeline_entries",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("service_order_id", sa.Integer(), nullable=False),
            sa.Column("author_user_id", sa.Integer(), nullable=True),
            sa.Column("entry_type", sa.String(length=40), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("parts_cost", sa.Numeric(precision=10, scale=2), nullable=True),
            sa.Column("labor_minutes", sa.Integer(), nullable=True),
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
            sa.ForeignKeyConstraint(["author_user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(["service_order_id"], ["service_orders.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid"),
        )

    inspector = sa.inspect(bind)
    entry_indexes = set()
    if inspector.has_table("service_order_timeline_entries"):
        entry_indexes = {index["name"] for index in inspector.get_indexes("service_order_timeline_entries")}

    for index_name, columns in [
        ("ix_so_timeline_entries_company_id", ["company_id"]),
        ("ix_so_timeline_entries_branch_id", ["branch_id"]),
        ("ix_so_timeline_entries_order_id", ["service_order_id"]),
        ("ix_so_timeline_entries_author_id", ["author_user_id"]),
        ("ix_so_timeline_entries_type", ["entry_type"]),
    ]:
        if index_name not in entry_indexes:
            op.create_index(index_name, "service_order_timeline_entries", columns, unique=False)

    inspector = sa.inspect(bind)
    if not inspector.has_table("service_order_timeline_attachments"):
        op.create_table(
            "service_order_timeline_attachments",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("entry_id", sa.Integer(), nullable=False),
            sa.Column("original_filename", sa.String(length=255), nullable=False),
            sa.Column("stored_filename", sa.String(length=255), nullable=False),
            sa.Column("relative_path", sa.String(length=500), nullable=False),
            sa.Column("content_type", sa.String(length=120), nullable=True),
            sa.Column("file_size", sa.Integer(), nullable=True),
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
            sa.ForeignKeyConstraint(["entry_id"], ["service_order_timeline_entries.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid"),
        )

    inspector = sa.inspect(bind)
    attachment_indexes = set()
    if inspector.has_table("service_order_timeline_attachments"):
        attachment_indexes = {index["name"] for index in inspector.get_indexes("service_order_timeline_attachments")}

    for index_name, columns in [
        ("ix_so_timeline_attachments_company_id", ["company_id"]),
        ("ix_so_timeline_attachments_branch_id", ["branch_id"]),
        ("ix_so_timeline_attachments_entry_id", ["entry_id"]),
    ]:
        if index_name not in attachment_indexes:
            op.create_index(index_name, "service_order_timeline_attachments", columns, unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("service_order_timeline_attachments"):
        indexes = {index["name"] for index in inspector.get_indexes("service_order_timeline_attachments")}
        for index_name in [
            "ix_so_timeline_attachments_entry_id",
            "ix_so_timeline_attachments_branch_id",
            "ix_so_timeline_attachments_company_id",
        ]:
            if index_name in indexes:
                op.drop_index(index_name, table_name="service_order_timeline_attachments")
        op.drop_table("service_order_timeline_attachments")

    inspector = sa.inspect(bind)
    if inspector.has_table("service_order_timeline_entries"):
        indexes = {index["name"] for index in inspector.get_indexes("service_order_timeline_entries")}
        for index_name in [
            "ix_so_timeline_entries_type",
            "ix_so_timeline_entries_author_id",
            "ix_so_timeline_entries_order_id",
            "ix_so_timeline_entries_branch_id",
            "ix_so_timeline_entries_company_id",
        ]:
            if index_name in indexes:
                op.drop_index(index_name, table_name="service_order_timeline_entries")
        op.drop_table("service_order_timeline_entries")
