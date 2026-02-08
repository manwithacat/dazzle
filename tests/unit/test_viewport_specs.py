"""Tests for custom viewport spec persistence."""

from __future__ import annotations

import json
from pathlib import Path

from dazzle.testing.viewport import ComponentPattern, ViewportAssertion
from dazzle.testing.viewport_specs import (
    ViewportAssertionEntry,
    ViewportSpecEntry,
    ViewportSpecsContainer,
    convert_to_patterns,
    load_custom_viewport_specs,
    merge_patterns,
    save_custom_viewport_specs,
)


def _make_spec_entry(
    name: str = "custom_grid",
    page_path: str = "/dashboard",
) -> ViewportSpecEntry:
    return ViewportSpecEntry(
        name=name,
        page_path=page_path,
        assertions=[
            ViewportAssertionEntry(
                selector=".custom-grid",
                property="display",
                expected="grid",
                viewport="desktop",
                description="Custom grid on desktop",
            ),
        ],
    )


class TestLoadSaveRoundtrip:
    """Tests for load/save roundtrip."""

    def test_save_and_load_dsl(self, tmp_path: Path) -> None:
        specs = [_make_spec_entry()]
        path = save_custom_viewport_specs(tmp_path, specs, to_dsl=True)
        assert path.exists()
        loaded = load_custom_viewport_specs(tmp_path)
        assert len(loaded) == 1
        assert loaded[0].name == "custom_grid"

    def test_save_and_load_runtime(self, tmp_path: Path) -> None:
        specs = [_make_spec_entry()]
        path = save_custom_viewport_specs(tmp_path, specs, to_dsl=False)
        assert ".dazzle" in str(path)
        loaded = load_custom_viewport_specs(tmp_path)
        assert len(loaded) == 1

    def test_load_empty_project(self, tmp_path: Path) -> None:
        loaded = load_custom_viewport_specs(tmp_path)
        assert loaded == []

    def test_dsl_location_takes_priority(self, tmp_path: Path) -> None:
        save_custom_viewport_specs(tmp_path, [_make_spec_entry("runtime")], to_dsl=False)
        save_custom_viewport_specs(tmp_path, [_make_spec_entry("dsl")], to_dsl=True)
        loaded = load_custom_viewport_specs(tmp_path)
        assert len(loaded) == 1
        assert loaded[0].name == "dsl"

    def test_multiple_specs(self, tmp_path: Path) -> None:
        specs = [_make_spec_entry("spec1"), _make_spec_entry("spec2", "/settings")]
        save_custom_viewport_specs(tmp_path, specs)
        loaded = load_custom_viewport_specs(tmp_path)
        assert len(loaded) == 2


class TestConvertToPatterns:
    """Tests for convert_to_patterns()."""

    def test_basic_conversion(self) -> None:
        specs = [_make_spec_entry()]
        patterns = convert_to_patterns(specs)
        assert "/dashboard" in patterns
        assert len(patterns["/dashboard"]) == 1
        assert patterns["/dashboard"][0].name == "custom_grid"

    def test_multiple_pages(self) -> None:
        specs = [
            _make_spec_entry("grid1", "/page1"),
            _make_spec_entry("grid2", "/page2"),
        ]
        patterns = convert_to_patterns(specs)
        assert "/page1" in patterns
        assert "/page2" in patterns

    def test_same_page_groups(self) -> None:
        specs = [
            _make_spec_entry("grid1", "/page"),
            _make_spec_entry("grid2", "/page"),
        ]
        patterns = convert_to_patterns(specs)
        assert len(patterns["/page"]) == 2


class TestMergePatterns:
    """Tests for merge_patterns()."""

    def test_merge_no_overlap(self) -> None:
        derived = {"/": [ComponentPattern(name="drawer", assertions=[])]}
        custom = {"/custom": [ComponentPattern(name="custom", assertions=[])]}
        merged = merge_patterns(derived, custom)
        assert "/" in merged
        assert "/custom" in merged

    def test_merge_same_page_different_names(self) -> None:
        derived = {"/": [ComponentPattern(name="drawer", assertions=[])]}
        custom = {"/": [ComponentPattern(name="custom", assertions=[])]}
        merged = merge_patterns(derived, custom)
        assert len(merged["/"]) == 2

    def test_merge_skips_duplicate_names(self) -> None:
        derived = {"/": [ComponentPattern(name="drawer", assertions=[])]}
        custom = {"/": [ComponentPattern(name="drawer", assertions=[])]}
        merged = merge_patterns(derived, custom)
        assert len(merged["/"]) == 1

    def test_merge_preserves_derived(self) -> None:
        assertion = ViewportAssertion(
            selector=".test",
            property="display",
            expected="block",
            viewport="mobile",
            description="test",
        )
        derived = {"/": [ComponentPattern(name="original", assertions=[assertion])]}
        custom: dict[str, list[ComponentPattern]] = {}
        merged = merge_patterns(derived, custom)
        assert len(merged["/"][0].assertions) == 1


class TestViewportSpecsContainer:
    """Tests for the container model."""

    def test_serialization(self) -> None:
        container = ViewportSpecsContainer(specs=[_make_spec_entry()])
        data = json.loads(container.model_dump_json())
        assert data["version"] == "1.0"
        assert len(data["specs"]) == 1
