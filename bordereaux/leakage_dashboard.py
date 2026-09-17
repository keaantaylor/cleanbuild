"""Truebind 2.1 frontend: Leakage & Duplicates dashboard.

Shown as a page in the multi-page app (see app.py). Reads persisted
LeakageFlag rows for a chosen report -- nothing here is computed live
from an in-memory upload, so this works across sessions.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from bordereaux import persistence, theme  # noqa: E402
from bordereaux.db.models import LeakageFlag, Report  # noqa: E402
from bordereaux.db.session import new_session  # noqa: E402
from bordereaux.leakage import CONFIDENCE_TIERS  # noqa: E402

theme.inject_theme_css()
persistence.ensure_schema()

st.title("Leakage & Duplicates")
st.caption(
    "Flags claims paid more than once — the same claim resubmitted, or a different claim "
    "reference for the same payee, amount and date. Every figure here is an estimate "
    "requiring human confirmation, never a confirmed recovery."
)

session = new_session()
reports = session.query(Report).order_by(Report.uploaded_at.desc()).limit(100).all()

if not reports:
    st.info("No processed reports yet. Upload a bordereau on the Upload & Process page first.")
    st.stop()

report_labels = {r.id: f"{r.source_name} — {r.uploaded_at:%Y-%m-%d %H:%M} ({r.rows_assessed} rows)" for r in reports}
selected_id = st.selectbox("Report", list(report_labels.keys()), format_func=lambda rid: report_labels[rid])

flags = session.query(LeakageFlag).filter(LeakageFlag.report_id == selected_id).all()

if not flags:
    st.success("No payment-leakage flags for this report.")
    st.stop()

exposure = sum(f.amount_exposure for f in flags if f.confidence in ("CERTAIN", "PROBABLE"))
tier_counts = {tier: sum(1 for f in flags if f.confidence == tier) for tier in CONFIDENCE_TIERS}

theme.render_stat("Estimated leakage exposure", f"€{exposure:,.2f}", tone="primary")
st.caption(
    "Sum of CERTAIN + PROBABLE flags only — POSSIBLE-tier matches are too weak to total. "
    "Estimate requiring human confirmation, not a confirmed recovery figure."
)

c1, c2, c3 = st.columns(3)
c1.metric("CERTAIN (exact claim ref match)", tier_counts["CERTAIN"])
c2.metric("PROBABLE (name+amount+date, <30d)", tier_counts["PROBABLE"])
c3.metric("POSSIBLE (name+amount, <90d)", tier_counts["POSSIBLE"])

st.divider()
st.subheader("Flagged items")

tier_filter = st.multiselect("Filter by confidence", list(CONFIDENCE_TIERS), default=list(CONFIDENCE_TIERS))
visible = [f for f in flags if f.confidence in tier_filter]

for flag in visible:
    header = f"{flag.insured_name_a or '(unknown)'} — €{flag.amount_exposure:,.2f} exposure"
    with st.expander(header):
        st.markdown(theme.leakage_tier_badge(flag.confidence), unsafe_allow_html=True)
        left, right = st.columns(2)
        with left:
            st.markdown("**Row A**")
            st.write({
                "Sheet": flag.sheet_a, "Row": flag.row_a, "Claim ref": flag.claim_ref_a,
                "Insured": flag.insured_name_a, "Paid amount": flag.amount_a,
            })
        with right:
            st.markdown("**Row B**")
            st.write({
                "Sheet": flag.sheet_b, "Row": flag.row_b, "Claim ref": flag.claim_ref_b,
                "Insured": flag.insured_name_b, "Paid amount": flag.amount_b,
            })
        st.caption(flag.detail)
        st.caption(f"Status: {flag.status}" + (f" · reviewed by {flag.reviewer}" if flag.reviewer else ""))
