"""#1567 — the LIVE Hyperpart taste-gate: every HM component must clear the
deterministic token-discipline floor. A new component is scored automatically and
fails here if it sprays raw values instead of delegating to HM tokens.

Page-level chrome (`PAGE_CHROME_EXEMPT`, e.g. transitions.css) is excluded — those
files are overlays/body-state helpers, not card/widget Hyperparts, so the
component-scoped rubric does not fit them.
"""

import pytest

from dazzle.core.component_hygiene import (
    PAGE_CHROME_EXEMPT,
    hm_component_paths,
    score_component_css,
)

pytestmark = pytest.mark.gate

# The per-component token-discipline floor (out of 100). Set just below the current
# gated-corpus minimum (feedback-widget, 73.4 — its accepted raw-inline-motion baseline)
# with a small margin. Teeth: a component that sprays raw colours loses the whole 40-pt
# colour dimension and tops out at 60 < FLOOR, so it fails here. Raise FLOOR as the
# corpus improves to ratchet the gains in.
FLOOR = 70.0

_GATED = [p for p in hm_component_paths() if p.name not in PAGE_CHROME_EXEMPT]


@pytest.mark.parametrize("path", _GATED, ids=lambda p: p.name)
def test_component_clears_the_floor(path) -> None:
    result = score_component_css(path.read_text(encoding="utf-8"))
    total = result["total"]
    if total < FLOOR:
        weakest = min(result["breakdown"].items(), key=lambda kv: kv[1]["sub_score"])
        pytest.fail(
            f"{path.name} scores {total} < floor {FLOOR}. "
            f"Weakest: {weakest[0]} ({weakest[1]['detail']}). "
            f"Use HM var(--dz-…) tokens instead of raw values."
        )


def test_floor_is_a_real_ratchet() -> None:
    # Guard against someone quietly zeroing the gate's teeth.
    assert 70.0 <= FLOOR <= 100.0


def test_gate_covers_the_corpus() -> None:
    # The gate must actually run over real components (not silently empty after a
    # directory move) and exempt only the documented page-chrome files.
    assert len(_GATED) >= 55
    assert all(p.name not in PAGE_CHROME_EXEMPT for p in _GATED)
