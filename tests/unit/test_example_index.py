"""Tests for the example index builder."""

from pathlib import Path

import pytest

from dazzle.core.discovery.example_index import build_example_index

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EXAMPLES_DIR = Path(__file__).parent.parent.parent / "examples"
COMPONENT_SHOWCASE = EXAMPLES_DIR / "component_showcase"

_has_component_showcase = (
    COMPONENT_SHOWCASE.is_dir() and (COMPONENT_SHOWCASE / "dazzle.toml").exists()
)


# ---------------------------------------------------------------------------
# Tests against component_showcase (skip if not available)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _has_component_showcase, reason="component_showcase not available")
class TestComponentShowcase:
    def test_widget_rich_text_indexed(self):
        index = build_example_index(EXAMPLES_DIR)
        assert "widget_rich_text" in index
        refs = index["widget_rich_text"]
        assert len(refs) > 0
        app_names = {r.app for r in refs}
        assert "component_showcase" in app_names

    def test_widget_picker_indexed(self):
        index = build_example_index(EXAMPLES_DIR)
        assert "widget_picker" in index
        refs = index["widget_picker"]
        assert len(refs) > 0
        app_names = {r.app for r in refs}
        assert "component_showcase" in app_names

    def test_example_ref_has_positive_line(self):
        index = build_example_index(EXAMPLES_DIR)
        assert "widget_rich_text" in index
        for ref in index["widget_rich_text"]:
            if ref.app == "component_showcase":
                assert ref.line > 0
                assert ref.file != ""
                assert ref.context != ""
                break

    def test_layout_kanban_indexed(self):
        index = build_example_index(EXAMPLES_DIR)
        assert "layout_kanban" in index
        refs = index["layout_kanban"]
        assert len(refs) > 0
        app_names = {r.app for r in refs}
        assert "component_showcase" in app_names


# ---------------------------------------------------------------------------
# Edge cases — no real parsing required
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_dir_returns_empty_index(self, tmp_path: Path):
        result = build_example_index(tmp_path)
        assert result == {}

    def test_nonexistent_dir_returns_empty_index(self, tmp_path: Path):
        result = build_example_index(tmp_path / "does_not_exist")
        assert result == {}

    def test_dir_with_no_dazzle_toml_returns_empty_index(self, tmp_path: Path):
        # A directory that has a sub-folder but no dazzle.toml
        (tmp_path / "my_app").mkdir()
        (tmp_path / "my_app" / "dsl").mkdir()
        result = build_example_index(tmp_path)
        assert result == {}
