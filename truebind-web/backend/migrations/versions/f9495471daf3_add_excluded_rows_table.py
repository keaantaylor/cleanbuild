"""add excluded_rows table

Revision ID: f9495471daf3
Revises: 5896de8d5326
Create Date: 2026-09-17 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f9495471daf3'
down_revision: Union[str, Sequence[str], None] = '5896de8d5326'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('excluded_rows',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('report_id', sa.String(length=36), nullable=False),
    sa.Column('sheet_name', sa.String(length=255), nullable=False),
    sa.Column('row_number', sa.Integer(), nullable=False),
    sa.Column('reason', sa.String(length=32), nullable=False),
    sa.Column('detail', sa.String(length=500), nullable=False),
    sa.Column('values', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['report_id'], ['reports.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_excluded_rows_report_id'), 'excluded_rows', ['report_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_excluded_rows_report_id'), table_name='excluded_rows')
    op.drop_table('excluded_rows')
