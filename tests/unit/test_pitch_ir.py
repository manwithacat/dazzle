"""Tests for PitchSpec IR models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from dazzle.pitch.ir import (
    BrandColors,
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
    create_default_pitchspec,
)


class TestCompanySpec:
    def test_defaults(self):
        c = CompanySpec(name="Test")
        assert c.name == "Test"
        assert c.stage == FundingStage.PRE_SEED
        assert c.currency == "GBP"
        assert c.funding_ask is None

    def test_frozen(self):
        c = CompanySpec(name="Test")
        with pytest.raises(ValidationError):
            c.name = "Changed"  # type: ignore[misc]


class TestPitchSpec:
    def test_minimal(self):
        spec = PitchSpec()
        assert spec.version == 1
        assert spec.company.name == "My App"
        assert spec.problem is None
        assert spec.competitors == []

    def test_full(self):
        spec = PitchSpec(
            company=CompanySpec(name="Acme", funding_ask=500000),
            problem=ProblemSpec(headline="Big problem", points=["p1"]),
            solution=SolutionSpec(headline="Our fix"),
            market=MarketSpec(
                tam=MarketSize(value=10_000_000_000, label="TAM"),
            ),
            business_model=BusinessModelSpec(tiers=[PricingTier(name="Pro", price=49)]),
            financials=FinancialsSpec(
                projections=[YearProjection(year=2025, revenue=100000)],
                use_of_funds=[FundAllocation(category="Eng", percent=100)],
            ),
            team=TeamSpec(
                founders=[TeamMember(name="Alice", role="CEO")],
            ),
            competitors=[Competitor(name="BigCo")],
            milestones=MilestonesSpec(completed=["MVP"]),
        )
        assert spec.company.name == "Acme"
        assert spec.problem is not None
        assert len(spec.competitors) == 1

    def test_serialization_roundtrip(self):
        spec = PitchSpec(
            company=CompanySpec(name="Test", stage=FundingStage.SEED),
        )
        data = spec.model_dump(mode="json")
        assert data["company"]["name"] == "Test"
        assert data["company"]["stage"] == "seed"

    def test_create_default(self):
        spec = create_default_pitchspec(name="MyApp", tagline="Build fast")
        assert spec.company.name == "MyApp"
        assert spec.company.tagline == "Build fast"
        assert spec.brand.primary == "#0F1A2E"


class TestBrandColors:
    def test_defaults(self):
        b = BrandColors()
        assert b.primary == "#0F1A2E"
        assert b.accent == "#2E86AB"


class TestMarketSpec:
    def test_with_sizes(self):
        m = MarketSpec(
            tam=MarketSize(value=10_000_000_000, label="TAM"),
            sam=MarketSize(value=1_000_000_000, label="SAM"),
            som=MarketSize(value=50_000_000, label="SOM"),
        )
        assert m.tam is not None
        assert m.tam.value == 10_000_000_000
