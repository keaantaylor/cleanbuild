"""The health report's single view: one set of numbers for the app, the PDF
and the exports; every finding carries a plain-English sentence and its cell."""

from __future__ import annotations

import csv
import io

from conftest import xlsx_bytes

HEADER = ["Claim Reference", "Insured Name", "Date of Loss", "Claim Status", "Currency", "Paid to Date",
          "Reserve", "Total Incurred"]


def _rows():
    rows = [HEADER]
    for i in range(6):
        rows.append([f"CLM-{i:04d}", f"Insured {i}", "2024-01-15", "Open", "GBP", 1000, 500, 1500])
    rows.append(["CLM-0100", "Arith Ltd", "2024-01-15", "Open", "GBP", 100, 50, 999])  # row 8: H8 wrong
    rows.append(["CLM-0101", "Cur Ltd", "2024-01-15", "Open", "XXX", 10, 0, 10])  # row 9: E9 invalid
    rows.append(["CLM-0102", "Euro Ltd", "2024-01-15", "Open", "Euro", 10, 0, 10])  # row 10: E10 normalised
    rows.append([None, "No Ref Ltd", "2024-01-15", "Open", "GBP", 10, 0, 10])  # row 11: A11 missing
    return rows


def _csv(api, rid):
    r = api.get(f"/api/v1/reports/{rid}/export/exceptions.csv")
    assert r.status_code == 200
    return list(csv.DictReader(io.StringIO(r.text)))


def test_counts_agree_with_the_export_and_findings_have_cells(api):
    rid, _ = api.full_run("hv.xlsx", xlsx_bytes(_rows()))
    hv = api.get(f"/api/v1/reports/{rid}/summary").json()["summary"]["health_view"]
    rows = _csv(api, rid)
    assert hv["counts"]["errors"] == sum(1 for r in rows if r["status"] == "FAIL")
    assert hv["counts"]["warnings"] == sum(1 for r in rows if r["status"] == "REVIEW")
    assert hv["verdict"] == "fix" and hv["verdict_label"] == "Fix before submitting"

    by_rule = {r["rule"]: r for r in rows}
    assert by_rule["arithmetic_mismatch"]["cell"] == "H8"
    assert by_rule["invalid_currency"]["cell"] == "E9"
    assert by_rule["currency_normalised"]["cell"] == "E10"
    assert by_rule["missing_mandatory_field"]["cell"] == "A11"
    assert by_rule["arithmetic_mismatch"]["plain_english"].startswith("Total incurred does not reconcile:")
    assert by_rule["arithmetic_mismatch"]["result"] == "Error"
    assert by_rule["currency_normalised"]["result"] == "Warning"
    assert by_rule["currency_normalised"]["who_fixes"] == "us"
    assert by_rule["invalid_currency"]["who_fixes"] == "sender"
    assert "CR0104M" not in by_rule["missing_mandatory_field"]["plain_english"]

    # Top fixes: errors first, by severity; each carries an example with its cell.
    top = hv["top_fixes"]
    assert top[0]["outcome"] == "FAIL" and top[0]["severity"] == "CRITICAL"
    assert all(t["examples"][0]["where"] for t in top)
    assert len(top) <= 5
    # Money is per currency, never added together.
    arith = next(t for t in hv["rules"] if t["rule"] == "arithmetic_mismatch")
    assert arith["money_at_risk"] == [{"currency": "GBP", "amount": 999.0}]


def test_exceptions_api_carries_sentence_and_cell(api):
    rid, _ = api.full_run("hv.xlsx", xlsx_bytes(_rows()))
    items = api.get(f"/api/v1/reports/{rid}/exceptions", params={"limit": 500}).json()["items"]
    arith = next(i for i in items if i["rule"] == "arithmetic_mismatch")
    assert arith["cell"] == "H8" and arith["source_column"] == "Total Incurred" and arith["sentence"]


def test_clean_file_is_ready_to_submit(api):
    rows = [HEADER] + [[f"CLM-{i:04d}", f"Insured {i}", "2024-01-15", "Open", "GBP", 1000, 500, 1500]
                       for i in range(5)]
    rid, _ = api.full_run("clean.xlsx", xlsx_bytes(rows))
    hv = api.get(f"/api/v1/reports/{rid}/summary").json()["summary"]["health_view"]
    assert hv["verdict"] == "ready" and hv["counts"]["errors"] == 0
    # Policy period / limit columns are absent: those checks are listed as couldn't check, with a mapping fix.
    keys = {c["key"] for c in hv["couldnt_check"]}
    assert {"field:policy_period", "field:policy_limit"} <= keys
    assert all(c["fix"] in ("mapping", "data") for c in hv["couldnt_check"])


def test_duplicate_counts_agree_everywhere(api):
    rows = _rows() + [["DUP-1", "Same Insured", "2024-01-15", "Open", "GBP", 1, 1, 2]] * 3
    rid, _ = api.full_run("dups.xlsx", xlsx_bytes(rows))
    summary = api.get(f"/api/v1/reports/{rid}/summary").json()["summary"]
    hv = summary["health_view"]
    listed = api.get(f"/api/v1/reports/{rid}/duplicates", params={"limit": 500}).json()
    exported = [r for r in _csv(api, rid) if r["check_type"] == "DUPLICATE"]
    exact_listed = sum(1 for p in listed["items"] if p["match_type"] == "exact_duplicate")
    exact_exported = sum(1 for r in exported if r["rule"] == "exact_duplicate")
    assert hv["duplicates"]["exact_pairs"] == summary["exact_duplicates"] == exact_listed == exact_exported
    assert exact_listed >= 2
    probable = summary["probable_duplicates"] or 0
    assert sum(1 for p in listed["items"] if p["match_type"] == "probable_duplicate") == probable
