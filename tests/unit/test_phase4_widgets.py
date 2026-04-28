"""Tests for Phase 4 vendored widget integration."""

import pathlib

import pytest

pytest.importorskip("dazzle_ui.runtime.template_renderer")

from dazzle_ui.runtime.template_renderer import create_jinja_env  # noqa: E402

STATIC_DIR = (
    pathlib.Path(__file__).resolve().parents[2] / "src" / "dazzle_ui" / "runtime" / "static"
)


@pytest.fixture
def jinja_env():
    return create_jinja_env()


# ── Vendor file existence ────────────────────────────────────────────────


class TestVendoredFiles:
    @pytest.mark.parametrize(
        "filename",
        [
            "vendor/tom-select.min.js",
            "vendor/tom-select.css",
            "vendor/flatpickr.min.js",
            "vendor/flatpickr.css",
            "vendor/pickr.min.js",
            "vendor/pickr.css",
            "vendor/quill.min.js",
            "vendor/quill.snow.css",
        ],
    )
    def test_vendor_file_exists(self, filename):
        path = STATIC_DIR / filename
        assert path.exists(), f"Missing vendored file: {filename}"
        assert path.stat().st_size > 100, f"Suspiciously small: {filename}"


# ── Widget registry ──────────────────────────────────────────────────────


class TestWidgetRegistry:
    def test_registry_script_exists(self):
        path = STATIC_DIR / "js" / "dz-widget-registry.js"
        assert path.exists()

    def test_registry_has_all_widget_types(self):
        content = (STATIC_DIR / "js" / "dz-widget-registry.js").read_text()
        for widget_type in [
            "combobox",
            "multiselect",
            "tags",
            "datepicker",
            "daterange",
            "colorpicker",
            "richtext",
            "range-tooltip",
        ]:
            assert f'"{widget_type}"' in content, f"Widget type {widget_type} not registered"

    def test_registry_uses_bridge(self):
        content = (STATIC_DIR / "js" / "dz-widget-registry.js").read_text()
        assert "bridge.registerWidget" in content


# ── CSS theme overrides ──────────────────────────────────────────────────


class TestWidgetCSS:
    def test_widget_css_exists(self):
        path = STATIC_DIR / "css" / "dz-widgets.css"
        assert path.exists()

    def test_widget_css_covers_all_libraries(self):
        content = (STATIC_DIR / "css" / "dz-widgets.css").read_text()
        assert ".ts-wrapper" in content, "Missing Tom Select overrides"
        assert ".flatpickr-calendar" in content, "Missing Flatpickr overrides"
        assert ".pcr-app" in content or ".pickr" in content, "Missing Pickr overrides"
        assert ".ql-container" in content or ".ql-toolbar" in content, "Missing Quill overrides"


# ── Form field widget rendering ──────────────────────────────────────────


class _FakeField:
    """Minimal field stub for template rendering tests."""

    def __init__(self, name, label, field_type="str", widget=None, **kwargs):
        self.name = name
        self.label = label
        self.type = field_type
        self.widget = widget
        self.required = kwargs.get("required", False)
        self.hint = kwargs.get("hint")
        self.help = kwargs.get("help")
        self.placeholder = kwargs.get("placeholder")
        self.default = kwargs.get("default")
        self.options = kwargs.get("options", [])
        self.source = kwargs.get("source")
        self.extra = kwargs.get("extra", {})


class TestFormFieldWidgets:
    def _render(self, jinja_env, field, values=None, errors=None):
        tmpl = jinja_env.from_string(
            '{% from "macros/form_field.html" import render_field %}'
            "{{ render_field(field, values, errors) }}"
        )
        return tmpl.render(field=field, values=values or {}, errors=errors or {})

    def test_combobox_renders_tom_select(self, jinja_env):
        field = _FakeField(
            "assignee",
            "Assignee",
            "ref",
            widget="combobox",
            options=[{"value": "1", "label": "Alice"}, {"value": "2", "label": "Bob"}],
        )
        html = self._render(jinja_env, field)
        assert 'data-dz-widget="combobox"' in html
        assert "Alice" in html
        assert "Bob" in html

    def test_multi_select_renders(self, jinja_env):
        field = _FakeField(
            "tags",
            "Categories",
            "ref",
            widget="multi_select",
            options=[{"value": "a", "label": "Alpha"}, {"value": "b", "label": "Beta"}],
        )
        html = self._render(jinja_env, field)
        assert 'data-dz-widget="multiselect"' in html
        assert "multiple" in html

    def test_tags_renders(self, jinja_env):
        field = _FakeField("labels", "Labels", "str", widget="tags")
        html = self._render(jinja_env, field)
        assert 'data-dz-widget="tags"' in html

    def test_datepicker_renders_for_date_type(self, jinja_env):
        field = _FakeField("due_date", "Due Date", "date", widget="picker")
        html = self._render(jinja_env, field)
        assert 'data-dz-widget="datepicker"' in html

    def test_daterange_renders(self, jinja_env):
        field = _FakeField("period", "Period", "date", widget="range")
        html = self._render(jinja_env, field)
        assert 'data-dz-widget="daterange"' in html

    def test_colorpicker_renders(self, jinja_env):
        field = _FakeField("brand_color", "Brand Color", "str", widget="color")
        html = self._render(jinja_env, field)
        assert 'data-dz-widget="colorpicker"' in html
        assert "pcr-trigger" in html

    def test_richtext_renders(self, jinja_env):
        field = _FakeField("description", "Description", "text", widget="rich_text")
        html = self._render(jinja_env, field)
        assert 'data-dz-widget="richtext"' in html
        assert "data-dz-editor" in html

    def test_slider_renders(self, jinja_env):
        field = _FakeField(
            "quality",
            "Quality",
            "int",
            widget="slider",
            extra={"min": 0, "max": 100, "step": 5},
        )
        html = self._render(jinja_env, field)
        assert 'data-dz-widget="range-tooltip"' in html
        assert 'type="range"' in html
        assert "data-dz-range-value" in html

    def test_regular_field_still_works(self, jinja_env):
        """Ensure non-widget fields render normally."""
        field = _FakeField("title", "Title", "str")
        html = self._render(jinja_env, field)
        assert 'type="text"' in html
        assert "data-dz-widget" not in html


class TestFieldHelpRendering:
    """#918 introduced `help:` on fields; #925 caught that the checkbox
    branch wired the aria reference but skipped the actual `<p>` element.
    Pin every widely-used branch so the regression can't recur."""

    def _render(self, jinja_env, field, values=None, errors=None):
        tmpl = jinja_env.from_string(
            '{% from "macros/form_field.html" import render_field %}'
            "{{ render_field(field, values, errors) }}"
        )
        return tmpl.render(field=field, values=values or {}, errors=errors or {})

    def test_help_renders_for_checkbox(self, jinja_env):
        """#925: boolean/checkbox branch must render the help paragraph."""
        field = _FakeField(
            "auto_match",
            "Auto-match",
            "checkbox",
            help="Suggested matches below 90% stay in review.",
        )
        html = self._render(jinja_env, field)
        assert 'class="dz-form-hint"' in html
        assert "Suggested matches below 90% stay in review." in html
        assert 'id="hint-auto_match"' in html
        assert 'aria-describedby="hint-auto_match"' in html

    def test_help_renders_for_text(self, jinja_env):
        field = _FakeField("title", "Title", "str", help="A short summary visible in lists")
        html = self._render(jinja_env, field)
        assert "A short summary visible in lists" in html
        assert 'class="dz-form-hint"' in html

    def test_help_renders_for_textarea(self, jinja_env):
        field = _FakeField("desc", "Description", "textarea", help="Markdown allowed.")
        html = self._render(jinja_env, field)
        assert "Markdown allowed." in html

    def test_help_renders_for_select(self, jinja_env):
        field = _FakeField(
            "status",
            "Status",
            "select",
            options=[{"value": "a", "label": "Active"}],
            help="Choose carefully.",
        )
        html = self._render(jinja_env, field)
        assert "Choose carefully." in html

    def test_help_omitted_when_no_help(self, jinja_env):
        field = _FakeField("plain", "Plain", "checkbox")
        html = self._render(jinja_env, field)
        assert 'class="dz-form-hint"' not in html
        assert "aria-describedby" not in html
