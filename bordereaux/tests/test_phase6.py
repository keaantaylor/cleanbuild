"""Phase 6 acceptance check: drive the Streamlit app headlessly through
the full flow (pick sample -> confirm mapping -> see results) for each
Phase 1 sample file and confirm it runs without raising."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from streamlit.testing.v1 import AppTest  # noqa: E402

EXAMPLES = [
    "Sedgwick Ireland — 50 rows, plain headers",
    "Crawford Ireland — 200 rows, reordered columns",
    "MX Underwriting — 80 rows, unfamiliar headers (needs AI-assisted mapping)",
]


def run_example(label: str) -> None:
    at = AppTest.from_file(str(REPO_ROOT / "app.py"), default_timeout=60)
    at.run()
    assert not at.exception, f"app raised on initial load: {at.exception}"

    # The sample-file selectbox is the first (and, before mapping suggestions
    # render, only) selectbox on the page.
    sample_selectbox = at.selectbox[0]
    sample_selectbox.select(label)
    at.run()
    assert not at.exception, f"app raised after selecting sample: {at.exception}"
    assert "Loaded" in " ".join(m.value for m in at.success), "expected a 'Loaded ...' success message"

    confirm_buttons = [b for b in at.button if "Confirm mapping" in b.label]
    assert confirm_buttons, "expected a 'Confirm mapping and process file' button"
    confirm_buttons[0].click()
    at.run()
    assert not at.exception, f"app raised after confirming mapping: {at.exception}"

    headers = " ".join(h.value for h in at.header)
    assert "Results" in headers and "Download" in headers

    download_buttons = at.download_button
    assert len(download_buttons) == 3, f"expected 3 download buttons, found {len(download_buttons)}"

    print(f"'{label}': OK — reached results + download step with no exceptions")


def main() -> None:
    for label in EXAMPLES:
        run_example(label)
    print("\nPhase 6 acceptance check PASSED.")


if __name__ == "__main__":
    main()
