"""Operational surfaces: alerts lifecycle, recommendations, overview, work
queue, deliveries (download + e-mail), channels, processing history,
exception review -- and tenant isolation for each."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from app.worker import Worker
from conftest import BORDEREAUX_ROOT, SIMPLE_HEADER, run_jobs, simple_rows, xlsx_bytes


def _stress(api):
    sys.path.insert(0, str(BORDEREAUX_ROOT / "tests" / "regression_fixtures"))
    import build_replicas as br
    br.OUT = Path(tempfile.mkdtemp(prefix="tb_replicas_"))
    path = br.stress_450()
    return api.full_run(path.name, path.read_bytes())


def test_upload_records_provenance_and_inbound_alert(api):
    r = api.post("/api/v1/reports/upload", files={"file": ("a.xlsx", xlsx_bytes(simple_rows()))},
                 data={"sender": "Meridian MGA", "programme": "Property 2024"})
    assert r.status_code == 202
    body = r.json()
    assert (body["sender"], body["programme"], body["source_channel"]) == ("Meridian MGA", "Property 2024", "upload")
    alerts = api.get("/api/v1/alerts").json()["items"]
    assert alerts[0]["source"] == "INBOUND" and "Meridian MGA" in alerts[0]["message"]


def test_lifecycle_alerts_and_stage_progress(api):
    rid, _ = api.full_run("a.xlsx", xlsx_bytes(simple_rows(4)))
    sources = {a["source"] for a in api.get("/api/v1/alerts", params={"report_id": rid}).json()["items"]}
    assert {"INBOUND", "REVIEW_NEEDED", "REPORT_READY"} <= sources
    jobs = api.get(f"/api/v1/reports/{rid}/jobs").json()
    assert [j["kind"] for j in jobs] == ["INGEST", "PROCESS"] and all(j["status"] == "SUCCEEDED" for j in jobs)


def test_failed_processing_raises_alert(api):
    rid = api.ingest("empty.xlsx", xlsx_bytes([["just a title"]]))
    alerts = api.get("/api/v1/alerts", params={"report_id": rid}).json()["items"]
    assert any(a["source"] == "PROCESSING_FAILED" and a["severity"] == "HIGH" for a in alerts)


def test_reprocessing_keeps_lifecycle_alerts(api):
    rid, _ = api.full_run("a.xlsx", xlsx_bytes(simple_rows(3)))
    api.post(f"/api/v1/reports/{rid}/process")
    run_jobs()
    sources = [a["source"] for a in api.get("/api/v1/alerts", params={"report_id": rid}).json()["items"]]
    assert "INBOUND" in sources


def test_recommendations_are_evidence_backed(api):
    rid, _ = _stress(api)
    s = api.get(f"/api/v1/reports/{rid}/summary").json()["summary"]
    recs = {r["id"]: r for r in s["recommendations"]}
    assert "exact_duplicates" in recs and "6" in recs["exact_duplicates"]["title"]
    assert "unmapped_columns" in recs and "Adjuster Reference" in recs["unmapped_columns"]["evidence"]
    assert "development" in recs
    assert "fees_GBP" in recs and "Paid expenses contribute" in recs["fees_GBP"]["title"]
    fees = next(t for t in s["totals_by_currency"] if t["currency"] == "GBP")
    assert fees["fees_rows"] == 450 and fees["fees_paid_to_date"] > 0
    assert all(r["evidence"] for r in s["recommendations"])


def test_overview_counts_and_activity(api):
    _stress(api)
    o = api.get("/api/v1/overview").json()
    assert o["reports"]["total"] == 1 and o["reports"]["complete"] == 1
    assert o["findings"]["exact_duplicates"] == 6 and o["findings"]["development_pairs"] == 6
    assert o["findings"]["unmapped_columns"] == 6
    assert len(o["trend"]) == 14 and o["trend"][-1]["reports"] == 1
    assert o["activity"] and o["latest_reports"][0]["status"] == "COMPLETE"
    assert o["alerts"]["unread"] >= 2


def test_work_queue_prioritises_real_work(api):
    rid = api.ingest("a.xlsx", xlsx_bytes(simple_rows()))
    items = api.get("/api/v1/work-queue").json()["items"]
    assert items[0]["kind"] == "mapping" and items[0]["href"] == f"/upload?reportId={rid}"


def test_work_queue_flags_stalled_uploads_when_no_worker(api):
    api.upload("a.xlsx", xlsx_bytes(simple_rows()))  # queued; no worker has checked in
    items = api.get("/api/v1/work-queue").json()["items"]
    assert items[0]["kind"] == "stalled" and items[0]["priority"] == "CRITICAL"
    w = Worker(worker_id="alive", prewarm=False)
    w.check_in(force=True)
    assert all(i["kind"] != "stalled" for i in api.get("/api/v1/work-queue").json()["items"])
    w.check_out()


def test_downloads_are_recorded_as_deliveries(api):
    rid, _ = api.full_run("a.xlsx", xlsx_bytes(simple_rows()))
    assert api.get(f"/api/v1/reports/{rid}/export/claims.csv").status_code == 200
    d = api.get("/api/v1/deliveries").json()["items"]
    assert d[0]["channel"] == "download" and d[0]["status"] == "DELIVERED" and d[0]["kind"] == "claims_csv"


def test_email_delivery_not_configured_is_honest(api, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "SMTP_HOST", None)
    rid, _ = api.full_run("a.xlsx", xlsx_bytes(simple_rows()))
    r = api.post(f"/api/v1/reports/{rid}/deliveries", json={"kind": "exceptions_csv", "channel": "email",
                                                            "recipient": "ops@cedant.example"})
    assert r.status_code == 201 and r.json()["status"] == "NOT_CONFIGURED" and "not configured" in r.json()["error"]
    assert any(a["source"] == "EXPORT_FAILED" for a in api.get("/api/v1/alerts").json()["items"])


def test_email_delivery_sends_attachment_when_configured(api, monkeypatch):
    import smtplib
    from app import config
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            self.host = host

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            pass

        def login(self, u, p):
            pass

        def send_message(self, msg):
            sent.append(msg)

    monkeypatch.setattr(config, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    rows = [SIMPLE_HEADER, ["=cmd()", "X", "2024-01-15", "Open", "GBP", 1, 1, 2]]
    rid, _ = api.full_run("a.xlsx", xlsx_bytes(rows[:1] + simple_rows(2)[1:]))
    r = api.post(f"/api/v1/reports/{rid}/deliveries", json={"kind": "claims_csv", "channel": "email",
                                                            "recipient": "Ops@Cedant.example"})
    assert r.json()["status"] == "DELIVERED" and r.json()["destination"] == "ops@cedant.example"
    msg = sent[0]
    assert msg["To"] == "ops@cedant.example"
    att = [p for p in msg.iter_attachments()][0]
    assert att.get_filename().endswith("_claims.csv") and b"CLM-0000" in att.get_payload(decode=True)


def test_channels_never_claim_planned_connectors_work(api):
    c = api.get("/api/v1/channels").json()
    status = {x["id"]: x["status"] for x in c["inbound"]}
    assert status["upload"] == "active" and status["email"] == "planned" and status["sftp"] == "planned"


def test_exception_review_workflow_is_audited(api):
    rows = simple_rows(0) + [[None, "No Ref Ltd", "2024-01-15", "Open", "GBP", 1, 1, 2]]
    rid, _ = api.full_run("a.xlsx", xlsx_bytes(rows))
    exc = api.get(f"/api/v1/reports/{rid}/exceptions", params={"sort": "severity"}).json()["items"]
    assert exc[0]["severity"] == "CRITICAL" and exc[0]["review_status"] is None
    vr = exc[0]["validation_result_id"]
    r = api.patch(f"/api/v1/reports/{rid}/exceptions/{vr}", json={"review_status": "in_review", "assignee": "Sam",
                                                                  "note": "Asked the coverholder"})
    assert r.status_code == 200 and r.json()["reviewed_by"] == "owner@a.example"
    exc = api.get(f"/api/v1/reports/{rid}/exceptions").json()["items"]
    mine = next(e for e in exc if e["validation_result_id"] == vr)
    assert (mine["review_status"], mine["assignee"]) == ("in_review", "Sam")
    audit = api.get(f"/api/v1/reports/{rid}/audit", params={"action_type": "EXCEPTION_STATUS_CHANGED"}).json()
    assert audit["total"] == 1
    bad = api.patch(f"/api/v1/reports/{rid}/exceptions/{vr}", json={"review_status": "deleted"})
    assert bad.status_code == 422


def test_operational_endpoints_are_tenant_isolated(api, api_b):
    rid, _ = api.full_run("a.xlsx", xlsx_bytes(simple_rows()))
    api.get(f"/api/v1/reports/{rid}/export/claims.csv")
    vr = api.get(f"/api/v1/reports/{rid}/exceptions").json()
    assert api_b.get("/api/v1/deliveries").json()["items"] == []
    assert api_b.get("/api/v1/overview").json()["reports"]["total"] == 0
    assert api_b.get("/api/v1/work-queue").json()["items"] == [] or all(
        i["report_id"] != rid for i in api_b.get("/api/v1/work-queue").json()["items"])
    assert api_b.get(f"/api/v1/reports/{rid}/jobs").status_code == 404
    assert api_b.post(f"/api/v1/reports/{rid}/deliveries", json={"kind": "claims_csv", "channel": "email",
                                                                 "recipient": "x@y.example"}).status_code == 404
    if vr["items"]:
        assert api_b.patch(f"/api/v1/reports/{rid}/exceptions/{vr['items'][0]['validation_result_id']}",
                           json={"review_status": "resolved"}).status_code == 404


# ---------------------------------------------------------------- real stages + product fields

def test_jobs_report_every_real_stage_in_order(api, monkeypatch):
    from app.services import job_service
    seen: list[tuple[str, str]] = []
    original = job_service.set_stage

    def record(db, job, stage, **progress):
        seen.append((job.kind, stage))
        return original(db, job, stage, **progress)

    monkeypatch.setattr(job_service, "set_stage", record)
    rid, _ = api.full_run("stages.xlsx", xlsx_bytes(simple_rows(5)))
    ingest = [s for k, s in seen if k == "INGEST"]
    process = [s for k, s in seen if k == "PROCESS"]
    assert ingest == ["inspecting", "detecting_sheets", "proposing_mapping", "saving"]
    assert process == ["parsing", "mapping", "mapping", "validating", "checking_duplicates", "building_report", "saving"]


def test_stage_facts_are_recorded_for_the_ui(api, db):
    from app.models.jobs import Job
    rid, _ = api.full_run("facts.xlsx", xlsx_bytes(simple_rows(4)))
    job = api.get(f"/api/v1/reports/{rid}/jobs").json()
    process = [j for j in job if j["kind"] == "PROCESS"][0]
    progress = process["metrics"]["progress"]
    assert progress["rows_mapped"] == 4 and progress["duplicate_pairs"] == 0
    assert "row_findings" in progress and "arithmetic_mismatches" in progress


def test_summary_has_status_and_period_breakdowns_and_list_has_issues(api):
    rid, _ = api.full_run("breakdown.xlsx", xlsx_bytes(simple_rows(6)))
    summary = api.get(f"/api/v1/reports/{rid}/summary").json()["summary"]
    assert summary["claim_status_counts"] == {"open": 6}  # engine normalises statuses
    assert summary["reporting_periods"] == {"Not stated": 6} or summary["reporting_periods"] == {}
    listed = {r["id"]: r for r in api.get("/api/v1/reports").json()["items"]}
    assert listed[rid]["issues_found"] == (summary["missing_mandatory_rows"] + summary["arithmetic_mismatches"]
                                         + summary["exact_duplicates"] + summary["probable_duplicates"])


def test_overview_lists_in_flight_reports(api):
    rid = api.upload("waiting.xlsx", xlsx_bytes(simple_rows(2))).json()["id"]
    o = api.get("/api/v1/overview").json()
    assert [r["id"] for r in o["in_flight_reports"]] == [rid]
