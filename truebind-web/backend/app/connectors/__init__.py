"""Provider-agnostic spreadsheet connectors.

Business logic (services/connector_service.py) talks only to the Connector
interface in base.py; Microsoft 365 and Google Sheets are two
implementations. Credentials are read from the server environment only, never
stored in the database or returned by the API.
"""

from __future__ import annotations

from .base import Connector, ConnectorError, RemoteFile
from .google import GoogleSheetsConnector
from .microsoft import Microsoft365Connector

PROVIDERS: dict[str, Connector] = {c.key: c for c in (Microsoft365Connector(), GoogleSheetsConnector())}


def get(key: str) -> Connector | None:
    return PROVIDERS.get(key)


__all__ = ["PROVIDERS", "Connector", "ConnectorError", "RemoteFile", "get"]
