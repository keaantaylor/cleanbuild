"""AI-generated exception triage summaries (see services/exception_
aggregation_service.py and exception_narrative_service.py). Append-only,
same pattern as audit_log: each POST /exceptions/summary creates a new
row rather than overwriting the last one, so "regenerate" has a history
and the audit trail (services/audit_service.log_action) can point at a
specific row.

The deterministic `aggregate` is computed synchronously (fast, no
external call) and is ALWAYS present once a row exists. `narrative` is
the LLM's structured output and may be null -- narrative_status says why
(GENERATING while the background task is still running, UNAVAILABLE if
no ANTHROPIC_API_KEY is configured, FAILED if the call errored or timed
out). The Exceptions page always has the hard numbers from `aggregate`
even when the narrative never arrives -- see fix spec Section 1's
requirement that an AI failure must never block access to the underlying
data."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ._util import created_at_col, uuid_pk

NARRATIVE_STATUSES = ("GENERATING", "COMPLETE", "UNAVAILABLE", "FAILED")


class ExceptionSummary(Base):
    __tablename__ = "exception_summaries"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    narrative_status: Mapped[str] = mapped_column(String(32), default="GENERATING")
    # The deterministic, code-computed aggregate (counts/values by
    # category/sheet/root-cause) -- see ExceptionAggregate in
    # exception_aggregation_service.py for the exact shape.
    aggregate: Mapped[dict] = mapped_column(JSON)
    # {executive_summary, actions, ingestion_issues, data_issues} once the
    # LLM call succeeds; null otherwise.
    narrative: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    narrative_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    narrative_error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # Set if the numeric-consistency check (exception_narrative_service.
    # _find_unverifiable_numbers) found a figure in the narrative that
    # doesn't trace back to the aggregate -- never blocks the narrative,
    # just flags it for a reviewer, since this is a compliance-sensitive
    # tool and an LLM figure that doesn't trace to the deterministic
    # engine must never be presented as if it does.
    narrative_warning: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = created_at_col()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
