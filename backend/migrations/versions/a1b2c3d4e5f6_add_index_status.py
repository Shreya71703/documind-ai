"""add index status

Revision ID: a1b2c3d4e5f6
Revises: f9d784a0d9b4
Create Date: 2026-07-12 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f9d784a0d9b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'documents',
        sa.Column('index_status', sa.String(length=50), nullable=False, server_default='not_indexed')
    )
    op.create_index(op.f('ix_documents_index_status'), 'documents', ['index_status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_documents_index_status'), table_name='documents')
    op.drop_column('documents', 'index_status')
