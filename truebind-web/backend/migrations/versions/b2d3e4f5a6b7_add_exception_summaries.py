"""add exception_summaries table

Revision ID: b2d3e4f5a6b7
Revises: a1c2d3e4f5a6
Create Date: 2026-09-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2d3e4f5a6b7'
down_revision: Union[str, Sequence[str], None] = 'a1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'exception_summaries',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('report_id', sa.String(length=36), nullable=False),
        sa.Column('narrative_status', sa.String(length=32), nullable=False),
        sa.Column('aggregate', sa.JSON(), nullable=False),
        sa.Column('narrative', sa.JSON(), nullable=True),
        sa.Column('narrative_model', sa.String(length=128), nullable=True),
        sa.Column('narrative_error', sa.String(length=2000), nullable=True),
        sa.Column('narrative_warning', sa.String(length=2000), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['report_id'], ['reports.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_exception_summaries_report_id'), 'exception_summaries', ['report_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_exception_summaries_report_id'), table_name='exception_summaries')
    op.drop_table('exception_summaries')
