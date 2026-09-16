"""Phase 6 (+ fix spec 3.1-3.4, 3.9): Streamlit demo -- upload -> review
mapping (per sheet, for a multi-sheet workbook) -> validation/duplicates
-> download clean export + health report.

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

from bordereaux import pipeline  # noqa: E402
from bordereaux.mapping import ai_mapping_available  # noqa: E402
from bordereaux.schema import FIELDS, REQUIRED_CODES  # noqa: E402

st.set_page_config(page_title="Bordereau Quality Checker", layout="wide", page_icon="📋")

EXAMPLE_FILE = REPO_ROOT / "data/synthetic/sender_a_sedgwick.csv"

FIELD_LABELS = {f.code: f"{f.code} — {f.name}" for f in FIELDS}
FIELD_LABELS["(unmapped)"] = "(unmapped)"
FIELD_OPTIONS = ["(unmapped)"] + [f.code for f in FIELDS]

st.title("Claims Bordereau Aggregation & Segregation Tool")
st.caption(
    "Upload a claims bordereau in any format -- a single sheet or a whole multi-sheet "
    "workbook. We standardise it, check it for errors and duplicates, and hand back a "
    "clean export plus a one-page data-quality report — no integration required."
)

with st.expander("What happens under the hood? (plain English)"):
    st.write(
        "Every insurer, MGA and TPA formats its claims spreadsheet differently — different "
        "column names, different date formats, different column order, sometimes even "
        "several senders' claims in one workbook, one sheet per sender. This tool reads "
        "every sheet in your file, works out which of each sheet's columns correspond to "
        "the ten core fields insurers care about (claim reference, status, key dates, "
        "insured name, policy reference, the paid / reserve / incurred amounts, and "
        "currency), and asks you to confirm that mapping before touching any data — a "
        "wrong mapping is never applied silently, and a column nobody could map is shown "
        "as not found rather than quietly treated as blank. It then checks every row for "
        "the kind of errors that creep into bordereaux — amounts that don't add up, "
        "required fields left blank, dates that don't make sense — and looks for claims "
        "that may have been reported more than once, including the same claim showing up "
        "on two different sheets. Nothing is changed, merged or deleted automatically: "
        "everything is flagged for a human to review. At the end you get back a clean file "
        "split by claim status, plus a one-page report grading the data quality of the file "
        "you sent, with a clear note if any part of the file couldn't be read so the score "
        "is never mistaken for a clean bill of health on data the tool never actually saw. "
        "The tool prepares data for human review; it does not make any claims decisions itself."
    )

st.divider()

# ---------------------------------------------------------------- Step 1
st.header("1. Choose a file")
col1, col2 = st.columns(2)
with col1:
    uploaded = st.file_uploader("Upload your own bordereau (single sheet or multi-sheet workbook)",
                                 type=["csv", "xlsx"])
with col2:
    st.write("...or")
    if st.button("Try it now with a sample bordereau"):
        st.session_state["use_example"] = True

if uploaded is not None:
    st.session_state["use_example"] = False

source_path = None
source_name = None
if uploaded is not None:
    suffix = ".csv" if uploaded.name.lower().endswith(".csv") else ".xlsx"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.write(uploaded.getvalue())
    tmp.close()
    source_path = Path(tmp.name)
    source_name = uploaded.name
elif st.session_state.get("use_example"):
    source_path = EXAMPLE_FILE
    source_name = EXAMPLE_FILE.name

if source_path is None:
    st.info("Upload a file or click 'Try it now' above to get started.")
    st.stop()

if st.session_state.get("loaded_source") != source_name:
    for key in list(st.session_state.keys()):
        if key.startswith("map_") or key in ("confirmed", "confirmed_mappings"):
            del st.session_state[key]
    st.session_state["loaded_source"] = source_name

sheets = pipeline.load_workbook(source_path)
active_sheets = [s for s in sheets if not s.skipped]
skipped_sheets = [s for s in sheets if s.skipped]

total_rows = sum(len(s.raw) for s in active_sheets)
st.success(f"Loaded **{source_name}**: {len(active_sheets)} of {len(sheets)} sheet(s) read, "
           f"{total_rows} rows total.")
if skipped_sheets:
    st.warning("Sheet(s) skipped — not read as claims data, not counted in any total below:\n\n"
               + "\n".join(f"- **{s.sheet_name}**: {s.skip_reason}" for s in skipped_sheets))

for s in active_sheets:
    with st.expander(f"Preview: {s.sheet_name} ({len(s.raw)} rows)", expanded=len(active_sheets) == 1):
        st.dataframe(s.raw.head(5), width="stretch")

# ---------------------------------------------------------------- Step 2
st.header("2. Review the proposed column mapping")
st.write(
    "Each sheet's columns have been matched to a standard field where possible. "
    "**Nothing is processed until you confirm every sheet's mapping below.**"
)

if not ai_mapping_available():
    st.warning(
        "AI-assisted mapping for unfamiliar headers is unavailable in this environment "
        "(ANTHROPIC_API_KEY is not set). Fuzzy matching against known aliases still ran for "
        "every sheet; any column left '(unmapped)' below needs a manual pick."
    )

with st.spinner("Matching columns against the standard fields, sheet by sheet..."):
    proposals = pipeline.propose_mapping_for_workbook(active_sheets)

confirmed_mappings: dict[str, dict[str, str]] = {}
audit_rows = []
for proposal in proposals:
    sheet = proposal.sheet
    suggestion_by_col = proposal.mapping.by_column
    sheet_mapped_codes = {s.field_code for s in proposal.mapping.suggestions if s.field_code}
    unmapped_required = [c for c in REQUIRED_CODES if c not in sheet_mapped_codes]

    label = f"{sheet.sheet_name} — {len(sheet.raw.columns)} columns"
    if unmapped_required:
        label += f" ⚠ {len(unmapped_required)} required field(s) still unmapped"

    with st.expander(label, expanded=bool(unmapped_required) or len(active_sheets) == 1):
        confirmed_mapping: dict[str, str] = {}
        for col in sheet.raw.columns:
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
                key=f"map_{source_name}_{sheet.sheet_name}_{col}",
            )
            audit_rows.append({"Sheet": sheet.sheet_name, "Your column": col,
                                "Suggested via": method_note, "Mapped to": FIELD_LABELS[chosen]})
            if chosen != "(unmapped)":
                confirmed_mapping[col] = chosen

        confirmed_mappings[sheet.sheet_name] = confirmed_mapping

with st.expander("Mapping audit trail (logged for every sheet processed)"):
    st.dataframe(pd.DataFrame(audit_rows), width="stretch", hide_index=True)

if st.button("Confirm all mappings and process file", type="primary"):
    st.session_state["confirmed_mappings"] = confirmed_mappings
    st.session_state["confirmed"] = True

if not st.session_state.get("confirmed"):
    st.stop()

# ---------------------------------------------------------------- Step 3
st.header("3. Results")
result = pipeline.run_workbook_pipeline(
    sheets, st.session_state["confirmed_mappings"], proposals, source_name=source_name,
)
h = result.health

coverage = h.coverage
coverage_msg = (f"Assessed {coverage.rows_assessed} of {coverage.rows_total} total rows "
                f"across {coverage.sheets_processed} of {coverage.sheets_total} sheets/tabs.")
if coverage.fully_covered:
    st.info(coverage_msg)
else:
    st.error(coverage_msg + " — some of the source file was not assessed; see skipped sheets above.")

if not h.score_reliable:
    reasons = []
    if not coverage.fully_covered:
        reasons.append("not every sheet/row was assessed")
    if h.unmapped_required_fields:
        reasons.append(f"required field(s) never mapped on at least one sheet: {', '.join(h.unmapped_required_fields)}")
    st.error("⚠ Score not fully reliable — " + "; ".join(reasons) + ".")

grade_color = {5: "green", 4: "green", 3: "orange", 2: "orange", 1: "red"}[h.grade]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Overall grade", f"{h.grade} / 5")
c1.markdown(f":{grade_color}[**{h.grade_label}**]")
c2.metric("Avg. field completeness", f"{h.overall_completeness_pct:.0f}%")
c3.metric("Rows with an exception", f"{h.exception_rate_pct:.0f}%")
c4.metric("Rows flagged as duplicates", f"{h.duplicate_rate_pct:.0f}%")

st.subheader("Field-by-field completeness")
completeness_df = pd.DataFrame([
    {
        "Field": fs.name,
        "Requirement": {
            "required": "Required", "optional": "Optional",
            "conditional_pair": "Conditional pair", "reconciled": "Reconciled",
        }[fs.requirement],
        "Completeness %": None if fs.never_mapped else fs.pct,
        "Status": "— column not found" if fs.never_mapped else "",
    }
    for fs in h.field_completeness
])
st.dataframe(
    completeness_df,
    width="stretch",
    hide_index=True,
    column_config={"Completeness %": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f%%")},
)

tab1, tab2 = st.tabs([f"Exceptions ({len(result.validation_result.exceptions)})",
                      f"Possible duplicates ({len(result.duplicates)})"])
with tab1:
    exceptions = result.validation_result.exceptions
    if exceptions.empty:
        st.write("No validation exceptions found.")
    else:
        st.dataframe(exceptions, width="stretch", hide_index=True)
    if result.validation_result.arithmetic_not_evaluable_count:
        st.caption(f"{result.validation_result.arithmetic_not_evaluable_count} row(s) could not be "
                   f"checked for paid + reserve = incurred (missing or unmapped inputs) — not counted "
                   f"as a mismatch, not counted as clean either.")
with tab2:
    if result.duplicates.empty:
        st.write("No possible duplicates found.")
    else:
        st.write("Flagged for review only — nothing is auto-merged. Checked across every sheet, "
                  "not just within one.")
        st.dataframe(result.duplicates, width="stretch", hide_index=True)

st.divider()
st.header("4. Download")

out_dir = Path(tempfile.mkdtemp(prefix="bordereaux_"))
stem = Path(source_name).stem
paths = pipeline.write_workbook_outputs(result, out_dir, stem)

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
