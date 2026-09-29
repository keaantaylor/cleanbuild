"""P7 -- one-click audit pack.

Acceptance:
- a processed report downloads as one ZIP holding the README (with the
  coverage statement), report.json, the original file byte for byte,
  mapping decisions, claims, exceptions, check runs, findings with their
  decisions, the report's audit entries and manifest.json;
- every file in the manifest carries the SHA-256 and size of its bytes in
  the ZIP; the audit trail states whether the organisation's chain verified;
- building the pack is audited; it is refused (409) for an unprocessed
  report and when the stored original no longer matches its SHA-256.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import zipfile

from app.models.reports import Report
from app.services.storage import LocalObjectStore, get_store
from conftest import Api, simple_rows, xlsx_bytes
from sqlalchemy.orm import Session

EXPECTED = ["README.txt", "report.json", "original/pack.xlsx", "mapping.csv", "claims.csv", "exceptions.csv",
            "checks.json", "findings.csv", "audit_trail.json", "manifest.json"]  # fmt: skip


def test_the_pack_holds_everything_with_verifiable_hashes(api: Api) -> None:
    content = xlsx_bytes([*simple_rows(3), ["X-1", "", "2024-01-15", "Closed", "GBP", 10, 5, 15]])
    rid, _ = api.full_run("pack.xlsx", content)
    r = api.get(f"/api/v1/reports/{rid}/audit-pack.zip")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert f"truebind_{rid}_audit_pack.zip" in r.headers["content-disposition"]
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert z.namelist() == EXPECTED
    assert z.read("original/pack.xlsx") == content
    manifest = json.loads(z.read("manifest.json"))
    assert [f["path"] for f in manifest["files"]] == EXPECTED[:-1]
    for f in manifest["files"]:
        body = z.read(f["path"])
        assert f["sha256"] == hashlib.sha256(body).hexdigest() and f["bytes"] == len(body)
    report = json.loads(z.read("report.json"))
    assert report["source_sha256"] == hashlib.sha256(content).hexdigest()
    assert "Coverage:" in z.read("README.txt").decode() and report["coverage_statement"]
    trail = json.loads(z.read("audit_trail.json"))
    assert trail["organisation_chain_intact"] is True
    assert {"REPORT_UPLOADED", "MODULE_RUN"} <= {e["action_type"] for e in trail["entries"]}
    findings = list(csv.DictReader(io.StringIO(z.read("findings.csv").decode())))
    assert any(f["rule_code"] == "LKG_CLOSED_WITH_RESERVE" and f["amount"] == "5.00" for f in findings)
    mapping = list(csv.DictReader(io.StringIO(z.read("mapping.csv").decode())))
    assert {m["mapping_state"] for m in mapping} >= {"MAPPED_BY_ALIAS"}
    checks = json.loads(z.read("checks.json"))
    assert {c["module"] for c in checks} == {"binder", "leakage", "sanctions"}
    actions = [e["action_type"] for e in api.get(f"/api/v1/reports/{rid}/audit").json()["items"]]
    assert "AUDIT_PACK_EXPORTED" in actions


def test_the_pack_is_refused_when_unprocessed_or_tampered(api: Api, db: Session) -> None:
    rid = api.ingest("w.xlsx", xlsx_bytes(simple_rows(2)))
    assert api.get(f"/api/v1/reports/{rid}/audit-pack.zip").status_code == 409
    rid, _ = api.full_run("t.xlsx", xlsx_bytes(simple_rows(2)))
    report = db.get(Report, rid)
    assert report is not None and report.storage_key
    store = get_store()
    assert isinstance(store, LocalObjectStore)  # the test suite stores originals on local disk
    path = store._path(report.storage_key)
    os.chmod(path, 0o600)
    path.write_bytes(b"not the original")
    r = api.get(f"/api/v1/reports/{rid}/audit-pack.zip")
    assert r.status_code == 409 and "no longer matches" in r.json()["detail"]
