"""merge service estimates and service order items heads

Revision ID: cfdaf0efbd19
Revises: b1f3c2d4a901, d4f6a1c8e2b7
Create Date: 2026-08-06 09:27:11.284044

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'cfdaf0efbd19'
down_revision = ('b1f3c2d4a901', 'd4f6a1c8e2b7')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
