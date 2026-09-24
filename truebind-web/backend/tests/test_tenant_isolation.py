"""Tenant B must not be able to see, change or even detect tenant A's data
through any endpoint (IDOR). Cross-tenant ids behave exactly like ids that
do not exist (404)."""

from __future__ import annotations

from conftest import simple_rows, xlsx_bytes


def _a_report(api):
    rows = simple_rows(0) + [["DUP-1", "Same", "2024-01-15", "Open", "GBP", 1, 1, 2]] * 2
    rid, _ = api.full_run("a.xlsx", xlsx_bytes(rows))
    sheet = api.get(f"/api/v1/reports/{rid}/sheets").json()[0]
    dup = api.get(f"/api/v1/reports/{rid}/duplicates").json()["items"][0]
    ob = api.post(f"/api/v1/reports/{rid}/obligations", json={"owner": "ops", "note": "chase"}).json()
    alert = api.get("/api/v1/alerts", params={"report_id": rid}).json()["items"][0]
    tpl = api.post("/api/v1/templates", json={"name": "T", "field_mappings": {"Ref": "CR0104M"}}).json()
    return {"rid": rid, "sheet": sheet["id"], "dup": dup["validation_result_id"], "ob": ob["id"],
            "alert": alert["id"], "tpl": tpl["id"]}


def test_cross_tenant_reads_are_404(api, api_b):
    ids = _a_report(api)
    rid = ids["rid"]
    for url in [f"/api/v1/reports/{rid}", f"/api/v1/reports/{rid}/summary", f"/api/v1/reports/{rid}/sheets",
                f"/api/v1/reports/{rid}/sheets/{ids['sheet']}/mapping", f"/api/v1/reports/{rid}/exceptions",
                f"/api/v1/reports/{rid}/duplicates", f"/api/v1/reports/{rid}/excluded-rows",
                f"/api/v1/reports/{rid}/claims", f"/api/v1/reports/{rid}/audit",
                f"/api/v1/reports/{rid}/export/claims.csv", f"/api/v1/reports/{rid}/export/exceptions.csv",
                f"/api/v1/reports/{rid}/export/audit.csv", f"/api/v1/reports/{rid}/exceptions/summary",
                f"/api/v1/templates/{ids['tpl']}"]:
        r = api_b.get(url)
        assert r.status_code == 404, (url, r.status_code)
        assert "a.xlsx" not in r.text and "CLM" not in r.text


def test_cross_tenant_writes_are_404_and_change_nothing(api, api_b):
    ids = _a_report(api)
    rid = ids["rid"]
    attempts = [
        ("post", f"/api/v1/reports/{rid}/process", None),
        ("post", f"/api/v1/reports/{rid}/cancel", None),
        ("post", f"/api/v1/reports/{rid}/retry", None),
        ("delete", f"/api/v1/reports/{rid}", None),
        ("post", f"/api/v1/reports/{rid}/sheets/{ids['sheet']}/mapping", {"mappings": {"CR0035M": None}}),
        ("patch", f"/api/v1/reports/{rid}/duplicates/{ids['dup']}/review", {"review_status": "not_duplicate"}),
        ("post", f"/api/v1/reports/{rid}/obligations", {"note": "x"}),
        ("patch", f"/api/v1/obligations/{ids['ob']}", {"status": "RESOLVED"}),
        ("post", f"/api/v1/alerts/{ids['alert']}/acknowledge", None),
        ("post", f"/api/v1/reports/{rid}/exceptions/summary", None),
    ]
    for method, url, body in attempts:
        r = getattr(api_b, method)(url, **({"json": body} if body is not None else {}))
        assert r.status_code == 404, (method, url, r.status_code, r.text)
    assert api.get(f"/api/v1/reports/{rid}").json()["status"] == "COMPLETE"
    assert api.get("/api/v1/obligations").json()["items"][0]["status"] != "RESOLVED"


def test_lists_only_show_own_tenant(api, api_b):
    _a_report(api)
    for url in ["/api/v1/reports", "/api/v1/alerts", "/api/v1/obligations"]:
        assert api_b.get(url).json()["items"] == [], url
    assert {e["action_type"] for e in api_b.get("/api/v1/audit").json()["items"]} == {"ACCOUNT_CREATED"}
    assert api_b.get("/api/v1/templates").json() == []


def test_body_cannot_smuggle_tenant_or_ownership(api, api_b):
    ids = _a_report(api)
    r = api_b.post(f"/api/v1/reports/{ids['rid']}/obligations", json={"note": "x", "tenant_id": "anything"})
    assert r.status_code in (404, 422)
    r = api.post(f"/api/v1/reports/{ids['rid']}/obligations", json={"note": "x", "created_by": "ceo@evil"})
    assert r.status_code == 422, "created_by is derived from the session"
    r = api.post(f"/api/v1/reports/{ids['rid']}/obligations", json={"claim_row_id": "not-a-row-of-this-report"})
    assert r.status_code == 422


def test_audit_chain_verify_is_per_tenant(api, api_b):
    _a_report(api)
    a = api.get("/api/v1/audit/verify").json()
    b = api_b.get("/api/v1/audit/verify").json()
    assert a["intact"] and b["intact"] and a["entries"] > b["entries"] >= 1
