"""Run check modules against a processed report and store the outcome.

- build_input() reads the report's claim rows, confirmed mappings and sheet
  read notes into the module contract (checks/base.py).
- run_module() runs one module, replaces its findings and run record, keeps
  people's dispositions for findings that are still raised (same
  fingerprint) and writes a MODULE_RUN audit event.
- run_all() runs every module after processing. A module that crashes is
  recorded as NOT_ASSESSED with a reason; it never fails the processing job.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..checks import LABELS, REGISTRY
from ..checks.base import CheckInput, ModuleResult, RowView, SheetView
from ..checks.sanctions import Entry, Index
from ..models.modules import Binder, Finding, ModuleRun, SanctionsEntry, SanctionsList
from ..models.reports import ClaimRow, Mapping, Report, Sheet
from . import audit_service, fx_service

log = logging.getLogger("truebind.modules")

_AMBIGUOUS = re.compile(r"""^(['"])(?P<col>.*)\1: every date in this column is ambiguous""")
_ROW_COLS = (
    "id",
    "sheet_id",
    "source_row_number",
    "claim_reference",
    "insured_name",
    "claim_status",
    "date_of_loss",
    "date_notified",
    "reporting_period",
    "paid_amount",
    "paid_this_month",
    "reserve_amount",
    "fees_paid_to_date",
    "incurred_amount",
    "currency",
)


def binder_config(b: Binder) -> dict[str, Any]:
    return {
        "id": b.id,
        "name": b.name,
        "umr": b.umr,
        "coverholder": b.coverholder,
        "inception_date": b.inception_date.isoformat(),
        "expiry_date": b.expiry_date.isoformat(),
        "currencies": list(b.currencies or []),
        "limit_currency": b.limit_currency,
        "claims_authority": str(b.claims_authority) if b.claims_authority is not None else None,
        "aggregate_limit": str(b.aggregate_limit) if b.aggregate_limit is not None else None,
    }


def _fx(db: Session):  # type: ignore[no-untyped-def]
    def convert(amount: Decimal, src: str, dst: str, on: date) -> tuple[Decimal | None, str | None]:
        c = fx_service.convert(db, amount, src, dst, on)
        return (c.amount, None) if c.status == "OK" else (None, c.reason)

    return convert


def build_input(db: Session, report: Report, module: str) -> CheckInput:
    sheets = {
        s.id: s for s in db.query(Sheet).filter(Sheet.report_id == report.id, Sheet.tenant_id == report.tenant_id)
    }
    mapped: dict[str, dict[str, str]] = {sid: {} for sid in sheets}
    for m in db.query(Mapping).filter(Mapping.report_id == report.id, Mapping.tenant_id == report.tenant_id):
        if m.source_column and m.mapping_state != "UNMAPPED" and sheets[m.sheet_id].status == "CONFIRMED":
            mapped[m.sheet_id][m.field_code] = m.source_column
    views: dict[str, SheetView] = {}
    for sid, s in sheets.items():
        amb = frozenset(mt.group("col") for n in (s.notes or []) if (mt := _AMBIGUOUS.match(str(n))))
        views[s.sheet_name] = SheetView(s.sheet_name, mapped[sid], amb)
    names = {sid: s.sheet_name for sid, s in sheets.items()}
    cols = [getattr(ClaimRow, c) for c in _ROW_COLS]
    rows = [
        RowView(r.id, names[r.sheet_id], r.source_row_number, *tuple(r)[3:])
        for r in db.execute(
            select(*cols)
            .where(ClaimRow.report_id == report.id, ClaimRow.tenant_id == report.tenant_id)
            .order_by(ClaimRow.sheet_id, ClaimRow.row_index)
        )
    ]
    config: dict[str, Any] = {}
    if module == "binder" and report.binder_id:
        b = db.query(Binder).filter(Binder.id == report.binder_id, Binder.tenant_id == report.tenant_id).first()
        if b is not None:
            config["binder"] = binder_config(b)
    context: dict[str, Any] = {"convert": _fx(db)}
    if module == "sanctions":
        lists = (
            db.query(SanctionsList)
            .filter(SanctionsList.tenant_id == report.tenant_id)
            .order_by(SanctionsList.uploaded_at)
            .all()
        )
        names = {x.id: x.name for x in lists}
        config["lists"] = [
            {
                "id": x.id,
                "name": x.name,
                "source": x.source,
                "sha256": x.sha256,
                "entries": x.entry_count,
                "uploaded_at": x.uploaded_at.isoformat(),
            }
            for x in lists
        ]
        entries = db.execute(
            select(SanctionsEntry.list_id, SanctionsEntry.reference, SanctionsEntry.name, SanctionsEntry.kind).where(
                SanctionsEntry.tenant_id == report.tenant_id
            )
        )
        context["sanctions_index"] = Index(
            [Entry(ref, name, names.get(lid, "?"), kind) for lid, ref, name, kind in entries]
        )
    return CheckInput(report.id, views, rows, config, context)


def _store(
    db: Session, report: Report, module: str, result: ModuleResult, actor: str, actor_user_id: str | None
) -> ModuleRun:
    previous = {
        f.fingerprint: f
        for f in db.query(Finding).filter(
            Finding.report_id == report.id, Finding.tenant_id == report.tenant_id, Finding.module == module
        )
    }
    db.query(Finding).filter(
        Finding.report_id == report.id, Finding.tenant_id == report.tenant_id, Finding.module == module
    ).delete(synchronize_session=False)
    db.query(ModuleRun).filter(
        ModuleRun.report_id == report.id, ModuleRun.tenant_id == report.tenant_id, ModuleRun.module == module
    ).delete(synchronize_session=False)
    for d in result.findings:
        fp = d.fingerprint(module)
        old = previous.get(fp)
        db.add(
            Finding(
                tenant_id=report.tenant_id,
                report_id=report.id,
                module=module,
                rule_code=d.rule_code,
                status=d.status,
                severity=d.severity,
                title=d.title[:200],
                explanation=d.explanation[:2000],
                sheet_name=d.sheet_name,
                row_number=d.row_number,
                field_code=d.field_code,
                source_column=d.source_column,
                claim_row_id=d.claim_row_id,
                claim_reference=d.claim_reference,
                amount=d.amount,
                currency=d.currency,
                evidence=d.evidence or None,
                fingerprint=fp,
                disposition=old.disposition if old else "OPEN",
                disposition_note=old.disposition_note if old else None,
                disposed_by=old.disposed_by if old else None,
                disposed_at=old.disposed_at if old else None,
            )
        )
    run = ModuleRun(
        tenant_id=report.tenant_id,
        report_id=report.id,
        module=module,
        state=result.state,
        reason=(result.reason or None) and str(result.reason)[:500],
        rules=[r.as_dict() for r in result.rules],
        config=result.config,
        finding_count=len(result.findings),
        ran_by=actor[:255],
    )
    db.add(run)
    db.flush()
    audit_service.log_action(
        db,
        report.tenant_id,
        report.id,
        "MODULE_RUN",
        "MODULE_RUN",
        run.id,
        after={"module": module, "state": result.state, "findings": len(result.findings)},
        actor=actor,
        actor_user_id=actor_user_id,
    )
    return run


def run_module(
    db: Session, report: Report, module: str, actor: str = audit_service.SYSTEM_ACTOR, actor_user_id: str | None = None
) -> ModuleRun:
    inp = build_input(db, report, module)
    try:
        with db.begin_nested():
            result = REGISTRY[module](inp)
    except Exception:
        log.exception("module %s failed on report %s", module, report.id)
        result = ModuleResult(
            "NOT_ASSESSED",
            f"{LABELS[module]} could not run because of an internal error; it has been logged. Nothing was assessed.",
            [],
            [],
            None,
        )
    return _store(db, report, module, result, actor, actor_user_id)


def run_all(db: Session, report: Report) -> list[ModuleRun]:
    return [run_module(db, report, m) for m in REGISTRY]
