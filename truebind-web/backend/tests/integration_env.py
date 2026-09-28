"""Where the docker-compose.test.yml services live, for integration tests.

scripts/verify.py --full sets TRUEBIND_IT=1 and the TRUEBIND_IT_* URLs
below; the defaults match docker-compose.test.yml's host ports so the
suite can also be run by hand after `docker compose -f docker-compose.test.yml up -d`."""

from __future__ import annotations

import os

IT = os.environ.get("TRUEBIND_IT") == "1"

DEFAULTS = {
    "DATABASE": "postgresql+psycopg://truebind_app:truebind-test-only@127.0.0.1:55433/truebind_test",
    "REDIS": "redis://127.0.0.1:56379",
    "S3": "http://127.0.0.1:59000",
    "SMTP": "smtp://127.0.0.1:51025",
    "MAILPIT_API": "http://127.0.0.1:58025",
    "SFTP": "sftp://127.0.0.1:52022",
    "SFTPGO_API": "http://127.0.0.1:58080",
    "OIDC_ISSUER": "http://127.0.0.1:58081/default",
    "STRIPE_API": "http://127.0.0.1:52111",
    "WEBHOOK_RECEIVER": "http://127.0.0.1:58090",
}


def service_url(name: str) -> str:
    return os.environ.get(f"TRUEBIND_IT_{name}", DEFAULTS[name])
