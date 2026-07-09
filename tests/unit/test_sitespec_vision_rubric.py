"""Structural test for the sitespec marketing vision rubric (Goal-2 2A-ii).

The rubric is the deterministic contract the vision judge runs on; the LLM call needs
infra, but the rubric shape + prompt are deterministic — so gate them: every dimension
carries 2/5/8 calibration anchors, the family-fidelity dimension exists, and the judge
prompt embeds every dimension key.
"""

import pytest

from dazzle.core.sitespec_vision_rubric import (
    SITESPEC_VISION_DIMENSIONS,
    build_sitespec_judge_prompt,
)

pytestmark = pytest.mark.gate


def test_dimensions_are_well_formed() -> None:
    assert len(SITESPEC_VISION_DIMENSIONS) >= 6, "too few marketing dimensions"
    keys = [d.key for d in SITESPEC_VISION_DIMENSIONS]
    assert len(keys) == len(set(keys)), f"duplicate dimension keys: {keys}"
    assert "family_fidelity" in keys, "the per-family fidelity dimension is required"
    for d in SITESPEC_VISION_DIMENSIONS:
        anchor_scores = [s for s, _ in d.anchors]
        assert anchor_scores == [2, 5, 8], f"{d.key}: anchors must calibrate at 2/5/8"
        assert d.title and d.question, f"{d.key}: title + question required"


def test_judge_prompt_embeds_every_dimension() -> None:
    prompt = build_sitespec_judge_prompt()
    for d in SITESPEC_VISION_DIMENSIONS:
        assert d.key in prompt, f"{d.key} missing from the judge prompt"
    assert "JSON" in prompt, "the prompt must instruct strict-JSON output for scoring"
