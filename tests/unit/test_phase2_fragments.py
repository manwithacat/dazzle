"""Tests for Phase 2 UI fragments — verify template rendering output."""

import pytest

pytest.importorskip("dazzle_ui.runtime.template_renderer")

from dazzle_ui.runtime.template_renderer import create_jinja_env  # noqa: E402


@pytest.fixture
def jinja_env():
    return create_jinja_env()


class TestToastFragment:
    def test_renders_alert_with_level(self, jinja_env):
        tmpl = jinja_env.from_string('{% include "fragments/toast.html" %}')
        html = tmpl.render(message="Saved", level="success")
        assert "alert-success" in html
        assert "Saved" in html
        assert 'remove-me="5s"' in html

    def test_default_level_is_info(self, jinja_env):
        tmpl = jinja_env.from_string('{% include "fragments/toast.html" %}')
        html = tmpl.render(message="Hello")
        assert "alert-info" in html


class TestAlertBanner:
    def test_renders_dismissible_banner(self, jinja_env):
        tmpl = jinja_env.from_string('{% include "fragments/alert_banner.html" %}')
        html = tmpl.render(message="Warning!", level="warning")
        assert "alert-warning" in html
        assert "Warning!" in html
        assert "x-data" in html
        assert "Dismiss" in html

    def test_non_dismissible_banner(self, jinja_env):
        tmpl = jinja_env.from_string('{% include "fragments/alert_banner.html" %}')
        html = tmpl.render(message="Info", level="info", dismissible=False)
        assert "alert-info" in html
        assert "x-data" not in html


class TestBreadcrumbs:
    def test_renders_breadcrumb_trail(self, jinja_env):
        from dazzle_back.runtime.breadcrumbs import Crumb

        crumbs = [
            Crumb(label="Home", url="/"),
            Crumb(label="Tasks", url="/tasks"),
            Crumb(label="Task 1", url=None),
        ]
        tmpl = jinja_env.from_string('{% include "fragments/breadcrumbs.html" %}')
        html = tmpl.render(crumbs=crumbs)
        assert "breadcrumbs" in html
        assert "Home" in html
        assert "Tasks" in html
        assert 'aria-current="page"' in html

    def test_single_crumb_hidden(self, jinja_env):
        from dazzle_back.runtime.breadcrumbs import Crumb

        crumbs = [Crumb(label="Home", url="/")]
        tmpl = jinja_env.from_string('{% include "fragments/breadcrumbs.html" %}')
        html = tmpl.render(crumbs=crumbs)
        assert html.strip() == ""


class TestStepsIndicator:
    def test_renders_steps(self, jinja_env):
        steps = [{"label": "Info"}, {"label": "Review"}, {"label": "Done"}]
        tmpl = jinja_env.from_string('{% include "fragments/steps_indicator.html" %}')
        html = tmpl.render(steps=steps, current_step=2)
        assert html.count("step-primary") == 2
        assert 'aria-current="step"' in html


class TestAccordion:
    def test_renders_static_sections(self, jinja_env):
        sections = [
            {"id": "a", "title": "Section A", "content": "<p>Content A</p>", "endpoint": None},
            {"id": "b", "title": "Section B", "content": "<p>Content B</p>", "endpoint": None},
        ]
        tmpl = jinja_env.from_string('{% include "fragments/accordion.html" %}')
        html = tmpl.render(sections=sections)
        assert "Section A" in html
        assert "Content A" in html
        assert "collapse-arrow" in html

    def test_lazy_load_section_has_htmx(self, jinja_env):
        sections = [
            {"id": "lazy", "title": "Lazy", "content": None, "endpoint": "/api/lazy"},
        ]
        tmpl = jinja_env.from_string('{% include "fragments/accordion.html" %}')
        html = tmpl.render(sections=sections)
        assert 'hx-get="/api/lazy"' in html
        assert 'hx-trigger="toggle once"' in html
        assert "loading loading-dots" in html


class TestSkeletonPatterns:
    def test_skeleton_table_rows(self, jinja_env):
        tmpl = jinja_env.from_string(
            '{% from "fragments/skeleton_patterns.html" import skeleton_table_rows %}'
            "{{ skeleton_table_rows(rows=3, cols=2) }}"
        )
        html = tmpl.render()
        assert html.count("<tr>") == 3
        assert html.count("skeleton") == 6

    def test_skeleton_card(self, jinja_env):
        tmpl = jinja_env.from_string(
            '{% from "fragments/skeleton_patterns.html" import skeleton_card %}'
            "{{ skeleton_card() }}"
        )
        html = tmpl.render()
        assert "skeleton" in html
        assert "card" in html


class TestModal:
    def test_renders_dialog(self, jinja_env):
        tmpl = jinja_env.from_string('{% include "components/modal.html" %}')
        html = tmpl.render(title="Edit Item", content="<form>Fields</form>")
        assert "<dialog" in html
        assert "Edit Item" in html
        assert "Fields" in html
        assert "modal-backdrop" in html

    def test_size_classes(self, jinja_env):
        tmpl = jinja_env.from_string('{% include "components/modal.html" %}')
        html = tmpl.render(title="Big", size="xl")
        assert "max-w-4xl" in html
