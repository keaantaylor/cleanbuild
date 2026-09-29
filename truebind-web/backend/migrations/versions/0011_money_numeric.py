"""Money columns become NUMERIC(18,2) (exact), rounded half-up to the cent.

Revision ID: 0011_money_numeric
Revises: 0010_report_soft_delete
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_money_numeric"
down_revision = "0010_report_soft_delete"
branch_labels = None
depends_on = None

MONEY = {
    "claim_rows": (
        "paid_amount", "paid_this_month", "previously_paid", "reserve_amount", "fees_paid_this_month",
        "fees_previously_paid", "fees_reserve", "fees_paid_to_date", "incurred_indemnity", "incurred_amount",
    ),
    "validation_results": ("delta",),
    "leakage_flags": ("amount_exposure",),
}  # fmt: skip


def upgrade() -> None:
    pg = op.get_bind().dialect.name == "postgresql"
    for table, columns in MONEY.items():
        if pg:
            for col in columns:
                # PostgreSQL ROUND(numeric) rounds half away from zero, i.e. half-up for money.
                op.execute(f"ALTER TABLE {table} ALTER COLUMN {col} TYPE NUMERIC(18,2) USING ROUND({col}::numeric, 2)")
        else:
            with op.batch_alter_table(table) as b:
                for col in columns:
                    b.alter_column(col, type_=sa.Numeric(18, 2), existing_nullable=True)


def downgrade() -> None:
    pg = op.get_bind().dialect.name == "postgresql"
    for table, columns in MONEY.items():
        if pg:
            for col in columns:
                op.execute(
                    f"ALTER TABLE {table} ALTER COLUMN {col} TYPE DOUBLE PRECISION USING {col}::double precision"
                )
        else:
            with op.batch_alter_table(table) as b:
                for col in columns:
                    b.alter_column(col, type_=sa.Float(), existing_nullable=True)
