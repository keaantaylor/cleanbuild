"""Truebind 2.2 frontend: Compliance & Audit view.

Reverse-chronological audit log with filters, plus the one-click
Governance Review Pack export. Reachable from the health report
dashboard (see app.py's navigation).
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from bordereaux import governance_pack, persistence, theme  # noqa: E402
from bordereaux.db.models import AuditLogEntry, Report  # noqa: E402
from bordereaux.db.session import new_session  # noqa: E402

theme.inject_theme_css()
persistence.ensure_schema()

st.title("Compliance & Audit")
st.caption(
    "Every mapping confirmation, override, obligation status change and export, logged with "
    "actor and timestamp. Append-only — nothing here is ever edited or deleted."
)

session = new_session()
reports = session.query(Report).order_by(Report.uploaded_at.desc()).limit(100).all()

if not reports:
    st.info("No processed reports yet. Upload a bordereau on the Upload & Process page first.")
    st.stop()

report_labels = {r.id: f"{r.source_name} — {r.uploaded_at:%Y-%m-%d %H:%M}" for r in reports}
selected_id = st.selectbox("Report / sender / period", list(report_labels.keys()),
                            format_func=lambda rid: report_labels[rid])
selected_report = next(r for r in reports if r.id == selected_id)

if st.button("📄 Export Governance Review Pack", type="primary"):
    out_dir = Path(tempfile.mkdtemp(prefix="governance_pack_"))
    out_path = out_dir / f"{selected_report.source_name}_governance_pack.pdf"
    governance_pack.build_governance_pack(session, selected_id, out_path)
    from bordereaux import audit
    audit.log_action(session, st.session_state.get("actor", "streamlit_user"),
                      audit.ACTION_EXPORT_TRIGGERED, entity_type="governance_pack",
                      entity_id=selected_id, report_id=selected_id)
    session.commit()
    st.download_button(
        "⬇ Download Governance Review Pack (.pdf)",
        data=out_path.read_bytes(),
        file_name=out_path.name,
        mime="application/pdf",
    )

st.divider()
st.subheader("Audit log")

entries = (
    session.query(AuditLogEntry)
    .filter(AuditLogEntry.report_id == selected_id)
    .order_by(AuditLogEntry.timestamp.desc())
    .all()
)

if not entries:
    st.write("No audit entries for this report.")
    st.stop()

actors = sorted({e.actor for e in entries})
action_types = sorted({e.action_type for e in entries})
c1, c2 = st.columns(2)
with c1:
    actor_filter = st.multiselect("Actor", actors, default=actors)
with c2:
    action_filter = st.multiselect("Action type", action_types, default=action_types)

filtered = [e for e in entries if e.actor in actor_filter and e.action_type in action_filter]

df = pd.DataFrame([
    {
        "When": e.timestamp, "Actor": e.actor, "Action": e.action_type,
        "Entity": f"{e.entity_type}:{e.entity_id}" if e.entity_id else e.entity_type,
        "Before": e.before_value, "After": e.after_value,
    }
    for e in filtered
])
st.dataframe(df, width="stretch", hide_index=True)
