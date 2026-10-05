"""The interface every spreadsheet provider implements."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ConnectorError(RuntimeError):
    """A provider call failed; the message is safe to show (no secrets, no tokens)."""


@dataclass(frozen=True)
class RemoteFile:
    file_id: str
    web_url: str
    name: str


class Connector(Protocol):
    key: str  # "microsoft365" | "google"
    label: str  # "Microsoft 365"
    open_label: str  # "Open in Excel"

    def configured(self) -> bool:
        """Credentials are present in the server environment."""

    def upload(self, name: str, body: bytes, file_id: str | None = None) -> RemoteFile:
        """Create a new file (or a new version of file_id) from xlsx bytes."""

    def download(self, file_id: str) -> bytes:
        """The file as it is now, as xlsx bytes."""
