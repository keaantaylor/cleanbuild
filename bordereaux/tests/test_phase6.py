"""Phase 6 acceptance check: drive the Streamlit app headlessly through
the full flow (click 'try it now' -> confirm mapping -> see results ->
download) and confirm it runs without raising."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from streamlit.testing.v1 import AppTest  # noqa: E402


def run_try_it_now() -> None:
    at = AppTest.from_file(str(REPO_ROOT / "app.py"), default_timeout=60)
    at.run()
    assert not at.exception, f"app raised on initial load: {at.exception}"

    try_it_buttons = [b for b in at.button if "Try it now" in b.label]
    assert try_it_buttons, "expected a 'Try it now with a sample bordereau' button"
    try_it_buttons[0].click()
    at.run()
    assert not at.exception, f"app raised after clicking 'Try it now': {at.exception}"
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

    print("'try it now' sample: OK — reached results + download step with no exceptions")


def main() -> None:
    run_try_it_now()
    print("\nPhase 6 acceptance check PASSED.")


if __name__ == "__main__":
    main()
