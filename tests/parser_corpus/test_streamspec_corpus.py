"""
StreamSpec (HLESS) corpus tests with snapshot regression testing.

Tests DSL → IR parsing stability for HLESS stream definitions.
Uses syrupy for snapshot comparison.
"""

from pathlib import Path

import pytest

from .harness import EmitMode, parse_streamspec_file

# Corpus directories
CORPUS_DIR = Path(__file__).parent.parent / "corpora" / "streamspec"


def get_valid_files() -> list[Path]:
    """Get all valid StreamSpec corpus files."""
    valid_dir = CORPUS_DIR / "valid"
    if not valid_dir.exists():
        return []
    return sorted(valid_dir.glob("*.dsl"))


def get_invalid_files() -> list[Path]:
    """Get all invalid StreamSpec corpus files."""
    invalid_dir = CORPUS_DIR / "invalid"
    if not invalid_dir.exists():
        return []
    return sorted(invalid_dir.glob("*.dsl"))


class TestValidStreamSpec:
    """Tests for valid StreamSpec corpus files."""

    @pytest.mark.corpus
    @pytest.mark.parametrize("dsl_file", get_valid_files(), ids=lambda p: p.stem)
    def test_valid_streamspec_parses_without_errors(self, dsl_file: Path):
        """Valid files must parse without errors."""
        result = parse_streamspec_file(dsl_file, EmitMode.IR)
        assert result["diagnostics"] == [], (
            f"Expected no diagnostics for valid file {dsl_file.name}, got: {result['diagnostics']}"
        )
        assert result["result"] is not None, f"Expected IR result for {dsl_file.name}"

    @pytest.mark.corpus
    @pytest.mark.parametrize("dsl_file", get_valid_files(), ids=lambda p: p.stem)
    def test_valid_streamspec_ir_snapshot(self, dsl_file: Path, snapshot):
        """Valid files must produce stable IR (snapshot test)."""
        result = parse_streamspec_file(dsl_file, EmitMode.IR)
        # Compare the full result structure against snapshot
        assert result == snapshot

    @pytest.mark.corpus
    @pytest.mark.parametrize("dsl_file", get_valid_files(), ids=lambda p: p.stem)
    def test_streams_have_valid_record_kind(self, dsl_file: Path):
        """All streams must have valid RecordKind."""
        result = parse_streamspec_file(dsl_file, EmitMode.IR)
        if result["result"] and result["result"]["streams"]:
            for stream in result["result"]["streams"]:
                assert "record_kind" in stream, f"Stream missing record_kind in {dsl_file.name}"
                assert stream["record_kind"] in ["intent", "fact", "observation", "derivation"], (
                    f"Invalid record_kind '{stream['record_kind']}' in {dsl_file.name}"
                )


class TestInvalidStreamSpec:
    """Tests for invalid StreamSpec corpus files."""

    @pytest.mark.corpus
    @pytest.mark.parametrize("dsl_file", get_invalid_files(), ids=lambda p: p.stem)
    def test_invalid_streamspec_produces_errors(self, dsl_file: Path):
        """Invalid files must produce at least one error."""
        result = parse_streamspec_file(dsl_file, EmitMode.DIAG)
        assert len(result["diagnostics"]) > 0, (
            f"Expected errors for invalid file {dsl_file.name}, got none"
        )

    @pytest.mark.corpus
    @pytest.mark.parametrize("dsl_file", get_invalid_files(), ids=lambda p: p.stem)
    def test_invalid_streamspec_diagnostics_snapshot(self, dsl_file: Path, snapshot):
        """Invalid files must produce expected diagnostics (snapshot test)."""
        result = parse_streamspec_file(dsl_file, EmitMode.DIAG)
        # Compare diagnostics against snapshot
        assert result == snapshot


class TestStreamSpecDeterminism:
    """Tests for parsing determinism."""

    @pytest.mark.corpus
    @pytest.mark.parametrize("dsl_file", get_valid_files(), ids=lambda p: p.stem)
    def test_parsing_is_deterministic(self, dsl_file: Path):
        """Parsing the same file twice must produce identical results."""
        result1 = parse_streamspec_file(dsl_file, EmitMode.IR)
        result2 = parse_streamspec_file(dsl_file, EmitMode.IR)
        assert result1 == result2, f"Non-deterministic parsing for {dsl_file.name}"
