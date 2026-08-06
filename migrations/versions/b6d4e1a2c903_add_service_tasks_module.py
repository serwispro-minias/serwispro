"""add service tasks module

Revision ID: b6d4e1a2c903
Revises: a91d4ef62c70
Create Date: 2026-08-06 18:10:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b6d4e1a2c903"
down_revision = "a91d4ef62c70"
branch_labels = None
depends_on = None


def _has_table(inspector, table_name: str) -> bool:
    return inspector.has_table(table_name)


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

    if not _has_table(inspector, "service_tasks"):
        op.create_table(
            "service_tasks",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("service_order_id", sa.Integer(), nullable=False),
            sa.Column("parent_task_id", sa.Integer(), nullable=True),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("task_type", sa.String(length=40), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("priority", sa.String(length=20), nullable=False),
            sa.Column("assigned_to", sa.Integer(), nullable=True),
            sa.Column("planned_start", sa.DateTime(), nullable=True),
            sa.Column("planned_finish", sa.DateTime(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("estimated_minutes", sa.Integer(), nullable=True),
            sa.Column("worked_minutes", sa.Integer(), nullable=False),
            sa.Column("completion_percent", sa.Integer(), nullable=False),
            sa.Column("requires_confirmation", sa.Boolean(), nullable=False),
            *_base_columns(),
            sa.ForeignKeyConstraint(["service_order_id"], ["service_orders.id"]),
            sa.ForeignKeyConstraint(["parent_task_id"], ["service_tasks.id"]),
            sa.ForeignKeyConstraint(["assigned_to"], ["users.id"]),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid"),
        )

    inspector = sa.inspect(bind)
    for table_name, index_name, columns in [
        ("service_tasks", "ix_service_tasks_company_id", ["company_id"]),
        ("service_tasks", "ix_service_tasks_branch_id", ["branch_id"]),
        ("service_tasks", "ix_service_tasks_service_order_id", ["service_order_id"]),
        ("service_tasks", "ix_service_tasks_parent_task_id", ["parent_task_id"]),
        ("service_tasks", "ix_service_tasks_status", ["status"]),
        ("service_tasks", "ix_service_tasks_priority", ["priority"]),
        ("service_tasks", "ix_service_tasks_assigned_to", ["assigned_to"]),
        ("service_tasks", "ix_service_tasks_planned_start", ["planned_start"]),
        ("service_tasks", "ix_service_tasks_planned_finish", ["planned_finish"]),
    ]:
        if not _has_index(inspector, table_name, index_name):
            op.create_index(index_name, table_name, columns, unique=False)

    inspector = sa.inspect(bind)
    if not _has_table(inspector, "service_task_comments"):
        op.create_table(
            "service_task_comments",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("service_task_id", sa.Integer(), nullable=False),
            sa.Column("author_id", sa.Integer(), nullable=True),
            sa.Column("content", sa.Text(), nullable=False),
            *_base_columns(),
            sa.ForeignKeyConstraint(["service_task_id"], ["service_tasks.id"]),
            sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid"),
        )

    inspector = sa.inspect(bind)
    for table_name, index_name, columns in [
        ("service_task_comments", "ix_service_task_comments_company_id", ["company_id"]),
        ("service_task_comments", "ix_service_task_comments_branch_id", ["branch_id"]),
        ("service_task_comments", "ix_service_task_comments_task_id", ["service_task_id"]),
        ("service_task_comments", "ix_service_task_comments_author_id", ["author_id"]),
    ]:
        if not _has_index(inspector, table_name, index_name):
            op.create_index(index_name, table_name, columns, unique=False)

    inspector = sa.inspect(bind)
    if not _has_table(inspector, "service_task_attachments"):
        op.create_table(
            "service_task_attachments",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("service_task_id", sa.Integer(), nullable=False),
            sa.Column("uploaded_by", sa.Integer(), nullable=True),
            sa.Column("original_filename", sa.String(length=255), nullable=False),
            sa.Column("stored_filename", sa.String(length=255), nullable=False),
            sa.Column("relative_path", sa.String(length=500), nullable=False),
            sa.Column("content_type", sa.String(length=120), nullable=True),
            sa.Column("file_size", sa.Integer(), nullable=True),
            *_base_columns(),
            sa.ForeignKeyConstraint(["service_task_id"], ["service_tasks.id"]),
            sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid"),
        )

    inspector = sa.inspect(bind)
    for table_name, index_name, columns in [
        ("service_task_attachments", "ix_service_task_attachments_company_id", ["company_id"]),
        ("service_task_attachments", "ix_service_task_attachments_branch_id", ["branch_id"]),
        ("service_task_attachments", "ix_service_task_attachments_task_id", ["service_task_id"]),
    ]:
        if not _has_index(inspector, table_name, index_name):
            op.create_index(index_name, table_name, columns, unique=False)

    inspector = sa.inspect(bind)
    if not _has_table(inspector, "service_task_time_entries"):
        op.create_table(
            "service_task_time_entries",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("service_task_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("ended_at", sa.DateTime(), nullable=True),
            sa.Column("duration_minutes", sa.Integer(), nullable=True),
            sa.Column("action", sa.String(length=24), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            *_base_columns(),
            sa.ForeignKeyConstraint(["service_task_id"], ["service_tasks.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid"),
        )

    inspector = sa.inspect(bind)
    for table_name, index_name, columns in [
        ("service_task_time_entries", "ix_service_task_time_entries_company_id", ["company_id"]),
        ("service_task_time_entries", "ix_service_task_time_entries_branch_id", ["branch_id"]),
        ("service_task_time_entries", "ix_service_task_time_entries_task_id", ["service_task_id"]),
        ("service_task_time_entries", "ix_service_task_time_entries_user_id", ["user_id"]),
        ("service_task_time_entries", "ix_service_task_time_entries_started_at", ["started_at"]),
    ]:
        if not _has_index(inspector, table_name, index_name):
            op.create_index(index_name, table_name, columns, unique=False)

    inspector = sa.inspect(bind)
    if not _has_table(inspector, "service_task_status_history"):
        op.create_table(
            "service_task_status_history",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("service_task_id", sa.Integer(), nullable=False),
            sa.Column("old_status", sa.String(length=24), nullable=True),
            sa.Column("new_status", sa.String(length=24), nullable=False),
            sa.Column("changed_at", sa.DateTime(), nullable=False),
            sa.Column("changed_by", sa.Integer(), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            *_base_columns(),
            sa.ForeignKeyConstraint(["service_task_id"], ["service_tasks.id"]),
            sa.ForeignKeyConstraint(["changed_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid"),
        )

    inspector = sa.inspect(bind)
    for table_name, index_name, columns in [
        ("service_task_status_history", "ix_service_task_status_history_company_id", ["company_id"]),
        ("service_task_status_history", "ix_service_task_status_history_branch_id", ["branch_id"]),
        ("service_task_status_history", "ix_service_task_status_history_task_id", ["service_task_id"]),
        ("service_task_status_history", "ix_service_task_status_history_changed_at", ["changed_at"]),
    ]:
        if not _has_index(inspector, table_name, index_name):
            op.create_index(index_name, table_name, columns, unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table_name, index_names in [
        (
            "service_task_status_history",
            [
                "ix_service_task_status_history_changed_at",
                "ix_service_task_status_history_task_id",
                "ix_service_task_status_history_branch_id",
                "ix_service_task_status_history_company_id",
            ],
        ),
        (
            "service_task_time_entries",
            [
                "ix_service_task_time_entries_started_at",
                "ix_service_task_time_entries_user_id",
                "ix_service_task_time_entries_task_id",
                "ix_service_task_time_entries_branch_id",
                "ix_service_task_time_entries_company_id",
            ],
        ),
        (
            "service_task_attachments",
            [
                "ix_service_task_attachments_task_id",
                "ix_service_task_attachments_branch_id",
                "ix_service_task_attachments_company_id",
            ],
        ),
        (
            "service_task_comments",
            [
                "ix_service_task_comments_author_id",
                "ix_service_task_comments_task_id",
                "ix_service_task_comments_branch_id",
                "ix_service_task_comments_company_id",
            ],
        ),
        (
            "service_tasks",
            [
                "ix_service_tasks_planned_finish",
                "ix_service_tasks_planned_start",
                "ix_service_tasks_assigned_to",
                "ix_service_tasks_priority",
                "ix_service_tasks_status",
                "ix_service_tasks_parent_task_id",
                "ix_service_tasks_service_order_id",
                "ix_service_tasks_branch_id",
                "ix_service_tasks_company_id",
            ],
        ),
    ]:
        if inspector.has_table(table_name):
            existing_indexes = {item["name"] for item in inspector.get_indexes(table_name)}
            for index_name in index_names:
                if index_name in existing_indexes:
                    op.drop_index(index_name, table_name=table_name)
            op.drop_table(table_name)
