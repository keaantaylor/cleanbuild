"""SFTP destination (Settings -> Channels).

GET    /api/v1/org/sftp        the destination without secrets, or null (org:read)
PUT    /api/v1/org/sftp        create or replace (org:manage); secrets write-only
DELETE /api/v1/org/sftp        remove (org:manage)
POST   /api/v1/org/sftp/test   connect, check the pinned host key, list the folder (org:manage)
"""

from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.channels import SftpDestination
from ..security import crypto
from ..security.auth import Context, require
from ..security.permissions import Permission
from ..services import audit_service, sftp_service

router = APIRouter(prefix="/api/v1/org/sftp", tags=["channels"])
_org_read = require(Permission.ORG_READ)
_org_manage = require(Permission.ORG_MANAGE)
_FINGERPRINT = re.compile(r"SHA256:[A-Za-z0-9+/]{43}")


class SftpIn(BaseModel):
    host: str = Field(min_length=1, max_length=253, pattern=r"^[A-Za-z0-9.-]+$")
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=200)
    password: str | None = Field(default=None, max_length=1000)
    private_key: str | None = Field(default=None, max_length=20000)
    host_key_fingerprint: str = Field(max_length=200)
    remote_dir: str = Field(default="/", max_length=500)
    auto_deliver: bool = False
    enabled: bool = True

    @model_validator(mode="after")
    def _check(self) -> SftpIn:
        if not _FINGERPRINT.fullmatch(self.host_key_fingerprint):
            raise ValueError(
                "host_key_fingerprint must look like SHA256:<43 base64 characters> (ssh-keyscan | ssh-keygen -lf -)"
            )
        if bool(self.password) == bool(self.private_key):
            raise ValueError("send exactly one of password or private_key")
        if ".." in self.remote_dir.split("/"):
            raise ValueError("remote_dir must not contain '..'")
        return self


class SftpOut(BaseModel):
    host: str
    port: int
    username: str
    auth: str
    host_key_fingerprint: str
    remote_dir: str
    auto_deliver: bool
    enabled: bool
    created_at: datetime


class TestOut(BaseModel):
    ok: bool
    message: str


def _out(d: SftpDestination) -> SftpOut:
    return SftpOut(
        host=d.host,
        port=d.port,
        username=d.username,
        auth="private_key" if d.private_key_enc else "password",
        host_key_fingerprint=d.host_key_fingerprint,
        remote_dir=d.remote_dir,
        auto_deliver=d.auto_deliver,
        enabled=d.enabled,
        created_at=d.created_at,
    )


def _get(db: Session, tenant_id: str) -> SftpDestination | None:
    return db.query(SftpDestination).filter(SftpDestination.tenant_id == tenant_id).first()


@router.get("", response_model=SftpOut | None)
def get_sftp(ctx: Context = Depends(_org_read), db: Session = Depends(get_db)) -> SftpOut | None:
    """The destination, or null when none is configured."""
    d = _get(db, ctx.tenant_id)
    return _out(d) if d else None


@router.put("", response_model=SftpOut)
def put_sftp(body: SftpIn, ctx: Context = Depends(_org_manage), db: Session = Depends(get_db)) -> SftpOut:
    d = _get(db, ctx.tenant_id)
    before = _out(d).model_dump(mode="json") if d else None
    if d is None:
        d = SftpDestination(tenant_id=ctx.tenant_id)
        db.add(d)
    d.host, d.port, d.username = body.host, body.port, body.username
    d.password_enc = crypto.encrypt(sftp_service.SECRET_PURPOSE, body.password) if body.password else None
    d.private_key_enc = crypto.encrypt(sftp_service.SECRET_PURPOSE, body.private_key) if body.private_key else None
    d.host_key_fingerprint, d.remote_dir = body.host_key_fingerprint, body.remote_dir
    d.auto_deliver, d.enabled = body.auto_deliver, body.enabled
    db.flush()
    after = _out(d).model_dump(mode="json")
    audit_service.log_action(
        db, ctx.tenant_id, None, "SFTP_DESTINATION_SAVED", "SFTP_DESTINATION", d.id, before=before, after=after,
        actor=ctx.actor, actor_user_id=ctx.user_id,
    )  # fmt: skip
    db.commit()
    return _out(d)


@router.delete("", status_code=204)
def delete_sftp(ctx: Context = Depends(_org_manage), db: Session = Depends(get_db)) -> Response:
    d = _get(db, ctx.tenant_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Not found.")
    audit_service.log_action(
        db, ctx.tenant_id, None, "SFTP_DESTINATION_DELETED", "SFTP_DESTINATION", d.id,
        before=_out(d).model_dump(mode="json"), actor=ctx.actor, actor_user_id=ctx.user_id,
    )  # fmt: skip
    db.delete(d)
    db.commit()
    return Response(status_code=204)


@router.post("/test", response_model=TestOut)
def test_sftp(ctx: Context = Depends(_org_manage), db: Session = Depends(get_db)) -> TestOut:
    d = _get(db, ctx.tenant_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Not found.")
    try:
        sftp_service.test_connection(d)
        result = TestOut(ok=True, message=f"Connected to {d.host} and listed {d.remote_dir!r}.")
    except sftp_service.SftpError as exc:
        result = TestOut(ok=False, message=str(exc))
    audit_service.log_action(
        db, ctx.tenant_id, None, "SFTP_CONNECTION_TESTED", "SFTP_DESTINATION", d.id,
        after={"ok": result.ok}, actor=ctx.actor, actor_user_id=ctx.user_id,
    )  # fmt: skip
    db.commit()
    return result
