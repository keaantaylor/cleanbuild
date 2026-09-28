"""Amazon SNS message signature verification (SES inbound mail arrives as
SNS notifications).

A message is accepted only if:
- SigningCertURL is https on an sns.<region>.amazonaws.com host and ends in
  .pem (so the certificate cannot come from anywhere else);
- the RSA signature over the canonical string (AWS's documented field order
  for the message Type) verifies with that certificate, SHA1 for
  SignatureVersion 1 and SHA256 for 2;
- the TopicArn is on the configured allow-list.
Certificates are fetched through an injectable function and cached by URL.
"""

from __future__ import annotations

import base64
import re
from collections.abc import Callable, Mapping
from functools import lru_cache
from urllib.parse import urlparse

import httpx
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

_CERT_HOST = re.compile(r"sns\.[a-z0-9-]+\.amazonaws\.com(\.cn)?")
_FIELDS = {
    "Notification": ("Message", "MessageId", "Subject", "Timestamp", "TopicArn", "Type"),
    "SubscriptionConfirmation": ("Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type"),
    "UnsubscribeConfirmation": ("Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type"),
}


class SnsVerificationError(Exception):
    pass


def canonical_string(message: Mapping[str, str]) -> bytes:
    fields = _FIELDS.get(str(message.get("Type", "")))
    if fields is None:
        raise SnsVerificationError("unknown message type")
    out = []
    for name in fields:
        if name in message and message[name] is not None:
            out.append(f"{name}\n{message[name]}\n")
    return "".join(out).encode("utf-8")


def cert_url_is_trusted(url: str) -> bool:
    parsed = urlparse(url)
    return (
        parsed.scheme == "https" and bool(_CERT_HOST.fullmatch(parsed.hostname or "")) and parsed.path.endswith(".pem")
    )


@lru_cache(maxsize=16)
def _fetch_cert(url: str) -> bytes:
    response = httpx.get(url, timeout=10)
    response.raise_for_status()
    return response.content


def verify(
    message: Mapping[str, str],
    allowed_topics: tuple[str, ...],
    fetch_cert: Callable[[str], bytes] | None = None,
) -> None:
    """Raise SnsVerificationError unless the message is authentic and allowed."""
    topic = str(message.get("TopicArn", ""))
    if not allowed_topics or topic not in allowed_topics:
        raise SnsVerificationError("topic not allowed")
    cert_url = str(message.get("SigningCertURL", ""))
    if not cert_url_is_trusted(cert_url):
        raise SnsVerificationError("untrusted certificate URL")
    version = str(message.get("SignatureVersion", ""))
    algorithm: hashes.HashAlgorithm
    if version == "1":
        algorithm = hashes.SHA1()  # noqa: S303 -- mandated by SNS SignatureVersion 1
    elif version == "2":
        algorithm = hashes.SHA256()
    else:
        raise SnsVerificationError("unsupported signature version")
    try:
        signature = base64.b64decode(str(message.get("Signature", "")), validate=True)
        cert = x509.load_pem_x509_certificate((fetch_cert or _fetch_cert)(cert_url))
    except (ValueError, httpx.HTTPError) as exc:
        raise SnsVerificationError("unreadable signature or certificate") from exc
    key = cert.public_key()
    if not isinstance(key, rsa.RSAPublicKey):
        raise SnsVerificationError("unexpected key type")
    try:
        key.verify(signature, canonical_string(message), padding.PKCS1v15(), algorithm)
    except InvalidSignature as exc:
        raise SnsVerificationError("bad signature") from exc
