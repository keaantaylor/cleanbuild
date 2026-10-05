"""Demo recording only: the local worker records its host name in the audit
trail ("claimed by <host>:<pid>"). Give it a neutral name so no machine or
user name appears on camera. Loaded via PYTHONPATH by playwright.demo.config.ts;
the application code is unchanged."""

import socket

socket.gethostname = lambda: "truebind-worker"

try:  # a local Windows test shim, when one is on the path
    import winfix  # noqa: F401
except ImportError:
    pass
