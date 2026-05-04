# tests/unit/test_asset_manifest.py
"""Tests for conditional JS asset derivation from surface specs."""

import pytest

from dazzle_back.runtime.asset_manifest import collect_required_assets


class _FakeField:
    """Minimal field stub for testing."""

    def __init__(self, field_type: str = "str", widget: str | None = None):
        self.type = field_type
        self.widget = widget


class _FakeSurface:
    """Minimal surface stub for testing."""

    def __init__(self, fields: list[_FakeField]):
        self.fields = fields


class TestCollectRequiredAssets:
    """Each (field_type, widget) → expected asset set.

    Drift gates are embedded in the parametric ids:
    - ``rich_text_no_vendor`` pins the dz-richtext migration (#977 cycle 4) —
      bundled with core JS, no Quill-style dependency.
    - ``color_no_vendor`` pins the native <input type=color> migration (#976) —
      no Pickr-style dependency.
    """

    @pytest.mark.parametrize(
        ("field_type", "widget", "expected_assets"),
        [
            # Vendor-asset-bearing widgets
            ("ref", "combobox", {"tom-select"}),
            ("ref", "multi_select", {"tom-select"}),
            ("str", "tags", {"tom-select"}),
            ("date", "picker", {"flatpickr"}),
            ("datetime", "picker", {"flatpickr"}),
            ("date", "range", {"flatpickr"}),
            # Native / bundled — no vendor asset (drift gates)
            ("text", "rich_text", set()),
            ("str", "color", set()),
            # Defensive
            ("str", "unknown_future_widget", set()),
            ("str", "picker", set()),  # picker only applies to date/datetime
        ],
        ids=[
            "combobox_requires_tom_select",
            "multi_select_requires_tom_select",
            "tags_requires_tom_select",
            "date_picker_requires_flatpickr",
            "datetime_picker_requires_flatpickr",
            "date_range_requires_flatpickr",
            "rich_text_no_vendor",
            "color_no_vendor",
            "unknown_widget_ignored",
            "non_date_type_with_picker_ignored",
        ],
    )
    def test_single_widget_field(self, field_type, widget, expected_assets) -> None:
        surface = _FakeSurface([_FakeField(field_type, widget=widget)])
        assert collect_required_assets(surface) == expected_assets

    def test_no_widgets_returns_empty(self) -> None:
        """Surface with only plain (no widget=) fields requires no vendor assets."""
        surface = _FakeSurface([_FakeField("str"), _FakeField("int")])
        assert collect_required_assets(surface) == set()

    def test_multiple_widgets_collect_all(self) -> None:
        """Mixed widget set — bundled widgets contribute nothing, vendor ones unify."""
        surface = _FakeSurface(
            [
                _FakeField("text", widget="rich_text"),  # bundled
                _FakeField("ref", widget="combobox"),  # vendor
                _FakeField("date", widget="picker"),  # vendor
                _FakeField("str", widget="color"),  # bundled
            ]
        )
        assert collect_required_assets(surface) == {"tom-select", "flatpickr"}

    def test_duplicate_widgets_deduplicated(self) -> None:
        """Multiple fields requiring the same vendor produce a single asset entry."""
        surface = _FakeSurface(
            [
                _FakeField("ref", widget="combobox"),
                _FakeField("ref", widget="multi_select"),
                _FakeField("str", widget="tags"),
            ]
        )
        assert collect_required_assets(surface) == {"tom-select"}
