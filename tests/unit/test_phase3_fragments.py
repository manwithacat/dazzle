"""Tests for Phase 3 Alpine interactive component fragments."""

import pathlib

import pytest

pytest.importorskip("dazzle_ui.runtime.template_renderer")

from dazzle_ui.runtime.template_renderer import create_jinja_env  # noqa: E402

JS_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle_ui"
    / "runtime"
    / "static"
    / "js"
    / "dz-alpine.js"
)


@pytest.fixture
def jinja_env():
    return create_jinja_env()


# ── JS registration tests ───────────────────────────────────────────────


class TestAlpineRegistrations:
    def test_all_phase3_components_registered(self):
        content = JS_PATH.read_text()
        for name in [
            "dzPopover",
            "dzTooltip",
            "dzContextMenu",
            "dzCommandPalette",
            "dzSlideOver",
            "dzToggleGroup",
        ]:
            assert f'"{name}"' in content, f"{name} not registered in dz-alpine.js"

    def test_command_palette_has_keyboard_shortcut(self):
        content = JS_PATH.read_text()
        assert 'key === "k"' in content


# ── Fragment rendering tests ─────────────────────────────────────────────


class TestPopover:
    def test_renders_with_alpine_data(self, jinja_env):
        tmpl = jinja_env.from_string('{% include "fragments/popover.html" %}')
        html = tmpl.render(trigger_text="Info", content="<p>Details</p>")
        assert 'x-data="dzPopover"' in html
        assert "Info" in html
        assert "Details" in html
        assert 'role="dialog"' in html


class TestTooltipRich:
    def test_renders_with_delays(self, jinja_env):
        tmpl = jinja_env.from_string('{% include "fragments/tooltip_rich.html" %}')
        html = tmpl.render(content="Help text", trigger="<span>Hover me</span>")
        assert 'x-data="dzTooltip"' in html
        assert 'role="tooltip"' in html
        assert "Help text" in html

    def test_custom_delays(self, jinja_env):
        tmpl = jinja_env.from_string('{% include "fragments/tooltip_rich.html" %}')
        html = tmpl.render(content="Tip", show_delay=500, hide_delay=200)
        assert 'data-dz-delay="500"' in html
        assert 'data-dz-hide-delay="200"' in html


class TestContextMenu:
    def test_renders_menu_items(self, jinja_env):
        items = [
            {"label": "Edit", "url": "/edit", "icon": "pencil"},
            {"label": "Delete", "url": "/delete", "icon": None},
        ]
        tmpl = jinja_env.from_string('{% include "fragments/context_menu.html" %}')
        html = tmpl.render(items=items)
        assert 'x-data="dzContextMenu"' in html
        assert 'role="menu"' in html
        assert "Edit" in html
        assert "Delete" in html

    def test_divider_item(self, jinja_env):
        items = [
            {"label": "A", "url": "#"},
            {"divider": True},
            {"label": "B", "url": "#"},
        ]
        tmpl = jinja_env.from_string('{% include "fragments/context_menu.html" %}')
        html = tmpl.render(items=items)
        assert "divider" in html


class TestCommandPalette:
    def test_renders_with_actions(self, jinja_env):
        actions = [
            {"label": "Go to Tasks", "url": "/tasks", "group": "Navigate"},
        ]
        tmpl = jinja_env.from_string('{% include "fragments/command_palette.html" %}')
        html = tmpl.render(actions=actions)
        assert 'x-data="dzCommandPalette"' in html
        assert 'role="dialog"' in html
        assert "Command palette" in html
        assert "palette-results" in html

    def test_keyboard_hints(self, jinja_env):
        tmpl = jinja_env.from_string('{% include "fragments/command_palette.html" %}')
        html = tmpl.render(actions=[])
        assert "Navigate" in html
        assert "Select" in html
        assert "Close" in html


class TestSlideOver:
    def test_renders_with_width(self, jinja_env):
        tmpl = jinja_env.from_string('{% include "fragments/slide_over.html" %}')
        html = tmpl.render(title="Task Details", width="lg")
        assert 'x-data="dzSlideOver"' in html
        assert 'data-dz-width="lg"' in html
        assert "Task Details" in html
        assert 'role="dialog"' in html
        assert 'aria-modal="true"' in html

    def test_default_id(self, jinja_env):
        tmpl = jinja_env.from_string('{% include "fragments/slide_over.html" %}')
        html = tmpl.render()
        assert 'id="dz-slideover"' in html


class TestToggleGroup:
    def test_renders_options(self, jinja_env):
        options = [
            {"value": "grid", "label": "Grid"},
            {"value": "list", "label": "List"},
        ]
        tmpl = jinja_env.from_string('{% include "fragments/toggle_group.html" %}')
        html = tmpl.render(options=options, name="view_mode")
        assert 'x-data="dzToggleGroup"' in html
        assert 'role="radiogroup"' in html
        assert 'name="view_mode"' in html
        assert "Grid" in html
        assert "List" in html

    def test_multi_mode(self, jinja_env):
        options = [{"value": "a", "label": "A"}, {"value": "b", "label": "B"}]
        tmpl = jinja_env.from_string('{% include "fragments/toggle_group.html" %}')
        html = tmpl.render(options=options, name="tags", multi=True)
        assert 'data-dz-multi="true"' in html
        assert 'role="group"' in html
