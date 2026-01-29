"""Tests for PitchSpec loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.pitch.ir import (
    CompanySpec,
    ExtraSlide,
    ExtraSlideLayout,
    FundingStage,
    PitchSpec,
    ProblemSpec,
)
from dazzle.pitch.loader import (
    PitchSpecError,
    load_pitchspec,
    pitchspec_exists,
    save_pitchspec,
    scaffold_pitchspec,
    validate_pitchspec,
)


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    return tmp_path


class TestLoadSave:
    def test_save_and_load_roundtrip(self, tmp_project: Path):
        spec = PitchSpec(
            company=CompanySpec(name="RoundTrip", stage=FundingStage.SEED),
            problem=ProblemSpec(headline="Test problem", points=["p1", "p2"]),
        )
        save_pitchspec(tmp_project, spec)
        assert pitchspec_exists(tmp_project)

        loaded = load_pitchspec(tmp_project)
        assert loaded.company.name == "RoundTrip"
        assert loaded.company.stage == FundingStage.SEED
        assert loaded.problem is not None
        assert loaded.problem.headline == "Test problem"
        assert len(loaded.problem.points) == 2

    def test_load_missing_file(self, tmp_project: Path):
        with pytest.raises(PitchSpecError, match="not found"):
            load_pitchspec(tmp_project)

    def test_load_empty_file(self, tmp_project: Path):
        (tmp_project / "pitchspec.yaml").write_text("")
        with pytest.raises(PitchSpecError, match="Empty"):
            load_pitchspec(tmp_project)

    def test_load_invalid_yaml(self, tmp_project: Path):
        (tmp_project / "pitchspec.yaml").write_text(":::bad yaml")
        with pytest.raises(PitchSpecError):
            load_pitchspec(tmp_project)


class TestScaffold:
    def test_scaffold_creates_file(self, tmp_project: Path):
        result = scaffold_pitchspec(tmp_project)
        assert result is not None
        assert result.exists()
        content = result.read_text()
        assert "company:" in content
        assert "problem:" in content

    def test_scaffold_no_overwrite(self, tmp_project: Path):
        scaffold_pitchspec(tmp_project)
        result = scaffold_pitchspec(tmp_project, overwrite=False)
        assert result is None

    def test_scaffold_overwrite(self, tmp_project: Path):
        scaffold_pitchspec(tmp_project)
        result = scaffold_pitchspec(tmp_project, overwrite=True)
        assert result is not None

    def test_scaffold_roundtrip(self, tmp_project: Path):
        """Scaffolded YAML should be loadable."""
        scaffold_pitchspec(tmp_project)
        spec = load_pitchspec(tmp_project)
        assert spec.company.name == "My App"


class TestValidation:
    def test_valid_spec(self):
        spec = PitchSpec(
            company=CompanySpec(name="ValidCo", funding_ask=500000),
        )
        result = validate_pitchspec(spec)
        assert result.is_valid

    def test_negative_funding(self):
        spec = PitchSpec(
            company=CompanySpec(name="Bad", funding_ask=-1),
        )
        result = validate_pitchspec(spec)
        assert not result.is_valid
        assert any("positive" in e for e in result.errors)

    def test_fund_allocation_warning(self):
        from dazzle.pitch.ir import FinancialsSpec, FundAllocation

        spec = PitchSpec(
            company=CompanySpec(name="Test"),
            financials=FinancialsSpec(
                use_of_funds=[
                    FundAllocation(category="Eng", percent=50),
                    FundAllocation(category="Sales", percent=30),
                ]
            ),
        )
        result = validate_pitchspec(spec)
        assert any("80%" in w for w in result.warnings)

    def test_default_name_warning(self):
        spec = PitchSpec()
        result = validate_pitchspec(spec)
        assert any("My App" in w for w in result.warnings)

    def test_invalid_slide_order_entry(self):
        spec = PitchSpec(slide_order=["title", "nonexistent", "closing"])
        result = validate_pitchspec(spec)
        assert any("nonexistent" in e for e in result.errors)

    def test_image_layout_missing_path(self):
        spec = PitchSpec(
            extra_slides=[
                ExtraSlide(title="Screenshot", layout=ExtraSlideLayout.IMAGE),
            ]
        )
        result = validate_pitchspec(spec)
        assert any("image_path" in e for e in result.errors)


class TestNewFieldsRoundTrip:
    def test_extra_slides_roundtrip(self, tmp_project: Path):
        spec = PitchSpec(
            company=CompanySpec(name="Test"),
            extra_slides=[
                ExtraSlide(
                    title="Case Study",
                    layout=ExtraSlideLayout.BULLETS,
                    items=["Item 1", "Item 2"],
                    speaker_notes="Talk about case study",
                ),
            ],
            slide_order=["title", "case_study", "closing"],
        )
        save_pitchspec(tmp_project, spec)
        loaded = load_pitchspec(tmp_project)
        assert len(loaded.extra_slides) == 1
        assert loaded.extra_slides[0].title == "Case Study"
        assert loaded.extra_slides[0].speaker_notes == "Talk about case study"
        assert loaded.slide_order == ["title", "case_study", "closing"]

    def test_speaker_notes_roundtrip(self, tmp_project: Path):
        spec = PitchSpec(
            company=CompanySpec(name="Test", speaker_notes="Welcome"),
            problem=ProblemSpec(headline="Problem", speaker_notes="Key point"),
        )
        save_pitchspec(tmp_project, spec)
        loaded = load_pitchspec(tmp_project)
        assert loaded.company.speaker_notes == "Welcome"
        assert loaded.problem is not None
        assert loaded.problem.speaker_notes == "Key point"


class TestReviewHandler:
    """Tests for the pitch review MCP handler."""

    def test_review_skeleton_spec(self, tmp_project: Path):
        """A default spec should be rated as skeleton/early_draft."""
        import json

        from dazzle.mcp.server.handlers.pitch import review_pitchspec_handler
        from dazzle.pitch.loader import save_pitchspec

        spec = PitchSpec()
        save_pitchspec(tmp_project, spec)

        result = json.loads(review_pitchspec_handler(tmp_project, {}))
        assert result["overall_assessment"] in ("skeleton", "early_draft")
        assert "problem" in result["section_scores"]
        assert result["section_scores"]["problem"] == "missing"
        assert len(result["suggestions"]) > 0
        assert len(result["next_steps"]) > 0
        assert "iteration_checklist" in result

    def test_review_complete_spec(self, tmp_project: Path):
        """A fully populated spec should score well."""
        import json

        from dazzle.mcp.server.handlers.pitch import review_pitchspec_handler
        from dazzle.pitch.ir import (
            BusinessModelSpec,
            FinancialsSpec,
            FundAllocation,
            MarketSize,
            MarketSpec,
            MilestonesSpec,
            PricingTier,
            SolutionSpec,
            TeamMember,
            TeamSpec,
            YearProjection,
        )
        from dazzle.pitch.loader import save_pitchspec

        spec = PitchSpec(
            company=CompanySpec(name="TestCo", tagline="We do things", funding_ask=1000000),
            problem=ProblemSpec(
                headline="Big problem",
                points=["p1", "p2", "p3"],
                market_failure=["Existing solutions fail"],
            ),
            solution=SolutionSpec(
                headline="Our solution",
                how_it_works=["Step 1", "Step 2"],
                value_props=["Fast", "Cheap"],
            ),
            market=MarketSpec(
                tam=MarketSize(value=1000000000, label="$1B"),
                sam=MarketSize(value=100000000, label="$100M"),
                som=MarketSize(value=10000000, label="$10M"),
                drivers=["Trend 1"],
            ),
            business_model=BusinessModelSpec(
                tiers=[
                    PricingTier(name="Free", price=0),
                    PricingTier(name="Pro", price=99),
                ],
            ),
            financials=FinancialsSpec(
                projections=[
                    YearProjection(year=2025, revenue=100000),
                    YearProjection(year=2026, revenue=500000),
                ],
                use_of_funds=[
                    FundAllocation(category="Eng", percent=60),
                    FundAllocation(category="Sales", percent=40),
                ],
            ),
            team=TeamSpec(
                founders=[
                    TeamMember(name="Alice", role="CEO", bio="10 years exp"),
                    TeamMember(name="Bob", role="CTO", bio="Ex-Google"),
                ],
            ),
            milestones=MilestonesSpec(
                completed=["MVP launched"],
                next_12_months=["Series A"],
            ),
        )
        save_pitchspec(tmp_project, spec)

        result = json.loads(review_pitchspec_handler(tmp_project, {}))
        assert result["overall_assessment"] == "investor_ready"
        assert result["completeness"] == "100%"

    def test_review_missing_file(self, tmp_project: Path):
        """Review should return error with next_steps when no pitchspec exists."""
        import json

        from dazzle.mcp.server.handlers.pitch import review_pitchspec_handler

        result = json.loads(review_pitchspec_handler(tmp_project, {}))
        assert "error" in result
        assert len(result["next_steps"]) > 0

    def test_scaffold_contains_new_examples(self, tmp_project: Path):
        scaffold_pitchspec(tmp_project, overwrite=True)
        content = (tmp_project / "pitchspec.yaml").read_text()
        assert "speaker_notes" in content
        assert "extra_slides" in content
        assert "slide_order" in content
        assert "logo_path" in content
