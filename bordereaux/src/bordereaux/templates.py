"""Truebind 2.3 prerequisite: saved sender mapping templates.

Neither this nor an "obligations/alerts system" existed anywhere in the
codebase before this session (confirmed by grep before starting this
build) despite the redevelopment prompt referring to them as already
scoped -- this module is the minimal, real implementation that 2.3's
Lloyd's v5.2 template and any future user-saved template both sit on top
of. A template is a saved sheet -> field-code mapping (CUSTOM, from a
confirmed upload) or a built-in standard (STANDARD, e.g. Lloyd's v5.2,
non-deletable). Scored against an incoming sheet's headers as a third
mapping signal alongside the fuzzy-alias and AI stages in mapping.py --
never auto-applied, exactly like those two.
"""

from __future__ import annotations

import json

from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from .db.models import Template, TemplateFieldMapping
from .mapping import FUZZY_THRESHOLD, normalize_header


def create_template(
    session: Session,
    name: str,
    template_type: str,
    field_mappings: list[tuple[str, str, bool]],  # (header_text, field_code, mandatory)
    created_by: str | None = None,
    is_deletable: bool = True,
    metadata: dict | None = None,
) -> Template:
    template = Template(
        name=name, template_type=template_type, created_by=created_by,
        is_deletable=is_deletable, metadata_json=json.dumps(metadata or {}),
    )
    session.add(template)
    session.flush()
    for header_text, field_code, mandatory in field_mappings:
        session.add(TemplateFieldMapping(
            template_id=template.id, header_text=header_text,
            field_code=field_code, mandatory=mandatory,
        ))
    session.flush()
    return template


def save_template_from_mapping(
    session: Session, name: str, created_by: str, confirmed_mapping: dict[str, str],
) -> Template:
    """Let a user turn a confirmed upload's mapping into a reusable CUSTOM
    template. `mandatory` is left False here -- a saved custom template
    doesn't carry an external standard's mandatory/conditional grid, only
    the header<->field_code pairing the user just confirmed."""
    field_mappings = [(header, code, False) for header, code in confirmed_mapping.items()]
    return create_template(session, name, "CUSTOM", field_mappings, created_by=created_by)


def score_template(template: Template, headers: list[str]) -> tuple[float, dict[str, str]]:
    """Fraction of the incoming sheet's headers this template explains
    (exact-after-normalization or fuzzy match against the template's own
    header text), plus the resulting header->field_code suggestion for
    whichever headers matched. Never auto-applied by the caller -- see
    mapping.py's confirmation-required discipline."""
    if not headers:
        return 0.0, {}

    normalized_template = {normalize_header(m.header_text): m.field_code for m in template.field_mappings}
    choices = list(normalized_template.keys())

    matched = 0
    suggestions: dict[str, str] = {}
    for header in headers:
        norm = normalize_header(header)
        if norm in normalized_template:
            matched += 1
            suggestions[header] = normalized_template[norm]
            continue
        if choices:
            best = max(choices, key=lambda c: fuzz.token_sort_ratio(norm, c))
            if fuzz.token_sort_ratio(norm, best) >= FUZZY_THRESHOLD:
                matched += 1
                suggestions[header] = normalized_template[best]

    return matched / len(headers), suggestions


def suggest_template(
    session: Session, headers: list[str], min_score: float = 0.6,
) -> tuple[Template, float, dict[str, str]] | None:
    """Best-scoring saved template for this sheet's headers, or None if
    nothing clears min_score. Ties broken in favour of STANDARD templates
    (a known market standard is a safer default suggestion than an
    arbitrary past upload that happens to score the same)."""
    best: tuple[Template, float, dict[str, str]] | None = None
    for template in session.query(Template).all():
        score, suggestions = score_template(template, headers)
        if score < min_score:
            continue
        if best is None or score > best[1] or (score == best[1] and template.template_type == "STANDARD"):
            best = (template, score, suggestions)
    return best
