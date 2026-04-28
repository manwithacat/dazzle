"""Cycle 247 — parking-lot primitive modernisation.

Batch tests for six small fragments modernised from DaisyUI to design
tokens in one autonomous-arc cycle. Each class verifies canonical class
markers, zero DaisyUI classes, and ARIA semantics.
"""

import pytest

pytest.importorskip("dazzle_ui", reason="dazzle_ui not installed")


def _render_fragment(path: str, **ctx) -> str:
    from dazzle_ui.runtime.template_renderer import create_jinja_env

    env = create_jinja_env()
    tmpl = env.get_template(path)
    return tmpl.render(**ctx)


# ── Breadcrumbs ────────────────────────────────────────────────────────


class TestBreadcrumbs:
    def test_canonical_marker(self) -> None:
        html = _render_fragment(
            "fragments/breadcrumbs.html",
            crumbs=[
                type("C", (), {"label": "Home", "url": "/"})(),
                type("C", (), {"label": "Tasks", "url": "/tasks"})(),
                type("C", (), {"label": "Edit", "url": None})(),
            ],
        )
        assert "dz-breadcrumbs" in html
        assert 'aria-label="Breadcrumb"' in html
        assert "breadcrumbs text-sm" not in html  # legacy DaisyUI

    def test_no_render_for_single_crumb(self) -> None:
        html = _render_fragment(
            "fragments/breadcrumbs.html",
            crumbs=[type("C", (), {"label": "Home", "url": "/"})()],
        )
        assert "dz-breadcrumbs" not in html

    def test_current_page_has_aria_current(self) -> None:
        html = _render_fragment(
            "fragments/breadcrumbs.html",
            crumbs=[
                type("C", (), {"label": "Home", "url": "/"})(),
                type("C", (), {"label": "Current", "url": None})(),
            ],
        )
        assert 'aria-current="page"' in html
        assert "Current" in html

    def test_uses_design_tokens(self) -> None:
        """v0.62 CSS refactor: token references move from inline
        Tailwind to CSS rules. Check the semantic class names + CSS
        rule content cross-reference."""
        html = _render_fragment(
            "fragments/breadcrumbs.html",
            crumbs=[
                type("C", (), {"label": "A", "url": "/"})(),
                type("C", (), {"label": "B", "url": None})(),
            ],
        )
        assert "dz-breadcrumb-link" in html
        assert "dz-breadcrumb-current" in html

        from pathlib import Path

        css = (
            Path(__file__).resolve().parents[2]
            / "src/dazzle_ui/runtime/static/css/components/fragments.css"
        ).read_text()
        link_block = css.split(".dz-breadcrumb-link {")[1].split("}")[0]
        current_block = css.split(".dz-breadcrumb-current {")[1].split("}")[0]
        assert "var(--colour-text-muted)" in link_block
        assert "var(--colour-text)" in current_block


# ── Alert banner ───────────────────────────────────────────────────────


class TestAlertBanner:
    def test_canonical_marker(self) -> None:
        html = _render_fragment(
            "fragments/alert_banner.html",
            message="System update at midnight",
        )
        assert "dz-alert-banner" in html
        assert 'role="alert"' in html
        assert "alert alert-" not in html  # legacy DaisyUI

    def test_info_tone_default(self) -> None:
        """v0.62 CSS refactor: tone tinting moved from inline
        `bg-[hsl(var(--info)/0.08)]` to attribute selectors on
        `.dz-alert-banner[data-dz-alert-level="info"]` in
        components/fragments.css. Pin the data-attribute emission +
        the CSS rule's brand colour reference."""
        html = _render_fragment(
            "fragments/alert_banner.html",
            message="Info",
        )
        assert 'data-dz-alert-level="info"' in html

        from pathlib import Path

        css = (
            Path(__file__).resolve().parents[2]
            / "src/dazzle_ui/runtime/static/css/components/fragments.css"
        ).read_text()
        assert '.dz-alert-banner[data-dz-alert-level="info"]' in css
        info_block = css.split('.dz-alert-banner[data-dz-alert-level="info"]')[1].split("}")[0]
        assert "var(--colour-brand)" in info_block

    def test_error_tone_uses_destructive_token(self) -> None:
        """v0.62 CSS refactor: same pattern as info — error tone uses
        `var(--colour-danger)` on the data-attribute selector."""
        html = _render_fragment(
            "fragments/alert_banner.html",
            message="Error",
            level="error",
        )
        assert 'data-dz-alert-level="error"' in html

        from pathlib import Path

        css = (
            Path(__file__).resolve().parents[2]
            / "src/dazzle_ui/runtime/static/css/components/fragments.css"
        ).read_text()
        assert '.dz-alert-banner[data-dz-alert-level="error"]' in css
        error_block = css.split('.dz-alert-banner[data-dz-alert-level="error"]')[1].split("}")[0]
        assert "var(--colour-danger)" in error_block

    def test_no_daisyui_btn(self) -> None:
        html = _render_fragment(
            "fragments/alert_banner.html",
            message="Msg",
            dismissible=True,
        )
        assert "btn-ghost" not in html
        assert "btn-circle" not in html


# ── Accordion ──────────────────────────────────────────────────────────


class TestAccordion:
    def test_canonical_marker(self) -> None:
        html = _render_fragment(
            "fragments/accordion.html",
            sections=[{"id": "s1", "title": "Section 1", "content": "Body 1", "endpoint": None}],
        )
        assert "dz-accordion" in html
        assert "dz-accordion-item" in html
        assert 'data-dz-section-id="s1"' in html
        # DaisyUI
        assert "collapse collapse-arrow" not in html
        assert "bg-base-100" not in html

    def test_content_autoescaped(self) -> None:
        html = _render_fragment(
            "fragments/accordion.html",
            sections=[
                {
                    "id": "s1",
                    "title": "XSS Test",
                    "content": "<script>alert(1)</script>",
                    "endpoint": None,
                }
            ],
        )
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html


# ── Context menu ───────────────────────────────────────────────────────


class TestContextMenu:
    def test_canonical_marker(self) -> None:
        html = _render_fragment(
            "fragments/context_menu.html",
            items=[{"label": "Copy", "url": "#", "icon": None, "divider": False}],
        )
        assert "dz-context-menu" in html
        assert "data-dz-context-menu-panel" in html
        assert 'role="menu"' in html
        # DaisyUI
        assert "menu bg-base-100" not in html
        assert "rounded-box" not in html

    def test_escape_to_close(self) -> None:
        html = _render_fragment(
            "fragments/context_menu.html",
            items=[{"label": "X", "url": "#"}],
        )
        assert "@keydown.escape.window" in html


# ── Skeleton patterns ──────────────────────────────────────────────────


class TestSkeletonPatterns:
    def _import_macros(self):
        from dazzle_ui.runtime.template_renderer import create_jinja_env

        env = create_jinja_env()
        tmpl = env.from_string(
            '{% from "fragments/skeleton_patterns.html" '
            "import skeleton_table_rows, skeleton_card, skeleton_detail %}"
            "{{ skeleton_table_rows(rows=2, cols=3) }}"
            "{{ skeleton_card() }}"
            "{{ skeleton_detail() }}"
        )
        return tmpl.render()

    def test_uses_design_tokens_not_daisyui(self) -> None:
        html = self._import_macros()
        assert "dz-skeleton" in html
        assert "animate-pulse" in html
        assert "hsl(var(--muted))" in html
        # DaisyUI
        assert 'class="skeleton ' not in html
        assert "card bg-base-100" not in html
        assert "card-body" not in html


# ── Date range picker ──────────────────────────────────────────────────


class TestDateRangePicker:
    def test_canonical_marker(self) -> None:
        html = _render_fragment(
            "fragments/date_range_picker.html",
            endpoint="/api/data",
            region_name="events",
        )
        assert "dz-date-range-picker" in html
        # DaisyUI
        assert "input input-xs" not in html
        assert "input-bordered" not in html
        assert "text-base-content" not in html

    def test_labels_have_for_attribute(self) -> None:
        html = _render_fragment(
            "fragments/date_range_picker.html",
            endpoint="/api/data",
            region_name="events",
        )
        assert 'for="date-from-events"' in html
        assert 'for="date-to-events"' in html
        assert 'id="date-from-events"' in html
        assert 'id="date-to-events"' in html

    def test_uses_design_tokens(self) -> None:
        html = _render_fragment(
            "fragments/date_range_picker.html",
            endpoint="/api/data",
            region_name="events",
        )
        assert "hsl(var(--border))" in html
        assert "hsl(var(--foreground))" in html
        assert "hsl(var(--ring))" in html
