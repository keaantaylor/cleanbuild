"""Read published sanctions lists into (reference, name, kind) entries.

Formats are recognised from the content, never from the file name:
- UK OFSI consolidated list CSV (a header row with "Name 6" and "Group ID";
  names are Name 1..5 followed by Name 6, the surname or entity name);
- US OFAC SDN list (sdn.csv: no header; ent_num, SDN_Name, SDN_Type, ...);
- EU financial sanctions file CSV (";"-separated, "NameAlias_WholeName");
- UN Security Council consolidated list XML (INDIVIDUAL / ENTITY records
  with their aliases), parsed without DTDs or entities;
- a simple CSV with a "name" column (optional "reference" and "type") for an
  organisation's own watch list.
Aliases become entries of their own under the same reference. Nothing is
fetched from the internet here: an administrator loads the file.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException

MAX_ENTRIES = 500_000


class ListFormatError(ValueError):
    """Customer-safe description of why a list could not be read."""


@dataclass(frozen=True)
class ParsedEntry:
    reference: str
    name: str
    kind: str


@dataclass(frozen=True)
class ParsedList:
    source: str  # OFSI | OFAC | EU | UN | CUSTOM
    entries: list[ParsedEntry]


def _text(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ListFormatError("the file is not readable text")  # pragma: no cover -- latin-1 decodes any bytes


def _clean(value: str | None) -> str:
    v = (value or "").strip()
    return "" if v in {"-0-", "-0- ", "NULL"} else v


def _ofsi(rows: list[list[str]], start: int) -> ParsedList:
    header = [h.strip() for h in rows[start]]
    col = {h: i for i, h in enumerate(header)}

    def get(r: list[str], name: str) -> str:
        i = col.get(name)
        return _clean(r[i]) if i is not None and i < len(r) else ""

    out = []
    for r in rows[start + 1 :]:
        name = " ".join(x for x in (get(r, f"Name {i}") for i in (1, 2, 3, 4, 5, 6)) if x)
        if name:
            out.append(ParsedEntry(get(r, "Group ID") or "?", name, get(r, "Group Type").lower() or "unknown"))
    return ParsedList("OFSI", out)


def _ofac(rows: list[list[str]]) -> ParsedList:
    out = []
    for r in rows:
        if len(r) >= 3 and r[0].strip().isdigit() and _clean(r[1]):
            kind = _clean(r[2]).lower() or "entity"
            out.append(ParsedEntry(r[0].strip(), _clean(r[1]), kind))
    return ParsedList("OFAC", out)


def _eu(text: str) -> ParsedList:
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    out = []
    for r in reader:
        name = _clean(r.get("NameAlias_WholeName"))
        if name:
            kind = {"P": "individual", "E": "entity"}.get(_clean(r.get("Entity_SubjectType")), "unknown")
            out.append(ParsedEntry(_clean(r.get("Entity_LogicalId")) or "?", name, kind))
    return ParsedList("EU", out)


_UN_NAME_PARTS = ("FIRST_NAME", "SECOND_NAME", "THIRD_NAME", "FOURTH_NAME")


def _un(data: bytes) -> ParsedList:
    try:
        root = SafeET.fromstring(data, forbid_dtd=True)
    except (DefusedXmlException, SafeET.ParseError) as exc:
        raise ListFormatError("the XML could not be read safely") from exc
    out = []
    kinds = (("INDIVIDUAL", "individual", "INDIVIDUAL_ALIAS"), ("ENTITY", "entity", "ENTITY_ALIAS"))
    for tag, kind, alias_tag in kinds:
        for rec in root.iter(tag):
            ref = (rec.findtext("REFERENCE_NUMBER") or rec.findtext("DATAID") or "?").strip()
            parts = [(rec.findtext(t) or "").strip() for t in _UN_NAME_PARTS]
            name = " ".join(p for p in parts if p)
            if name:
                out.append(ParsedEntry(ref, name, kind))
            for alias in rec.iter(alias_tag):
                a = (alias.findtext("ALIAS_NAME") or "").strip()
                if a:
                    out.append(ParsedEntry(ref, a, kind))
    return ParsedList("UN", out)


def _custom(rows: list[list[str]]) -> ParsedList:
    header = [h.strip().lower() for h in rows[0]]
    name_i = next((i for i, h in enumerate(header) if h in {"name", "full name", "entity name"}), None)
    if name_i is None:
        raise ListFormatError("no 'name' column was found")
    ref_i = next((i for i, h in enumerate(header) if h in {"reference", "id", "ref"}), None)
    type_i = next((i for i, h in enumerate(header) if h in {"type", "kind"}), None)
    out = []
    for n, r in enumerate(rows[1:], start=2):
        name = _clean(r[name_i]) if name_i < len(r) else ""
        if name:
            ref = _clean(r[ref_i]) if ref_i is not None and ref_i < len(r) else f"row-{n}"
            kind = _clean(r[type_i]).lower() if type_i is not None and type_i < len(r) else "unknown"
            out.append(ParsedEntry(ref or f"row-{n}", name, kind or "unknown"))
    return ParsedList("CUSTOM", out)


def parse(data: bytes) -> ParsedList:
    head = data[:2048].lstrip()
    if head.startswith((b"<?xml", b"<CONSOLIDATED_LIST", b"\xef\xbb\xbf<")):
        parsed = _un(data)
    else:
        text = _text(data)
        first = text.splitlines()[0] if text.strip() else ""
        if "NameAlias_WholeName" in first:
            parsed = _eu(text)
        else:
            rows = list(csv.reader(io.StringIO(text)))
            ofsi_at = next((i for i, r in enumerate(rows[:5]) if "Name 6" in [c.strip() for c in r]), None)
            if ofsi_at is not None:
                parsed = _ofsi(rows, ofsi_at)
            elif rows and rows[0] and rows[0][0].strip().isdigit():
                parsed = _ofac(rows)
            elif rows:
                parsed = _custom(rows)
            else:
                raise ListFormatError("the file is empty")
    if not parsed.entries:
        raise ListFormatError("no names were found in the file")
    if len(parsed.entries) > MAX_ENTRIES:
        raise ListFormatError(f"the list has more than {MAX_ENTRIES:,} names")
    return parsed
