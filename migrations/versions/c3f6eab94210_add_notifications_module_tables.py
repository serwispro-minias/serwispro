"""add notifications module tables

Revision ID: c3f6eab94210
Revises: b2f4a61c9d3e
Create Date: 2026-08-03 20:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c3f6eab94210"
down_revision = "b2f4a61c9d3e"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

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

    inspector = sa.inspect(bind)
    template_indexes = set()
    if inspector.has_table("notification_templates"):
        template_indexes = {index["name"] for index in inspector.get_indexes("notification_templates")}

    for index_name, columns in [
        ("ix_notification_templates_company_id", ["company_id"]),
        ("ix_notification_templates_branch_id", ["branch_id"]),
        ("ix_notification_templates_event", ["event_key"]),
        ("ix_notification_templates_channel", ["channel"]),
    ]:
        if index_name not in template_indexes:
            op.create_index(index_name, "notification_templates", columns, unique=False)

    if not inspector.has_table("notification_logs"):
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

    inspector = sa.inspect(bind)
    message_indexes = set()
    if inspector.has_table("notification_logs"):
        message_indexes = {index["name"] for index in inspector.get_indexes("notification_logs")}

    for index_name, columns in [
        ("ix_notification_logs_company_id", ["company_id"]),
        ("ix_notification_logs_branch_id", ["branch_id"]),
        ("ix_notification_logs_order_id", ["service_order_id"]),
        ("ix_notification_logs_channel", ["channel"]),
        ("ix_notification_logs_status", ["status"]),
        ("ix_notification_logs_created_at", ["created_at"]),
    ]:
        if index_name not in message_indexes:
            op.create_index(index_name, "notification_logs", columns, unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("notification_logs"):
        indexes = {index["name"] for index in inspector.get_indexes("notification_logs")}
        for index_name in [
            "ix_notification_logs_created_at",
            "ix_notification_logs_status",
            "ix_notification_logs_channel",
            "ix_notification_logs_order_id",
            "ix_notification_logs_branch_id",
            "ix_notification_logs_company_id",
        ]:
            if index_name in indexes:
                op.drop_index(index_name, table_name="notification_logs")
        op.drop_table("notification_logs")

    inspector = sa.inspect(bind)
    if inspector.has_table("notification_templates"):
        indexes = {index["name"] for index in inspector.get_indexes("notification_templates")}
        for index_name in [
            "ix_notification_templates_channel",
            "ix_notification_templates_event",
            "ix_notification_templates_branch_id",
            "ix_notification_templates_company_id",
        ]:
            if index_name in indexes:
                op.drop_index(index_name, table_name="notification_templates")
        op.drop_table("notification_templates")
