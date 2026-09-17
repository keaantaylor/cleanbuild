"""Truebind Section 5 acceptance test: every color token pair meets WCAG
AA (theme.py's _validate_tokens() already asserts this at import time --
this test re-checks it explicitly plus the "genuinely distinct family"
requirements the redevelopment prompt calls out by name)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from bordereaux import theme  # noqa: E402


def test_all_families_meet_wcag_aa() -> None:
    families = {
        "mapping": theme.MAPPING_STATE_COLORS,
        "arithmetic": theme.ARITHMETIC_STATE_COLORS,
        "leakage": theme.LEAKAGE_TIER_COLORS,
        "grade": theme.GRADE_COLORS,
    }
    checked = 0
    for family_name, family in families.items():
        for state, modes in family.items():
            for mode, (fg, bg) in modes.items():
                ratio = theme.contrast_ratio(fg, bg)
                assert ratio >= 4.5, f"{family_name}/{state}/{mode}: contrast {ratio:.2f} < 4.5"
                checked += 1
    assert checked > 0
    print(f"{checked} fg/bg pairs across {len(families)} families all meet WCAG AA (>=4.5:1)")


def test_not_evaluable_is_a_distinct_family_from_match_and_mismatch() -> None:
    match_fg = theme.ARITHMETIC_STATE_COLORS["match"]["light"][0]
    mismatch_fg = theme.ARITHMETIC_STATE_COLORS["mismatch"]["light"][0]
    not_evaluable_fg = theme.ARITHMETIC_STATE_COLORS["not_evaluable"]["light"][0]

    def hue_family(hex_color: str) -> str:
        r, g, b = theme._hex_to_rgb(hex_color)
        if r > g and r > b and g < 100:
            return "red_orange"
        if g > r and g > b:
            return "green"
        if b > r and b > g:
            return "violet_blue"
        return "other"

    families = {hue_family(match_fg), hue_family(mismatch_fg), hue_family(not_evaluable_fg)}
    assert hue_family(not_evaluable_fg) not in (hue_family(match_fg), hue_family(mismatch_fg)), (
        "not_evaluable must never share a hue family with match (green) or mismatch (red/orange) -- "
        "it must never be visually mistaken for 'clean'"
    )
    print(f"match={hue_family(match_fg)}, mismatch={hue_family(mismatch_fg)}, "
          f"not_evaluable={hue_family(not_evaluable_fg)} -- all distinct: {len(families) == 3}")


def test_sanctions_severity_is_reserved_and_theme_invariant() -> None:
    all_other_colors = set()
    for family in (theme.MAPPING_STATE_COLORS, theme.ARITHMETIC_STATE_COLORS,
                    theme.LEAKAGE_TIER_COLORS, theme.GRADE_COLORS):
        for modes in family.values():
            for fg, bg in modes.values():
                all_other_colors.add(fg.upper())
                all_other_colors.add(bg.upper())

    sanctions_fg, sanctions_bg = theme.SANCTIONS_SEVERITY_COLOR
    assert sanctions_bg.upper() not in all_other_colors, "sanctions background must not be reused elsewhere"
    ratio = theme.contrast_ratio(sanctions_fg, sanctions_bg)
    assert ratio >= 4.5
    print(f"sanctions severity color reserved (not reused elsewhere), contrast {ratio:.2f}:1")


def main() -> None:
    test_all_families_meet_wcag_aa()
    test_not_evaluable_is_a_distinct_family_from_match_and_mismatch()
    test_sanctions_severity_is_reserved_and_theme_invariant()
    print("\nDesign system (Section 5) acceptance test PASSED.")


if __name__ == "__main__":
    main()
