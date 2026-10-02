"""Website enquiries (demo / Health Check / contact / product-update sign-ups),
and the file a visitor may send with a Health Check request.

Not tenant data, so no Row Level Security policy; read access is limited in
the API to LEADS_ADMIN_EMAILS. (First drafted as 0017_leads on the
launch-readiness branch; renumbered after 0017-0019.)

Revision ID: 0020_leads
Revises: 0019_privacy_controls
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020_leads"
down_revision = "0019_privacy_controls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "leads",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("company", sa.String(length=200), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("attribution", sa.JSON(), nullable=True),
        sa.Column("page", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("file_name", sa.String(length=255), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("file_sha256", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_leads")),
    )
    op.create_index(op.f("ix_leads_kind"), "leads", ["kind"])
    op.create_index(op.f("ix_leads_email"), "leads", ["email"])
    op.create_table(
        "lead_files",
        sa.Column("lead_id", sa.String(length=36), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], name=op.f("fk_lead_files_lead_id_leads"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("lead_id", name=op.f("pk_lead_files")),
    )


def downgrade() -> None:
    op.drop_table("lead_files")
    op.drop_index(op.f("ix_leads_email"), table_name="leads")
    op.drop_index(op.f("ix_leads_kind"), table_name="leads")
    op.drop_table("leads")
