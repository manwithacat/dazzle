"""#1144 part 1: multi-threshold `tone_bands:` on cohort_strip lenses.

Pre-fix `CohortStripLens.threshold` was a single float yielding a
hardcoded good/warn/bad trichotomy at threshold / 90% / below. DSL
authors couldn't tune the band ranges or use more than 3 tones.
After #1144 part 1, `tone_bands:` is an ordered list of
`(at: <number>, tone: <token>)` entries — the highest band a value
clears determines its tone.

The scalar `threshold:` path stays exactly as before when
`tone_bands` is empty. The two are mutually exclusive (IR validator
raises) so DSL authors can't half-migrate.
"""

from __future__ import annotations

import pytest

from dazzle.core.ir.workspaces import (
    CohortStripConfig,
    CohortStripLens,
    ToneBandSpec,
)
from dazzle.http.runtime.workspace_card_data import _build_cohort_cells


def _config(*, lens: CohortStripLens) -> CohortStripConfig:
    return CohortStripConfig(member_via="member_id", lenses=[lens])


def _row(member_id: str, primary_value: float) -> dict:
    return {"id": member_id, "member_id": member_id, "score": primary_value}


# ---------------------------------------------------------------------------
# Tone-band evaluation
# ---------------------------------------------------------------------------


def test_value_clears_highest_band_takes_that_tone() -> None:
    lens = CohortStripLens(
        id="score",
        label="Score",
        primary="score",
        tone_bands=[
            ToneBandSpec(at=90, tone="good"),
            ToneBandSpec(at=70, tone="warn"),
            ToneBandSpec(at=0, tone="bad"),
        ],
    )
    cells = _build_cohort_cells(
        items=[_row("m1", 95)],
        config=_config(lens=lens),
        active_lens_id="score",
    )
    assert cells[0]["tone"] == "good"


def test_value_falls_to_middle_band() -> None:
    lens = CohortStripLens(
        id="score",
        label="Score",
        primary="score",
        tone_bands=[
            ToneBandSpec(at=90, tone="good"),
            ToneBandSpec(at=70, tone="warn"),
            ToneBandSpec(at=0, tone="bad"),
        ],
    )
    cells = _build_cohort_cells(
        items=[_row("m1", 85)],
        config=_config(lens=lens),
        active_lens_id="score",
    )
    assert cells[0]["tone"] == "warn"


def test_value_below_all_bands_stays_neutral() -> None:
    """A value lower than every band's `at` matches no band — tone
    falls back to ``neutral`` (no implicit catch-all)."""
    lens = CohortStripLens(
        id="score",
        label="Score",
        primary="score",
        tone_bands=[
            ToneBandSpec(at=90, tone="good"),
            ToneBandSpec(at=70, tone="warn"),
        ],
    )
    cells = _build_cohort_cells(
        items=[_row("m1", 50)],
        config=_config(lens=lens),
        active_lens_id="score",
    )
    assert cells[0]["tone"] == "neutral"


def test_bands_sorted_descending_regardless_of_authoring_order() -> None:
    """Authors can declare bands in any order — the runtime sorts
    descending by `at` so the highest band a value clears always
    wins."""
    lens = CohortStripLens(
        id="score",
        label="Score",
        primary="score",
        tone_bands=[
            ToneBandSpec(at=0, tone="bad"),
            ToneBandSpec(at=90, tone="good"),
            ToneBandSpec(at=70, tone="warn"),
        ],
    )
    cells = _build_cohort_cells(
        items=[_row("m1", 95)],
        config=_config(lens=lens),
        active_lens_id="score",
    )
    assert cells[0]["tone"] == "good"


def test_at_boundary_is_inclusive() -> None:
    """`value >= at` — clearing exactly the threshold still matches.
    Pins the bound so it matches the scalar `threshold` semantics."""
    lens = CohortStripLens(
        id="score",
        label="Score",
        primary="score",
        tone_bands=[ToneBandSpec(at=90, tone="good")],
    )
    cells = _build_cohort_cells(
        items=[_row("m1", 90)],
        config=_config(lens=lens),
        active_lens_id="score",
    )
    assert cells[0]["tone"] == "good"


def test_non_numeric_primary_stays_neutral() -> None:
    """A row whose primary value can't be coerced to a number gets
    neutral tone — no spurious match against bands."""
    lens = CohortStripLens(
        id="status",
        label="Status",
        primary="status",
        tone_bands=[ToneBandSpec(at=90, tone="good")],
    )
    item = {"id": "m1", "member_id": "m1", "status": "open"}
    cells = _build_cohort_cells(items=[item], config=_config(lens=lens), active_lens_id="status")
    assert cells[0]["tone"] == "neutral"


# ---------------------------------------------------------------------------
# Mutual exclusion + back-compat
# ---------------------------------------------------------------------------


def test_threshold_and_tone_bands_mutually_exclusive() -> None:
    """Setting both `threshold:` and `tone_bands:` on one lens
    raises at IR construction — DSL authors see the conflict at
    parse time, not at render."""
    with pytest.raises(ValueError, match="mutually exclusive"):
        CohortStripLens(
            id="score",
            label="Score",
            primary="score",
            threshold=80,
            tone_bands=[ToneBandSpec(at=90, tone="good")],
        )


def test_scalar_threshold_unchanged_when_no_bands() -> None:
    """Regression guard: lenses that only set `threshold:` still get
    the pre-#1144 good/warn/bad trichotomy."""
    lens = CohortStripLens(
        id="score",
        label="Score",
        primary="score",
        threshold=80,
    )
    cells = _build_cohort_cells(
        items=[
            _row("m1", 90),  # >= 80 → good
            _row("m2", 75),  # >= 72 (80*0.9) → warn
            _row("m3", 60),  # < 72 → bad
        ],
        config=_config(lens=lens),
        active_lens_id="score",
    )
    tones = {c["member_id"]: c["tone"] for c in cells}
    assert tones == {"m1": "good", "m2": "warn", "m3": "bad"}


def test_neither_set_stays_neutral() -> None:
    """No threshold AND no tone_bands → neutral. Pre-existing
    behaviour, regression-tested here for completeness."""
    lens = CohortStripLens(id="score", label="Score", primary="score")
    cells = _build_cohort_cells(
        items=[_row("m1", 99)], config=_config(lens=lens), active_lens_id="score"
    )
    assert cells[0]["tone"] == "neutral"
