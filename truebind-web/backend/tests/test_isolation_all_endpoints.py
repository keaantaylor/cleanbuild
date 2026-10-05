"""P1.3 -- tenant isolation over EVERY endpoint, derived from the OpenAPI document.

Acceptance:
- every operation with a path id, called by another organisation's owner
  (who holds every permission) with tenant A's ids, returns 404 and leaks
  nothing; tenant A's data is unchanged afterwards;
- every list/overview endpoint of tenant B shows none of tenant A's data;
- the suite is self-enforcing: an endpoint with a path id or a request body
  it does not know how to exercise fails the test until a case is added;
- on PostgreSQL, every table carrying tenant_id has RLS enabled + forced and
  a policy (the database backstop).
"""

from __future__ import annotations

from typing import Any

import pytest
from app.main import app
from conftest import IS_PG, Api, simple_rows, xlsx_bytes
from sqlalchemy import text
from sqlalchemy.orm import Session

MARKER_FILE = "iso-a-marker.xlsx"
MARKER_REF = "ISOA-REF"
PUBLIC = {
    "/api/v1/auth/signup",
    "/api/v1/auth/login",
    "/api/v1/auth/invitations/accept",
    "/api/v1/auth/sso/start",
    "/api/v1/auth/sso/callback",
}
# Global reference data (health probes, ECB FX rates): no tenant rows to leak.
NO_TENANT_DATA = {"/health", "/health/ready", "/api/v1/fx/rates", "/api/v1/fx/convert"}
# The sender portal lists only the calling SENDER's own submissions; other roles are refused (403).
SENDER_ONLY = {"/api/v1/sender/submissions"}
# Website enquiries are not tenant data; only operators in LEADS_ADMIN_EMAILS may read them.
OPERATOR_ONLY = {"/api/v1/leads", "/api/v1/leads/export.csv", "/api/v1/leads/{lead_id}/file"}

# Bodies that pass validation, so the handler (and its tenant check) runs.
BODIES: dict[tuple[str, str], dict[str, Any]] = {
    ("patch", "/api/v1/obligations/{obligation_id}"): {"status": "RESOLVED"},
    ("patch", "/api/v1/org/members/{membership_id}"): {"role": "VIEWER"},
    ("post", "/api/v1/reports/{report_id}/deliveries"): {
        "kind": "claims_csv",
        "channel": "email",
        "recipient": "x@b.example",
    },
    ("patch", "/api/v1/reports/{report_id}/duplicates/{validation_result_id}/review"): {
        "review_status": "not_duplicate"
    },
    ("patch", "/api/v1/reports/{report_id}/exceptions/{validation_result_id}"): {"review_status": "resolved"},
    ("post", "/api/v1/reports/{report_id}/obligations"): {"note": "x"},
    ("post", "/api/v1/reports/{report_id}/sheets/{sheet_id}/mapping"): {"mappings": {"CR0035M": None}},
    ("put", "/api/v1/reports/{report_id}/binder"): {"binder_id": None},
    ("patch", "/api/v1/reports/{report_id}/checks/findings/{finding_id}"): {"disposition": "CONFIRMED"},
    ("post", "/api/v1/reports/{report_id}/issues/{issue_id}/status"): {"status": "RESOLVED"},
    ("post", "/api/v1/reports/{report_id}/issues/bulk"): {"root_cause": "arithmetic_mismatch:Total Incurred",
                                                          "action": "resolve"},
    ("post", "/api/v1/reports/{report_id}/corrections"): {"sheet_id": "x", "cell": "A1", "reason": "x"},
    ("post", "/api/v1/reports/{report_id}/corrections/{correction_id}/decision"): {"approve": True},
    ("post", "/api/v1/reports/{report_id}/versions/{version_id}/approve"): {"note": "x"},
}


def _tenant_a(api: Api) -> dict[str, str]:
    rows = [
        *simple_rows(1),
        [f"{MARKER_REF}-1", "", "2024-01-15", "Open", "GBP", 10, 5, 15],  # missing insured -> exception
        [f"{MARKER_REF}-D", "Same Insured", "2024-01-15", "Open", "GBP", 1, 1, 2],
        [f"{MARKER_REF}-D", "Same Insured", "2024-01-15", "Open", "GBP", 1, 1, 2],
    ]
    rid, _ = api.full_run(MARKER_FILE, xlsx_bytes(rows))
    sheet = api.get(f"/api/v1/reports/{rid}/sheets").json()[0]
    dup = api.get(f"/api/v1/reports/{rid}/duplicates").json()["items"][0]
    exc = api.get(f"/api/v1/reports/{rid}/exceptions").json()["items"][0]
    ob = api.post(f"/api/v1/reports/{rid}/obligations", json={"owner": "ops", "note": "chase"}).json()
    alert = api.get("/api/v1/alerts", params={"report_id": rid}).json()["items"][0]
    tpl = api.post("/api/v1/templates", json={"name": "T", "field_mappings": {"Ref": "CR0104M"}}).json()
    inv = api.post("/api/v1/org/invitations", json={"email": "invitee@a.example", "role": "VIEWER"}).json()
    member = api.get("/api/v1/org/members").json()[0]
    from app import config

    saved, config.WEBHOOK_ALLOW_PRIVATE_TARGETS = config.WEBHOOK_ALLOW_PRIVATE_TARGETS, True  # no DNS in this suite
    try:
        hook = api.post(
            "/api/v1/org/webhooks", json={"url": "https://hooks.a.example/x", "events": ["report.completed"]}
        ).json()
    finally:
        config.WEBHOOK_ALLOW_PRIVATE_TARGETS = saved
    delivery = api.post(f"/api/v1/org/webhooks/{hook['id']}/test").json()
    binder_in = {"name": "B", "inception_date": "2025-01-01", "expiry_date": "2025-12-31", "limit_currency": "GBP"}
    binder = api.post("/api/v1/binders", json=binder_in).json()
    api.put(f"/api/v1/reports/{rid}/binder", json={"binder_id": binder["id"]})
    finding = api.get(f"/api/v1/reports/{rid}/checks/findings").json()["items"][0]
    slist = api.post(
        "/api/v1/sanctions/lists", files={"file": ("l.csv", b"Name\nHarrow Quay\n", "text/csv")}, data={"name": "L"}
    ).json()
    corr = api.post(f"/api/v1/reports/{rid}/corrections", json={"sheet_id": sheet["id"], "cell": "B3",
                                                                 "after_value": "Named Ltd", "reason": "x"}).json()
    api.post(f"/api/v1/reports/{rid}/corrections/{corr['id']}/decision", json={"approve": True})
    version = api.post(f"/api/v1/reports/{rid}/versions").json()
    return {
        "issue_id": exc["validation_result_id"],
        "correction_id": corr["id"],
        "version_id": version["id"],
        "report_id": rid,
        "sheet_id": sheet["id"],
        "validation_result_id": exc["validation_result_id"],
        "dup_id": dup["validation_result_id"],
        "obligation_id": ob["id"],
        "alert_id": alert["id"],
        "template_id": tpl["id"],
        "invitation_id": inv["id"],
        "membership_id": member["membership_id"],
        "endpoint_id": hook["id"],
        "delivery_id": delivery["id"],
        "binder_id": binder["id"],
        "finding_id": finding["id"],
        "module": "binder",
        "list_id": slist["id"],
    }


def _operations() -> list[tuple[str, str, dict[str, Any]]]:
    doc = app.openapi()
    return [
        (method, path, op)
        for path, ops in doc["paths"].items()
        for method, op in ops.items()
        # "/__..." routes are injected by other tests (e.g. an exception probe), not product endpoints
        if method in {"get", "post", "patch", "put", "delete"} and not path.startswith("/__")
    ]


def _fill(path: str, ids: dict[str, str]) -> str:
    url = path
    if "/duplicates/{validation_result_id}" in path:
        url = url.replace("{validation_result_id}", ids["dup_id"])
    for name, value in ids.items():
        url = url.replace("{" + name + "}", value)
    return url


def test_every_id_endpoint_is_404_for_another_tenant(api: Api, api_b: Api) -> None:
    ids = _tenant_a(api)
    before_status = api.get(f"/api/v1/reports/{ids['report_id']}").json()["status"]
    probed = 0
    for method, path, op in _operations():
        if "{" not in path:
            continue
        if path in OPERATOR_ONLY:  # not tenant data: refused outright to anyone but an operator
            assert getattr(api_b, method)(path.replace("{lead_id}", "x")).status_code == 403, path
            continue
        url = _fill(path, ids)
        assert "{" not in url, f"no isolation id for {method.upper()} {path}: add it to _tenant_a()"
        kwargs: dict[str, Any] = {}
        if "requestBody" in op:
            key = (method, path)
            assert key in BODIES, f"no isolation body for {method.upper()} {path}: add it to BODIES"
            kwargs["json"] = BODIES[key]
        r = getattr(api_b, method)(url, **kwargs)
        assert r.status_code == 404, (method, path, r.status_code, r.text[:200])
        assert MARKER_FILE not in r.text and MARKER_REF not in r.text
        probed += 1
    assert probed >= 30, probed
    # nothing of A's changed
    assert api.get(f"/api/v1/reports/{ids['report_id']}").json()["status"] == before_status
    obligations = api.get("/api/v1/obligations").json()["items"]
    assert all(o["status"] != "RESOLVED" for o in obligations)
    members = api.get("/api/v1/org/members").json()
    assert [m["role"] for m in members] == ["OWNER"]
    assert any(i["id"] == ids["invitation_id"] for i in api.get("/api/v1/org/invitations").json())


def test_every_list_endpoint_hides_other_tenants(api: Api, api_b: Api) -> None:
    ids = _tenant_a(api)
    leaks = [MARKER_FILE, MARKER_REF, "owner@a.example", "invitee@a.example", *ids.values()]
    checked = 0
    for method, path, _op in _operations():
        if method != "get" or "{" in path or path in PUBLIC or path in NO_TENANT_DATA:
            continue
        r = api_b.get(path)
        assert r.status_code == (403 if path in SENDER_ONLY | OPERATOR_ONLY else 200), (path, r.status_code)
        for leak in leaks:
            assert leak not in r.text, (path, leak)
        checked += 1
    assert checked >= 10, checked


def test_body_only_writes_cannot_target_another_tenant(api: Api, api_b: Api) -> None:
    """Operations that take ids in the BODY rather than the path."""
    ids = _tenant_a(api)
    r = api_b.post(f"/api/v1/reports/{ids['report_id']}/obligations", json={"claim_row_id": ids["report_id"]})
    assert r.status_code == 404
    r = api_b.post("/api/v1/templates", json={"name": "T", "field_mappings": {"Ref": "CR0104M"}})
    assert r.status_code == 201
    assert all(t["name"] == "T" for t in api.get("/api/v1/templates").json())
    assert len(api.get("/api/v1/templates").json()) == 1


@pytest.mark.skipif(not IS_PG, reason="Row-Level Security exists on PostgreSQL only")
def test_every_tenant_table_has_forced_rls_and_a_policy(db: Session) -> None:
    tables = {
        r[0]
        for r in db.execute(
            text(
                "SELECT table_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND column_name = 'tenant_id'"
            )
        )
    }
    assert {"reports", "memberships", "auth_sessions", "invitations"} <= tables
    flags = {
        r[0]: (r[1], r[2])
        for r in db.execute(
            text("SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = ANY(:t)"),
            {"t": list(tables)},
        )
    }
    policies = {r[0] for r in db.execute(text("SELECT tablename FROM pg_policies WHERE schemaname = 'public'"))}
    missing = sorted(t for t in tables if flags.get(t) != (True, True) or t not in policies)
    assert not missing, f"tables with tenant_id but no forced RLS policy: {missing}"


@pytest.mark.skipif(not IS_PG, reason="Row-Level Security exists on PostgreSQL only")
def test_identity_rows_are_visible_only_to_their_tenant_user_or_token_holder(api: Api, api_b: Api) -> None:
    from app.database import get_session_factory, set_identity, set_tenant
    from app.models.identity import AuthSession, Membership
    from app.security.auth import token_hash

    a_tenant, a_user = api.me["tenant"]["id"], api.me["user"]["id"]
    s = get_session_factory()()
    try:
        set_tenant(s, api_b.me["tenant"]["id"])
        assert s.query(Membership).filter_by(tenant_id=a_tenant).count() == 0
        assert s.query(AuthSession).filter_by(tenant_id=a_tenant).count() == 0
        s.rollback()
        set_tenant(s, None)
        assert s.query(Membership).count() == 0, "no tenant, no identity: nothing visible"
        set_identity(s, user_id=a_user)
        assert {m.tenant_id for m in s.query(Membership)} == {a_tenant}, "a user sees only their own memberships"
        assert {x.tenant_id for x in s.query(AuthSession)} == {a_tenant}, "a user sees only their own sessions (0008)"
    finally:
        s.close()
    # Token-holder path, on a fresh session with no user identity bound.
    s = get_session_factory()()
    try:
        set_identity(s, session_token_hash=token_hash("not-a-real-session-token"))
        assert s.query(AuthSession).count() == 0, "a wrong token hash reveals no session"
        cookie = api.client.cookies.get("tb_session")
        assert cookie
        set_identity(s, session_token_hash=token_hash(cookie))
        assert [x.tenant_id for x in s.query(AuthSession)] == [a_tenant], "the token holder sees exactly that session"
    finally:
        s.close()
