"""add estimate approval tokens

Revision ID: f7d3b2a9810c
Revises: cfdaf0efbd19
Create Date: 2026-08-06 11:10:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f7d3b2a9810c"
down_revision = "cfdaf0efbd19"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("estimate_approval_tokens"):
        op.create_table(
            "estimate_approval_tokens",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("estimate_id", sa.Integer(), nullable=False),
            sa.Column("token", sa.String(length=36), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("used_at", sa.DateTime(), nullable=True),
            sa.Column("ip_address", sa.String(length=64), nullable=True),
            sa.Column("user_agent", sa.String(length=512), nullable=True),
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
            sa.ForeignKeyConstraint(["estimate_id"], ["service_estimates.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token"),
            sa.UniqueConstraint("uuid"),
        )

    inspector = sa.inspect(bind)
    existing_indexes = set()
    if inspector.has_table("estimate_approval_tokens"):
        existing_indexes = {index["name"] for index in inspector.get_indexes("estimate_approval_tokens")}

    if "ix_estimate_approval_tokens_company_id" not in existing_indexes:
        op.create_index("ix_estimate_approval_tokens_company_id", "estimate_approval_tokens", ["company_id"], unique=False)
    if "ix_estimate_approval_tokens_branch_id" not in existing_indexes:
        op.create_index("ix_estimate_approval_tokens_branch_id", "estimate_approval_tokens", ["branch_id"], unique=False)
    if "ix_estimate_approval_tokens_estimate_id" not in existing_indexes:
        op.create_index("ix_estimate_approval_tokens_estimate_id", "estimate_approval_tokens", ["estimate_id"], unique=False)
    if "ix_estimate_approval_tokens_status" not in existing_indexes:
        op.create_index("ix_estimate_approval_tokens_status", "estimate_approval_tokens", ["status"], unique=False)
    if "ix_estimate_approval_tokens_expires_at" not in existing_indexes:
        op.create_index("ix_estimate_approval_tokens_expires_at", "estimate_approval_tokens", ["expires_at"], unique=False)
    if "ix_estimate_approval_tokens_token" not in existing_indexes:
        op.create_index("ix_estimate_approval_tokens_token", "estimate_approval_tokens", ["token"], unique=True)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("estimate_approval_tokens"):
        existing_indexes = {index["name"] for index in inspector.get_indexes("estimate_approval_tokens")}
        if "ix_estimate_approval_tokens_token" in existing_indexes:
            op.drop_index("ix_estimate_approval_tokens_token", table_name="estimate_approval_tokens")
        if "ix_estimate_approval_tokens_expires_at" in existing_indexes:
            op.drop_index("ix_estimate_approval_tokens_expires_at", table_name="estimate_approval_tokens")
        if "ix_estimate_approval_tokens_status" in existing_indexes:
            op.drop_index("ix_estimate_approval_tokens_status", table_name="estimate_approval_tokens")
        if "ix_estimate_approval_tokens_estimate_id" in existing_indexes:
            op.drop_index("ix_estimate_approval_tokens_estimate_id", table_name="estimate_approval_tokens")
        if "ix_estimate_approval_tokens_branch_id" in existing_indexes:
            op.drop_index("ix_estimate_approval_tokens_branch_id", table_name="estimate_approval_tokens")
        if "ix_estimate_approval_tokens_company_id" in existing_indexes:
            op.drop_index("ix_estimate_approval_tokens_company_id", table_name="estimate_approval_tokens")
        op.drop_table("estimate_approval_tokens")
