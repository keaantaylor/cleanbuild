"""SFTP delivery of outputs to a partner server (one destination per
organisation).

- The server's host key is pinned: the configured SHA256 fingerprint must
  match the key presented, otherwise nothing is sent (no trust-on-first-use).
- Password or private key (PEM) is stored encrypted (purpose "sftp-secret")
  and never returned by the API.
- Files are written under a temporary name and renamed into place, so the
  partner never picks up a half-written file.
- Every attempt is recorded as a Delivery (channel "sftp") with a
  customer-safe outcome, alerted and audited -- never silently dropped.
"""

from __future__ import annotations

import base64
import hashlib
import io
import logging
import posixpath
import socket
from dataclasses import dataclass

import paramiko
from sqlalchemy.orm import Session

from ..models.channels import SftpDestination
from ..models.deliveries import Delivery
from ..models.reports import Report
from ..security import crypto
from . import alert_service, audit_service, delivery_service, export_service

log = logging.getLogger("truebind.sftp")

SECRET_PURPOSE = "sftp-secret"  # noqa: S105 -- a key-derivation label, not a secret
TIMEOUT_S = 20


class SftpError(Exception):
    """Customer-safe message."""


@dataclass(frozen=True)
class Credentials:
    password: str | None
    private_key: str | None


def fingerprint(key: paramiko.PKey) -> str:
    digest = hashlib.sha256(key.asbytes()).digest()
    return "SHA256:" + base64.b64encode(digest).decode().rstrip("=")


def _load_key(pem: str) -> paramiko.PKey:
    for cls in (paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.RSAKey):
        try:
            return cls.from_private_key(io.StringIO(pem))
        except (paramiko.SSHException, ValueError):
            continue
    raise SftpError("The private key could not be read (PEM, Ed25519, ECDSA or RSA).")


def credentials(dest: SftpDestination) -> Credentials:
    return Credentials(
        password=crypto.decrypt(SECRET_PURPOSE, dest.password_enc) if dest.password_enc else None,
        private_key=crypto.decrypt(SECRET_PURPOSE, dest.private_key_enc) if dest.private_key_enc else None,
    )


def _connect(dest: SftpDestination) -> tuple[paramiko.Transport, paramiko.SFTPClient]:
    creds = credentials(dest)
    try:
        sock = socket.create_connection((dest.host, dest.port), timeout=TIMEOUT_S)
    except OSError as exc:
        raise SftpError(f"Could not reach {dest.host}:{dest.port}.") from exc
    transport = paramiko.Transport(sock)
    try:
        transport.start_client(timeout=TIMEOUT_S)
        presented = fingerprint(transport.get_remote_server_key())
        if presented != dest.host_key_fingerprint:
            raise SftpError(
                f"The server's host key ({presented}) does not match the pinned fingerprint. Nothing was sent."
            )
        if creds.private_key:
            transport.auth_publickey(dest.username, _load_key(creds.private_key))
        else:
            transport.auth_password(dest.username, creds.password or "")
        client = paramiko.SFTPClient.from_transport(transport)
        if client is None:
            raise SftpError("The server did not open an SFTP session.")
        return transport, client
    except paramiko.AuthenticationException as exc:
        transport.close()
        raise SftpError("The server rejected the username or credentials.") from exc
    except (paramiko.SSHException, OSError) as exc:
        transport.close()
        raise SftpError("The SFTP connection failed.") from exc
    except SftpError:
        transport.close()
        raise


def test_connection(dest: SftpDestination) -> None:
    transport, client = _connect(dest)
    try:
        client.listdir(dest.remote_dir or ".")
    except OSError as exc:
        raise SftpError(f"The folder {dest.remote_dir!r} is not accessible.") from exc
    finally:
        client.close()
        transport.close()


def upload(dest: SftpDestination, name: str, data: bytes) -> None:
    transport, client = _connect(dest)
    remote_dir = dest.remote_dir or "."
    final = posixpath.join(remote_dir, name)
    partial = posixpath.join(remote_dir, f".{name}.part")
    try:
        with client.open(partial, "wb") as fh:
            fh.write(data)
        try:
            client.posix_rename(partial, final)
        except OSError:
            client.rename(partial, final)
    except OSError as exc:
        raise SftpError(f"Writing to {remote_dir!r} failed.") from exc
    finally:
        client.close()
        transport.close()


def deliver(db: Session, tenant_id: str, report: Report, kind: str, actor: str, actor_user_id: str | None) -> Delivery:
    dest = db.query(SftpDestination).filter(SftpDestination.tenant_id == tenant_id).first()
    name = export_service.file_name(report, kind)
    target = f"{dest.username}@{dest.host}:{dest.remote_dir}" if dest else None
    if dest is None or not dest.enabled:
        d = delivery_service.record(
            db, tenant_id, report.id, kind, "sftp", target, name, None, "NOT_CONFIGURED",
            "No SFTP destination is configured for this organisation.", actor,
        )  # fmt: skip
    else:
        try:
            header, rows = export_service.export_rows(db, tenant_id, report, kind)
            data = export_service.render_csv(header, rows)
            upload(dest, name, data)
            d = delivery_service.record(
                db, tenant_id, report.id, kind, "sftp", target, name, len(data), "DELIVERED", None, actor
            )
        except SftpError as exc:
            log.warning("sftp delivery failed: %s", exc)
            d = delivery_service.record(
                db, tenant_id, report.id, kind, "sftp", target, name, None, "FAILED", str(exc)[:500], actor
            )
    ok = d.status == "DELIVERED"
    alert_service.raise_alert(
        db,
        tenant_id,
        report.id,
        "INFO" if ok else "MEDIUM",
        alert_service.EXPORT_COMPLETE if ok else alert_service.EXPORT_FAILED,
        f"{export_service.KINDS[kind].capitalize()} export for {report.file_name} "
        + ("delivered by SFTP." if ok else f"was not delivered by SFTP: {d.error}"),
    )
    audit_service.log_action(
        db,
        tenant_id,
        report.id,
        "EXPORT_GENERATED",
        "REPORT",
        report.id,
        after={"export": kind, "channel": "sftp", "destination": target, "status": d.status},
        actor=actor,
        actor_user_id=actor_user_id,
    )
    return d
