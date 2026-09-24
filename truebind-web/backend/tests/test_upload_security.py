"""Hostile-file gate (forensic S1-S10): every rejection happens before any
parser runs, is audited with the file hash (not the file), and leaves
nothing in storage."""

from __future__ import annotations

import io
import zipfile

import pytest

from app.config import STORAGE_DIR
from conftest import XLSX, run_jobs, simple_rows, xlsx_bytes


def _stored_files():
    root = STORAGE_DIR / "tenants"
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


def _zip(entries: dict[str, bytes], compression=zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression) as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return buf.getvalue()


OLE = bytes.fromhex("D0CF11E0A1B11AE1") + b"\x00" * 504


@pytest.mark.parametrize("name,content,status,code", [
    ("payload.exe", b"MZ\x90\x00", 415, "unsupported_type"),
    ("claims.xlsx.exe", b"MZ", 415, "unsupported_type"),
    ("empty.xlsx", b"", 400, "empty_file"),
    ("text.xlsx", b"just some text pretending", 400, "signature_mismatch"),
    ("protected.xlsx", OLE, 400, "encrypted_or_legacy"),
    ("fake.xls", b"PK\x03\x04 not ole", 400, "signature_mismatch"),
    ("notbook.xlsx", None, 400, "not_a_workbook"),
    ("bin.csv", b"a,b\x00,c\n", 400, "binary_csv"),
    ("disguised.csv", None, 400, "signature_mismatch"),
])
def test_hostile_files_rejected_before_parsing(api, db, name, content, status, code):
    from app.models.audit import AuditLogEntry
    if name == "notbook.xlsx":
        content = _zip({"readme.txt": b"hello"})
    if name == "disguised.csv":
        content = xlsx_bytes(simple_rows())
    r = api.upload(name, content)
    assert r.status_code == status, r.text
    assert "Traceback" not in r.text
    assert _stored_files() == []
    assert api.get("/api/v1/reports").json()["total"] == 0
    rej = db.query(AuditLogEntry).filter_by(action_type="UPLOAD_REJECTED").one()
    assert rej.after_value["code"] == code and len(rej.after_value["sha256"]) == 64


def test_decompression_bomb_rejected(api, monkeypatch):
    import app.security.file_guard as fg
    monkeypatch.setattr(fg, "MAX_UNCOMPRESSED_BYTES", 5 * 1024 * 1024)
    bomb = _zip({"[Content_Types].xml": b"<Types/>", "xl/workbook.xml": b"<workbook/>",
                 "xl/worksheets/sheet1.xml": b"0" * (20 * 1024 * 1024)})
    assert len(bomb) < 200_000
    r = api.upload("bomb.xlsx", bomb)
    assert r.status_code == 413 and _stored_files() == []


def test_high_ratio_part_rejected(api):
    bomb = _zip({"[Content_Types].xml": b"<Types/>", "xl/workbook.xml": b"<workbook/>",
                 "xl/worksheets/sheet1.xml": b"A" * (60 * 1024 * 1024)})
    r = api.upload("ratio.xlsx", bomb)
    assert r.status_code == 413


def test_oversized_upload_rejected(api, monkeypatch):
    import app.main as main
    import app.routes.reports as reports
    monkeypatch.setattr(reports, "MAX_UPLOAD_BYTES", 1000)
    monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", 0)
    monkeypatch.setattr(main, "_UPLOAD_OVERHEAD", 50_000)
    r = api.upload("big.xlsx", xlsx_bytes(simple_rows(200)))
    assert r.status_code == 413
    assert _stored_files() == []


def test_path_traversal_filename_cannot_escape_storage(api):
    r = api.upload("../../../../etc/cron.d/evil.xlsx", xlsx_bytes(simple_rows()))
    assert r.status_code == 202
    body = r.json()
    assert body["file_name"] == "evil.xlsx"
    files = _stored_files()
    assert len(files) == 1 and files[0].name == "source.xlsx"
    assert STORAGE_DIR.resolve() in files[0].resolve().parents


def test_control_characters_stripped_from_display_name(api):
    from app.security.file_guard import safe_display_name
    r = api.upload("inv\u202eoice.xlsx", xlsx_bytes(simple_rows()))
    assert r.status_code == 202 and r.json()["file_name"] == "invoice.xlsx"
    assert safe_display_name("a\x00b\n\r.xlsx") == "ab.xlsx"
    assert safe_display_name("..\\..\\x.xlsx") == "x.xlsx"
    assert safe_display_name("." * 3) == "upload"
    assert len(safe_display_name("x" * 5000 + ".xlsx")) <= 200


def test_macro_workbook_accepted_with_disclosure_and_never_executed(api):
    import openpyxl
    wb = openpyxl.Workbook()
    for row in simple_rows():
        wb.active.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    # add a vbaProject part to the package (content is never executed or parsed)
    data = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as src, zipfile.ZipFile(data, "w") as dst:
        for item in src.infolist():
            dst.writestr(item, src.read(item.filename))
        dst.writestr("xl/vbaProject.bin", b"\x00" * 64)
    r = api.upload("macro.xlsm", data.getvalue(), "application/vnd.ms-excel.sheet.macroEnabled.12")
    assert r.status_code == 202
    notes = r.json()["ingest_notes"]["file_notes"]
    assert any("macros" in n and "never executed" in n for n in notes)
    run_jobs()
    assert api.get(f"/api/v1/reports/{r.json()['id']}").json()["status"] == "WAITING_FOR_REVIEW"


def test_csv_upload_works_end_to_end(api):
    csv = "\n".join(",".join(str(c) for c in row) for row in simple_rows(5)).encode()
    rid, report = api.full_run("claims.csv", csv)
    assert report["rows_processed"] == 5


def test_limit_exceeding_workbook_fails_instead_of_truncating(api, monkeypatch):
    from bordereaux.ingest import ReadLimits
    import app.services.job_handlers as jh
    monkeypatch.setattr(jh, "LIMITS", ReadLimits(max_sheets=200, max_rows_total=10, max_cells_total=10_000))
    rid = api.ingest("many.xlsx", xlsx_bytes(simple_rows(50)))
    report = api.get(f"/api/v1/reports/{rid}").json()
    assert report["status"] == "FAILED" and report["error_code"] == "file_too_large"
    assert "limit" in report["processing_error"]
