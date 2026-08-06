"""notifications logs and queue repair

Revision ID: e9a24f3d7c11
Revises: c3f6eab94210
Create Date: 2026-08-03 21:20:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e9a24f3d7c11"
down_revision = "c3f6eab94210"
branch_labels = None
depends_on = None


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return index_name in {item["name"] for item in inspector.get_indexes(table_name)}


def _ensure_notification_templates(inspector) -> None:
    if not inspector.has_table("notification_templates"):
        op.create_table(
            "notification_templates",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("event_key", sa.String(length=60), nullable=False),
            sa.Column("channel", sa.String(length=16), nullable=False),
            sa.Column("subject", sa.String(length=255), nullable=True),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("is_enabled", sa.Boolean(), nullable=False),
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
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid"),
        )


def _ensure_notification_logs(inspector) -> None:
    has_logs = inspector.has_table("notification_logs")
    has_messages = inspector.has_table("notification_messages")

    if not has_logs and has_messages:
        op.rename_table("notification_messages", "notification_logs")
        has_logs = True

    if not has_logs:
        op.create_table(
            "notification_logs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("service_order_id", sa.Integer(), nullable=False),
            sa.Column("template_id", sa.Integer(), nullable=True),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("event_key", sa.String(length=60), nullable=True),
            sa.Column("channel", sa.String(length=16), nullable=False),
            sa.Column("recipient", sa.String(length=255), nullable=True),
            sa.Column("subject", sa.String(length=255), nullable=True),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("provider_name", sa.String(length=120), nullable=True),
            sa.Column("server_response", sa.Text(), nullable=True),
            sa.Column("sent_at", sa.DateTime(), nullable=True),
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
            sa.ForeignKeyConstraint(["service_order_id"], ["service_orders.id"]),
            sa.ForeignKeyConstraint(["template_id"], ["notification_templates.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid"),
        )


def _ensure_notification_queue(inspector) -> None:
    if not inspector.has_table("notification_queue"):
        op.create_table(
            "notification_queue",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("service_order_id", sa.Integer(), nullable=False),
            sa.Column("template_id", sa.Integer(), nullable=True),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("event_key", sa.String(length=60), nullable=True),
            sa.Column("channel", sa.String(length=16), nullable=False),
            sa.Column("recipient", sa.String(length=255), nullable=True),
            sa.Column("subject", sa.String(length=255), nullable=True),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("provider_name", sa.String(length=120), nullable=True),
            sa.Column("retry_count", sa.Integer(), nullable=False),
            sa.Column("next_retry_at", sa.DateTime(), nullable=True),
            sa.Column("locked_at", sa.DateTime(), nullable=True),
            sa.Column("sent_at", sa.DateTime(), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
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
            sa.ForeignKeyConstraint(["service_order_id"], ["service_orders.id"]),
            sa.ForeignKeyConstraint(["template_id"], ["notification_templates.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid"),
        )


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    _ensure_notification_templates(inspector)

    inspector = sa.inspect(bind)
    _ensure_notification_logs(inspector)

    inspector = sa.inspect(bind)
    _ensure_notification_queue(inspector)

    inspector = sa.inspect(bind)
    for index_name, columns in [
        ("ix_notification_templates_company_id", ["company_id"]),
        ("ix_notification_templates_branch_id", ["branch_id"]),
        ("ix_notification_templates_event", ["event_key"]),
        ("ix_notification_templates_channel", ["channel"]),
    ]:
        if not _has_index(inspector, "notification_templates", index_name):
            op.create_index(index_name, "notification_templates", columns, unique=False)

    inspector = sa.inspect(bind)
    for index_name, columns in [
        ("ix_notification_logs_company_id", ["company_id"]),
        ("ix_notification_logs_branch_id", ["branch_id"]),
        ("ix_notification_logs_order_id", ["service_order_id"]),
        ("ix_notification_logs_channel", ["channel"]),
        ("ix_notification_logs_status", ["status"]),
        ("ix_notification_logs_created_at", ["created_at"]),
    ]:
        if not _has_index(inspector, "notification_logs", index_name):
            op.create_index(index_name, "notification_logs", columns, unique=False)

    inspector = sa.inspect(bind)
    for index_name, columns in [
        ("ix_notification_queue_company_id", ["company_id"]),
        ("ix_notification_queue_branch_id", ["branch_id"]),
        ("ix_notification_queue_order_id", ["service_order_id"]),
        ("ix_notification_queue_channel", ["channel"]),
        ("ix_notification_queue_status", ["status"]),
        ("ix_notification_queue_next_retry_at", ["next_retry_at"]),
    ]:
        if not _has_index(inspector, "notification_queue", index_name):
            op.create_index(index_name, "notification_queue", columns, unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("notification_queue"):
        queue_indexes = {item["name"] for item in inspector.get_indexes("notification_queue")}
        for index_name in [
            "ix_notification_queue_next_retry_at",
            "ix_notification_queue_status",
            "ix_notification_queue_channel",
            "ix_notification_queue_order_id",
            "ix_notification_queue_branch_id",
            "ix_notification_queue_company_id",
        ]:
            if index_name in queue_indexes:
                op.drop_index(index_name, table_name="notification_queue")
        op.drop_table("notification_queue")

    inspector = sa.inspect(bind)
    if inspector.has_table("notification_logs"):
        log_indexes = {item["name"] for item in inspector.get_indexes("notification_logs")}
        for index_name in [
            "ix_notification_logs_created_at",
            "ix_notification_logs_status",
            "ix_notification_logs_channel",
            "ix_notification_logs_order_id",
            "ix_notification_logs_branch_id",
            "ix_notification_logs_company_id",
        ]:
            if index_name in log_indexes:
                op.drop_index(index_name, table_name="notification_logs")

        if inspector.has_table("notification_messages"):
            op.drop_table("notification_logs")
        else:
            op.rename_table("notification_logs", "notification_messages")
