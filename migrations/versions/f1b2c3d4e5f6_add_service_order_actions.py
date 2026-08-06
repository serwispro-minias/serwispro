"""add service order actions

Revision ID: f1b2c3d4e5f6
Revises: e9a24f3d7c11
Create Date: 2026-08-03 23:20:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f1b2c3d4e5f6"
down_revision = "e9a24f3d7c11"
branch_labels = None
depends_on = None


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    if not inspector.has_table(table_name):
        return False
    return index_name in {item["name"] for item in inspector.get_indexes(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("service_order_actions"):
        op.create_table(
            "service_order_actions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("service_order_id", sa.Integer(), nullable=False),
            sa.Column("action_date", sa.Date(), nullable=False),
            sa.Column("technician_id", sa.Integer(), nullable=True),
            sa.Column("action_type", sa.String(length=40), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("work_time_minutes", sa.Integer(), nullable=True),
            sa.Column("cost", sa.Numeric(10, 2), nullable=True),
            sa.Column("is_visible_for_customer", sa.Boolean(), nullable=False),
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
            sa.ForeignKeyConstraint(["technician_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid"),
        )

    inspector = sa.inspect(bind)
    for index_name, columns in [
        ("ix_service_order_actions_company_id", ["company_id"]),
        ("ix_service_order_actions_branch_id", ["branch_id"]),
        ("ix_service_order_actions_order_id", ["service_order_id"]),
        ("ix_service_order_actions_action_date", ["action_date"]),
        ("ix_service_order_actions_technician_id", ["technician_id"]),
    ]:
        if not _has_index(inspector, "service_order_actions", index_name):
            op.create_index(index_name, "service_order_actions", columns, unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("service_order_actions"):
        existing_indexes = {item["name"] for item in inspector.get_indexes("service_order_actions")}
        for index_name in [
            "ix_service_order_actions_technician_id",
            "ix_service_order_actions_action_date",
            "ix_service_order_actions_order_id",
            "ix_service_order_actions_branch_id",
            "ix_service_order_actions_company_id",
        ]:
            if index_name in existing_indexes:
                op.drop_index(index_name, table_name="service_order_actions")
        op.drop_table("service_order_actions")
