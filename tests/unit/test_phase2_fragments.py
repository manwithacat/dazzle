"""Tests for Phase 2 UI fragments — verify template rendering output."""

import pytest

pytest.importorskip("dazzle_ui.runtime.template_renderer")

from dazzle_ui.runtime.template_renderer import create_jinja_env  # noqa: E402


@pytest.fixture
def jinja_env():
    return create_jinja_env()


class TestToastFragment:
    def test_renders_alert_with_level(self, jinja_env):
        """v0.62 CSS refactor: tone tinting moved from inline
        `text-[hsl(var(--success))]` / `border-l-[hsl(var(--success))]`
        Tailwind dictionaries to attribute selectors on
        `.dz-toast[data-dz-toast-level="success"]` in
        components/fragments.css."""
        tmpl = jinja_env.from_string('{% include "fragments/toast.html" %}')
        html = tmpl.render(message="Saved", level="success")
        assert 'data-dz-toast-level="success"' in html
        assert "Saved" in html
        assert 'remove-me="5s"' in html

    def test_default_level_is_info(self, jinja_env):
        """info is the default level — tone tinting via
        data-dz-toast-level attribute selector for `.dz-toast` in CSS."""
        tmpl = jinja_env.from_string('{% include "fragments/toast.html" %}')
        html = tmpl.render(message="Hello")
        assert 'data-dz-toast-level="info"' in html


class TestAlertBanner:
    def test_renders_dismissible_banner(self, jinja_env):
        tmpl = jinja_env.from_string('{% include "fragments/alert_banner.html" %}')
        html = tmpl.render(message="Warning!", level="warning")
        # Cycle 247 — modernised to design tokens; DaisyUI alert-* removed
        assert "dz-alert-banner" in html
        assert 'data-dz-alert-level="warning"' in html
        assert "Warning!" in html
        assert "x-data" in html
        assert "Dismiss" in html

    def test_non_dismissible_banner(self, jinja_env):
        tmpl = jinja_env.from_string('{% include "fragments/alert_banner.html" %}')
        html = tmpl.render(message="Info", level="info", dismissible=False)
        # Cycle 247 — modernised; DaisyUI alert-info removed
        assert 'data-dz-alert-level="info"' in html
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
        """v0.62 CSS refactor: completed/current step styling moved
        from inline `bg-[hsl(var(--primary))]` to .is-completed
        modifier on .dz-steps-circle (components/fragments.css)."""
        steps = [{"label": "Info"}, {"label": "Review"}, {"label": "Done"}]
        tmpl = jinja_env.from_string('{% include "fragments/steps_indicator.html" %}')
        html = tmpl.render(steps=steps, current_step=2)
        assert "dz-steps" in html
        # 2 circles + 2 labels emit .is-completed (steps 1, 2)
        assert html.count("dz-steps-circle is-completed") == 2
        assert 'aria-current="step"' in html


class TestAccordion:
    def test_renders_static_sections(self, jinja_env):
        sections = [
            {"id": "a", "title": "Section A", "content": "Content A", "endpoint": None},
            {"id": "b", "title": "Section B", "content": "Content B", "endpoint": None},
        ]
        tmpl = jinja_env.from_string('{% include "fragments/accordion.html" %}')
        html = tmpl.render(sections=sections)
        assert "Section A" in html
        assert "Content A" in html
        # Cycle 247 — modernised; DaisyUI collapse-arrow removed
        assert "dz-accordion-item" in html

    def test_lazy_load_section_has_htmx(self, jinja_env):
        sections = [
            {"id": "lazy", "title": "Lazy", "content": None, "endpoint": "/api/lazy"},
        ]
        tmpl = jinja_env.from_string('{% include "fragments/accordion.html" %}')
        html = tmpl.render(sections=sections)
        assert 'hx-get="/api/lazy"' in html
        assert 'hx-trigger="toggle once"' in html
        # Cycle 247 — modernised; DaisyUI loading loading-dots → SVG spinner
        assert "Loading" in html


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
        # Post-DaisyUI refactor: native <dialog> uses CSS ::backdrop pseudo
        # via Tailwind's `backdrop:` prefix, not a modal-backdrop class.
        assert "backdrop:bg-black" in html

    def test_size_classes(self, jinja_env):
        tmpl = jinja_env.from_string('{% include "components/modal.html" %}')
        html = tmpl.render(title="Big", size="xl")
        assert "max-w-4xl" in html
