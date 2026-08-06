"""Add devices table

Revision ID: 9f8e7d6c5b4a
Revises: 7769584704da
Create Date: 2026-08-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9f8e7d6c5b4a'
down_revision = '7769584704da'
branch_labels = None
depends_on = None


def upgrade():
    """Create the devices table with tenant and customer foreign keys."""

    op.create_table(
        'devices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('manufacturer', sa.String(length=120), nullable=True),
        sa.Column('model', sa.String(length=120), nullable=True),
        sa.Column('serial_number', sa.String(length=120), nullable=True),
        sa.Column('inventory_number', sa.String(length=120), nullable=True),
        sa.Column('device_type', sa.String(length=80), nullable=True),
        sa.Column('purchase_date', sa.Date(), nullable=True),
        sa.Column('warranty_until', sa.Date(), nullable=True),
        sa.Column('password', sa.String(length=255), nullable=True),
        sa.Column('condition_description', sa.Text(), nullable=True),
        sa.Column('accessories', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('branch_id', sa.Integer(), nullable=True),
        sa.Column('uuid', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('deleted_by', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['branch_id'], ['branches.id']),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid'),
    )

    op.create_index('ix_devices_company_id', 'devices', ['company_id'], unique=False)
    op.create_index('ix_devices_branch_id', 'devices', ['branch_id'], unique=False)
    op.create_index('ix_devices_customer_id', 'devices', ['customer_id'], unique=False)


def downgrade():
    """Drop the devices table and its indexes."""

    op.drop_index('ix_devices_customer_id', table_name='devices')
    op.drop_index('ix_devices_branch_id', table_name='devices')
    op.drop_index('ix_devices_company_id', table_name='devices')
    op.drop_table('devices')
