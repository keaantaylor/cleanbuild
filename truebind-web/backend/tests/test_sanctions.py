"""P5 -- sanctions lists and name screening.

(The precision/recall proof on a planted file is fixtures/golden/sanctions.)

Acceptance:
- lists are recognised from their content: UK OFSI CSV, US OFAC SDN CSV, EU
  financial sanctions CSV, UN consolidated XML (DTDs and entities refused)
  and a simple name CSV; aliases become their own entries; an unreadable
  file is refused with a reason;
- names compare after removing accents, case, punctuation, legal-form words
  and word order; matches are REVIEW, one per list entity, at most three
  per row, never below the threshold;
- lists are loaded and removed by writers only, audited, tenant-scoped, and
  a report screened before any list was loaded says so;
- screening 20,000 names against 20,000 entries takes seconds, not minutes.
"""

from __future__ import annotations

import random
import time

import pytest
from app.checks import sanctions
from app.checks.base import CheckInput, RowView, SheetView
from app.checks.sanctions import Entry, Index, normalise
from app.services import sanctions_lists
from app.services.sanctions_lists import ListFormatError
from conftest import Api, simple_rows, xlsx_bytes

OFSI = (
    b"Last Updated,01/01/2026\nName 6,Name 1,Name 2,Name 3,Name 4,Name 5,Group Type,Alias Type,Group ID\n"
    b"Velkaris,Anatol,Brenn,,,,Individual,Primary name,90002\nVelkaris,Tolya,,,,,Individual,AKA,90002\n"
)
OFAC = b'36,"AEROCARIBBEAN AIRLINES",-0- ,"CUBA",-0- \n173,"ZORVANE, Ilya",individual,"SDGT",-0- \n'
EU = (
    "Entity_LogicalId;Entity_SubjectType;NameAlias_WholeName\n13;E;Orskaya Metals AG\n14;P;Jörg Talvenko\n14;P;\n"
).encode()
UN = b"""<?xml version="1.0" encoding="UTF-8"?><CONSOLIDATED_LIST><INDIVIDUALS><INDIVIDUAL><DATAID>1</DATAID>
<REFERENCE_NUMBER>QDi.001</REFERENCE_NUMBER><FIRST_NAME>BRAVOK</FIRST_NAME><SECOND_NAME>TELLUN</SECOND_NAME>
<INDIVIDUAL_ALIAS><ALIAS_NAME>Bravo Tellun</ALIAS_NAME></INDIVIDUAL_ALIAS></INDIVIDUAL></INDIVIDUALS><ENTITIES><ENTITY>
<DATAID>2</DATAID><REFERENCE_NUMBER>QDe.002</REFERENCE_NUMBER><FIRST_NAME>KESTRAN FOUNDATION</FIRST_NAME>
</ENTITY></ENTITIES></CONSOLIDATED_LIST>"""
CUSTOM = b"Name,Reference,Type\nHarrow Quay Traders,W-1,entity\n,W-2,entity\n"


@pytest.mark.parametrize(
    ("data", "source", "entries"),
    [
        (OFSI, "OFSI", [("90002", "Anatol Brenn Velkaris", "individual"), ("90002", "Tolya Velkaris", "individual")]),
        (OFAC, "OFAC", [("36", "AEROCARIBBEAN AIRLINES", "entity"), ("173", "ZORVANE, Ilya", "individual")]),
        (EU, "EU", [("13", "Orskaya Metals AG", "entity"), ("14", "Jörg Talvenko", "individual")]),
        (UN, "UN", [("QDi.001", "BRAVOK TELLUN", "individual"), ("QDi.001", "Bravo Tellun", "individual"),
                    ("QDe.002", "KESTRAN FOUNDATION", "entity")]),
        (CUSTOM, "CUSTOM", [("W-1", "Harrow Quay Traders", "entity")]),
    ],
)  # fmt: skip
def test_list_formats_are_recognised(data: bytes, source: str, entries: list[tuple[str, str, str]]) -> None:
    parsed = sanctions_lists.parse(data)
    assert parsed.source == source
    assert [(e.reference, e.name, e.kind) for e in parsed.entries] == entries


@pytest.mark.parametrize(
    ("data", "fragment"),
    [
        (b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e "boom">]><CONSOLIDATED_LIST>&e;</CONSOLIDATED_LIST>',
         "could not be read safely"),
        (b"Surname,Given\nA,B\n", "no 'name' column"),
        (b"Name\n\n", "no names"),
        (b"", "empty"),
    ],
)  # fmt: skip
def test_unreadable_lists_are_refused(data: bytes, fragment: str) -> None:
    with pytest.raises(ListFormatError, match=fragment):
        sanctions_lists.parse(data)


def test_normalisation() -> None:
    assert normalise("Müller & Co. GmbH") == normalise("MULLER") == "muller"
    assert normalise("Velkaris, Anatol-Brenn") == "anatol brenn velkaris"
    assert normalise(None) == "" and normalise(" Ltd. ") == ""


def test_matches_are_deduplicated_capped_and_thresholded() -> None:
    idx = Index([Entry("1", "Anatol Velkaris", "L"), Entry("1", "A. Velkaris", "L"),
                 *[Entry(str(i), f"Velkaris Anatol{c}", "L") for i, c in enumerate("abcde", start=2)]])  # fmt: skip
    hits = idx.search("Anatol Velkaris", 90)
    assert [h[0] for h in hits][:1] == ["exact"] and len(hits) == sanctions.MAX_MATCHES_PER_ROW
    assert len({h[2].entity_id for h in hits}) == len(hits)
    assert idx.search("Completely Different", 90) == [] and idx.search("", 90) == []


def test_screening_scales() -> None:
    rng = random.Random(7)  # noqa: S311 -- deterministic test data, not security
    syll = ["ka", "lo", "mir", "vend", "tor", "sa", "bel", "quin", "dro", "hal", "zen", "or"]

    def name() -> str:
        return " ".join("".join(rng.choice(syll) for _ in range(3)).title() for _ in range(2))

    idx = Index([Entry(str(i), name(), "L") for i in range(20_000)])
    rows = [RowView(str(i), "S", i + 2, insured_name=name()) for i in range(20_000)]
    inp = CheckInput(
        "r", {"S": SheetView("S", {"CR0035M": "Insured"})}, rows, {"lists": [{"id": "x"}]}, {"sanctions_index": idx}
    )
    t = time.perf_counter()
    result = sanctions.run(inp)
    assert time.perf_counter() - t < 30
    assert result.rules[0].assessed == 20_000


def _load(api: Api, data: bytes = OFSI, name: str = "Fixture") -> dict[str, object]:
    r = api.post("/api/v1/sanctions/lists", files={"file": ("list.csv", data, "text/csv")}, data={"name": name})
    assert r.status_code == 201, r.text
    body: dict[str, object] = r.json()
    return body


def test_lists_api_is_scoped_audited_and_writers_only(api: Api, api_b: Api) -> None:
    loaded = _load(api)
    assert loaded["source"] == "OFSI" and loaded["entry_count"] == 2 and len(str(loaded["sha256"])) == 64
    assert [x["id"] for x in api.get("/api/v1/sanctions/lists").json()] == [loaded["id"]]
    assert api_b.get("/api/v1/sanctions/lists").json() == []
    assert api_b.delete(f"/api/v1/sanctions/lists/{loaded['id']}").status_code == 404
    bad = api.post(
        "/api/v1/sanctions/lists", files={"file": ("x.csv", b"Surname\nA\n", "text/csv")}, data={"name": "Bad"}
    )
    assert bad.status_code == 422 and "no 'name' column" in bad.json()["detail"]
    actions = [e["action_type"] for e in api.get("/api/v1/audit").json()["items"]]
    assert "SANCTIONS_LIST_LOADED" in actions
    assert api.delete(f"/api/v1/sanctions/lists/{loaded['id']}").status_code == 204
    assert api.get("/api/v1/sanctions/lists").json() == []


def test_screening_through_the_report(api: Api) -> None:
    rows = simple_rows(2)
    rows[1][1] = "Tolya VELKARIS"
    rid, _ = api.full_run("s.xlsx", xlsx_bytes(rows))
    run = next(r for r in api.get(f"/api/v1/reports/{rid}/checks").json() if r["module"] == "sanctions")
    assert run["state"] == "NOT_ASSESSED"
    _load(api)
    run = api.post(f"/api/v1/reports/{rid}/checks/sanctions/run").json()
    assert run["state"] == "ASSESSED" and run["finding_count"] == 1
    f = api.get(f"/api/v1/reports/{rid}/checks/findings", params={"module": "sanctions"}).json()["items"][0]
    assert f["rule_code"] == "SAN_EXACT_MATCH" and f["severity"] == "CRITICAL" and f["row_number"] == 2
    assert f["evidence"]["entry_reference"] == "90002" and f["evidence"]["list"] == "Fixture"
