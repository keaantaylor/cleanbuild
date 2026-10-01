"""Object storage for uploaded original files -- write once, never deleted.

Originals are content-addressed: ``tenants/<tenant>/originals/<sha256>.<kind>``.
The SHA-256 is computed on write, recorded with the object and verified on
every read, so a changed file is detected and never parsed. There is no
delete, overwrite or rename operation anywhere in this interface; purging
originals after the retention period is a storage-level lifecycle rule run
by the operator (docs/RETENTION.md), not application code.

Backends:
- ``LocalObjectStore`` -- files under TRUEBIND_STORAGE_DIR (development, tests);
  new objects are created read-only (0400) and never replaced.
- ``S3ObjectStore`` -- AWS S3, Cloudflare R2 or MinIO via boto3; server-side
  encryption on every object, SHA-256 in object metadata, and a conditional
  ``If-None-Match: *`` write so an existing key can never be replaced.
- ``DbObjectStore`` -- rows in PostgreSQL (``stored_blobs``, Row Level Security).
  The production default: hosts with an ephemeral local disk (Render, Fly)
  lose files on every restart or redeploy, which left jobs failing with
  "source_missing"; the database is already durable and backed up.

Besides originals, a store keeps *derived* artefacts (``put_derived`` /
``get_derived``): the parsed-workbook cache that lets processing reuse the
parse done at mapping time. Derived objects are a cache: losing one only
means the workbook is parsed again.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..settings import get_settings

_KIND = r"(xlsx|xlsm|xls|csv|zip)"
_KEY_RE = re.compile(
    rf"^tenants/[0-9a-f-]{{36}}/(originals/[0-9a-f]{{64}}\.{_KIND}|reports/[0-9a-f-]{{36}}/source\.{_KIND})$"
)
_DERIVED_RE = re.compile(r"^tenants/[0-9a-f-]{36}/derived/[0-9a-f]{64}-[a-z0-9-]{1,40}\.json\.gz$")
_CHUNK = 1 << 20


class IntegrityError(Exception):
    """The stored bytes do not match the SHA-256 recorded when they were written."""


class ImmutableObjectError(Exception):
    """An attempt to write different bytes to an existing key."""


@dataclass(frozen=True)
class StoredObject:
    key: str
    sha256: str
    size: int


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def original_key(tenant_id: str, sha256: str, kind: str) -> str:
    """kind is the file-gate verdict (signature-checked), never the upload name."""
    key = f"tenants/{tenant_id}/originals/{sha256}.{kind}"
    check_key(key)
    return key


def check_key(key: str) -> None:
    if not _KEY_RE.match(key) or ".." in key:
        raise ValueError("invalid storage key")


def derived_key(tenant_id: str, source_sha256: str, name: str) -> str:
    """Key for an artefact derived from one original (e.g. its parsed sheets)."""
    key = f"tenants/{tenant_id}/derived/{source_sha256}-{name}.json.gz"
    check_derived_key(key)
    return key


def check_derived_key(key: str) -> None:
    if not _DERIVED_RE.match(key) or ".." in key:
        raise ValueError("invalid derived key")


def _tenant_of(key: str) -> str:
    return key.split("/")[1]


class LocalObjectStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or get_settings().storage_path).resolve()

    def _path(self, key: str) -> Path:
        check_key(key)
        p = (self.root / key).resolve()
        if self.root not in p.parents:
            raise ValueError("invalid storage key")
        return p

    def put_original(self, tenant_id: str, kind: str, src: Path, db: Any = None) -> StoredObject:
        digest, size = sha256_file(src), src.stat().st_size
        key = original_key(tenant_id, digest, kind)
        dest = self._path(key)
        if dest.exists():
            if sha256_file(dest) != digest:  # pragma: no cover -- would need a SHA-256 collision or tampering
                raise ImmutableObjectError(key)
            return StoredObject(key, digest, size)
        dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=".incoming-")
        try:
            with os.fdopen(fd, "wb") as out, open(src, "rb") as inp:
                for chunk in iter(lambda: inp.read(_CHUNK), b""):
                    out.write(chunk)
            os.chmod(tmp, 0o400)
            # Atomic, and refuses to replace: link() fails if dest appeared meanwhile.
            try:
                os.link(tmp, dest)
            except FileExistsError:
                if sha256_file(dest) != digest:  # pragma: no cover
                    raise ImmutableObjectError(key) from None
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(tmp)  # the staging name only; the stored original is `dest`
        return StoredObject(key, digest, size)

    def _derived_path(self, key: str) -> Path:
        check_derived_key(key)
        p = (self.root / key).resolve()
        if self.root not in p.parents:
            raise ValueError("invalid derived key")
        return p

    def put_derived(self, key: str, data: bytes, db: Any = None) -> None:
        p = self._derived_path(key)
        p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".derived-")
        with os.fdopen(fd, "wb") as out:
            out.write(data)
        os.replace(tmp, p)

    def get_derived(self, key: str, db: Any = None) -> bytes | None:
        p = self._derived_path(key)
        return p.read_bytes() if p.exists() else None

    @contextlib.contextmanager
    def local_copy(self, key: str, expected_sha256: str, db: Any = None) -> Iterator[Path]:
        """Yield a readable path to the original after verifying its hash."""
        p = self._path(key)
        if not p.exists():
            raise FileNotFoundError("stored source file is missing")
        if sha256_file(p) != expected_sha256:
            raise IntegrityError(key)
        yield p


class S3ObjectStore:
    def __init__(self, client: Any, bucket: str, sse: str = "AES256", cache_dir: Path | None = None) -> None:
        self.client = client
        self.bucket = bucket
        self.sse = sse
        self.cache_dir = cache_dir

    @classmethod
    def from_settings(cls) -> S3ObjectStore:
        import boto3

        s = get_settings()
        client = boto3.client(
            "s3",
            endpoint_url=s.s3_endpoint_url or None,
            region_name=s.s3_region,
            aws_access_key_id=s.s3_access_key_id or None,
            aws_secret_access_key=s.s3_secret_access_key.get_secret_value() or None,
        )
        return cls(client, s.s3_bucket, s.s3_sse, s.data_dir / "cache")

    def _put(self, key: str, body: bytes | Any, sha256: str) -> None:
        from botocore.exceptions import ClientError

        extra: dict[str, Any] = {"Metadata": {"sha256": sha256}, "IfNoneMatch": "*"}
        if self.sse != "none":
            extra["ServerSideEncryption"] = self.sse
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=body, **extra)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("PreconditionFailed", "412", "ConditionalRequestConflict"):
                raise ImmutableObjectError(key) from exc
            raise

    def put_original(self, tenant_id: str, kind: str, src: Path, db: Any = None) -> StoredObject:
        digest, size = sha256_file(src), src.stat().st_size
        key = original_key(tenant_id, digest, kind)
        try:
            with open(src, "rb") as body:
                self._put(key, body, digest)
        except ImmutableObjectError:
            head = self.client.head_object(Bucket=self.bucket, Key=key)
            if head.get("Metadata", {}).get("sha256") != digest:  # pragma: no cover
                raise
        return StoredObject(key, digest, size)

    def put_derived(self, key: str, data: bytes, db: Any = None) -> None:
        check_derived_key(key)
        extra: dict[str, Any] = {} if self.sse == "none" else {"ServerSideEncryption": self.sse}
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, **extra)

    def get_derived(self, key: str, db: Any = None) -> bytes | None:
        from botocore.exceptions import ClientError

        check_derived_key(key)
        try:
            return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except ClientError:
            return None

    @contextlib.contextmanager
    def local_copy(self, key: str, expected_sha256: str, db: Any = None) -> Iterator[Path]:
        """Download to a private temporary file, verify the hash, yield it,
        then remove the temporary copy (the original in the bucket is untouched)."""
        check_key(key)
        base = self.cache_dir or Path(tempfile.gettempdir())
        base.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, tmp_name = tempfile.mkstemp(dir=base, prefix="original-", suffix=Path(key).suffix)
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as out:
                self.client.download_fileobj(self.bucket, key, out)
            if sha256_file(tmp) != expected_sha256:
                raise IntegrityError(key)
            yield tmp
        finally:
            tmp.unlink(missing_ok=True)


class DbObjectStore:
    """Objects as rows in ``stored_blobs`` (PostgreSQL in production).

    Pass the caller's session (``db=``) so a write commits with the record that
    points at it; without one a short-lived session bound to the key's tenant
    is used. Originals stay write-once: the same key with different bytes
    raises ImmutableObjectError. Reports stored before this backend existed
    are still read from the local disk if present."""

    def __init__(self, legacy: LocalObjectStore | None = None) -> None:
        self.legacy = legacy or LocalObjectStore()

    @contextlib.contextmanager
    def _session(self, key: str, db: Any) -> Iterator[Any]:
        if db is not None:
            yield db
            return
        from ..database import get_session_factory, set_tenant

        own = get_session_factory()()
        try:
            set_tenant(own, _tenant_of(key))
            yield own
            own.commit()
        except Exception:
            own.rollback()
            raise
        finally:
            own.close()

    def put_original(self, tenant_id: str, kind: str, src: Path, db: Any = None) -> StoredObject:
        from ..models.blobs import StoredBlob

        digest, size = sha256_file(src), src.stat().st_size
        key = original_key(tenant_id, digest, kind)
        with self._session(key, db) as s:
            existing = s.get(StoredBlob, key)
            if existing is not None:
                if existing.sha256 != digest:  # pragma: no cover -- SHA-256 collision or tampering
                    raise ImmutableObjectError(key)
            else:
                s.add(StoredBlob(key=key, tenant_id=tenant_id, sha256=digest, size=size, content=src.read_bytes()))
                s.flush()
        return StoredObject(key, digest, size)

    def put_derived(self, key: str, data: bytes, db: Any = None) -> None:
        from ..models.blobs import StoredBlob

        check_derived_key(key)
        with self._session(key, db) as s:
            row = s.get(StoredBlob, key)
            digest = hashlib.sha256(data).hexdigest()
            if row is None:
                s.add(StoredBlob(key=key, tenant_id=_tenant_of(key), sha256=digest, size=len(data), content=data))
            else:
                row.sha256, row.size, row.content = digest, len(data), data
            s.flush()

    def get_derived(self, key: str, db: Any = None) -> bytes | None:
        from ..models.blobs import StoredBlob

        check_derived_key(key)
        with self._session(key, db) as s:
            row = s.get(StoredBlob, key)
            return bytes(row.content) if row is not None else None

    @contextlib.contextmanager
    def local_copy(self, key: str, expected_sha256: str, db: Any = None) -> Iterator[Path]:
        from ..models.blobs import StoredBlob

        check_key(key)
        with self._session(key, db) as s:
            row = s.get(StoredBlob, key)
            content = bytes(row.content) if row is not None else None
        if content is None:
            # Stored before the database backend existed: fall back to local disk.
            with self.legacy.local_copy(key, expected_sha256) as p:
                yield p
            return
        if hashlib.sha256(content).hexdigest() != expected_sha256:
            raise IntegrityError(key)
        fd, tmp_name = tempfile.mkstemp(prefix="original-", suffix=Path(key).suffix)
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as out:
                out.write(content)
            yield tmp
        finally:
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)


ObjectStore = LocalObjectStore | S3ObjectStore | DbObjectStore
_store: ObjectStore | None = None


def get_store() -> ObjectStore:
    global _store
    if _store is None:
        backend = get_settings().storage_backend
        _store = (S3ObjectStore.from_settings() if backend == "s3"
                  else DbObjectStore() if backend == "db" else LocalObjectStore())
    return _store


def reset_store() -> None:
    """Forget the cached backend (tests that switch STORAGE_BACKEND)."""
    global _store
    _store = None
