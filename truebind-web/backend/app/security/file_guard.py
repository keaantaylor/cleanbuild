"""Hostile-file gate, run on every upload BEFORE any parser sees the bytes
(OWASP File Upload Cheat Sheet: allowlist, don't trust Content-Type,
signature checks, decompressed-size limits).

Verdicts: ACCEPT (with disclosure notes) or REJECT (safe reason). There is
no QUARANTINE tier: a rejected file is deleted immediately and only its
hash, size and reason are kept in the audit log. Parsing then runs in an
isolated, memory- and time-limited worker process (app/worker.py) as a
second line of defence against parser-level attacks."""

from __future__ import annotations

import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from ..config import MAX_COMPRESSION_RATIO, MAX_UNCOMPRESSED_BYTES

ALLOWED = {".xlsx": "xlsx", ".xlsm": "xlsm", ".xls": "xls", ".csv": "csv"}
_ZIP_MAGIC = b"PK\x03\x04"
_OLE_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")
MAX_ZIP_ENTRIES = 5000


@dataclass
class Verdict:
    accepted: bool
    kind: str | None = None
    reason: str | None = None  # customer-safe
    code: str | None = None
    notes: list[str] = field(default_factory=list)


def safe_display_name(name: str | None) -> str:
    """Basename only, control/format characters removed, bounded length.
    Used for display; never for a path."""
    name = (name or "upload").replace("\\", "/").split("/")[-1]
    name = "".join(c for c in unicodedata.normalize("NFC", name)
                   if unicodedata.category(c)[0] != "C").strip().lstrip(".")
    name = re.sub(r"\s+", " ", name)
    if len(name) > 200:
        stem, dot, ext = name.rpartition(".")
        name = (stem[: 200 - len(ext) - 1] + "." + ext) if dot else name[:200]
    return name or "upload"


def _reject(code: str, reason: str) -> Verdict:
    return Verdict(False, reason=reason, code=code)


def inspect_upload(path: Path, display_name: str) -> Verdict:
    ext = Path(display_name).suffix.lower()
    kind = ALLOWED.get(ext)
    if kind is None:
        return _reject("unsupported_type", "Unsupported file type. Upload .xlsx, .xlsm, .xls or .csv.")
    size = path.stat().st_size
    if size == 0:
        return _reject("empty_file", "The file is empty.")
    with open(path, "rb") as f:
        head = f.read(8)

    if kind in ("xlsx", "xlsm"):
        if head.startswith(_OLE_MAGIC):
            return _reject("encrypted_or_legacy",
                           "This file is password-protected or is an old .xls saved with a .xlsx name. "
                           "Remove the password (or save as .xlsx) and upload again.")
        if not head.startswith(_ZIP_MAGIC):
            return _reject("signature_mismatch", "The file content does not match its .xlsx extension.")
        return _inspect_ooxml(path, size, kind)
    if kind == "xls":
        if not head.startswith(_OLE_MAGIC):
            return _reject("signature_mismatch", "The file content does not match its .xls extension.")
        return Verdict(True, kind=kind)
    # csv
    with open(path, "rb") as f:
        sample = f.read(65536)
    if head.startswith(_ZIP_MAGIC) or head.startswith(_OLE_MAGIC):
        return _reject("signature_mismatch", "This is a spreadsheet file with a .csv name; upload it as .xlsx/.xls.")
    if b"\x00" in sample:
        return _reject("binary_csv", "This .csv file contains binary data and cannot be read as text.")
    return Verdict(True, kind=kind)


def _inspect_ooxml(path: Path, size: int, kind: str) -> Verdict:
    try:
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
    except zipfile.BadZipFile:
        return _reject("corrupt_file", "The workbook is damaged or truncated and cannot be opened.")
    if len(infos) > MAX_ZIP_ENTRIES:
        return _reject("too_many_parts", "The workbook has an abnormal internal structure and was rejected.")
    names = {i.filename for i in infos}
    if "xl/workbook.xml" not in names:
        return _reject("not_a_workbook", "The file is not a valid Excel workbook.")
    total = 0
    for i in infos:
        total += i.file_size
        if i.compress_size and i.file_size / max(i.compress_size, 1) > MAX_COMPRESSION_RATIO and i.file_size > 10_000_000:
            return _reject("compression_bomb", "The workbook expands to an abnormal size and was rejected.")
        if total > MAX_UNCOMPRESSED_BYTES:
            return _reject("too_large_uncompressed",
                           f"The workbook expands to more than {MAX_UNCOMPRESSED_BYTES // (1024 * 1024)} MB and was rejected.")
    v = Verdict(True, kind=kind)
    if "xl/vbaProject.bin" in names:
        v.notes.append("the workbook contains macros; they are never executed -- only cell values are read")
    if any(n.startswith("xl/externalLinks/") for n in names):
        v.notes.append("the workbook links to other files; linked values are read as last saved, never refreshed")
    return v
