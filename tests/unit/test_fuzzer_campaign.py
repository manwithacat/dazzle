"""Tests for the fuzzer campaign runner."""

from pathlib import Path

from dazzle.testing.fuzzer import run_campaign
from dazzle.testing.fuzzer.oracle import Classification


class TestCampaign:
    def test_mutation_campaign_produces_results(self) -> None:
        """Run a small mutation-only campaign against the example corpus."""
        examples_dir = Path(__file__).resolve().parents[2] / "examples"
        results = run_campaign(
            examples_dir=examples_dir,
            layers=["mutate"],
            samples_per_layer=10,
        )
        assert len(results) > 0
        for r in results:
            assert r.classification in Classification

    def test_mutation_campaign_no_hangs(self) -> None:
        """No mutation of valid DSL should cause a parser hang."""
        examples_dir = Path(__file__).resolve().parents[2] / "examples"
        results = run_campaign(
            examples_dir=examples_dir,
            layers=["mutate"],
            samples_per_layer=20,
        )
        hangs = [r for r in results if r.classification == Classification.HANG]
        assert len(hangs) == 0, f"Found {len(hangs)} hangs: {[h.dsl_input[:80] for h in hangs]}"

    def test_dry_run_returns_inputs_without_classifying(self) -> None:
        examples_dir = Path(__file__).resolve().parents[2] / "examples"
        inputs = run_campaign(
            examples_dir=examples_dir,
            layers=["mutate"],
            samples_per_layer=5,
            dry_run=True,
        )
        assert len(inputs) > 0
