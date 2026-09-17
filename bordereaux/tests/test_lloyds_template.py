"""Truebind 2.3 acceptance test: the seeded Lloyd's Standard v5.2
template is suggested (and mapped correctly) for a sheet using
Lloyd's-standard headers -- both bare codes and the real field names --
and is NOT wrongly suggested for an unrelated sender's header style."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from bordereaux import persistence, templates  # noqa: E402
from bordereaux.db.models import Template  # noqa: E402
from bordereaux.db.session import build_engine, get_session_factory  # noqa: E402
from bordereaux.db import models as db_models  # noqa: E402
from bordereaux.lloyds_template import LLOYDS_CLAIMS_FIELDS, seed_lloyds_template  # noqa: E402

BARE_CODE_HEADERS = [code for code, *_ in LLOYDS_CLAIMS_FIELDS]
NAME_HEADERS = [name for _, name, *_ in LLOYDS_CLAIMS_FIELDS]
EXPECTED_MAPPING = {code: internal for code, _, internal, *_ in LLOYDS_CLAIMS_FIELDS}


def _fresh_session():
    engine = build_engine("sqlite:///:memory:")
    db_models.Base.metadata.create_all(engine)
    import bordereaux.db.session as session_module
    session_module._engine = engine
    session_module._SessionLocal = None
    return get_session_factory()()


def test_seed_is_idempotent_and_non_deletable() -> None:
    session = _fresh_session()
    first = seed_lloyds_template(session)
    session.commit()
    second = seed_lloyds_template(session)
    assert first.id == second.id
    assert session.query(Template).filter(Template.template_type == "STANDARD").count() == 1
    assert second.is_deletable is False
    print("seed idempotency + non-deletable: OK")
    return session


def test_bare_codes_suggest_lloyds_template(session) -> None:
    result = templates.suggest_template(session, BARE_CODE_HEADERS)
    assert result is not None, "expected the Lloyd's template to be suggested for bare CR-codes"
    template, score, suggestions = result
    assert template.name == "Lloyd's Standard v5.2"
    assert score == 1.0
    for code, expected_internal in EXPECTED_MAPPING.items():
        assert suggestions[code] == expected_internal, f"{code}: expected {expected_internal}, got {suggestions.get(code)}"
    print(f"bare-code headers: suggested '{template.name}' at score {score}, all {len(EXPECTED_MAPPING)} fields correct")


def test_real_field_names_suggest_lloyds_template(session) -> None:
    result = templates.suggest_template(session, NAME_HEADERS)
    assert result is not None
    template, score, suggestions = result
    assert template.name == "Lloyd's Standard v5.2"
    assert score == 1.0
    print(f"real field-name headers: suggested '{template.name}' at score {score}")


def test_unrelated_sender_headers_not_suggested(session) -> None:
    markel_headers = ["CLAIM_REF", "CLAIM_STATUS", "LOSS_DATE", "NOTIFIED_DATE",
                       "INSURED_NAME", "POLICY_REF", "PAID_AMT", "RESERVE_AMT",
                       "INCURRED_AMT", "CURRENCY"]
    result = templates.suggest_template(session, markel_headers, min_score=0.6)
    assert result is None, f"expected no suggestion for an unrelated header style, got {result}"
    print("unrelated sender headers: correctly not suggested")


def main() -> None:
    session = test_seed_is_idempotent_and_non_deletable()
    test_bare_codes_suggest_lloyds_template(session)
    test_real_field_names_suggest_lloyds_template(session)
    test_unrelated_sender_headers_not_suggested(session)
    print("\nLloyd's v5.2 template acceptance test PASSED.")


if __name__ == "__main__":
    main()
