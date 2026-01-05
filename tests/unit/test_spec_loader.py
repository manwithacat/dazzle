"""
Unit tests for flexible spec loading.

Tests loading from:
- spec/ directory with multiple files
- SPEC.md single file
- Nested directories within spec/
"""

from __future__ import annotations

from pathlib import Path

from dazzle.core.spec_loader import SpecContent, get_spec_summary, load_spec


class TestSpecContent:
    """Test SpecContent dataclass."""

    def test_is_empty_with_content(self) -> None:
        """Should not be empty when content exists."""
        spec = SpecContent(content="# My Spec", source_files=[], source_type="single_file")
        assert spec.is_empty is False

    def test_is_empty_without_content(self) -> None:
        """Should be empty when no content."""
        spec = SpecContent(content="", source_files=[], source_type="none")
        assert spec.is_empty is True

    def test_is_empty_with_whitespace(self) -> None:
        """Should be empty when only whitespace."""
        spec = SpecContent(content="   \n\t  ", source_files=[], source_type="none")
        assert spec.is_empty is True

    def test_file_count(self) -> None:
        """Should return correct file count."""
        spec = SpecContent(
            content="content",
            source_files=[Path("a.md"), Path("b.md"), Path("c.md")],
            source_type="directory",
        )
        assert spec.file_count == 3


class TestLoadSpecFromDirectory:
    """Test loading from spec/ directory."""

    def test_load_from_spec_directory(self, tmp_path: Path) -> None:
        """Should load all markdown files from spec/ directory."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        (spec_dir / "01-overview.md").write_text("# Overview\nThis is the overview.")
        (spec_dir / "02-features.md").write_text("# Features\nList of features.")

        result = load_spec(tmp_path)

        assert result.source_type == "directory"
        assert result.file_count == 2
        assert "Overview" in result.content
        assert "Features" in result.content
        assert result.is_empty is False

    def test_load_from_nested_directories(self, tmp_path: Path) -> None:
        """Should load markdown files from nested directories."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        features_dir = spec_dir / "features"
        features_dir.mkdir()

        (spec_dir / "overview.md").write_text("# Overview")
        (features_dir / "auth.md").write_text("# Authentication")
        (features_dir / "payments.md").write_text("# Payments")

        result = load_spec(tmp_path)

        assert result.source_type == "directory"
        assert result.file_count == 3
        assert "Overview" in result.content
        assert "Authentication" in result.content
        assert "Payments" in result.content

    def test_alphabetical_sorting(self, tmp_path: Path) -> None:
        """Files should be sorted alphabetically."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        (spec_dir / "z-last.md").write_text("# Last")
        (spec_dir / "a-first.md").write_text("# First")
        (spec_dir / "m-middle.md").write_text("# Middle")

        result = load_spec(tmp_path)

        # Content should be in alphabetical order
        first_pos = result.content.find("# First")
        middle_pos = result.content.find("# Middle")
        last_pos = result.content.find("# Last")

        assert first_pos < middle_pos < last_pos

    def test_source_markers_included(self, tmp_path: Path) -> None:
        """Should include source file markers by default."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        (spec_dir / "test.md").write_text("# Test")

        result = load_spec(tmp_path, include_sources=True)

        assert "<!-- Source: spec/test.md -->" in result.content

    def test_source_markers_excluded(self, tmp_path: Path) -> None:
        """Should exclude source markers when requested."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        (spec_dir / "test.md").write_text("# Test")

        result = load_spec(tmp_path, include_sources=False)

        assert "<!-- Source:" not in result.content

    def test_empty_spec_directory(self, tmp_path: Path) -> None:
        """Should handle empty spec directory gracefully."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        result = load_spec(tmp_path)

        assert result.source_type == "directory"
        assert result.file_count == 0
        assert result.is_empty is True

    def test_ignores_non_markdown_files(self, tmp_path: Path) -> None:
        """Should only load .md files."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()

        (spec_dir / "readme.md").write_text("# Readme")
        (spec_dir / "notes.txt").write_text("Some notes")
        (spec_dir / "data.json").write_text('{"key": "value"}')

        result = load_spec(tmp_path)

        assert result.file_count == 1
        assert "Readme" in result.content
        assert "Some notes" not in result.content


class TestLoadSpecFromFile:
    """Test loading from SPEC.md single file."""

    def test_load_from_spec_md(self, tmp_path: Path) -> None:
        """Should load from SPEC.md file."""
        spec_file = tmp_path / "SPEC.md"
        spec_file.write_text("# Product Spec\nThis is my product.")

        result = load_spec(tmp_path)

        assert result.source_type == "single_file"
        assert result.file_count == 1
        assert "Product Spec" in result.content
        assert result.is_empty is False

    def test_source_marker_for_single_file(self, tmp_path: Path) -> None:
        """Should include source marker for single file."""
        spec_file = tmp_path / "SPEC.md"
        spec_file.write_text("# Test")

        result = load_spec(tmp_path, include_sources=True)

        assert "<!-- Source: SPEC.md -->" in result.content


class TestLoadSpecPriority:
    """Test loading priority between spec/ and SPEC.md."""

    def test_directory_takes_priority(self, tmp_path: Path) -> None:
        """spec/ directory should take priority over SPEC.md."""
        # Create both
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        (spec_dir / "from-dir.md").write_text("# From Directory")

        spec_file = tmp_path / "SPEC.md"
        spec_file.write_text("# From Single File")

        result = load_spec(tmp_path)

        assert result.source_type == "directory"
        assert "From Directory" in result.content
        assert "From Single File" not in result.content

    def test_fallback_to_spec_md(self, tmp_path: Path) -> None:
        """Should fall back to SPEC.md when no spec/ directory."""
        spec_file = tmp_path / "SPEC.md"
        spec_file.write_text("# Fallback Spec")

        result = load_spec(tmp_path)

        assert result.source_type == "single_file"
        assert "Fallback Spec" in result.content

    def test_no_spec_found(self, tmp_path: Path) -> None:
        """Should return empty when no spec exists."""
        result = load_spec(tmp_path)

        assert result.source_type == "none"
        assert result.is_empty is True
        assert result.file_count == 0


class TestGetSpecSummary:
    """Test get_spec_summary function."""

    def test_summary_for_directory(self, tmp_path: Path) -> None:
        """Should return summary for spec directory."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        (spec_dir / "a.md").write_text("# A")
        (spec_dir / "b.md").write_text("# B")

        summary = get_spec_summary(tmp_path)

        assert summary["source_type"] == "directory"
        assert summary["file_count"] == 2
        assert "spec/a.md" in summary["file_paths"]
        assert "spec/b.md" in summary["file_paths"]

    def test_summary_for_single_file(self, tmp_path: Path) -> None:
        """Should return summary for SPEC.md."""
        (tmp_path / "SPEC.md").write_text("# Spec")

        summary = get_spec_summary(tmp_path)

        assert summary["source_type"] == "single_file"
        assert summary["file_count"] == 1
        assert summary["file_paths"] == ["SPEC.md"]

    def test_summary_for_no_spec(self, tmp_path: Path) -> None:
        """Should return empty summary when no spec."""
        summary = get_spec_summary(tmp_path)

        assert summary["source_type"] == "none"
        assert summary["file_count"] == 0
        assert summary["file_paths"] == []
