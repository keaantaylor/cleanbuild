"""Merge Alembic heads

Revision ID: 645325baf0c2
Revises: a1c3e7f92b4d, b2d3e4f5a6b7
Create Date: 2026-09-21 13:41:04.811365

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '645325baf0c2'
down_revision: Union[str, Sequence[str], None] = ('a1c3e7f92b4d', 'b2d3e4f5a6b7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
