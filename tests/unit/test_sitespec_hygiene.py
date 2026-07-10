"""Sitespec aesthetic-hygiene gate (Goal 2, deterministic floor).

Scores the HM sitespec CSS design system against the modern-landing-page hygiene
rubric (`dazzle.core.sitespec_hygiene`). Two guarantees, mirroring the
delegation-proof ratchet:

1. ``test_sitespec_hygiene_floor`` — the score never regresses below the ratchet
   FLOOR. Green today at the post-port baseline; raise FLOOR as 2B lifts the score
   so gains are locked in.
2. ``test_sitespec_hygiene_meets_modern_bar`` — the score clears MODERN_BAR. It is
   ``xfail(strict=True)`` today (baseline < bar → expected fail → green). When 2B's
   uplift (a real type scale + fluid ``clamp()`` type) pushes the score over the
   bar it XPASSes, and strict-xfail trips CI — forcing removal of the marker and
   standing up the real green "sitespec meets modern hygiene" gate.

The holistic "reads as modern to a web dev" judgment is the reference-anchored
vision score (Phase 2A-ii), not this floor — this catches gross structural
modernity failures deterministically.
"""

import pytest

from dazzle.core.sitespec_hygiene import hm_sitespec_css, score_sitespec_css

pytestmark = pytest.mark.gate

# Ratchet floor — raised to 90 after Phase 2B (type scale + fluid clamp type lifted
# the score 60.2 → 97.2). Locks in the 2B gain; never regress below this.
FLOOR = 90.0

# The modern-hygiene bar. Clearing it means the deterministic structural signals of
# a modern landing page are all substantially present. Cleared by 2B (97.2 ≥ 85) —
# this is now a standing green gate, not a target.
MODERN_BAR = 85.0


def test_sitespec_hygiene_floor() -> None:
    """The sitespec design system never regresses below the hygiene ratchet."""
    result = score_sitespec_css(hm_sitespec_css())
    total = result["total"]
    assert isinstance(total, (int, float)) and total >= FLOOR, (
        f"sitespec hygiene score {total} fell below the ratchet floor {FLOOR}. "
        f"Breakdown: {result['breakdown']}. A regression in the sitespec design "
        "system — restore the lost dimension, or (if intentional) lower FLOOR with "
        "a rationale."
    )


def test_sitespec_hygiene_meets_modern_bar() -> None:
    """The sitespec clears the modern-hygiene bar — standing green proof since 2B
    (type scale + fluid clamp type took it to 97.2/100)."""
    result = score_sitespec_css(hm_sitespec_css())
    total = result["total"]
    assert isinstance(total, (int, float)) and total >= MODERN_BAR, (
        f"sitespec hygiene score {total} is below the modern bar {MODERN_BAR}. "
        f"Breakdown: {result['breakdown']}"
    )
