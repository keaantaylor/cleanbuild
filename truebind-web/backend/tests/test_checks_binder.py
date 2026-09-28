"""P3 -- binder compliance and the shared check-module framework.

(The precision/recall proof on a planted file is the golden suite in
fixtures/golden/binder; these tests pin the API and the edge cases.)

Acceptance:
- binders are validated (ISO 4217 codes, expiry not before inception,
  non-negative exact amounts) and cannot be deleted while reports use them;
- a person can confirm or dismiss a finding (dismissing needs a reason);
  the disposition survives a re-run while the finding is still raised;
- checks run only on processed reports, only for writers, and a check that
  crashes is recorded NOT_ASSESSED with a reason without failing processing;
- rules the binder does not configure are NOT_ASSESSED with the reason;
- currencies are read strictly: '$' is never guessed.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from app import checks
from app.checks import binder
from app.checks.base import CheckInput, FindingDraft, RowView, SheetView, iso_currency
from app.main import app
from app.routes.checks import coverage_statement
from conftest import PASSWORD, Api, simple_rows, xlsx_bytes
from fastapi.testclient import TestClient

BINDER = {"name": "B", "inception_date": "2025-01-01", "expiry_date": "2025-12-31", "limit_currency": "GBP"}


def _processed_with_binder(api: Api, **binder: Any) -> tuple[str, dict[str, Any]]:
    rid, _ = api.full_run("b.xlsx", xlsx_bytes(simple_rows(3)))
    b = api.post("/api/v1/binders", json={**BINDER, **binder})
    assert b.status_code == 201, b.text
    runs = api.put(f"/api/v1/reports/{rid}/binder", json={"binder_id": b.json()["id"]})
    assert runs.status_code == 200, runs.text
    return rid, b.json()


@pytest.mark.parametrize(
    ("body", "fragment"),
    [
        ({"currencies": ["GBP", "XYZ"]}, "XYZ"),
        ({"limit_currency": "$"}, "ISO 4217"),
        ({"expiry_date": "2024-12-31"}, "expiry_date"),
        ({"claims_authority": "-1"}, "greater than or equal"),
    ],
)
def test_binders_are_validated(api: Api, body: dict[str, Any], fragment: str) -> None:
    r = api.post("/api/v1/binders", json={**BINDER, **body})
    assert r.status_code == 422 and fragment in r.text


def test_binder_amounts_round_trip_as_exact_strings(api: Api) -> None:
    b = api.post("/api/v1/binders", json={**BINDER, "claims_authority": "50000.10", "currencies": ["gbp", "EUR"]})
    assert b.json()["claims_authority"] == "50000.10" and b.json()["currencies"] == ["EUR", "GBP"]
    assert [x["id"] for x in api.get("/api/v1/binders").json()] == [b.json()["id"]]


def test_a_binder_in_use_cannot_be_deleted(api: Api) -> None:
    rid, b = _processed_with_binder(api)
    assert api.delete(f"/api/v1/binders/{b['id']}").status_code == 409
    assert api.put(f"/api/v1/reports/{rid}/binder", json={"binder_id": None}).status_code == 200
    assert api.delete(f"/api/v1/binders/{b['id']}").status_code == 204
    assert api.put(f"/api/v1/reports/{rid}/binder", json={"binder_id": b["id"]}).status_code == 404


def test_dispositions_need_a_reason_and_survive_a_rerun(api: Api) -> None:
    rid, _ = _processed_with_binder(api)
    items = api.get(f"/api/v1/reports/{rid}/checks/findings", params={"module": "binder"}).json()["items"]
    assert len(items) == 3 and {f["rule_code"] for f in items} == {"BND_LOSS_OUTSIDE_PERIOD"}
    first = items[0]
    url = f"/api/v1/reports/{rid}/checks/findings/{first['id']}"
    assert api.patch(url, json={"disposition": "DISMISSED"}).status_code == 422
    r = api.patch(url, json={"disposition": "DISMISSED", "note": "  agreed with the insurer  "})
    assert r.json()["disposition"] == "DISMISSED" and r.json()["disposition_note"] == "agreed with the insurer"
    assert r.json()["disposed_by"]
    api.post(f"/api/v1/reports/{rid}/checks/binder/run")
    after = api.get(f"/api/v1/reports/{rid}/checks/findings", params={"disposition": "DISMISSED"}).json()["items"]
    assert [(f["row_number"], f["disposition_note"]) for f in after] == [
        (first["row_number"], "agreed with the insurer")
    ]
    run = next(x for x in api.get(f"/api/v1/reports/{rid}/checks").json() if x["module"] == "binder")
    assert run["finding_count"] == 3 and run["open_count"] == 2
    reopened = api.patch(url.replace(first["id"], after[0]["id"]), json={"disposition": "OPEN"}).json()
    assert reopened["disposed_by"] is None and reopened["disposed_at"] is None


def test_checks_need_a_processed_report_and_a_writer(api: Api) -> None:
    rid = api.ingest("w.xlsx", xlsx_bytes(simple_rows(2)))
    assert api.post(f"/api/v1/reports/{rid}/checks/binder/run").status_code == 409
    assert api.post(f"/api/v1/reports/{rid}/checks/nope/run").status_code == 404
    assert api.get(f"/api/v1/reports/{rid}/checks/findings", params={"module": "nope"}).status_code == 404
    runs = api.get(f"/api/v1/reports/{rid}/checks").json()
    assert {r["state"] for r in runs} == {"NOT_RUN"} and "has not run" in runs[0]["coverage_statement"]
    inv = api.post("/api/v1/org/invitations", json={"email": "v@a.example", "role": "VIEWER"}).json()
    viewer = TestClient(app)
    accepted = viewer.post(
        "/api/v1/auth/invitations/accept",
        json={"token": inv["accept_token"], "display_name": "V", "password": PASSWORD},
    )
    csrf = {"X-CSRF-Token": accepted.json()["csrf_token"]}
    assert viewer.get(f"/api/v1/reports/{rid}/checks").status_code == 200
    assert viewer.post(f"/api/v1/reports/{rid}/checks/binder/run", headers=csrf).status_code == 403
    assert viewer.post("/api/v1/binders", json=BINDER, headers=csrf).status_code == 403


def test_a_crashing_check_is_not_assessed_and_processing_completes(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(inp: CheckInput) -> Any:
        raise RuntimeError("bug")

    monkeypatch.setitem(checks.REGISTRY, "binder", boom)
    rid, report = api.full_run("c.xlsx", xlsx_bytes(simple_rows(2)))
    assert report["status"] == "COMPLETE"
    run = next(x for x in api.get(f"/api/v1/reports/{rid}/checks").json() if x["module"] == "binder")
    assert run["state"] == "NOT_ASSESSED" and "internal error" in run["reason"]


def test_unconfigured_rules_are_not_assessed_with_reasons(api: Api) -> None:
    rid, _ = _processed_with_binder(api, inception_date="2024-01-01")
    run = next(x for x in api.get(f"/api/v1/reports/{rid}/checks").json() if x["module"] == "binder")
    assert run["state"] == "PARTIAL"
    reasons = {r["code"]: r["reasons"] for r in run["rules"]}
    assert reasons["BND_CURRENCY_NOT_PERMITTED"] == ["the binder lists no permitted currencies"]
    assert reasons["BND_OVER_AUTHORITY"] == ["the binder sets no claims settlement authority"]
    assert reasons["BND_AGGREGATE_EXCEEDED"] == ["the binder sets no aggregate limit"]
    assert "3 assessed" in run["coverage_statement"] and "not assessed" in run["coverage_statement"]


def test_currencies_are_read_strictly() -> None:
    assert iso_currency(" gbp ") == "GBP" and iso_currency("£") == "GBP" and iso_currency("Euro") == "EUR"
    assert iso_currency("$") is None and iso_currency("XYZ") is None and iso_currency(None) is None


def _inp(rows: list[RowView], **cfg: Any) -> CheckInput:
    b = {**BINDER, "inception_date": "2024-01-01", "currencies": ["GBP"], "claims_authority": None,
         "aggregate_limit": None, **cfg}  # fmt: skip
    sheet = SheetView("S", {"CR0119CM": "Loss", "CR0110CM": "Ccy", "CR0155CM": "Inc", "TB_PAID_TD": "Paid"})
    return CheckInput("r", {"S": sheet}, rows, {"binder": b})


def test_aggregate_with_unconvertible_rows_under_the_limit_is_not_assessed() -> None:
    rows = [RowView("1", "S", 2, "A", paid_amount=Decimal(10), currency="GBP"),
            RowView("2", "S", 3, "B", paid_amount=Decimal(10), currency="USD")]  # fmt: skip
    result = binder.run(_inp(rows, aggregate_limit="100.00"))
    agg = next(r for r in result.rules if r.code == "BND_AGGREGATE_EXCEEDED")
    assert agg.assessed == 0 and agg.not_assessed == 2
    assert [f.rule_code for f in result.findings] == ["BND_CURRENCY_NOT_PERMITTED"]  # USD itself, not the total
    assert any("incomplete" in x for x in agg.reasons)


def test_blank_values_are_counted_not_passed() -> None:
    rows = [RowView("1", "S", 2, "A", currency="XX"), RowView("2", "S", 3, "B", currency="GBP",
                                                               incurred_amount=Decimal(5))]  # fmt: skip
    result = binder.run(_inp(rows, claims_authority="1.00"))
    period, ccy, auth, _ = result.rules
    assert (period.assessed, period.not_assessed) == (0, 2)
    assert period.reasons == ["date of loss is blank or unreadable"]
    assert (ccy.assessed, ccy.not_assessed) == (1, 1)
    assert (auth.assessed, auth.not_assessed) == (1, 1)
    assert [f.rule_code for f in result.findings] == ["BND_OVER_AUTHORITY"]
    assert result.findings[0].amount == Decimal("4.00")


def test_fingerprints_are_stable_and_specific() -> None:
    a = FindingDraft("R", "FAIL", "HIGH", "t", "e", "S", 2, amount=Decimal("1.00"), currency="GBP")
    b = FindingDraft("R", "FAIL", "HIGH", "other title", "other text", "S", 2, amount=Decimal("1.00"), currency="GBP")
    assert a.fingerprint("binder") == b.fingerprint("binder") != a.fingerprint("leakage")


def test_coverage_statement_wording() -> None:
    assert coverage_statement("X", "NOT_ASSESSED", [], None) == "X was not assessed: no reason recorded."
    rules = [{"label": "L", "assessed": 2, "not_assessed": 1, "reasons": ["r"]}]
    assert coverage_statement("X", "PARTIAL", rules, "r") == "X — L: 2 assessed, 1 not assessed (r)."
