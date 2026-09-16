"""Phase 6: Streamlit demo -- upload -> review mapping -> validation /
duplicates -> download clean export + health report.

Run: streamlit run app.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from bordereaux import ingest, pipeline  # noqa: E402
from bordereaux.mapping import fuzzy_match_headers  # noqa: E402
from bordereaux.schema import FIELDS  # noqa: E402

st.set_page_config(page_title="Bordereau Quality Checker", layout="wide", page_icon="📋")

EXAMPLE_FILES = {
    "Sedgwick Ireland — 50 rows, plain headers": REPO_ROOT / "data/synthetic/sender_a_sedgwick.csv",
    "Crawford Ireland — 200 rows, reordered columns": REPO_ROOT / "data/synthetic/sender_b_crawford.xlsx",
    "Blackrock MGA — 1,000 rows, camelCase headers": REPO_ROOT / "data/synthetic/sender_c_blackrock.xlsx",
    "MX Underwriting — 80 rows, unfamiliar headers (needs AI-assisted mapping)":
        REPO_ROOT / "data/synthetic/sender_d_mx_underwriting.xlsx",
}

FIELD_LABELS = {f.code: f"{f.code} — {f.name}" for f in FIELDS}
FIELD_LABELS["(unmapped)"] = "(unmapped)"
FIELD_OPTIONS = ["(unmapped)"] + [f.code for f in FIELDS]

st.title("Claims Bordereau Aggregation & Segregation Tool")
st.caption(
    "Upload a claims bordereau in any format. We standardise it, check it for errors and "
    "duplicates, and hand back a clean export plus a one-page data-quality report — no "
    "integration required."
)

with st.expander("What happens under the hood? (plain English)"):
    st.write(
        "Every insurer, MGA and TPA formats its claims spreadsheet differently — different "
        "column names, different date formats, different column order. This tool reads your "
        "file, works out which of your columns correspond to the ten core fields insurers care "
        "about (claim reference, status, key dates, insured name, policy reference, the paid / "
        "reserve / incurred amounts, and currency), and asks you to confirm that mapping before "
        "touching any data — a wrong mapping is never applied silently. It then checks every row "
        "for the kind of errors that creep into bordereaux — amounts that don't add up, required "
        "fields left blank, dates that don't make sense — and looks for claims that may have been "
        "reported more than once. Nothing is changed, merged or deleted automatically: everything "
        "is flagged for a human to review. At the end you get back a clean file split by claim "
        "status, plus a one-page report grading the data quality of the file you sent. The tool "
        "prepares data for human review; it does not make any claims decisions itself."
    )

st.divider()

# ---------------------------------------------------------------- Step 1
st.header("1. Choose a file")
col1, col2 = st.columns(2)
with col1:
    uploaded = st.file_uploader("Upload your own bordereau", type=["csv", "xlsx"])
with col2:
    example_choice = st.selectbox("...or try a sample bordereau now", ["(none)"] + list(EXAMPLE_FILES.keys()))

raw_df = None
source_name = None
if uploaded is not None:
    if uploaded.name.lower().endswith(".csv"):
        raw_df = pd.read_csv(uploaded, dtype="string")
    else:
        raw_df = pd.read_excel(uploaded, dtype="string", engine="openpyxl")
    source_name = uploaded.name
elif example_choice != "(none)":
    path = EXAMPLE_FILES[example_choice]
    raw_df = ingest.load_raw(path)
    source_name = path.name

if raw_df is None:
    st.info("Upload a file or pick a sample above to get started.")
    st.stop()

if st.session_state.get("loaded_source") != source_name:
    for key in list(st.session_state.keys()):
        if key.startswith("map_") or key in ("confirmed", "confirmed_mapping"):
            del st.session_state[key]
    st.session_state["loaded_source"] = source_name

st.success(f"Loaded **{source_name}**: {len(raw_df)} rows, {len(raw_df.columns)} columns.")
st.dataframe(raw_df.head(10), width="stretch")

# ---------------------------------------------------------------- Step 2
st.header("2. Review the proposed column mapping")
st.write(
    "Each of your columns has been matched to a standard field where possible. "
    "**Nothing is processed until you confirm this mapping below.**"
)

try:
    with st.spinner("Matching your columns against the standard fields..."):
        suggestions = pipeline.propose_mapping(raw_df)
    ai_error = None
except Exception as exc:  # AI fallback unavailable (e.g. no ANTHROPIC_API_KEY)
    suggestions = list(fuzzy_match_headers(raw_df.columns.tolist()).values())
    ai_error = str(exc)

if ai_error:
    st.warning(
        f"AI-assisted mapping for unfamiliar headers is unavailable in this environment "
        f"({ai_error}). Fuzzy matching against known aliases still ran; any column left "
        f"'(unmapped)' below needs a manual pick."
    )

suggestion_by_col = {s.source_column: s for s in suggestions}

confirmed_mapping: dict[str, str] = {}
mapping_rows = []
for col in raw_df.columns:
    s = suggestion_by_col.get(col)
    default_code = s.field_code if s else None
    default_index = FIELD_OPTIONS.index(default_code) if default_code in FIELD_OPTIONS else 0
    method_note = f"{s.method}, confidence {s.confidence:.0f}" if s else "no suggestion"

    chosen = st.selectbox(
        f"'{col}'",
        FIELD_OPTIONS,
        index=default_index,
        format_func=lambda code: FIELD_LABELS[code],
        help=f"Suggested via {method_note}",
        key=f"map_{source_name}_{col}",
    )
    mapping_rows.append({"Your column": col, "Suggested via": method_note, "Mapped to": FIELD_LABELS[chosen]})
    if chosen != "(unmapped)":
        confirmed_mapping[col] = chosen

with st.expander("Mapping audit trail (logged for every file processed)"):
    st.dataframe(pd.DataFrame(mapping_rows), width="stretch", hide_index=True)

if st.button("Confirm mapping and process file", type="primary"):
    st.session_state["confirmed_mapping"] = confirmed_mapping
    st.session_state["confirmed"] = True

if not st.session_state.get("confirmed"):
    st.stop()

# ---------------------------------------------------------------- Step 3
st.header("3. Results")
result = pipeline.run_pipeline(raw_df, st.session_state["confirmed_mapping"], source_name=source_name)
h = result.health

grade_color = {5: "green", 4: "green", 3: "orange", 2: "orange", 1: "red"}[h.grade]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Overall grade", f"{h.grade} / 5")
c1.markdown(f":{grade_color}[**{h.grade_label}**]")
c2.metric("Avg. field completeness", f"{h.overall_completeness_pct:.0f}%")
c3.metric("Rows with an exception", f"{h.exception_rate_pct:.0f}%")
c4.metric("Rows flagged as duplicates", f"{h.duplicate_rate_pct:.0f}%")

st.subheader("Field-by-field completeness")
completeness_df = pd.DataFrame([
    {"Field": fs.name, "Required": "Yes" if fs.required else "Conditional", "Completeness %": fs.pct}
    for fs in h.field_completeness
])
st.dataframe(
    completeness_df,
    width="stretch",
    hide_index=True,
    column_config={"Completeness %": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f%%")},
)

tab1, tab2 = st.tabs([f"Exceptions ({len(result.exceptions)})", f"Possible duplicates ({len(result.duplicates)})"])
with tab1:
    if result.exceptions.empty:
        st.write("No validation exceptions found.")
    else:
        st.dataframe(result.exceptions, width="stretch", hide_index=True)
with tab2:
    if result.duplicates.empty:
        st.write("No possible duplicates found.")
    else:
        st.write("Flagged for review only — nothing is auto-merged.")
        st.dataframe(result.duplicates, width="stretch", hide_index=True)

st.divider()
st.header("4. Download")

out_dir = Path(tempfile.mkdtemp(prefix="bordereaux_"))
stem = Path(source_name).stem
paths = pipeline.write_outputs(result, out_dir, stem)

d1, d2, d3 = st.columns(3)
with d1:
    st.download_button(
        "⬇ Clean, segregated export (.xlsx)",
        data=paths["segregated"].read_bytes(),
        file_name=f"{stem}_segregated.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
with d2:
    st.download_button(
        "⬇ Health report — full detail (.xlsx)",
        data=paths["health"].read_bytes(),
        file_name=f"{stem}_health_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
with d3:
    st.download_button(
        "⬇ Health report — one-pager (.pdf)",
        data=paths["health_pdf"].read_bytes(),
        file_name=f"{stem}_health_report.pdf",
        mime="application/pdf",
    )
