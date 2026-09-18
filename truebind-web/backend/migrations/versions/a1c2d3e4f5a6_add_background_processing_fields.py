"""add background processing fields to reports

Revision ID: a1c2d3e4f5a6
Revises: 5896de8d5326
Create Date: 2026-09-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c2d3e4f5a6'
down_revision: Union[str, Sequence[str], None] = '5896de8d5326'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('reports', sa.Column('processing_phase', sa.String(length=64), nullable=True))
    op.add_column('reports', sa.Column('processing_error', sa.String(length=2000), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('reports', 'processing_error')
    op.drop_column('reports', 'processing_phase')
