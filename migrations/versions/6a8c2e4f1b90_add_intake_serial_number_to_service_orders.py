"""Store the serial number recorded for each service-order intake.

Revision ID: 6a8c2e4f1b90
Revises: 5c8e2b4a1d70
"""

from alembic import op
import sqlalchemy as sa


revision = "6a8c2e4f1b90"
down_revision = "5c8e2b4a1d70"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "service_orders",
        sa.Column("intake_serial_number", sa.String(length=120), nullable=True),
    )


def downgrade():
    op.drop_column("service_orders", "intake_serial_number")
