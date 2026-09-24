"""Bridges bordereaux pipeline results into the database.

Rules:
- Every row written carries the report's tenant_id.
- Writes are bulk (Core insert executemany), not one ORM object per row
  (forensic: persist was 43 s at 100k rows / 109-115 s at 250k).
- Idempotent: ingest and process REPLACE a report's previous results inside
  the job's transaction, so a retry or re-process never duplicates rows
  (forensic S10).
- The report summary is computed ONCE, at persist time, from the engine's
  own reconciliation (bordereaux.report) -- the API serves it, it does not
  re-derive it per request (forensic: 17-19 s summary GET at 250k rows).
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict

import pandas as pd
from sqlalchemy import delete, func, insert
from sqlalchemy.orm import Session

from ..models._util import new_uuid, utcnow
from ..models.alerts import Alert
from ..models.reports import ClaimRow, ExcludedRow, Mapping, Report, Sheet, ValidationResult
from . import alert_service, audit_service
from .pipeline_service import FIELDS, FIELDS_BY_CODE, REQUIRED_CODES as _REQUIRED, classify_sheet_status, mapping_mod

FIELD_TO_COLUMN = {
    "CR0104M": "claim_reference", "CR0105CM": "claim_status", "CR0119CM": "date_of_loss",
    "CR0136CM": "date_notified", "CR0035M": "insured_name", "CR0029M": "policy_reference",
    "TB_PAID_TD": "paid_amount", "CR0126CM": "paid_this_month", "CR0128CM": "previously_paid",
    "CR0130CM": "reserve_amount", "CR0127CM": "fees_paid_this_month", "CR0129CM": "fees_previously_paid",
    "CR0131CM": "fees_reserve", "TB_FEES_PAID_TD": "fees_paid_to_date", "CR0134CM": "incurred_indemnity", "CR0155CM": "incurred_amount",
    "CR0110CM": "currency", "TB_PERIOD": "reporting_period",
}
assert set(FIELD_TO_COLUMN) == set(FIELDS_BY_CODE), "every canonical field needs a claim_rows column"

RULE_CHECK_TYPE = {
    "missing_mandatory_field": "MANDATORY_FIELD", "arithmetic_mismatch": "ARITHMETIC",
    "date_order": "DATE", "date_in_future": "DATE", "invalid_currency": "CURRENCY",
    "currency_inconsistency": "CURRENCY", "invalid_status": "STATUS", "schema_violation": "OTHER",
}
RULE_SEVERITY = {
    "missing_mandatory_field": "CRITICAL", "arithmetic_mismatch": "HIGH", "invalid_currency": "HIGH",
    "currency_inconsistency": "HIGH", "date_order": "MEDIUM", "date_in_future": "MEDIUM", "invalid_status": "MEDIUM", "schema_violation": "HIGH",
}
_CHUNK = 5000


def _bulk(db: Session, model, rows: list[dict]) -> None:
    for i in range(0, len(rows), _CHUNK):
        db.execute(insert(model), rows[i:i + _CHUNK])


def _clean(v):
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


# --------------------------------------------------------------------- ingest

def _samples(raw: pd.DataFrame, per_column: int = 3, max_len: int = 60) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for col in raw.columns[:500]:
        if str(col).startswith("__blank_col_"):
            continue
        vals: list[str] = []
        for v in raw[col].head(200).tolist():
            if _clean(v) is None or str(v).strip() == "":
                continue
            sv = str(v)[:max_len]
            if sv not in vals:
                vals.append(sv)
            if len(vals) >= per_column:
                break
        out[str(col)[:255]] = vals
    return out


def persist_ingest(db: Session, report: Report, sheets, proposals, ai_meta: dict) -> None:
    tid = report.tenant_id
    for model in (ExcludedRow, Mapping, Sheet):
        db.execute(delete(model).where(model.report_id == report.id))
    proposal_by_sheet = {p.sheet.sheet_name: p for p in proposals}
    excluded: list[dict] = []
    mappings: list[dict] = []
    for i, s in enumerate(sheets):
        sheet_id = new_uuid()
        headers = [c for c in s.raw.columns] if not s.skipped else []
        db.add(Sheet(
            id=sheet_id, tenant_id=tid, report_id=report.id, sheet_name=s.sheet_name[:255], sheet_index=i,
            header_row_index=s.header_row_index if not s.skipped else None,
            row_count=len(s.raw) if not s.skipped else 0,
            source_column_count=sum(1 for c in headers if not str(c).startswith("__blank_col_")),
            headers=[str(h)[:255] for h in headers], status="SKIPPED" if s.skipped else "PENDING_CONFIRMATION",
            skip_reason=(s.skip_reason or None) and s.skip_reason[:500], hidden=s.hidden, notes=list(s.notes),
            trailing_blank_rows=s.trailing_blank_rows, samples=_samples(s.raw) if not s.skipped else None,
        ))
        for er in s.excluded_rows:
            excluded.append({"id": new_uuid(), "tenant_id": tid, "report_id": report.id,
                             "sheet_name": er.sheet_name[:255], "row_number": er.row_number, "row_count": er.count,
                             "reason": er.reason, "detail": er.detail[:500],
                             "values": {str(k)[:255]: str(v)[:500] for k, v in er.values.items()}})
        proposal = proposal_by_sheet.get(s.sheet_name)
        if proposal is None:
            continue
        by_field = {sg.field_code: sg for sg in proposal.mapping.suggestions if sg.field_code}
        for f in FIELDS:
            sg = by_field.get(f.code)
            if sg is None:
                mappings.append({"id": new_uuid(), "tenant_id": tid, "report_id": report.id, "sheet_id": sheet_id,
                                 "field_code": f.code, "field_name": f.name, "source_column": None,
                                 "mapping_state": "UNMAPPED", "review_state": "UNMAPPED",
                                 "evidence": None, "rule_version": mapping_mod.MAPPING_RULE_VERSION,
                                 "ai_model": None, "confidence_score": None})
            else:
                mappings.append({"id": new_uuid(), "tenant_id": tid, "report_id": report.id, "sheet_id": sheet_id,
                                 "field_code": f.code, "field_name": f.name, "source_column": sg.source_column[:255],
                                 "mapping_state": "MAPPED_BY_AI" if sg.method == "ai" else "MAPPED_BY_ALIAS",
                                 "review_state": sg.review_state, "evidence": (sg.evidence or "")[:1000],
                                 "rule_version": sg.rule_version,
                                 "ai_model": proposal.mapping.ai_model if sg.method == "ai" else None,
                                 "confidence_score": float(sg.confidence)})
        if proposal.mapping.ai_attempted:
            audit_service.log_action(
                db, tid, report.id, "AI_MAPPING_SUGGESTED", "REPORT", report.id,
                after={"sheet": s.sheet_name, "model": proposal.mapping.ai_model,
                       "suggested": {sg.source_column: sg.field_code for sg in proposal.mapping.suggestions
                                     if sg.method == "ai"},
                       "error": proposal.mapping.ai_unavailable_reason, "usage": proposal.mapping.ai_usage})
    db.flush()
    _bulk(db, ExcludedRow, excluded)
    _bulk(db, Mapping, mappings)
    report.sheet_count_total = len(sheets)
    report.ingest_notes = ai_meta


def validate_mapping_choices(sheet: Sheet, choices: dict[str, str | None]) -> None:
    """Server-side validation of a mapping confirmation. Raises ValueError
    with a customer-safe message. The browser is untrusted: field codes must
    be canonical, columns must exist in THIS sheet's detected headers, and a
    column may feed at most one field (P7)."""
    headers = set(sheet.headers or [])
    used: dict[str, str] = {}
    for code, col in choices.items():
        if code not in FIELDS_BY_CODE:
            raise ValueError(f"Unknown field {code!r}.")
        if col is None:
            continue
        if col not in headers:
            raise ValueError(f"Column {col!r} does not exist on sheet {sheet.sheet_name!r}.")
        if col in used:
            raise ValueError(f"Column {col!r} is assigned to both {used[col]} and {code}; choose one.")
        used[col] = code


def confirm_sheet_mapping(db: Session, report: Report, sheet: Sheet, choices: dict[str, str | None],
                          actor: str, actor_user_id: str | None) -> None:
    existing = {m.field_code: m for m in db.query(Mapping).filter_by(sheet_id=sheet.id).all()}
    # Validate the RESULTING mapping (stored choices overlaid by this
    # request), so a partial update cannot bind one column to two fields.
    merged = {code: m.source_column for code, m in existing.items() if m.mapping_state != "UNMAPPED"}
    merged.update(choices)
    validate_mapping_choices(sheet, merged)
    now = utcnow()
    for code, col in choices.items():
        row = existing.get(code)
        if row is None:
            continue
        before = {"source_column": row.source_column, "mapping_state": row.mapping_state,
                  "review_state": row.review_state}
        if col is None:
            row.mapping_state, row.source_column = "UNMAPPED", None
        elif not (row.source_column == col and row.mapping_state in ("MAPPED_BY_ALIAS", "MAPPED_BY_AI")):
            row.mapping_state, row.source_column = "MANUAL", col
            row.evidence = "chosen by a person"
        row.review_state = "CONFIRMED" if col else "UNMAPPED"
        row.confirmed_at, row.confirmed_by = now, actor
        after = {"source_column": row.source_column, "mapping_state": row.mapping_state, "review_state": row.review_state}
        action = "MAPPING_OVERRIDDEN" if before["source_column"] != after["source_column"] else "MAPPING_CONFIRMED"
        audit_service.log_action(db, report.tenant_id, report.id, action, "MAPPING", row.id,
                                 before={"field": code, **before}, after={"field": code, **after},
                                 actor=actor, actor_user_id=actor_user_id)
    sheet.status = "CONFIRMED"


def confirmed_mapping_for_sheet(db: Session, sheet: Sheet) -> dict[str, str]:
    rows = db.query(Mapping).filter_by(sheet_id=sheet.id).all()
    return {m.source_column: m.field_code for m in rows if m.source_column and m.mapping_state != "UNMAPPED"}


def proposals_from_db(db: Session, report: Report, sheets):
    """Rebuild mapping provenance from stored rows (so /process never calls
    the AI again -- forensic: proposals were regenerated, doubling cost)."""
    from bordereaux.mapping import MappingBatchResult, MappingSuggestion
    from bordereaux.pipeline import SheetMappingProposal

    db_sheets = {s.sheet_name: s for s in db.query(Sheet).filter_by(report_id=report.id)}
    out = []
    for s in sheets:
        if s.skipped or s.sheet_name not in db_sheets:
            continue
        rows = db.query(Mapping).filter_by(sheet_id=db_sheets[s.sheet_name].id).all()
        sugg = [MappingSuggestion(m.source_column, m.field_code, m.confidence_score or 0.0,
                                  "ai" if m.mapping_state == "MAPPED_BY_AI" else "alias")
                for m in rows if m.source_column and m.mapping_state in ("MAPPED_BY_ALIAS", "MAPPED_BY_AI")]
        out.append(SheetMappingProposal(s, MappingBatchResult(suggestions=sugg)))
    return out


def sheet_mapping_status(sheet: Sheet, mapping_rows: list[Mapping]) -> tuple[str, int, int]:
    if sheet.status == "SKIPPED":
        is_crash = bool(sheet.skip_reason and sheet.skip_reason.startswith("error while reading"))
        return ("error" if is_crash else "empty"), 0, len(FIELDS)
    mapped_codes = [m.field_code for m in mapping_rows if m.mapping_state != "UNMAPPED"]
    status, _ = classify_sheet_status(False, None, mapped_codes, source_column_count=sheet.source_column_count or None)
    return status, len(set(mapped_codes)), len(FIELDS)


# --------------------------------------------------------------------- process

def persist_pipeline_result(db: Session, report: Report, sheets, result, sheet_id_by_name: dict[str, str]) -> None:
    tid = report.tenant_id
    db.execute(delete(ValidationResult).where(ValidationResult.report_id == report.id))
    db.execute(delete(ClaimRow).where(ClaimRow.report_id == report.id))
    db.execute(delete(Alert).where(Alert.report_id == report.id, Alert.source.in_(alert_service.QUALITY_SOURCES)))

    canonical = result.canonical.reset_index(drop=True)
    n = len(canonical)
    local_idx = canonical.groupby("_source_sheet").cumcount().tolist() if n else []
    ids = [new_uuid() for _ in range(n)]
    cols = {code: canonical[code].tolist() if code in canonical.columns else [None] * n for code in FIELD_TO_COLUMN}
    src_rows = canonical["_source_row"].tolist() if "_source_row" in canonical.columns else [None] * n
    extras = canonical["_unmapped_values"].tolist() if "_unmapped_values" in canonical.columns else [None] * n
    sheets_col = canonical["_source_sheet"].tolist() if n else []
    rows = []
    for i in range(n):
        r = {"id": ids[i], "tenant_id": tid, "report_id": report.id, "sheet_id": sheet_id_by_name.get(sheets_col[i]),
             "row_index": int(local_idx[i]), "source_row_number": _clean(src_rows[i]), "extracted_at": utcnow(),
             "unmapped_values": (extras[i] or None) if isinstance(extras[i], dict) else None}
        for code, col in FIELD_TO_COLUMN.items():
            v = _clean(cols[code][i])
            if v is not None and col in ("date_of_loss", "date_notified"):
                v = v.date()
            elif v is not None and isinstance(v, str):
                v = v[:500 if col == "insured_name" else 255 if col != "currency" else 64]
            elif v is not None and hasattr(v, "item"):
                v = v.item()
            r[col] = v
        if r["source_row_number"] is not None:
            r["source_row_number"] = int(r["source_row_number"])
        rows.append(r)
    _bulk(db, ClaimRow, rows)

    vrs: list[dict] = []

    def vr(pos, check_type, status, severity, message, rule, extra=None):
        if pos >= n:
            raise RuntimeError(f"finding references row {pos} but only {n} rows were persisted (integrity bug)")
        vrs.append({"id": new_uuid(), "tenant_id": tid, "report_id": report.id, "claim_row_id": ids[pos],
                    "check_type": check_type, "rule": rule, "status": status, "severity": severity,
                    "message": str(message)[:2000], "delta": None, "extra": extra or {"rule": rule}})

    exc = result.validation_result.exceptions
    for pos, rule, detail in zip(exc["row_index"].tolist(), exc["rule"].tolist(), exc["detail"].tolist()):
        vr(int(pos), RULE_CHECK_TYPE.get(rule, "OTHER"), "FAIL", RULE_SEVERITY.get(rule, "INFO"), detail, rule)
    ne = result.validation_result.not_evaluable_detail
    for pos, reason, detail in zip(ne["row_index"].tolist(), ne["reason"].tolist(), ne["detail"].tolist()):
        vr(int(pos), "ARITHMETIC", "NOT_EVALUABLE", "MEDIUM", detail, reason)
    dups = result.duplicates
    for a, b, mt, detail in zip(dups["row_index_a"].tolist(), dups["row_index_b"].tolist(),
                                dups["match_type"].tolist(), dups["detail"].tolist()):
        if b >= n:
            raise RuntimeError("duplicate pair references a missing row (integrity bug)")
        severity = "HIGH" if mt == "exact_duplicate" else "MEDIUM"
        status = "REVIEW" if mt == "repeat_period_unknown" else "FAIL"
        vr(int(a), "DUPLICATE", status, severity, detail, mt, {"rule": mt, "match_type": mt,
                                                              "match_claim_row_id": ids[int(b)]})
    alerts = _mapping_completeness(result, canonical, ids, vr, tid, report.id)
    _bulk(db, ValidationResult, vrs)

    cov, health = result.coverage, result.health
    db_sheets = {s.sheet_name: s for s in db.query(Sheet).filter_by(report_id=report.id)}
    for name, tr in cov.sheet_transforms.items():
        if name in db_sheets:
            db_sheets[name].transforms = tr
    for name, notes in cov.sheet_notes.items():
        if name in db_sheets:
            db_sheets[name].notes = notes

    report.rows_processed = n
    report.rows_total = cov.rows_total
    report.coverage_pct = (100.0 * cov.rows_assessed / cov.rows_total) if cov.rows_total else 0.0
    report.grade = str(health.grade)
    report.score = health.composite_score
    report.arithmetic_not_evaluable = health.arithmetic_not_evaluable
    report.summary = build_summary(result, canonical)
    # Reverse mapping audit: every source column no canonical field claimed
    # gets its own entry (mirror of the per-field UNMAPPED mapping rows).
    for sheet_name, cols in (cov.unmapped_source_columns or {}).items():
        for col in cols:
            audit_service.log_action(db, tid, report.id, "SOURCE_COLUMN_UNMAPPED", "MAPPING",
                                     sheet_id_by_name.get(sheet_name) or report.id,
                                     after={"sheet": sheet_name, "field_code": None, "source_column": col,
                                            "mapping_state": "UNMAPPED", "data_retained": True})
    for a in alerts + _report_alerts(health, cov):
        db.add(Alert(tenant_id=tid, report_id=report.id, **a))


def _mapping_completeness(result, canonical, ids, vr, tid, report_id) -> list[dict]:
    cov = result.coverage
    ncs = set(cov.non_claim_summary_sheets)
    mapped_counts = {name: sum(1 for v in st.values() if v != "unmapped")
                     for name, st in cov.sheet_field_state.items() if name not in ncs}
    alerts = []
    if not mapped_counts or canonical.empty:
        return alerts
    best = max(mapped_counts.values())
    first_pos = {}
    for pos, name in enumerate(canonical["_source_sheet"].tolist()):
        first_pos.setdefault(name, pos)
    for name, mapped in mapped_counts.items():
        if not (mapped == 0 or (best > 0 and mapped < best / 2)):
            continue
        severity = "CRITICAL" if mapped == 0 else "HIGH"
        msg = (f"Sheet {name!r}: {mapped} of {len(FIELDS)} canonical fields mapped -- "
               + ("no columns matched a known field; needs manual review." if mapped == 0
                  else "well below the rest of this file; needs manual review."))
        alerts.append({"severity": severity, "source": "MAPPING_COMPLETENESS", "message": msg})
        if name in first_pos:
            vr(first_pos[name], "MAPPING_COMPLETENESS", "FAIL", severity, msg, "mapping_completeness",
               {"rule": "mapping_completeness", "sheet_name": name, "mapped": mapped})
    return alerts


def _report_alerts(health, cov) -> list[dict]:
    out = []
    if not cov.fully_covered:
        skipped = "; ".join(f"{n!r} ({r})" for n, r in cov.skipped_sheets)
        out.append({"severity": "HIGH", "source": "COVERAGE",
                    "message": f"Assessed {cov.rows_assessed} of {cov.rows_total} rows across {cov.sheets_processed} "
                               f"of {cov.sheets_total} sheets." + (f" Skipped: {skipped}." if skipped else "")})
    if health.missing_mandatory_rows:
        out.append({"severity": "CRITICAL", "source": "MANDATORY_FAIL",
                    "message": f"{health.missing_mandatory_rows} row(s) missing a mandatory field."})
    if health.arithmetic_not_evaluable:
        out.append({"severity": "MEDIUM", "source": "NOT_EVALUABLE",
                    "message": f"{health.arithmetic_not_evaluable} row(s) not evaluable for arithmetic reconciliation."})
    if health.exact_duplicates or health.probable_duplicates or health.period_unknown_repeats:
        out.append({"severity": "MEDIUM", "source": "DUPLICATE",
                    "message": f"{health.exact_duplicates} certain + {health.probable_duplicates} probable duplicate(s); "
                               f"{health.period_unknown_repeats} repeat(s) needing a reporting period."})
    return out


def build_summary(result, canonical: pd.DataFrame) -> dict:
    """Everything the report screen shows, computed from the engine's own
    objects. Every number here has one definition (see `definitions`)."""
    cov, health, vres = result.coverage, result.health, result.validation_result
    devs = getattr(result, "developments", None)
    if devs is None:
        devs = pd.DataFrame(columns=["claim_ref_a"])
    rec = cov.reconciliation
    exc = vres.exceptions
    rule_counts = exc["rule"].value_counts().to_dict() if not exc.empty else {}
    ne_counts = vres.not_evaluable_detail["reason"].value_counts().to_dict() if not vres.not_evaluable_detail.empty else {}
    totals = []
    if not canonical.empty:
        ccy = canonical["CR0110CM"].astype("object").where(canonical["CR0110CM"].notna(), None)
        grp = defaultdict(lambda: {"rows": 0, "paid_to_date": 0.0, "reserve": 0.0, "incurred": 0.0,
                                   "fees_paid_to_date": 0.0, "paid_rows": 0, "reserve_rows": 0, "incurred_rows": 0,
                                   "fees_rows": 0})
        fees_col = canonical["TB_FEES_PAID_TD"].tolist() if "TB_FEES_PAID_TD" in canonical.columns else [None] * len(canonical)
        row_keys = {"paid_to_date": "paid_rows", "reserve": "reserve_rows", "incurred": "incurred_rows",
                    "fees_paid_to_date": "fees_rows"}
        for c, paid, res, inc, fee in zip(ccy.tolist(), canonical["TB_PAID_TD"].tolist(),
                                          canonical["CR0130CM"].tolist(), canonical["CR0155CM"].tolist(), fees_col):
            g = grp[c or "UNKNOWN"]
            g["rows"] += 1
            for key, v in (("paid_to_date", paid), ("reserve", res), ("incurred", inc), ("fees_paid_to_date", fee)):
                if _clean(v) is not None:
                    g[key] += float(v)
                    g[row_keys[key]] += 1
        totals = [{"currency": k, **{kk: (round(vv, 2) if isinstance(vv, float) else vv) for kk, vv in v.items()}}
                  for k, v in sorted(grp.items())]
    def _value_counts(code: str, limit: int = 12) -> dict[str, int]:
        """Row counts per distinct value of one canonical field, as reported
        (dates as ISO dates); blanks are counted as "Not stated"."""
        if canonical.empty or code not in canonical.columns:
            return {}
        counts: Counter = Counter()
        for v in canonical[code].tolist():
            if _clean(v) is None or str(v).strip() == "":
                counts["Not stated"] += 1
            else:
                counts[v.date().isoformat() if hasattr(v, "date") and callable(v.date) else str(v).strip()] += 1
        return dict(counts.most_common(limit))

    summary = {
        "claim_status_counts": _value_counts("CR0105CM"),
        "reporting_periods": _value_counts("TB_PERIOD"),
        "sheets_total": cov.sheets_total,
        "sheets_processed": cov.sheets_processed,
        "total_claims": health.total_claims,
        "grade": health.grade, "grade_label": health.grade_label,
        "composite_score": round(health.composite_score, 2),
        "score_reliable": health.score_reliable,
        "missing_mandatory_rows": health.missing_mandatory_rows,
        "arithmetic_matches": vres.arithmetic_match_count,
        "arithmetic_mismatches": health.arithmetic_mismatches,
        "arithmetic_not_evaluable": health.arithmetic_not_evaluable,
        "not_evaluable_by_reason": ne_counts,
        "exception_counts_by_rule": rule_counts,
        "exact_duplicates": health.exact_duplicates,
        "probable_duplicates": health.probable_duplicates,
        "period_unknown_repeats": health.period_unknown_repeats,
        "field_completeness": [{"field_code": f.code, "field_name": f.name, "present": f.present,
                                "denominator": f.denominator, "never_mapped": f.never_mapped}
                               for f in health.field_completeness],
        "excluded_row_counts": cov.excluded_row_counts,
        "skipped_sheets": [{"sheet_name": n, "reason": r} for n, r in cov.skipped_sheets],
        "sheet_audit": [{"sheet_name": a.sheet_name, "status": a.status, "reason": a.reason,
                         "rows_processed": a.rows_processed, "rows_rejected": a.rows_rejected,
                         "fields_mapped": a.fields_mapped} for a in cov.sheet_audit],
        "unmapped_sheets": [{"sheet_name": a.sheet_name, "reason": a.reason} for a in cov.sheet_audit
                            if a.status == "unmapped"],
        "non_claim_summary_sheets": [{"sheet_name": a.sheet_name, "reason": a.reason} for a in cov.sheet_audit
                                     if a.status == "non_claim_summary"],
        "totals_by_currency": totals,
        "unmapped_source_columns": [{"sheet_name": s, "columns": cols}
                                    for s, cols in (cov.unmapped_source_columns or {}).items() if cols],
        "development_pairs": int(len(devs)),
        "development_refs": sorted({str(r) for r in devs["claim_ref_a"].dropna()})[:200] if len(devs) else [],
        "reconciliation": {
            "source_worksheets": rec.source_worksheets, "source_data_rows": rec.source_data_rows,
            "mapped_rows": rec.mapped_rows, "unmapped_rows": rec.unmapped_rows, "rejected_rows": rec.rejected_rows,
            "duplicate_rows": rec.duplicate_rows, "exported_rows": rec.exported_rows,
            "rows_requiring_review": rec.rows_requiring_review, "non_claim_summary_rows": rec.non_claim_summary_rows,
            "skipped_sheet_rows": rec.skipped_sheet_rows, "reconciles": rec.reconciles,
        },
        "definitions": {
            "source_data_rows": "Rows below each sheet's header row on processed sheets, including excluded rows.",
            "mapped_rows": "Rows on sheets where at least one canonical field was mapped.",
            "rejected_rows": "Structural rows excluded with a stated reason (blank, subtotal, repeated header, title).",
            "exported_rows": "Claim rows persisted and available for export (one per source claim row).",
            "rows_requiring_review": "Distinct claim rows with any exception, duplicate flag, or on an unmapped sheet.",
            "missing_mandatory_rows": "Distinct rows missing a required field (one row can have several exceptions).",
            "totals_by_currency": "Sums per currency of rows where the value is present; never summed across currencies.",
            "unmapped_source_columns": "Source columns not bound to any canonical field. Their values are kept on each row.",
            "development_pairs": "Same claim reference re-reported with a later period or changed amounts/status: "
                                 "normal claim development, never counted as a duplicate.",
        },
    }
    summary["recommendations"] = recommendations(summary, cov)
    return summary


def _money(amount: float, ccy: str) -> str:
    return f"{amount:,.2f} {ccy}" if ccy != "UNKNOWN" else f"{amount:,.2f} (currency not stated)"


def recommendations(s: dict, cov) -> list[dict]:
    """Next actions derived ONLY from this report's own counts. Each carries
    its evidence; where the evidence cannot settle a question the text says
    so instead of drawing a conclusion. Ordered most important first."""
    out: list[dict] = []

    def rec(key, severity, title, evidence, action, target=None):
        out.append({"id": key, "severity": severity, "title": title, "evidence": evidence, "action": action,
                    "target": target})

    missing_required = [f for f in s["field_completeness"]
                        if not f["never_mapped"] and f["present"] < f["denominator"]
                        and f["field_code"] in _REQUIRED]
    if s["missing_mandatory_rows"]:
        detail = "; ".join(f"{f['field_name']}: {f['denominator'] - f['present']} blank" for f in missing_required[:4])
        rec("missing_mandatory", "CRITICAL", f"{s['missing_mandatory_rows']} row(s) are missing a required field",
            detail or "See the Missing mandatory findings.", "Query the sender for the missing values.", "MANDATORY_FIELD")
    if s["arithmetic_mismatches"]:
        rec("arithmetic", "HIGH", f"{s['arithmetic_mismatches']} row(s) do not reconcile to total incurred",
            "Paid to date + reserve (+ fees/expenses where reported) differs from the reported total incurred.",
            "Review the arithmetic findings, largest first; each shows both sides of the sum.", "ARITHMETIC")
    if s["exact_duplicates"]:
        rec("exact_duplicates", "HIGH", f"{s['exact_duplicates']} exact resubmission(s) of a claim",
            "Same claim reference, same reporting period and identical amounts/status.",
            "Confirm each pair and ask the sender to withdraw the repeat.", "DUPLICATE")
    if s["probable_duplicates"]:
        rec("probable_duplicates", "MEDIUM", f"{s['probable_duplicates']} probable duplicate pair(s)",
            "Similar insured names with close loss dates under different claim references. This is a similarity "
            "signal, not proof.", "Review each pair side by side before acting.", "DUPLICATE")
    if s.get("period_unknown_repeats"):
        rec("period_unknown", "MEDIUM", f"{s['period_unknown_repeats']} repeat(s) could be duplicates or development",
            "The same claim appears on several sheets with no reporting period, so TrueBind cannot tell which.",
            "Map a reporting-period column or confirm each repeat manually.", "DUPLICATE")
    unmapped = s.get("unmapped_source_columns") or []
    n_unmapped = sum(len(u["columns"]) for u in unmapped)
    if n_unmapped:
        names = ", ".join(c for u in unmapped for c in u["columns"])
        rec("unmapped_columns", "INFO", f"{n_unmapped} source column(s) were not mapped",
            f"Not validated, but kept on every row and in the claims export: {names[:300]}.",
            "If any of these carry a canonical field, re-map the sheet and re-process.", "MAPPING")
    period_field = next((f for f in s["field_completeness"] if f["field_code"] == "TB_PERIOD"), None)
    if period_field and period_field["never_mapped"]:
        rec("no_period", "INFO", "No reporting-period column was mapped",
            "Duplicate detection falls back to sheet names for the period, so a repeat on another sheet can only "
            "be flagged for review, not classified.", "Map a Period End / As At column if the file has one.", "MAPPING")
    for t in s.get("totals_by_currency") or []:
        if t.get("fees_rows"):
            rec(f"fees_{t['currency']}", "INFO",
                f"Paid expenses contribute {_money(t['fees_paid_to_date'], t['currency'])} to incurred",
                f"From {t['fees_rows']} row(s) with a fees/expenses paid figure, included in the total-incurred check.",
                "No action needed unless this differs from the sender's statement.", None)
    if s.get("development_pairs"):
        rec("development", "INFO", f"{s['development_pairs']} claim(s) show development between reports",
            "Same claim reference with a later period or changed amounts. Treated as movement, never as duplication.",
            "No action needed; review if a movement looks unexpected.", "DUPLICATE")
    if s["arithmetic_not_evaluable"]:
        reasons = ", ".join(f"{k.replace('_', ' ')} ({v})" for k, v in list(s["not_evaluable_by_reason"].items())[:3])
        rec("not_evaluable", "MEDIUM", f"{s['arithmetic_not_evaluable']} row(s) could not be reconciled",
            f"TrueBind will not guess missing inputs: {reasons}.", "Map the missing amount columns if they exist.",
            "ARITHMETIC")
    if not s.get("score_reliable", True):
        rec("score_unreliable", "MEDIUM", "The health score is provisional",
            "At least one sheet was only partly understood, so the score may not reflect the whole file.",
            "Resolve the sheets marked for review, then re-process.", "MAPPING")
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "INFO": 3}
    return sorted(out, key=lambda r: order[r["severity"]])


def exception_counts(db: Session, report_id: str) -> dict:
    rows = (db.query(ValidationResult.check_type, ValidationResult.status, func.count())
            .filter(ValidationResult.report_id == report_id)
            .group_by(ValidationResult.check_type, ValidationResult.status).all())
    return {f"{ct}:{st}": n for ct, st, n in rows}
