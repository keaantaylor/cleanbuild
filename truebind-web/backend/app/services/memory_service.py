"""Counterparty memory: what TrueBind knows about how one sender behaves.

Everything here is read from records already kept (reports, sheets, confirmed
mappings, findings and their statuses, corrections, information requests);
nothing is learned silently. Memory is used in three deterministic ways:

- the mapping a person confirmed for the same sender and the same sheet
  layout is proposed again (shown as remembered, still confirmed by a person)
- a finding a person accepted as reported last time (same rule, claim, column
  and value) is marked as a known exception, with who accepted it and why;
  it is NOT closed automatically
- a correction a person approved repeatedly is offered as a reusable rule:
  "TrueBind has observed this correction N times. Create an approved reusable
  rule?" Only a person can create one.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.corrections import Correction
from ..models.memory import ApprovedRule, InfoRequest
from ..models.reports import ClaimRow, Mapping, Report, Sheet, ValidationResult
from . import audit_service, issues

SUGGEST_AFTER = 3  # approved by a person this many times before a reusable rule is offered


def sender_key(sender: str | None) -> str:
    return (sender or "").strip().lower()


def _reports(db: Session, tenant_id: str, sender: str, before=None, exclude: str | None = None):
    q = db.query(Report).filter(Report.tenant_id == tenant_id, func.lower(Report.sender) == sender_key(sender))
    if before is not None:
        q = q.filter(Report.created_at <= before)
    if exclude:
        q = q.filter(Report.id != exclude)
    return q.order_by(Report.created_at.desc())


def remembered_mapping(db: Session, report: Report, headers: list[str]) -> tuple[dict[str, str | None], dict] | None:
    """The mapping a person confirmed for the latest earlier file from the same
    sender whose sheet had exactly these headers. None if there is none."""
    if not sender_key(report.sender):
        return None
    wanted = [str(h)[:255] for h in headers]
    for prev in _reports(db, report.tenant_id, report.sender, report.created_at, report.id).limit(24):
        for sh in db.query(Sheet).filter(Sheet.report_id == prev.id, Sheet.status == "CONFIRMED"):
            if list(sh.headers or []) != wanted:
                continue
            rows = db.query(Mapping).filter(Mapping.sheet_id == sh.id, Mapping.confirmed_at.isnot(None)).all()
            if not rows:
                continue
            by = rows[0].confirmed_by
            return ({m.field_code: m.source_column for m in rows},
                    {"report_id": prev.id, "file_name": prev.file_name, "sheet": sh.sheet_name, "confirmed_by": by,
                     "confirmed_at": rows[0].confirmed_at.isoformat() if rows[0].confirmed_at else None})
    return None


def recurring_causes(db: Session, report: Report, last: int = 6) -> dict[str, int]:
    """Root-cause key -> in how many of the sender's previous `last` files it appeared."""
    if not sender_key(report.sender):
        return {}
    prev_ids = [r.id for r in _reports(db, report.tenant_id, report.sender, report.created_at, report.id)
                .filter(Report.status == "COMPLETE").limit(last)]
    if not prev_ids:
        return {}
    seen: dict[str, set] = defaultdict(set)
    for rid, rule, extra in db.query(ValidationResult.report_id, ValidationResult.rule, ValidationResult.extra).filter(
            ValidationResult.report_id.in_(prev_ids)):
        seen[(extra or {}).get("root_cause") or rule].add(rid)
    return {k: len(v) for k, v in seen.items()}


def mark_known_exceptions(db: Session, report: Report) -> int:
    """Annotate findings a person accepted as reported on an earlier file from
    the same sender (same rule, claim, column and value). Status unchanged."""
    if not sender_key(report.sender):
        return 0
    prev_ids = [r.id for r in _reports(db, report.tenant_id, report.sender, report.created_at, report.id).limit(24)]
    if not prev_ids:
        return 0
    accepted: dict[tuple, dict] = {}
    for vr, ref in (db.query(ValidationResult, ClaimRow.claim_reference)
                    .join(ClaimRow, ClaimRow.id == ValidationResult.claim_row_id)
                    .filter(ValidationResult.report_id.in_(prev_ids))):
        x = vr.extra or {}
        if x.get("issue_status") != "OVERRIDDEN":
            continue
        last = next((h for h in reversed(x.get("history") or []) if h.get("status") == "OVERRIDDEN"), {})
        accepted.setdefault((vr.rule, (ref or "").strip().upper(), x.get("column"), str(x.get("actual"))), {
            "report_id": vr.report_id, "by": last.get("actor"), "at": last.get("at"), "reason": last.get("note")})
    if not accepted:
        return 0
    n = 0
    for vr, ref in (db.query(ValidationResult, ClaimRow.claim_reference)
                    .join(ClaimRow, ClaimRow.id == ValidationResult.claim_row_id)
                    .filter(ValidationResult.report_id == report.id)):
        x = vr.extra or {}
        hit = accepted.get((vr.rule, (ref or "").strip().upper(), x.get("column"), str(x.get("actual"))))
        if hit:
            vr.extra = {**x, "known_exception": hit}
            n += 1
    return n


def rule_suggestions(db: Session, tenant_id: str) -> list[dict]:
    """Corrections a person approved at least SUGGEST_AFTER times, not yet a rule."""
    counts: Counter = Counter()
    senders: dict[tuple, set] = defaultdict(set)
    for c, sender in (db.query(Correction, Report.sender).join(Report, Report.id == Correction.report_id)
                      .filter(Correction.tenant_id == tenant_id, Correction.status == "APPROVED")):
        if (c.approval or {}).get("by") != "person":
            continue
        key = (c.field_code, c.rule, c.before_value, c.after_value)
        counts[key] += 1
        senders[key].add(sender_key(sender))
    existing = {(r.field_code, r.rule, r.match_value, r.replace_value)
                for r in db.query(ApprovedRule).filter(ApprovedRule.tenant_id == tenant_id,
                                                       ApprovedRule.status == "ACTIVE")}
    out = []
    for (field, rule, before, after), n in counts.most_common():
        if n < SUGGEST_AFTER or (field, rule, before, after) in existing:
            continue
        s = senders[(field, rule, before, after)]
        out.append({"field_code": field, "rule": rule, "match_value": before, "replace_value": after, "observed": n,
                    "sender": next(iter(s)) if len(s) == 1 and next(iter(s)) else None,
                    "prompt": f"TrueBind has observed this correction {n} times "
                              f"({before!r} -> {after!r}). Create an approved reusable rule?"})
    return out


def approve_rule(db: Session, tenant_id: str, suggestion: dict, actor: str, actor_user_id: str | None) -> ApprovedRule:
    """A person turns a suggestion into a rule. The suggestion is looked up
    again server-side: a rule cannot be created for something not observed."""
    match = next((s for s in rule_suggestions(db, tenant_id)
                  if all(s[k] == suggestion.get(k) for k in ("field_code", "rule", "match_value", "replace_value"))),
                 None)
    if match is None:
        raise ValueError("That correction has not been observed often enough to become a rule.")
    r = ApprovedRule(tenant_id=tenant_id, sender=match["sender"], field_code=match["field_code"], rule=match["rule"],
                     match_value=match["match_value"], replace_value=match["replace_value"],
                     observed=match["observed"], created_by=actor)
    db.add(r)
    db.flush()
    audit_service.log_action(db, tenant_id, None, "RULE_APPROVED", "APPROVED_RULE", r.id,
                             after={k: match[k] for k in ("field_code", "rule", "match_value", "replace_value",
                                                          "observed", "sender")},
                             actor=actor, actor_user_id=actor_user_id)
    return r


def active_rules(db: Session, tenant_id: str, sender: str | None) -> list[ApprovedRule]:
    key = sender_key(sender)
    return [r for r in db.query(ApprovedRule).filter(ApprovedRule.tenant_id == tenant_id, ApprovedRule.status == "ACTIVE")
            if r.sender is None or r.sender == key]


def profile(db: Session, tenant_id: str, sender: str) -> dict:
    reports = _reports(db, tenant_id, sender).all()
    ids = [r.id for r in reports]
    structures: Counter = Counter()
    periods: set = set()
    for sh in db.query(Sheet).filter(Sheet.report_id.in_(ids or [""]), Sheet.status == "CONFIRMED"):
        structures[(sh.sheet_name, tuple(sh.headers or []))] += 1
    for (p,) in db.query(ClaimRow.reporting_period).filter(ClaimRow.report_id.in_(ids or [""])).distinct().limit(60):
        if p:
            periods.add(p)
    by_rule: Counter = Counter()
    statuses: dict[str, Counter] = defaultdict(Counter)
    known = []
    for vr in db.query(ValidationResult).filter(ValidationResult.report_id.in_(ids or [""])):
        x = vr.extra or {}
        by_rule[vr.rule] += 1
        st = x.get("issue_status") or issues.initial_status(vr.status, vr.rule or "")
        statuses[vr.rule][st] += 1
        if st == "OVERRIDDEN" and len(known) < 50:
            note = next((h.get("note") for h in reversed(x.get("history") or []) if h.get("status") == "OVERRIDDEN"), None)
            known.append({"rule": vr.rule, "cell": x.get("cell"), "actual": x.get("actual"), "reason": note})
    corrections = Counter((c.rule, c.before_value, c.after_value) for c in db.query(Correction).filter(
        Correction.report_id.in_(ids or [""]), Correction.status == "APPROVED"))
    contacts = sorted({r.to_address for r in db.query(InfoRequest).filter(InfoRequest.report_id.in_(ids or [""]))
                       if r.to_address} | {r.sender for r in reports if r.sender and "@" in r.sender})
    return {
        "sender": sender,
        "submissions": [{"report_id": r.id, "file_name": r.file_name, "received_at": r.created_at.isoformat(),
                         "status": r.status, "sha256": r.source_sha256} for r in reports],
        "structures": [{"sheet": name, "headers": list(h), "seen": n} for (name, h), n in structures.most_common(10)],
        "reporting_periods": sorted(periods),
        "recurring_errors": [{"rule": k, "findings": n, "by_status": dict(statuses[k])} for k, n in by_rule.most_common(15)],
        "known_exceptions": known,
        "approved_corrections": [{"rule": k[0], "before": k[1], "after": k[2], "times": n}
                                 for k, n in corrections.most_common(20)],
        "approved_rules": [{"id": r.id, "field_code": r.field_code, "rule": r.rule, "match_value": r.match_value,
                            "replace_value": r.replace_value, "applied": r.applied}
                           for r in active_rules(db, tenant_id, sender)],
        "contacts": contacts,
        "open_requests": db.query(InfoRequest).filter(InfoRequest.report_id.in_(ids or [""]),
                                                      InfoRequest.status != "RESOLVED").count(),
    }
