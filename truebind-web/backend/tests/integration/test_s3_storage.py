"""P1.5 -- the S3 backend against MinIO (verify --full).

Acceptance: server-side encryption on every object, SHA-256 recorded as
object metadata and verified on read, write-once (a different body can
never replace a key), and a full upload -> ingest -> process run on S3.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterator
from pathlib import Path

import boto3
import pytest
from app.services import storage
from app.services.storage import IntegrityError, S3ObjectStore
from conftest import Api, simple_rows, xlsx_bytes
from integration_env import IT, service_url

pytestmark = [pytest.mark.integration, pytest.mark.skipif(not IT, reason="integration: run via verify.py --full")]
TENANT = "00000000-0000-4000-8000-000000000002"


@pytest.fixture
def s3_store() -> Iterator[S3ObjectStore]:
    bucket = f"truebind-test-{uuid.uuid4().hex[:12]}"
    client = boto3.client(
        "s3",
        endpoint_url=service_url("S3"),
        aws_access_key_id="truebind-test",
        aws_secret_access_key="truebind-test-secret",
        region_name="us-east-1",
    )
    client.create_bucket(Bucket=bucket)
    yield S3ObjectStore(client=client, bucket=bucket, sse="AES256", cache_dir=None)


def test_objects_are_encrypted_hashed_and_write_once(s3_store: S3ObjectStore, tmp_path: Path) -> None:
    content = b"claims bordereau original"
    src = tmp_path / "a.csv"
    src.write_bytes(content)
    obj = s3_store.put_original(TENANT, "csv", src)
    head = s3_store.client.head_object(Bucket=s3_store.bucket, Key=obj.key)
    assert head["ServerSideEncryption"] == "AES256"
    assert head["Metadata"]["sha256"] == hashlib.sha256(content).hexdigest() == obj.sha256
    # same bytes again: idempotent
    assert s3_store.put_original(TENANT, "csv", src) == obj
    # a different body under the same key is refused by the conditional write
    with pytest.raises(storage.ImmutableObjectError):
        s3_store._put(obj.key, b"forged", obj.sha256)
    with s3_store.local_copy(obj.key, obj.sha256) as p:
        assert p.read_bytes() == content


def test_read_verifies_the_hash(s3_store: S3ObjectStore, tmp_path: Path) -> None:
    src = tmp_path / "b.csv"
    src.write_bytes(b"x,y\n")
    obj = s3_store.put_original(TENANT, "csv", src)
    with pytest.raises(IntegrityError), s3_store.local_copy(obj.key, "0" * 64):
        pass


def test_full_workflow_on_s3(
    s3_store: S3ObjectStore, api: Api, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    s3_store.cache_dir = tmp_path / "cache"
    monkeypatch.setattr(storage, "_store", s3_store)
    rid, report = api.full_run("s3.xlsx", xlsx_bytes(simple_rows(4)))
    assert report["status"] == "COMPLETE" and report["rows_processed"] == 4
    keys = [o["Key"] for o in s3_store.client.list_objects_v2(Bucket=s3_store.bucket).get("Contents", [])]
    assert len(keys) == 1 and keys[0].startswith("tenants/") and "/originals/" in keys[0]
    assert api.delete(f"/api/v1/reports/{rid}").status_code == 204
    after = [o["Key"] for o in s3_store.client.list_objects_v2(Bucket=s3_store.bucket).get("Contents", [])]
    assert after == keys, "deleting a report never deletes the original"
