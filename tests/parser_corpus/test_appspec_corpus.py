"""
AppSpec corpus tests with snapshot regression testing.

Tests DSL → IR parsing stability for the main AppSpec language.
Uses syrupy for snapshot comparison.
"""

from pathlib import Path

import pytest

from .harness import EmitMode, parse_corpus_file

# Corpus directories
CORPUS_DIR = Path(__file__).parent.parent / "corpora" / "appspec"


def get_valid_files() -> list[Path]:
    """Get all valid AppSpec corpus files."""
    valid_dir = CORPUS_DIR / "valid"
    if not valid_dir.exists():
        return []
    return sorted(valid_dir.glob("*.dsl"))


def get_invalid_files() -> list[Path]:
    """Get all invalid AppSpec corpus files."""
    invalid_dir = CORPUS_DIR / "invalid"
    if not invalid_dir.exists():
        return []
    return sorted(invalid_dir.glob("*.dsl"))


class TestValidAppSpec:
    """Tests for valid AppSpec corpus files."""

    @pytest.mark.corpus
    @pytest.mark.parametrize("dsl_file", get_valid_files(), ids=lambda p: p.stem)
    def test_valid_appspec_parses_without_errors(self, dsl_file: Path):
        """Valid files must parse without errors."""
        result = parse_corpus_file(dsl_file, EmitMode.IR)
        assert result["diagnostics"] == [], (
            f"Expected no diagnostics for valid file {dsl_file.name}, "
            f"got: {result['diagnostics']}"
        )
        assert result["result"] is not None, f"Expected IR result for {dsl_file.name}"

    @pytest.mark.corpus
    @pytest.mark.parametrize("dsl_file", get_valid_files(), ids=lambda p: p.stem)
    def test_valid_appspec_ir_snapshot(self, dsl_file: Path, snapshot):
        """Valid files must produce stable IR (snapshot test)."""
        result = parse_corpus_file(dsl_file, EmitMode.IR)
        # Compare the full result structure against snapshot
        assert result == snapshot


class TestInvalidAppSpec:
    """Tests for invalid AppSpec corpus files."""

    @pytest.mark.corpus
    @pytest.mark.parametrize("dsl_file", get_invalid_files(), ids=lambda p: p.stem)
    def test_invalid_appspec_produces_errors(self, dsl_file: Path):
        """Invalid files must produce at least one error."""
        result = parse_corpus_file(dsl_file, EmitMode.DIAG)
        assert len(result["diagnostics"]) > 0, (
            f"Expected errors for invalid file {dsl_file.name}, got none"
        )

    @pytest.mark.corpus
    @pytest.mark.parametrize("dsl_file", get_invalid_files(), ids=lambda p: p.stem)
    def test_invalid_appspec_diagnostics_snapshot(self, dsl_file: Path, snapshot):
        """Invalid files must produce expected diagnostics (snapshot test)."""
        result = parse_corpus_file(dsl_file, EmitMode.DIAG)
        # Compare diagnostics against snapshot
        assert result == snapshot


class TestAppSpecDeterminism:
    """Tests for parsing determinism."""

    @pytest.mark.corpus
    @pytest.mark.parametrize("dsl_file", get_valid_files(), ids=lambda p: p.stem)
    def test_parsing_is_deterministic(self, dsl_file: Path):
        """Parsing the same file twice must produce identical results."""
        result1 = parse_corpus_file(dsl_file, EmitMode.IR)
        result2 = parse_corpus_file(dsl_file, EmitMode.IR)
        assert result1 == result2, f"Non-deterministic parsing for {dsl_file.name}"
