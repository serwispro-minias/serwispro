"""add workflow engine tables

Revision ID: a91d4ef62c70
Revises: f7d3b2a9810c
Create Date: 2026-08-06 14:30:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a91d4ef62c70"
down_revision = "f7d3b2a9810c"
branch_labels = None
depends_on = None


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return index_name in {item["name"] for item in inspector.get_indexes(table_name)}


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return column_name in {item["name"] for item in inspector.get_columns(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("workflow_statuses"):
        op.create_table(
            "workflow_statuses",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("code", sa.String(length=80), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("color", sa.String(length=40), nullable=False),
            sa.Column("icon", sa.String(length=80), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False),
            sa.Column("is_initial", sa.Boolean(), nullable=False),
            sa.Column("is_closed", sa.Boolean(), nullable=False),
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
            sa.UniqueConstraint("company_id", "branch_id", "code", name="uq_workflow_status_scope_code"),
        )

    if not inspector.has_table("workflow_transitions"):
        op.create_table(
            "workflow_transitions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("from_status_id", sa.Integer(), nullable=False),
            sa.Column("to_status_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("requires_permission", sa.String(length=120), nullable=True),
            sa.Column("requires_estimate", sa.Boolean(), nullable=False),
            sa.Column("requires_parts", sa.Boolean(), nullable=False),
            sa.Column("requires_payment", sa.Boolean(), nullable=False),
            sa.Column("auto_email", sa.Boolean(), nullable=False),
            sa.Column("auto_sms", sa.Boolean(), nullable=False),
            sa.Column("auto_notification", sa.Boolean(), nullable=False),
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
            sa.ForeignKeyConstraint(["from_status_id"], ["workflow_statuses.id"]),
            sa.ForeignKeyConstraint(["to_status_id"], ["workflow_statuses.id"]),
            sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid"),
            sa.UniqueConstraint("company_id", "branch_id", "from_status_id", "to_status_id", name="uq_workflow_transition_scope"),
        )

    inspector = sa.inspect(bind)
    for table_name, index_name, columns in [
        ("workflow_statuses", "ix_workflow_statuses_company_id", ["company_id"]),
        ("workflow_statuses", "ix_workflow_statuses_branch_id", ["branch_id"]),
        ("workflow_statuses", "ix_workflow_statuses_code", ["code"]),
        ("workflow_statuses", "ix_workflow_statuses_sort_order", ["sort_order"]),
        ("workflow_transitions", "ix_workflow_transitions_company_id", ["company_id"]),
        ("workflow_transitions", "ix_workflow_transitions_branch_id", ["branch_id"]),
        ("workflow_transitions", "ix_workflow_transitions_from_status_id", ["from_status_id"]),
        ("workflow_transitions", "ix_workflow_transitions_to_status_id", ["to_status_id"]),
    ]:
        if not _has_index(inspector, table_name, index_name):
            op.create_index(index_name, table_name, columns, unique=False)

    inspector = sa.inspect(bind)
    if _has_column(inspector, "service_order_status_history", "ip_address") is False:
        op.add_column("service_order_status_history", sa.Column("ip_address", sa.String(length=64), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_column(inspector, "service_order_status_history", "ip_address"):
        op.drop_column("service_order_status_history", "ip_address")

    if inspector.has_table("workflow_transitions"):
        for index_name in [
            "ix_workflow_transitions_to_status_id",
            "ix_workflow_transitions_from_status_id",
            "ix_workflow_transitions_branch_id",
            "ix_workflow_transitions_company_id",
        ]:
            if _has_index(inspector, "workflow_transitions", index_name):
                op.drop_index(index_name, table_name="workflow_transitions")
        op.drop_table("workflow_transitions")

    inspector = sa.inspect(bind)
    if inspector.has_table("workflow_statuses"):
        for index_name in [
            "ix_workflow_statuses_sort_order",
            "ix_workflow_statuses_code",
            "ix_workflow_statuses_branch_id",
            "ix_workflow_statuses_company_id",
        ]:
            if _has_index(inspector, "workflow_statuses", index_name):
                op.drop_index(index_name, table_name="workflow_statuses")
        op.drop_table("workflow_statuses")
