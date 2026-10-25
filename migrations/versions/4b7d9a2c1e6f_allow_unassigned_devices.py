"""Allow devices in the unassigned device catalog.

Revision ID: 4b7d9a2c1e6f
Revises: f4a5b6c7d8e9
"""

from alembic import op
import sqlalchemy as sa


revision = "4b7d9a2c1e6f"
down_revision = "f4a5b6c7d8e9"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("devices") as batch_op:
        batch_op.alter_column(
            "customer_id",
            existing_type=sa.Integer(),
            nullable=True,
        )


def downgrade():
    bind = op.get_bind()
    unassigned_count = bind.execute(
        sa.text("SELECT COUNT(*) FROM devices WHERE customer_id IS NULL")
    ).scalar_one()
    if unassigned_count:
        raise RuntimeError(
            "Cannot restore NOT NULL on devices.customer_id while unassigned devices exist."
        )
    with op.batch_alter_table("devices") as batch_op:
        batch_op.alter_column(
            "customer_id",
            existing_type=sa.Integer(),
            nullable=False,
        )