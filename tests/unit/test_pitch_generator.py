"""Tests for pitch deck generators."""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.pitch.extractor import PitchContext
from dazzle.pitch.ir import (
    BusinessModelSpec,
    CompanySpec,
    Competitor,
    FinancialsSpec,
    FundAllocation,
    FundingStage,
    MarketSize,
    MarketSpec,
    MilestonesSpec,
    PitchSpec,
    PricingTier,
    ProblemSpec,
    SolutionSpec,
    TeamMember,
    TeamSpec,
    YearProjection,
)


def _make_full_context() -> PitchContext:
    """Create a fully-populated PitchContext for testing."""
    spec = PitchSpec(
        company=CompanySpec(
            name="TestCo",
            tagline="Testing pitch generation",
            stage=FundingStage.SEED,
            funding_ask=500000,
            runway_months=18,
        ),
        problem=ProblemSpec(
            headline="Testing is hard",
            points=["Point 1", "Point 2"],
            market_failure=["No good tools"],
        ),
        solution=SolutionSpec(
            headline="We make it easy",
            how_it_works=["Step 1", "Step 2"],
            value_props=["Fast", "Reliable"],
        ),
        market=MarketSpec(
            tam=MarketSize(value=10_000_000_000, label="TAM"),
            sam=MarketSize(value=1_000_000_000, label="SAM"),
            som=MarketSize(value=50_000_000, label="SOM"),
        ),
        business_model=BusinessModelSpec(
            tiers=[
                PricingTier(name="Free", price=0),
                PricingTier(name="Pro", price=49, highlighted=True),
            ]
        ),
        financials=FinancialsSpec(
            projections=[
                YearProjection(year=2025, customers=100, revenue=50000, costs=200000),
                YearProjection(year=2026, customers=500, revenue=300000, costs=350000),
            ],
            use_of_funds=[
                FundAllocation(category="Eng", percent=60),
                FundAllocation(category="Sales", percent=40),
            ],
        ),
        team=TeamSpec(
            founders=[TeamMember(name="Alice", role="CEO", bio="Expert")],
        ),
        competitors=[Competitor(name="BigCo", strength="Large", weakness="Slow")],
        milestones=MilestonesSpec(
            completed=["MVP"],
            next_12_months=["Launch"],
        ),
    )
    ctx = PitchContext(
        spec=spec,
        entities=["Task", "Project"],
        surfaces=["task_list", "project_detail"],
        personas=[{"id": "admin", "label": "Admin", "description": "System admin"}],
    )
    return ctx


class TestPptxGenerator:
    def test_generate_pptx(self, tmp_path: Path):
        """Test PPTX generation with full context."""
        try:
            import pptx  # noqa: F401
        except ImportError:
            pytest.skip("python-pptx not installed")

        from dazzle.pitch.generators.pptx_gen import generate_pptx

        ctx = _make_full_context()
        output = tmp_path / "test_deck.pptx"
        result = generate_pptx(ctx, output)

        assert result.success
        assert result.output_path == output
        assert output.exists()
        assert result.slide_count > 0

    def test_generate_pptx_minimal(self, tmp_path: Path):
        """Test PPTX generation with minimal context."""
        try:
            import pptx  # noqa: F401
        except ImportError:
            pytest.skip("python-pptx not installed")

        from dazzle.pitch.generators.pptx_gen import generate_pptx

        spec = PitchSpec()
        ctx = PitchContext(spec=spec)
        output = tmp_path / "minimal.pptx"
        result = generate_pptx(ctx, output)

        assert result.success
        # Should have at least title + closing
        assert result.slide_count >= 2

    def test_fmt_currency(self):
        from dazzle.pitch.generators.pptx_gen import _fmt_currency

        assert _fmt_currency(500000, "GBP") == "£500K"
        assert _fmt_currency(1500000, "USD") == "$1.5M"
        assert _fmt_currency(10_000_000_000, "EUR") == "€10.0B"
        assert _fmt_currency(42, "GBP") == "£42"


class TestNarrativeGenerator:
    def test_generate_narrative(self, tmp_path: Path):
        from dazzle.pitch.generators.narrative import generate_narrative

        ctx = _make_full_context()
        output = tmp_path / "narrative.md"
        result = generate_narrative(ctx, output)

        assert result.success
        assert output.exists()
        content = output.read_text()
        assert "TestCo" in content
        assert "Testing is hard" in content
        assert "Market Opportunity" in content

    def test_generate_narrative_minimal(self, tmp_path: Path):
        from dazzle.pitch.generators.narrative import generate_narrative

        spec = PitchSpec()
        ctx = PitchContext(spec=spec)
        output = tmp_path / "minimal.md"
        result = generate_narrative(ctx, output)

        assert result.success
        assert output.exists()
