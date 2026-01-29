"""Tests for PitchSpec loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.pitch.ir import CompanySpec, FundingStage, PitchSpec, ProblemSpec
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
