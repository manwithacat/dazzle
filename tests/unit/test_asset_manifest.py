# tests/unit/test_asset_manifest.py
"""Tests for conditional JS asset derivation from surface specs."""

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
    def test_no_widgets_returns_empty(self):
        surface = _FakeSurface([_FakeField("str"), _FakeField("int")])
        assert collect_required_assets(surface) == set()

    def test_rich_text_requires_quill(self):
        surface = _FakeSurface([_FakeField("text", widget="rich_text")])
        assert collect_required_assets(surface) == {"quill"}

    def test_combobox_requires_tom_select(self):
        surface = _FakeSurface([_FakeField("ref", widget="combobox")])
        assert collect_required_assets(surface) == {"tom-select"}

    def test_multi_select_requires_tom_select(self):
        surface = _FakeSurface([_FakeField("ref", widget="multi_select")])
        assert collect_required_assets(surface) == {"tom-select"}

    def test_tags_requires_tom_select(self):
        surface = _FakeSurface([_FakeField("str", widget="tags")])
        assert collect_required_assets(surface) == {"tom-select"}

    def test_date_picker_requires_flatpickr(self):
        surface = _FakeSurface([_FakeField("date", widget="picker")])
        assert collect_required_assets(surface) == {"flatpickr"}

    def test_datetime_picker_requires_flatpickr(self):
        surface = _FakeSurface([_FakeField("datetime", widget="picker")])
        assert collect_required_assets(surface) == {"flatpickr"}

    def test_date_range_requires_flatpickr(self):
        surface = _FakeSurface([_FakeField("date", widget="range")])
        assert collect_required_assets(surface) == {"flatpickr"}

    def test_color_requires_pickr(self):
        surface = _FakeSurface([_FakeField("str", widget="color")])
        assert collect_required_assets(surface) == {"pickr"}

    def test_multiple_widgets_collect_all(self):
        surface = _FakeSurface(
            [
                _FakeField("text", widget="rich_text"),
                _FakeField("ref", widget="combobox"),
                _FakeField("date", widget="picker"),
                _FakeField("str", widget="color"),
            ]
        )
        assert collect_required_assets(surface) == {
            "quill",
            "tom-select",
            "flatpickr",
            "pickr",
        }

    def test_duplicate_widgets_deduplicated(self):
        surface = _FakeSurface(
            [
                _FakeField("ref", widget="combobox"),
                _FakeField("ref", widget="multi_select"),
                _FakeField("str", widget="tags"),
            ]
        )
        assert collect_required_assets(surface) == {"tom-select"}

    def test_unknown_widget_ignored(self):
        surface = _FakeSurface([_FakeField("str", widget="unknown_future_widget")])
        assert collect_required_assets(surface) == set()

    def test_non_date_type_with_picker_widget_ignored(self):
        """Picker widget only applies to date/datetime fields."""
        surface = _FakeSurface([_FakeField("str", widget="picker")])
        assert collect_required_assets(surface) == set()
