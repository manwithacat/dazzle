"""Blueprint gates (L3) — full-page motifs behave at every viewport.

A Blueprint's promise is intrinsic responsiveness: the layout primitives
wrap on their own minimums, so the SAME page works at phone, tablet, and
desktop widths with no media queries. These gates prove that promise per
viewport, run axe over each sub-page, and sweep for zero-paint collapses
(the separator bug class) — the tiers the design doc mandates.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PKG / "site"))

from blueprints import BLUEPRINTS  # noqa: E402
from test_wcag import AXE_JS, _assert_clean  # noqa: E402
from test_wcag import RUN as AXE_RUN  # noqa: E402

_BP_IDS = [bp.id for bp in BLUEPRINTS]

# The design-doc viewport tier: phone / tablet / desktop.
_VIEWPORTS = {"phone": 390, "tablet": 834, "desktop": 1280}


def _bp_uri(bp_id: str) -> str:
    return (PKG / "site" / "blueprints" / f"{bp_id}.html").as_uri()


def _goto(page, bp_id: str, width: int) -> None:  # type: ignore[no-untyped-def]
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(_bp_uri(bp_id))
    page.wait_for_timeout(150)


class TestWorkspaceDrawer:
    def test_desktop_sidebar_shares_the_row(self, page) -> None:  # type: ignore[no-untyped-def]
        _goto(page, "workspace-drawer", _VIEWPORTS["desktop"])
        tops = page.eval_on_selector(
            ".sidebar-layout",
            "e => [e.children[0].getBoundingClientRect().top,"
            " e.children[1].getBoundingClientRect().top]",
        )
        assert tops[0] == tops[1], "desktop: nav and content share a row"

    def test_phone_sidebar_wraps_under_content(self, page) -> None:  # type: ignore[no-untyped-def]
        _goto(page, "workspace-drawer", _VIEWPORTS["phone"])
        tops = page.eval_on_selector(
            ".sidebar-layout",
            "e => [e.children[0].getBoundingClientRect().top,"
            " e.children[1].getBoundingClientRect().top]",
        )
        assert tops[0] != tops[1], "phone: the panes must stack"

    def test_kpi_grid_packs_per_viewport(self, page) -> None:  # type: ignore[no-untyped-def]
        counts = {}
        for name, width in _VIEWPORTS.items():
            _goto(page, "workspace-drawer", width)
            counts[name] = page.eval_on_selector(
                ".auto-grid",
                "e => getComputedStyle(e).gridTemplateColumns.split(' ').length",
            )
        assert counts["desktop"] >= 3, counts
        assert counts["phone"] == 1, counts
        assert counts["phone"] <= counts["tablet"] <= counts["desktop"], counts

    def test_drawer_opens_and_escape_closes(self, page) -> None:  # type: ignore[no-untyped-def]
        _goto(page, "workspace-drawer", _VIEWPORTS["desktop"])
        page.click('[data-dialog-open="bp-drawer"]')
        page.wait_for_timeout(120)
        assert page.evaluate("document.getElementById('bp-drawer').open"), (
            "the header button must open the drawer dialog"
        )
        page.keyboard.press("Escape")
        page.wait_for_timeout(120)
        assert not page.evaluate("document.getElementById('bp-drawer').open"), (
            "Esc must close (native <dialog> behaviour)"
        )

    def test_no_page_specific_css_classes(self, page) -> None:  # type: ignore[no-untyped-def]
        """No gallery-chrome (`hm-*`) classes leak inside the composition —
        the broader every-class-is-published claim is enforced by the
        contract gate (test_contract sweeps Blueprint partials for
        rule-less dz-* classes)."""
        _goto(page, "workspace-drawer", _VIEWPORTS["desktop"])
        leaks = page.eval_on_selector(
            ".hm-blueprint-live",
            """e => Array.from(e.querySelectorAll('*'))
                 .flatMap(el => Array.from(el.classList))
                 .filter(c => c.startsWith('hm-'))""",
        )
        assert not leaks, f"gallery chrome classes inside the composition: {leaks}"


@pytest.mark.parametrize("bp_id", _BP_IDS)
@pytest.mark.parametrize("width", sorted(set(_VIEWPORTS.values())))
def test_blueprint_zero_paint_sweep(page, bp_id, width) -> None:  # type: ignore[no-untyped-def]
    """The separator bug class, per blueprint per viewport: every visible
    element in the composition paints a nonzero box."""
    _goto(page, bp_id, width)
    collapsed = page.evaluate(
        """() => {
          const out = [];
          const host = document.querySelector('.hm-blueprint-live');
          for (const el of host.querySelectorAll('*')) {
            const tag = el.tagName.toLowerCase();
            if (['col', 'colgroup', 'option', 'template', 'script', 'style',
                 'use', 'defs', 'symbol', 'dialog', 'form'].includes(tag)) continue;
            if (el.closest('dialog:not([open])')) continue;
            if (el.checkVisibility && !el.checkVisibility()) continue;
            const s = getComputedStyle(el);
            if (s.display === 'none' || s.visibility === 'hidden') continue;
            const r = el.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) {
              const painted = s.borderTopWidth !== '0px' || s.borderLeftWidth !== '0px'
                || s.backgroundColor !== 'rgba(0, 0, 0, 0)' || el.children.length > 0
                || (el.textContent || '').trim() !== '';
              if (painted) out.push(tag + '.' + (el.className || '') + ' ' + r.width + 'x' + r.height);
            }
          }
          return out;
        }"""
    )
    assert not collapsed, f"{bp_id}@{width}: zero-paint elements:\n  " + "\n  ".join(collapsed)


@pytest.mark.parametrize("bp_id", _BP_IDS)
def test_blueprint_wcag(page, bp_id) -> None:  # type: ignore[no-untyped-def]
    """Axe WCAG 2.2 A/AA over each blueprint sub-page (light scheme; the
    tokens are the same scheme-aware set the index gate covers in dark)."""
    _goto(page, bp_id, _VIEWPORTS["desktop"])
    page.evaluate(AXE_JS)
    violations = page.evaluate(AXE_RUN)
    _assert_clean(violations, f"blueprint:{bp_id}")


class TestMasterDetail:
    def test_list_docks_beside_detail_on_desktop_stacks_on_phone(self, page) -> None:  # type: ignore[no-untyped-def]
        _goto(page, "master-detail", _VIEWPORTS["desktop"])
        tops = page.eval_on_selector(
            ".hm-blueprint-live .sidebar-layout",
            "e => [e.children[0].getBoundingClientRect().top,"
            " e.children[1].getBoundingClientRect().top]",
        )
        assert tops[0] == tops[1], "desktop: list docks beside the reading pane"
        _goto(page, "master-detail", _VIEWPORTS["phone"])
        tops = page.eval_on_selector(
            ".hm-blueprint-live .sidebar-layout",
            "e => [e.children[0].getBoundingClientRect().top,"
            " e.children[1].getBoundingClientRect().top]",
        )
        assert tops[0] != tops[1], "phone: the list stacks above the detail"

    def test_selection_exchange_loads_the_detail_card(self, page) -> None:  # type: ignore[no-untyped-def]
        _goto(page, "master-detail", _VIEWPORTS["desktop"])
        page.click('.master-detail__item[hx-get$="inv-002"]')
        page.wait_for_timeout(150)
        assert "Globex" in page.inner_text(".master-detail__detail")


class TestDashboard:
    def test_kpi_grid_packs_per_viewport(self, page) -> None:  # type: ignore[no-untyped-def]
        counts = {}
        for name, width in _VIEWPORTS.items():
            _goto(page, "dashboard", width)
            counts[name] = page.eval_on_selector(
                ".auto-grid",
                "e => getComputedStyle(e).gridTemplateColumns.split(' ').length",
            )
        assert counts["desktop"] >= 4, counts
        assert counts["phone"] <= 2, counts

    def test_progress_values_paint(self, page) -> None:  # type: ignore[no-untyped-def]
        """The public knob at page scale: each bar's width tracks its
        inline --progress-value (the v0.93.96 prefix strategy live)."""
        _goto(page, "dashboard", _VIEWPORTS["desktop"])
        widths = page.eval_on_selector_all(
            ".progress",
            """els => els.map(e => {
              const bar = e.querySelector('.progress__bar');
              return Math.round(bar.getBoundingClientRect().width /
                e.getBoundingClientRect().width * 100);
            })""",
        )
        assert widths and abs(widths[0] - 62) <= 2 and abs(widths[1] - 38) <= 2, widths


class TestAuth:
    def test_card_keeps_the_reading_measure(self, page) -> None:  # type: ignore[no-untyped-def]
        _goto(page, "auth", _VIEWPORTS["desktop"])
        w = page.eval_on_selector(
            '.hm-blueprint-live > .center[data-measure="prose"]',
            "e => e.getBoundingClientRect().width",
        )
        # 65ch at 16px base is well under 800px — the card must not span
        # the desktop viewport.
        assert w < 800, f"the auth column must hold its measure: {w}px"

    def test_form_fields_are_labelled(self, page) -> None:  # type: ignore[no-untyped-def]
        _goto(page, "auth", _VIEWPORTS["phone"])
        pairs = page.eval_on_selector_all(
            ".form-input",
            """els => els.map(e => !!document.querySelector('label[for="' + e.id + '"]'))""",
        )
        assert pairs and all(pairs), "every input must have a bound label"
