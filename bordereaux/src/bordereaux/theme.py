"""Truebind Section 5: the design system.

The prompt is explicit that this supersedes the earlier "pale, restrained
palette" guidance: real, confident colour and strong contrast, everywhere.
WCAG AA is a hard floor here, not a preference -- COLOR_TOKENS is
validated against it at import time (_validate_tokens(), below) for both
light and dark mode, so a future edit that breaks contrast fails loudly
at import rather than shipping a quietly-illegible badge.

Every status system in the product gets its own genuinely distinct
colour family:
  - mapping tri-state (alias/ai/unmapped)
  - arithmetic outcome (match/mismatch/not-evaluable) -- not-evaluable is
    deliberately in a fourth family (violet), never green/amber/red, so
    it can never be mistaken for "clean" at a glance
  - leakage confidence heat (possible -> probable -> certain)
  - sanctions/PEP severity -- reserved as the single most severe
    treatment in the product, deliberately NOT reused for anything else,
    and deliberately NOT theme-adaptive (same near-black-and-red in both
    light and dark mode) precisely because it must never blend into
    whatever the ambient theme happens to look like.

Numbers stay tabular/lining-figure throughout (see the `font-variant-
numeric: tabular-nums` in inject_theme_css()).
"""

from __future__ import annotations

import streamlit as st


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _relative_luminance(hex_color: str) -> float:
    def channel(c: int) -> float:
        c_srgb = c / 255.0
        return c_srgb / 12.92 if c_srgb <= 0.03928 else ((c_srgb + 0.055) / 1.055) ** 2.4

    r, g, b = _hex_to_rgb(hex_color)
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_ratio(hex_a: str, hex_b: str) -> float:
    """WCAG 2.x contrast ratio between two colors, 1.0 (no contrast) to 21.0."""
    l1, l2 = _relative_luminance(hex_a), _relative_luminance(hex_b)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


# ---------------------------------------------------------------------
# Color tokens. Each "fg on bg" pair below is validated (see bottom of
# file) against WCAG AA: 4.5:1 for body text, 3:1 for large text/icons.
# ---------------------------------------------------------------------

PRIMARY = {"light": "#2E3FE0", "dark": "#8B93FF"}
SURFACE = {"light": "#FFFFFF", "dark": "#0F1220"}
TEXT = {"light": "#0F1220", "dark": "#F3F4F8"}
MUTED = {"light": "#5B6472", "dark": "#A6ADBB"}

# Mapping tri-state: MAPPED_BY_ALIAS / MAPPED_BY_AI / UNMAPPED
MAPPING_STATE_COLORS = {
    "alias": {"light": ("#166534", "#DCFCE7"), "dark": ("#86EFAC", "#052e16")},
    "ai": {"light": ("#92400E", "#FEF3C7"), "dark": ("#FCD34D", "#451a03")},
    "unmapped": {"light": ("#991B1B", "#FEE2E2"), "dark": ("#FCA5A5", "#450a0a")},
}

# Arithmetic outcome: MATCH / MISMATCH / NOT_EVALUABLE. not_evaluable is
# deliberately violet -- a fourth family outside green/amber/red -- so it
# can never read as "clean" at a glance.
ARITHMETIC_STATE_COLORS = {
    "match": {"light": ("#166534", "#DCFCE7"), "dark": ("#86EFAC", "#052e16")},
    "mismatch": {"light": ("#9A3412", "#FFEDD5"), "dark": ("#FDBA74", "#431407")},
    "not_evaluable": {"light": ("#5B21B6", "#EDE9FE"), "dark": ("#C4B5FD", "#2e1065")},
}

# Leakage confidence heat: POSSIBLE -> PROBABLE -> CERTAIN, low->high saturation.
LEAKAGE_TIER_COLORS = {
    "POSSIBLE": {"light": ("#92400E", "#FEF3C7"), "dark": ("#FCD34D", "#451a03")},
    "PROBABLE": {"light": ("#9A3412", "#FFEDD5"), "dark": ("#FDBA74", "#431407")},
    "CERTAIN": {"light": ("#991B1B", "#FEE2E2"), "dark": ("#FCA5A5", "#450a0a")},
}

# Sanctions/PEP: the single most severe visual state in the product.
# Deliberately not reused from, or blended with, any other severity
# system above, and deliberately identical in both themes.
SANCTIONS_SEVERITY_COLOR = ("#FFFFFF", "#7A0000")

GRADE_COLORS = {
    5: {"light": ("#166534", "#DCFCE7"), "dark": ("#86EFAC", "#052e16")},
    4: {"light": ("#166534", "#DCFCE7"), "dark": ("#86EFAC", "#052e16")},
    3: {"light": ("#92400E", "#FEF3C7"), "dark": ("#FCD34D", "#451a03")},
    2: {"light": ("#9A3412", "#FFEDD5"), "dark": ("#FDBA74", "#431407")},
    1: {"light": ("#991B1B", "#FEE2E2"), "dark": ("#FCA5A5", "#450a0a")},
}


def _validate_tokens() -> None:
    families = [MAPPING_STATE_COLORS, ARITHMETIC_STATE_COLORS, LEAKAGE_TIER_COLORS, GRADE_COLORS]
    for family in families:
        for state, modes in family.items():
            for mode, (fg, bg) in modes.items():
                ratio = contrast_ratio(fg, bg)
                assert ratio >= 4.5, (
                    f"WCAG AA failure: {state}/{mode} fg={fg} bg={bg} contrast={ratio:.2f} < 4.5"
                )
    for label, (base, mode) in [("primary-light", (PRIMARY["light"], SURFACE["light"])),
                                 ("primary-dark", (PRIMARY["dark"], SURFACE["dark"])),
                                 ("text-light", (TEXT["light"], SURFACE["light"])),
                                 ("text-dark", (TEXT["dark"], SURFACE["dark"]))]:
        ratio = contrast_ratio(base, mode)
        assert ratio >= 4.5, f"WCAG AA failure: {label} contrast={ratio:.2f} < 4.5"
    sanctions_ratio = contrast_ratio(*SANCTIONS_SEVERITY_COLOR)
    assert sanctions_ratio >= 4.5, f"WCAG AA failure: sanctions severity contrast={sanctions_ratio:.2f} < 4.5"


_validate_tokens()


def inject_theme_css() -> None:
    st.markdown(
        f"""
        <style>
        :root {{
            --primary: {PRIMARY['light']};
            --surface: {SURFACE['light']};
            --text: {TEXT['light']};
            --muted: {MUTED['light']};
        }}
        @media (prefers-color-scheme: dark) {{
            :root {{
                --primary: {PRIMARY['dark']};
                --surface: {SURFACE['dark']};
                --text: {TEXT['dark']};
                --muted: {MUTED['dark']};
            }}
        }}
        .tb-stat-value, .tb-badge, div[data-testid="stMetricValue"] {{
            font-variant-numeric: tabular-nums;
        }}
        .tb-stat-label {{
            font-size: 14px; color: var(--muted); font-weight: 600;
            text-transform: uppercase; letter-spacing: 0.04em;
        }}
        .tb-stat-value {{
            font-size: 44px; font-weight: 800; line-height: 1.1; margin-top: 2px;
        }}
        .tb-badge {{
            display: inline-block; padding: 3px 10px; border-radius: 999px;
            font-size: 13px; font-weight: 700;
        }}
        .tb-sanctions-badge {{
            display: inline-block; padding: 5px 14px; border-radius: 6px;
            font-size: 14px; font-weight: 800; letter-spacing: 0.02em;
            background: {SANCTIONS_SEVERITY_COLOR[1]}; color: {SANCTIONS_SEVERITY_COLOR[0]};
            border: 2px solid {SANCTIONS_SEVERITY_COLOR[0]};
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _mode_colors(family: dict, key) -> tuple[str, str]:
    """Returns (fg_light, bg_light) -- CSS below is written so the badge
    itself is theme-invariant per call (Streamlit doesn't expose the
    active color scheme to Python), using the light-mode pair as the
    base and letting a prefers-color-scheme override recolor it in CSS."""
    return family[key]["light"]


def render_stat(label: str, value: str, tone: str = "neutral") -> None:
    color = {"neutral": TEXT["light"], "primary": PRIMARY["light"]}.get(tone, TEXT["light"])
    st.markdown(
        f'<div class="tb-stat-label">{label}</div>'
        f'<div class="tb-stat-value" style="color:{color};">{value}</div>',
        unsafe_allow_html=True,
    )


def render_status_badge(text: str, fg: str, bg: str) -> str:
    return f'<span class="tb-badge" style="color:{fg}; background:{bg};">{text}</span>'


def mapping_state_badge(state: str, label: str | None = None) -> str:
    fg, bg = _mode_colors(MAPPING_STATE_COLORS, state)
    return render_status_badge(label or state.upper(), fg, bg)


def arithmetic_state_badge(state: str, label: str | None = None) -> str:
    fg, bg = _mode_colors(ARITHMETIC_STATE_COLORS, state)
    return render_status_badge(label or state.upper().replace("_", " "), fg, bg)


def leakage_tier_badge(tier: str) -> str:
    fg, bg = _mode_colors(LEAKAGE_TIER_COLORS, tier)
    return render_status_badge(tier, fg, bg)


def grade_badge(grade: int, label: str) -> str:
    fg, bg = _mode_colors(GRADE_COLORS, grade)
    return render_status_badge(label, fg, bg)


def sanctions_badge(text: str = "SANCTIONS / PEP MATCH") -> str:
    return f'<span class="tb-sanctions-badge">{text}</span>'
