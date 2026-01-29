"""Tests for PitchSpec IR models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from dazzle.pitch.ir import (
    BrandColors,
    BusinessModelSpec,
    CompanySpec,
    Competitor,
    ExtraSlide,
    ExtraSlideLayout,
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

    def test_font_family_default(self):
        b = BrandColors()
        assert b.font_family == "Calibri"

    def test_font_family_custom(self):
        b = BrandColors(font_family="Arial")
        assert b.font_family == "Arial"


class TestExtraSlide:
    def test_defaults(self):
        es = ExtraSlide(title="Demo")
        assert es.layout == ExtraSlideLayout.BULLETS
        assert es.items == []
        assert es.speaker_notes is None
        assert es.image_path is None

    def test_stats_layout(self):
        es = ExtraSlide(
            title="Key Metrics",
            layout=ExtraSlideLayout.STATS,
            items=["100|Users", "50K|Revenue"],
        )
        assert es.layout == ExtraSlideLayout.STATS
        assert len(es.items) == 2

    def test_image_layout(self):
        es = ExtraSlide(
            title="Screenshot",
            layout=ExtraSlideLayout.IMAGE,
            image_path="assets/screenshot.png",
        )
        assert es.image_path == "assets/screenshot.png"

    def test_theme_default(self):
        es = ExtraSlide(title="Demo")
        assert es.theme == "dark"

    def test_theme_light(self):
        es = ExtraSlide(title="Demo", theme="light")
        assert es.theme == "light"

    def test_table_layout(self):
        es = ExtraSlide(
            title="Data",
            layout=ExtraSlideLayout.TABLE,
            items=["A|B|C", "1|2|3"],
        )
        assert es.layout == ExtraSlideLayout.TABLE

    def test_callout_layout(self):
        es = ExtraSlide(
            title="Quote",
            layout=ExtraSlideLayout.CALLOUT,
            items=["Big statement", "Supporting point"],
        )
        assert es.layout == ExtraSlideLayout.CALLOUT


class TestSpeakerNotes:
    def test_company_speaker_notes(self):
        c = CompanySpec(name="Test", speaker_notes="Welcome everyone")
        assert c.speaker_notes == "Welcome everyone"

    def test_problem_speaker_notes(self):
        p = ProblemSpec(headline="Big problem", speaker_notes="Key talking point")
        assert p.speaker_notes == "Key talking point"

    def test_solution_speaker_notes(self):
        s = SolutionSpec(headline="Fix", speaker_notes="Demo this")
        assert s.speaker_notes == "Demo this"

    def test_market_speaker_notes(self):
        m = MarketSpec(speaker_notes="Cite sources")
        assert m.speaker_notes == "Cite sources"

    def test_business_model_speaker_notes(self):
        bm = BusinessModelSpec(speaker_notes="Focus on Pro tier")
        assert bm.speaker_notes == "Focus on Pro tier"

    def test_financials_speaker_notes(self):
        f = FinancialsSpec(speaker_notes="Conservative estimates")
        assert f.speaker_notes == "Conservative estimates"

    def test_team_speaker_notes(self):
        t = TeamSpec(speaker_notes="Highlight experience")
        assert t.speaker_notes == "Highlight experience"

    def test_milestones_speaker_notes(self):
        m = MilestonesSpec(speaker_notes="On track")
        assert m.speaker_notes == "On track"


class TestPitchSpecNewFields:
    def test_extra_slides(self):
        spec = PitchSpec(
            extra_slides=[
                ExtraSlide(title="Case Study", items=["Great result"]),
            ]
        )
        assert len(spec.extra_slides) == 1
        assert spec.extra_slides[0].title == "Case Study"

    def test_slide_order(self):
        spec = PitchSpec(slide_order=["title", "problem", "closing"])
        assert spec.slide_order == ["title", "problem", "closing"]

    def test_logo_path(self):
        c = CompanySpec(name="Test", logo_path="assets/logo.png")
        assert c.logo_path == "assets/logo.png"

    def test_defaults_unchanged(self):
        spec = PitchSpec()
        assert spec.extra_slides == []
        assert spec.slide_order is None


class TestMarketSpec:
    def test_with_sizes(self):
        m = MarketSpec(
            tam=MarketSize(value=10_000_000_000, label="TAM"),
            sam=MarketSize(value=1_000_000_000, label="SAM"),
            som=MarketSize(value=50_000_000, label="SOM"),
        )
        assert m.tam is not None
        assert m.tam.value == 10_000_000_000
