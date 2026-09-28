"""P1.2 -- organisations, roles, permissions, members and invitations.

Acceptance:
- roles are owner | admin | analyst | viewer | sender with a fixed,
  server-side permission matrix; the legacy REVIEWER role migrates to ANALYST;
- viewers read but cannot change data; senders cannot read provider data;
- owners/admins invite members by one-time token; admins cannot create or
  modify owners; the last owner can never be demoted or removed;
- a removed member's sessions stop working immediately;
- every membership / settings change is audited (hash chain still verifies);
- organisation settings (type, 2FA enforcement) are editable by owner/admin only.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from app.main import app
from app.security.permissions import ROLE_PERMISSIONS, Permission, has_permission
from conftest import PASSWORD, Api, simple_rows, xlsx_bytes
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

BACKEND = Path(__file__).resolve().parents[1]


def _invite(owner: Api, email: str, role: str) -> str:
    r = owner.post("/api/v1/org/invitations", json={"email": email, "role": role})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["role"] == role and body["email"] == email
    return str(body["accept_token"])


def _accept(token: str, name: str = "New Member", password: str = PASSWORD) -> TestClient:
    c = TestClient(app)
    r = c.post("/api/v1/auth/invitations/accept", json={"token": token, "display_name": name, "password": password})
    assert r.status_code == 200, r.text
    c.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    return c


def _member_id(owner: Api, email: str) -> str:
    members = owner.get("/api/v1/org/members").json()
    return str(next(m["membership_id"] for m in members if m["email"] == email))


# ---------------------------------------------------------------- matrix


def test_permission_matrix_is_explicit() -> None:
    assert set(ROLE_PERMISSIONS) == {"OWNER", "ADMIN", "ANALYST", "VIEWER", "SENDER"}
    assert has_permission("VIEWER", Permission.DATA_READ)
    assert not has_permission("VIEWER", Permission.DATA_WRITE)
    assert has_permission("ANALYST", Permission.DATA_WRITE)
    assert not has_permission("ANALYST", Permission.MEMBER_MANAGE)
    assert has_permission("ADMIN", Permission.MEMBER_MANAGE) and has_permission("ADMIN", Permission.ORG_MANAGE)
    assert not has_permission("ADMIN", Permission.BILLING_MANAGE)
    assert has_permission("OWNER", Permission.BILLING_MANAGE)
    assert not has_permission("SENDER", Permission.DATA_READ)
    assert not has_permission("REVIEWER", Permission.DATA_READ), "unknown/legacy roles get nothing"


# ---------------------------------------------------------------- invitations + roles


def test_owner_invites_analyst_who_can_work(api: Api) -> None:
    token = _invite(api, "analyst@a.example", "ANALYST")
    analyst = _accept(token)
    me = analyst.get("/api/v1/auth/me").json()
    assert me["role"] == "ANALYST" and me["tenant"]["id"] == api.me["tenant"]["id"]
    assert "data:write" in me["permissions"] and "member:manage" not in me["permissions"]
    r = analyst.post(
        "/api/v1/reports/upload",
        files={
            "file": (
                "a.xlsx",
                xlsx_bytes(simple_rows()),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert r.status_code == 202, r.text
    assert analyst.post("/api/v1/org/invitations", json={"email": "x@a.example", "role": "VIEWER"}).status_code == 403


def test_viewer_reads_but_cannot_write(api: Api) -> None:
    viewer = _accept(_invite(api, "viewer@a.example", "VIEWER"))
    assert viewer.get("/api/v1/reports").status_code == 200
    up = viewer.post(
        "/api/v1/reports/upload",
        files={
            "file": (
                "a.xlsx",
                xlsx_bytes(simple_rows()),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert up.status_code == 403


def test_sender_cannot_read_provider_data(api: Api) -> None:
    sender = _accept(_invite(api, "sender@tpa.example", "SENDER"))
    for url in ("/api/v1/reports", "/api/v1/overview", "/api/v1/audit", "/api/v1/org/members", "/api/v1/alerts"):
        assert sender.get(url).status_code == 403, url
    assert sender.get("/api/v1/auth/me").json()["role"] == "SENDER"


def test_existing_user_accepts_with_their_own_password(api: Api, api_b: Api) -> None:
    token = _invite(api, "owner@b.example", "VIEWER")
    c = TestClient(app)
    bad = c.post(
        "/api/v1/auth/invitations/accept", json={"token": token, "display_name": "x", "password": "wrong password here"}
    )
    assert bad.status_code == 401
    ok = c.post(
        "/api/v1/auth/invitations/accept", json={"token": token, "display_name": "ignored", "password": PASSWORD}
    )
    assert ok.status_code == 200 and ok.json()["tenant"]["id"] == api.me["tenant"]["id"]
    assert ok.json()["user"]["display_name"] == "owner", "an existing account keeps its profile"


def test_invitation_tokens_are_single_use_expiring_and_revocable(api: Api, db: Session) -> None:
    token = _invite(api, "once@a.example", "VIEWER")
    _accept(token)
    again = TestClient(app).post(
        "/api/v1/auth/invitations/accept", json={"token": token, "display_name": "x", "password": PASSWORD}
    )
    assert again.status_code == 404

    token2 = _invite(api, "late@a.example", "VIEWER")
    inv_id = next(i["id"] for i in api.get("/api/v1/org/invitations").json() if i["email"] == "late@a.example")
    from app.models.identity import Invitation

    inv = db.get(Invitation, inv_id)
    assert inv is not None
    inv.expires_at = inv.created_at - timedelta(seconds=1)
    db.commit()
    expired = TestClient(app).post(
        "/api/v1/auth/invitations/accept", json={"token": token2, "display_name": "x", "password": PASSWORD}
    )
    assert expired.status_code == 410

    token3 = _invite(api, "revoked@a.example", "VIEWER")
    inv3 = next(i["id"] for i in api.get("/api/v1/org/invitations").json() if i["email"] == "revoked@a.example")
    assert api.delete(f"/api/v1/org/invitations/{inv3}").status_code == 204
    revoked = TestClient(app).post(
        "/api/v1/auth/invitations/accept", json={"token": token3, "display_name": "x", "password": PASSWORD}
    )
    assert revoked.status_code == 404


def test_admin_cannot_touch_owners_and_last_owner_is_protected(api: Api) -> None:
    admin = _accept(_invite(api, "admin@a.example", "ADMIN"))
    assert admin.post("/api/v1/org/invitations", json={"email": "o2@a.example", "role": "OWNER"}).status_code == 403
    owner_mid = _member_id(api, "owner@a.example")
    assert admin.patch(f"/api/v1/org/members/{owner_mid}", json={"role": "VIEWER"}).status_code == 403
    assert admin.delete(f"/api/v1/org/members/{owner_mid}").status_code == 403
    # the only owner cannot demote or remove themselves
    assert api.patch(f"/api/v1/org/members/{owner_mid}", json={"role": "ADMIN"}).status_code == 409
    assert api.delete(f"/api/v1/org/members/{owner_mid}").status_code == 409
    # admin may manage non-owners
    viewer_mid = _member_id(api, "admin@a.example")
    assert api.patch(f"/api/v1/org/members/{viewer_mid}", json={"role": "ANALYST"}).json()["role"] == "ANALYST"


def test_removed_member_is_signed_out_everywhere(api: Api) -> None:
    viewer = _accept(_invite(api, "gone@a.example", "VIEWER"))
    assert viewer.get("/api/v1/reports").status_code == 200
    assert api.delete(f"/api/v1/org/members/{_member_id(api, 'gone@a.example')}").status_code == 204
    assert viewer.get("/api/v1/reports").status_code == 401


def test_cross_tenant_member_ids_are_404(api: Api, api_b: Api) -> None:
    mid_a = _member_id(api, "owner@a.example")
    assert api_b.patch(f"/api/v1/org/members/{mid_a}", json={"role": "VIEWER"}).status_code == 404
    assert api_b.delete(f"/api/v1/org/members/{mid_a}").status_code == 404
    _invite(api, "pending@a.example", "VIEWER")
    inv_a = api.get("/api/v1/org/invitations").json()[0]["id"]
    assert api_b.delete(f"/api/v1/org/invitations/{inv_a}").status_code == 404


def test_membership_and_settings_changes_are_audited(api: Api) -> None:
    _accept(_invite(api, "audited@a.example", "VIEWER"))
    mid = _member_id(api, "audited@a.example")
    api.patch(f"/api/v1/org/members/{mid}", json={"role": "ANALYST"})
    r = api.patch("/api/v1/org", json={"org_type": "mga", "require_2fa": True})
    assert r.status_code == 200 and r.json()["org_type"] == "mga" and r.json()["require_2fa"] is True
    api.delete(f"/api/v1/org/members/{mid}")
    entries = api.get("/api/v1/audit", params={"limit": 200}).json()
    items = entries["items"] if isinstance(entries, dict) else entries
    actions = [e["action_type"] for e in items]
    for expected in ("INVITATION_CREATED", "INVITATION_ACCEPTED", "ROLE_CHANGED", "SETTINGS_CHANGED", "MEMBER_REMOVED"):
        assert expected in actions, (expected, actions)
    role_change = next(e for e in items if e["action_type"] == "ROLE_CHANGED")
    assert role_change["before_value"]["role"] == "VIEWER" and role_change["after_value"]["role"] == "ANALYST"
    settings = next(e for e in items if e["action_type"] == "SETTINGS_CHANGED")
    assert settings["before_value"]["require_2fa"] is False and settings["after_value"]["require_2fa"] is True
    assert api.get("/api/v1/audit/verify").json()["intact"] is True


def test_org_settings_need_org_manage(api: Api) -> None:
    analyst = _accept(_invite(api, "a2@a.example", "ANALYST"))
    assert analyst.get("/api/v1/org").status_code == 200
    assert analyst.patch("/api/v1/org", json={"require_2fa": True}).status_code == 403
    assert api.patch("/api/v1/org", json={"org_type": "insurer"}).status_code == 422


# ---------------------------------------------------------------- migration


def test_reviewer_role_migrates_to_analyst(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    url = f"sqlite:///{tmp_path / 'mig.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    command.upgrade(cfg, "0005_inbound_outbound")
    eng = create_engine(url)
    with eng.begin() as c:
        c.execute(
            text("INSERT INTO tenants (id, name, retention_days, created_at) VALUES ('t1','T',90,CURRENT_TIMESTAMP)")
        )
        c.execute(
            text(
                "INSERT INTO users (id, email, password_hash, display_name, is_active, failed_logins, created_at) "
                "VALUES ('u1','r@x.example','h','R',1,0,CURRENT_TIMESTAMP)"
            )
        )
        c.execute(
            text(
                "INSERT INTO memberships (id, user_id, tenant_id, role, created_at) "
                "VALUES ('m1','u1','t1','REVIEWER',CURRENT_TIMESTAMP)"
            )
        )
    command.upgrade(cfg, "head")
    with eng.begin() as c:
        assert c.execute(text("SELECT role FROM memberships WHERE id='m1'")).scalar() == "ANALYST"
        assert c.execute(text("SELECT org_type, require_2fa FROM tenants WHERE id='t1'")).one() == (
            "capacity_provider",
            0,
        )
    command.downgrade(cfg, "0005_inbound_outbound")
    with eng.begin() as c:
        assert c.execute(text("SELECT role FROM memberships WHERE id='m1'")).scalar() == "REVIEWER"
    eng.dispose()
