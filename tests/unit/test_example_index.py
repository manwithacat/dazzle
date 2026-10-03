"""Tests for the example index builder."""

from pathlib import Path

import pytest

from dazzle.core.discovery.example_index import build_example_index

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EXAMPLES_DIR = Path(__file__).parent.parent.parent / "examples"
# component_showcase was reclassified examples/ → fixtures/ (2026-06-13 guides
# Phase 0); the index builder still validates it at its new home.
FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures"
COMPONENT_SHOWCASE = FIXTURES_DIR / "component_showcase"

_has_component_showcase = (
    COMPONENT_SHOWCASE.is_dir() and (COMPONENT_SHOWCASE / "dazzle.toml").exists()
)


# ---------------------------------------------------------------------------
# Tests against component_showcase (skip if not available)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _has_component_showcase, reason="component_showcase not available")
class TestComponentShowcase:
    def test_widget_rich_text_indexed(self):
        index = build_example_index(FIXTURES_DIR)
        assert "widget_rich_text" in index
        refs = index["widget_rich_text"]
        assert len(refs) > 0
        app_names = {r.app for r in refs}
        assert "component_showcase" in app_names

    def test_widget_picker_indexed(self):
        index = build_example_index(FIXTURES_DIR)
        assert "widget_picker" in index
        refs = index["widget_picker"]
        assert len(refs) > 0
        app_names = {r.app for r in refs}
        assert "component_showcase" in app_names

    def test_example_ref_names_the_usage_it_points_at(self):
        """A ref is checkable without a line number (#1755).

        It used to carry `file`/`line` resolved by scanning the app's DSL for
        the *first* line containing the capability's option value, so every
        field using it was cited at the same unrelated line. What makes a ref
        verifiable now is its context: it names the field and the surface.
        """
        index = build_example_index(FIXTURES_DIR)
        assert "widget_rich_text" in index
        refs = [r for r in index["widget_rich_text"] if r.app == "component_showcase"]
        assert refs
        for ref in refs:
            assert ref.context != ""
            assert "widget=rich_text" in ref.context

    def test_index_holds_no_duplicate_usages(self):
        """One ref per place a capability is used. The fan-out was the payload
        bug in #1755: 416 exemplar rows on fieldtest_hub for 18 usages."""
        index = build_example_index(EXAMPLES_DIR)
        for cap_key, refs in index.items():
            usages = [(r.app, r.context) for r in refs]
            assert len(usages) == len(set(usages)), f"{cap_key} indexes a usage twice"

    def test_layout_kanban_indexed(self):
        index = build_example_index(FIXTURES_DIR)
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
