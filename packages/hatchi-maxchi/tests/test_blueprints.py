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
    # The behaviour tests drive the STANDALONE live page (its own
    # browsing context — exactly what the doc page's iframe embeds and
    # what a consumer ships). The {id}.html doc page is chrome + iframe.
    return (PKG / "site" / "blueprints" / f"{bp_id}-live.html").as_uri()


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
            "body",
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
          const host = document.body;
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
              // Out-of-flow (fixed/absolute) children paint on their own
              // box, not the wrapper's — a zero-size wrapper whose only
              // content is out-of-flow is structural, not collapsed (the
              // app-shell's <aside> around its fixed sidebar).
              const inFlowChild = Array.from(el.children).some(c => {
                const p = getComputedStyle(c).position;
                return p !== 'fixed' && p !== 'absolute';
              });
              // direct text nodes only — textContent would count the
              // out-of-flow child's text and defeat the wrapper exemption
              const ownText = Array.from(el.childNodes).some(
                n => n.nodeType === 3 && n.textContent.trim() !== '');
              const painted = s.borderTopWidth !== '0px' || s.borderLeftWidth !== '0px'
                || s.backgroundColor !== 'rgba(0, 0, 0, 0)' || inFlowChild || ownText;
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
            "body .sidebar-layout",
            "e => [e.children[0].getBoundingClientRect().top,"
            " e.children[1].getBoundingClientRect().top]",
        )
        assert tops[0] == tops[1], "desktop: list docks beside the reading pane"
        _goto(page, "master-detail", _VIEWPORTS["phone"])
        tops = page.eval_on_selector(
            "body .sidebar-layout",
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
            'body > .center[data-measure="prose"]',
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


class TestSaasShell:
    def test_toggle_collapses_and_mirrors_aria(self, page) -> None:  # type: ignore[no-untyped-def]
        _goto(page, "saas-shell", _VIEWPORTS["desktop"])
        state = "e => e.getAttribute('data-sidebar')"
        assert page.eval_on_selector(".app-shell", state) == "open"
        page.click("[data-sidebar-toggle]")
        page.wait_for_timeout(100)
        assert page.eval_on_selector(".app-shell", state) == "closed"
        assert (
            page.eval_on_selector("[data-sidebar-toggle]", "e => e.getAttribute('aria-expanded')")
            == "false"
        )
        page.click("[data-sidebar-toggle]")
        page.wait_for_timeout(100)
        assert page.eval_on_selector(".app-shell", state) == "open"

    def test_routed_navigation_swaps_only_the_main_slot(self, page) -> None:  # type: ignore[no-untyped-def]
        _goto(page, "saas-shell", _VIEWPORTS["desktop"])
        page.click('.sidebar-nav-link[hx-get$="invoices"]')
        page.wait_for_timeout(150)
        assert "routed workspace swapped" in page.inner_text("#main-content")
        # the shell + sidebar survived the navigation
        assert page.eval_on_selector(".app-shell", "e => e.getAttribute('data-sidebar')") == "open"
        assert page.query_selector(".sidebar-brand") is not None

    def test_sidebar_offsets_content_on_desktop_overlays_on_phone(self, page) -> None:  # type: ignore[no-untyped-def]
        """The component's deliberate media query: ≥64rem the open sidebar
        pads the content pane; narrow, the pane takes the full width and the
        sidebar overlays (off-canvas when closed)."""
        _goto(page, "saas-shell", _VIEWPORTS["desktop"])
        pad = page.eval_on_selector(".app-content", "e => getComputedStyle(e).paddingInlineStart")
        assert pad == "256px", f"desktop open-sidebar content offset: {pad}"
        _goto(page, "saas-shell", _VIEWPORTS["phone"])
        pad = page.eval_on_selector(".app-content", "e => getComputedStyle(e).paddingInlineStart")
        assert pad == "0px", f"phone: content must take the full width: {pad}"

    def test_fixed_sidebar_positions_at_page_origin(self, page) -> None:  # type: ignore[no-untyped-def]
        """The iframe replaced the translateZ device-frame hack: the live
        page is a REAL browsing context, so position:fixed means the page
        viewport — the sidebar sits at the origin, exactly as shipped."""
        _goto(page, "saas-shell", _VIEWPORTS["desktop"])
        box = page.eval_on_selector(
            ".sidebar",
            "e => { const r = e.getBoundingClientRect(); return [r.left, r.top]; }",
        )
        assert box[0] <= 1 and box[1] <= 1, f"fixed sidebar at page origin: {box}"


def test_blueprint_doc_pages_embed_the_live_iframe(page) -> None:  # type: ignore[no-untyped-def]
    """The doc page never inlines full-page markup (the Pages-layout
    breakage class): the live rendering is an iframe onto the standalone
    page, with viewport toggle buttons resizing it."""
    page.goto((PKG / "site" / "blueprints" / "workspace-drawer.html").as_uri())
    page.wait_for_timeout(200)
    frame_el = page.query_selector("iframe.hm-bp-frame")
    assert frame_el is not None
    assert frame_el.get_attribute("src") == "workspace-drawer-live.html"
    # no inlined blueprint markup on the doc page itself
    assert page.query_selector(".hm-blueprint-live .workspace") is None
    page.click('[data-bp-width="390"]')
    # the frame width is CSS-transitioned — wait for it to settle
    page.wait_for_function(
        "Math.abs(document.querySelector('iframe.hm-bp-frame')"
        ".getBoundingClientRect().width - 390) < 2"
    )


class TestFramedHyperpartIframe:
    """The index never inlines a framed (fixed-position) Hyperpart demo
    either — the app-shell demo gets the same iframe treatment as the
    blueprints (the translateZ containment hack is gone with it)."""

    def test_index_embeds_app_shell_via_iframe(self, page) -> None:  # type: ignore[no-untyped-def]
        html = (PKG / "site" / "index.html").read_text(encoding="utf-8")
        assert 'class="hm-hp-frame" src="hyperparts/app-shell-live.html"' in html
        assert "hm-blueprint-live--framed" not in html
        assert "hm-blueprint-live" not in html  # the base rule is dead too

    def test_app_shell_live_page_renders_standalone(self, page) -> None:  # type: ignore[no-untyped-def]
        page.set_viewport_size({"width": 1280, "height": 900})
        page.goto((PKG / "site" / "hyperparts" / "app-shell-live.html").as_uri())
        page.wait_for_timeout(150)
        assert page.query_selector(".app-shell") is not None
        # the controller mounts in the standalone context
        assert page.eval_on_selector(".app-shell", "e => e.getAttribute('data-sidebar')") == "open"
        page.click("[data-sidebar-toggle]")
        page.wait_for_timeout(100)
        assert (
            page.eval_on_selector(".app-shell", "e => e.getAttribute('data-sidebar')") == "closed"
        )
