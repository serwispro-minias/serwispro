"""service orders

Revision ID: 8c16f851bbd8
Revises: 9f8e7d6c5b4a
Create Date: 2026-08-02 09:28:45.642103

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8c16f851bbd8'
down_revision = '9f8e7d6c5b4a'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table('service_orders'):
        op.create_table('service_orders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.Integer(), nullable=False),
        sa.Column('order_number', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=40), nullable=False),
        sa.Column('priority', sa.String(length=20), nullable=False),
        sa.Column('intake_date', sa.Date(), nullable=False),
        sa.Column('planned_finish_date', sa.Date(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('warranty_repair', sa.Boolean(), nullable=False),
        sa.Column('issue_description', sa.Text(), nullable=False),
        sa.Column('diagnosis', sa.Text(), nullable=True),
        sa.Column('repair_description', sa.Text(), nullable=True),
        sa.Column('technician_notes', sa.Text(), nullable=True),
        sa.Column('customer_notes', sa.Text(), nullable=True),
        sa.Column('estimated_cost', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('final_cost', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('external_reference', sa.String(length=120), nullable=True),
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
        sa.ForeignKeyConstraint(['branch_id'], ['branches.id'], ),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid')
        )

    inspector = sa.inspect(bind)
    service_order_indexes = set()
    if inspector.has_table('service_orders'):
        service_order_indexes = {index['name'] for index in inspector.get_indexes('service_orders')}

    required_indexes = [
        ('ix_service_orders_branch_id', ['branch_id']),
        ('ix_service_orders_company_id', ['company_id']),
        ('ix_service_orders_customer_id', ['customer_id']),
        ('ix_service_orders_device_id', ['device_id']),
        ('ix_service_orders_external_reference', ['external_reference']),
        ('ix_service_orders_order_number', ['order_number']),
        ('ix_service_orders_priority', ['priority']),
        ('ix_service_orders_status', ['status']),
    ]
    for index_name, columns in required_indexes:
        if index_name not in service_order_indexes:
            op.create_index(index_name, 'service_orders', columns, unique=False)

    # Keep existing device indexes unchanged.
    # On MySQL these indexes may be required by active FK constraints.


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Keep existing device indexes unchanged.

    if inspector.has_table('service_orders'):
        service_order_indexes = {index['name'] for index in inspector.get_indexes('service_orders')}
        for index_name in [
            'ix_service_orders_status',
            'ix_service_orders_priority',
            'ix_service_orders_order_number',
            'ix_service_orders_external_reference',
            'ix_service_orders_device_id',
            'ix_service_orders_customer_id',
            'ix_service_orders_company_id',
            'ix_service_orders_branch_id',
        ]:
            if index_name in service_order_indexes:
                op.drop_index(index_name, table_name='service_orders')

        op.drop_table('service_orders')
