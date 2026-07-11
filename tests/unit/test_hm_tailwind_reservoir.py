"""HM zero-floor: no Tailwind utilities in emitters; no residual Dazzle design CSS.

The 2026-07 drain campaign is complete. This gate is a permanent regression
floor — not a shrink-over-cycle thermometer.

- **Markup:** ``total_tailwind_tokens == 0`` in ``src/dazzle/render`` +
  ``src/dazzle/page`` ``class="…"`` literals. The CSS allowlist gate does not
  see emitter class strings; this assertion owns that surface.
- **CSS lines:** ``css_lines_grand_total == 0`` as belt-and-braces beside
  ``tests/unit/test_hm_delegation_proof.py`` (exact served-set allowlist —
  the stronger CSS boundary proof).

Diagnose a red floor with::

    python scripts/hm_tailwind_reservoir.py
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.hm_tailwind_reservoir import floor_is_green, is_tailwind_token, scan

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]


def test_zero_floor_markup_and_css() -> None:
    result = scan(REPO)
    assert result["total_tailwind_tokens"] == 0, (
        "Tailwind utility tokens reappeared in render/page emitter class attrs: "
        f"{result['top_tokens'][:10]} in {result['top_files'][:10]}. "
        "Author dz-* / HM vocabulary — do not reintroduce utility classes."
    )
    assert result["css_lines_grand_total"] == 0, (
        "Dazzle-native design CSS reappeared outside HM: "
        f"main={result['css_files'][:10]} peripheral={result['css_peripheral_files'][:10]}. "
        "Author in packages/hatchi-maxchi/ or register a KEEP with rationale in "
        "test_hm_delegation_proof.DELEGATION_ALLOWLIST."
    )
    assert floor_is_green(result)


@pytest.mark.parametrize(
    "tok,expect",
    [
        ("dz-button", False),
        ("flex", False),  # bare flex is not in the utility-shape set (too noisy)
        ("inline-flex", True),
        ("items-center", True),
        ("gap-2", True),
        ("sm:hidden", True),
        ("hover:bg-muted", True),
        ("opacity-50", True),
        ("w-3-4", False),  # skeleton fractional width, not Tailwind w-N
        ("", False),
    ],
)
def test_is_tailwind_token_classifier(tok: str, expect: bool) -> None:
    assert is_tailwind_token(tok) is expect
