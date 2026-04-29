"""PDF viewer quality gates (#942 cycle 1c).

Browser-driven verification of the cycle 1b chrome and keyboard
shortcuts. Runs Playwright (chromium) against a static harness at
``src/dazzle_ui/runtime/static/test-pdf-viewer.html`` served via
Python's ``http.server`` — same pattern as
``test_dashboard_gates.py``.

Three classes of gate:

1. **Layout invariants** — the chrome's geometry has to hold
   regardless of viewport (header anchored top, footer anchored
   bottom, body fills the gap, no overflow).
2. **Keyboard wiring** — Esc / j / k / arrows actually fire
   navigation; modifier and editable suppression behaves as
   advertised.
3. **Visual capture** — screenshots of every variant land in
   ``dev_docs/pdf-viewer-screenshots/`` for human inspection.
   Filenames are deterministic so ``git status`` shows what
   changed when CSS shifts. Not a strict comparison gate (cross-OS
   antialiasing makes pixel-diff brittle); the layout assertions
   above carry the load-bearing checks.

Skipped wholesale when Playwright is unavailable (mirrors the
dashboard-gates skip).
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("playwright.sync_api")

from playwright.sync_api import sync_playwright  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = REPO_ROOT / "src/dazzle_ui/runtime/static"
SCREENSHOT_DIR = REPO_ROOT / "dev_docs/pdf-viewer-screenshots"
HARNESS_PORT = 8767  # different from dashboard's 8766 — both can run together


@pytest.fixture(scope="module")
def server() -> Any:
    """Static-files server pointing at the runtime/static dir."""
    proc = subprocess.Popen(
        [
            "python3",
            "-m",
            "http.server",
            str(HARNESS_PORT),
            "--directory",
            str(STATIC_DIR),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(0.5)
    base = f"http://localhost:{HARNESS_PORT}/test-pdf-viewer.html"
    yield base
    proc.terminate()
    proc.wait()


@pytest.fixture(scope="module")
def browser() -> Any:
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


def _new_page(
    browser: Any,
    server: str,
    *,
    variant: str = "both",
    dark: bool = False,
    embed: bool = False,
) -> Any:
    """Open the harness in a fresh page and wait for the bridge to
    register the pdf-viewer widget. ``variant`` controls sibling-
    nav presence; ``dark`` mirrors the cycle-1d theme toggle;
    ``embed`` swaps the body's div stub for an actual
    ``<embed type="application/pdf" src="about:blank">`` so cycle
    1h gates can exercise the production layout pathway."""
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    qs = f"?variant={variant}"
    if dark:
        qs += "&dark=1"
    if embed:
        qs += "&embed=1"
    page.goto(f"{server}{qs}")
    # Bridge is loaded `defer`; wait for the registry to be present.
    page.wait_for_function(
        "window.pdfViewerGates && window.pdfViewerGates.widgetMounted().bridgePresent",
        timeout=5000,
    )
    return page


def _resolved_luminance(s: str) -> float:
    """Return a 0–1 perceptual lightness for any colour function
    Chromium's getComputedStyle might return.

    Chromium 141+ preserves the source colour function — tokens.css
    uses ``oklch(...)`` so we get oklch back. Older browsers
    normalise to ``rgb(...)`` / ``rgba(...)``. Both shapes carry
    enough info to answer the binary question the gates ask:
    "is this band lighter than 0.5 lightness?".

    For ``oklch(L C H[ / A])`` the L term IS the perceptual
    lightness in [0, 1]; just read it. For ``rgb(R, G, B)`` /
    ``rgba(R, G, B, A)`` we average the channels — crude but
    sufficient as a binary-mode classifier.
    """
    s = s.strip()
    if s.startswith("oklch("):
        body = s[s.index("(") + 1 : s.rindex(")")].strip()
        # Drop alpha if present: "0.985 0.002 247.84 / 0.5"
        if "/" in body:
            body = body[: body.index("/")].strip()
        # Tokens are space-separated; oklch L can be `0.985` or `98.5%`.
        first = body.split()[0]
        if first.endswith("%"):
            return float(first[:-1]) / 100.0
        return float(first)
    if s.startswith("rgb(") or s.startswith("rgba("):
        body = s[s.index("(") + 1 : s.rindex(")")]
        parts = [p.strip() for p in body.replace(",", " ").split()]
        rgb = [float(p) for p in parts[:3]]
        return sum(rgb) / (3 * 255)
    raise ValueError(f"unrecognised colour function: {s!r}")


_COLOUR_FUNC_PREFIXES = ("rgb(", "rgba(", "oklch(", "color(", "hsl(", "hsla(")


def _is_colour_function(s: str) -> bool:
    return any(s.startswith(p) for p in _COLOUR_FUNC_PREFIXES)


# ---------------------------------------------------------------------------
# Gate 1 — chrome elements present
# ---------------------------------------------------------------------------


class TestChromeStructure:
    def test_all_chrome_elements_render(self, browser: Any, server: str) -> None:
        page = _new_page(browser, server)
        present = page.evaluate("window.pdfViewerGates.chromePresent()")
        assert present == {
            "host": True,
            "header": True,
            "body": True,
            "footer": True,
            "back": True,
            "title": True,
        }
        page.screenshot(path=str(SCREENSHOT_DIR / "default-both-siblings.png"))
        page.close()

    def test_data_dz_widget_marker_present(self, browser: Any, server: str) -> None:
        """Confirms the bridge's mount point is on the wrapper —
        without it the keyboard handler never installs."""
        page = _new_page(browser, server)
        marker = page.locator("#pdf-viewer-host").get_attribute("data-dz-widget")
        assert marker == "pdf-viewer"
        page.close()


# ---------------------------------------------------------------------------
# Gate 2 — layout invariants
# ---------------------------------------------------------------------------


class TestChromeLayout:
    """Geometric invariants that hold across viewports.

    We check arrangement and bounds rather than exact pixel values
    so the gates survive harmless token tweaks (font-size bumps,
    spacing nudges) but catch real regressions (header overflow,
    footer occlusion, body collapse)."""

    def test_three_band_vertical_stack(self, browser: Any, server: str) -> None:
        """Header above body above footer; all three contiguous."""
        page = _new_page(browser, server)
        rects = page.evaluate("window.pdfViewerGates.chromeRectangles()")
        host = rects["host"]
        header = rects["header"]
        body = rects["body"]
        footer = rects["footer"]

        # Header anchored at top; footer anchored at bottom; body
        # spans the gap.
        assert header["top"] == pytest.approx(host["top"], abs=1)
        assert header["bottom"] == pytest.approx(body["top"], abs=1)
        assert body["bottom"] == pytest.approx(footer["top"], abs=1)
        assert footer["bottom"] == pytest.approx(host["bottom"], abs=1)
        # Body MUST be the largest band — it's the content area.
        assert body["height"] > header["height"]
        assert body["height"] > footer["height"]
        page.close()

    def test_full_viewport_coverage(self, browser: Any, server: str) -> None:
        """Wrapper fills the viewport — no whitespace gutters above
        the header or below the footer."""
        page = _new_page(browser, server)
        rects = page.evaluate("window.pdfViewerGates.chromeRectangles()")
        host = rects["host"]
        viewport = page.viewport_size
        assert host["top"] == pytest.approx(0, abs=1)
        assert host["left"] == pytest.approx(0, abs=1)
        assert host["width"] == pytest.approx(viewport["width"], abs=1)
        assert host["height"] == pytest.approx(viewport["height"], abs=1)
        page.close()

    def test_header_chrome_height_reasonable(self, browser: Any, server: str) -> None:
        """Header is compact — between 30 and 80 px on a 1280px-wide
        viewport. Catches regressions where padding tokens balloon
        or font-size tokens shift the chrome to comically tall."""
        page = _new_page(browser, server)
        rects = page.evaluate("window.pdfViewerGates.chromeRectangles()")
        assert 30 <= rects["header"]["height"] <= 80
        assert 24 <= rects["footer"]["height"] <= 60
        page.close()

    def test_narrow_viewport_hides_back_label(self, browser: Any, server: str) -> None:
        """Below 640px the back-link label hides (icon alone speaks
        the action). Pinned because it's a deliberate responsive
        decision in pdf-viewer.css."""
        page = browser.new_page(viewport={"width": 480, "height": 800})
        page.goto(f"{server}?variant=both")
        page.wait_for_function(
            "window.pdfViewerGates && window.pdfViewerGates.widgetMounted().bridgePresent",
            timeout=5000,
        )
        label = page.locator(".dz-pdf-viewer-back-label")
        assert label.evaluate("el => getComputedStyle(el).display") == "none"
        page.screenshot(path=str(SCREENSHOT_DIR / "narrow-viewport-480.png"))
        page.close()


# ---------------------------------------------------------------------------
# Gate 3 — keyboard wiring
# ---------------------------------------------------------------------------


class TestKeyboardShortcuts:
    """Hash-based assertions: harness uses ``#back`` / ``#prev`` /
    ``#next`` URLs so navigation produces a hashchange we can read
    off ``page.url`` without an actual page load."""

    def _press(self, page: Any, key: str) -> str:
        page.keyboard.press(key)
        # Hashchange fires synchronously after location.href set.
        page.wait_for_timeout(50)
        return str(page.url)

    def test_escape_navigates_to_back(self, browser: Any, server: str) -> None:
        page = _new_page(browser, server)
        url = self._press(page, "Escape")
        assert url.endswith("#back")
        page.close()

    def test_j_key_navigates_to_prev(self, browser: Any, server: str) -> None:
        page = _new_page(browser, server)
        url = self._press(page, "j")
        assert url.endswith("#prev")
        page.close()

    def test_k_key_navigates_to_next(self, browser: Any, server: str) -> None:
        page = _new_page(browser, server)
        url = self._press(page, "k")
        assert url.endswith("#next")
        page.close()

    def test_arrow_left_navigates_to_prev(self, browser: Any, server: str) -> None:
        page = _new_page(browser, server)
        url = self._press(page, "ArrowLeft")
        assert url.endswith("#prev")
        page.close()

    def test_arrow_right_navigates_to_next(self, browser: Any, server: str) -> None:
        page = _new_page(browser, server)
        url = self._press(page, "ArrowRight")
        assert url.endswith("#next")
        page.close()


# ---------------------------------------------------------------------------
# Gate 4 — suppression
# ---------------------------------------------------------------------------


class TestKeyboardSuppression:
    def test_typing_in_input_does_not_navigate(self, browser: Any, server: str) -> None:
        """Critical safety property — without this, every form
        autocompletion that types 'j' or 'k' would yank the user to
        the next manuscript."""
        page = _new_page(browser, server)
        # Park a known hash, focus the harness's text input, then
        # type 'jjkk' — none of the keys should change location.hash.
        page.evaluate("window.location.hash = 'sentinel'")
        page.wait_for_timeout(20)
        page.locator("#harness-text-input").click()
        page.locator("#harness-text-input").fill("")  # ensure focus
        page.keyboard.type("jjkk")
        page.wait_for_timeout(50)
        assert "#sentinel" in str(page.url), (
            "j/k typed into an input must NOT trigger sibling navigation"
        )
        page.close()

    def test_modifier_keys_pass_through(self, browser: Any, server: str) -> None:
        """Cmd+j / Ctrl+k must NOT navigate — those are typically
        browser shortcuts (downloads, address bar) and shouldn't be
        hijacked."""
        page = _new_page(browser, server)
        page.evaluate("window.location.hash = 'sentinel'")
        page.wait_for_timeout(20)
        page.keyboard.press("Meta+j")
        page.keyboard.press("Control+k")
        page.wait_for_timeout(50)
        assert "#sentinel" in str(page.url), (
            "modifier-keyed j/k must pass through, not hijack navigation"
        )
        page.close()


# ---------------------------------------------------------------------------
# Gate 5 — variant rendering (visual capture only)
# ---------------------------------------------------------------------------


class TestVariantRendering:
    """Each variant renders a different chrome shape. We capture
    screenshots for human inspection; the structural assertions
    elsewhere catch the load-bearing regressions."""

    def test_no_siblings_variant(self, browser: Any, server: str) -> None:
        page = _new_page(browser, server, variant="none")
        # Sibling nav block is removed entirely when both URLs
        # are unset.
        nav_count = page.locator(".dz-pdf-viewer-nav").count()
        assert nav_count == 0
        page.screenshot(path=str(SCREENSHOT_DIR / "no-siblings.png"))
        page.close()

    def test_prev_only_variant(self, browser: Any, server: str) -> None:
        page = _new_page(browser, server, variant="prev")
        # Both buttons render, but next is aria-disabled (so the
        # chrome stays symmetrical even with one direction available).
        next_btn = page.locator("#harness-next")
        assert next_btn.get_attribute("aria-disabled") == "true"
        # j fires; k does NOT (the data-dz-next-url attr was stripped).
        page.evaluate("window.location.hash = 'sentinel'")
        page.wait_for_timeout(20)
        page.keyboard.press("k")
        page.wait_for_timeout(50)
        assert "#sentinel" in str(page.url), "k must no-op when next-url is unset"
        page.screenshot(path=str(SCREENSHOT_DIR / "prev-only.png"))
        page.close()

    def test_next_only_variant(self, browser: Any, server: str) -> None:
        page = _new_page(browser, server, variant="next")
        prev_btn = page.locator("#harness-prev")
        assert prev_btn.get_attribute("aria-disabled") == "true"
        page.evaluate("window.location.hash = 'sentinel'")
        page.wait_for_timeout(20)
        page.keyboard.press("j")
        page.wait_for_timeout(50)
        assert "#sentinel" in str(page.url), "j must no-op when prev-url is unset"
        page.screenshot(path=str(SCREENSHOT_DIR / "next-only.png"))
        page.close()


# ---------------------------------------------------------------------------
# Gate 6 — dark-mode parity (#942 cycle 1d)
# ---------------------------------------------------------------------------


class TestDarkModeParity:
    """Every chrome band must adapt to the dark-mode toggle from
    #938. Catches the class of bug where a CSS rule uses a raw
    neutral ramp value (e.g. ``var(--neutral-100)``) instead of a
    semantic token (``var(--colour-bg)``) — the raw value won't
    flip under ``[data-theme="dark"]``, leaving a jarring light
    panel in an otherwise-dark viewer."""

    def test_all_bands_resolve_to_concrete_colours(self, browser: Any, server: str) -> None:
        """First contract: every chrome band must compute a real
        colour function. If a token didn't resolve, the browser
        surfaces ``rgba(0, 0, 0, 0)`` (transparent) or an empty
        string and the chrome visually merges with the page bg.

        Chromium 141+ preserves the source colour function — tokens.css
        uses ``oklch(...)`` so we get oklch back; older browsers
        normalise to ``rgb(...)`` / ``rgba(...)``. Both shapes are
        accepted by ``_is_colour_function``."""
        for theme in ("light", "dark"):
            page = _new_page(browser, server, dark=(theme == "dark"))
            bg = page.evaluate("window.pdfViewerGates.chromeBackgrounds()")
            for band in ("host", "header", "body", "footer", "kbd"):
                assert bg[band] and _is_colour_function(bg[band]), (
                    f"{theme} mode: band {band!r} resolved to {bg[band]!r} "
                    "(expected a colour function — rgb / rgba / oklch / etc)"
                )
            page.close()

    def test_chrome_flips_between_light_and_dark(self, browser: Any, server: str) -> None:
        """Header, footer, body, and the kbd hint backgrounds must
        ALL change between the two themes — otherwise something is
        pinned to a non-flipping ramp value."""
        light_page = _new_page(browser, server)
        light_bg = light_page.evaluate("window.pdfViewerGates.chromeBackgrounds()")
        light_page.close()

        dark_page = _new_page(browser, server, dark=True)
        dark_bg = dark_page.evaluate("window.pdfViewerGates.chromeBackgrounds()")
        dark_page.screenshot(path=str(SCREENSHOT_DIR / "dark-mode.png"))
        dark_page.close()

        for band in ("header", "body", "footer", "kbd"):
            assert light_bg[band] != dark_bg[band], (
                f"band {band!r} did not flip between themes — "
                f"light: {light_bg[band]}, dark: {dark_bg[band]}. "
                "Raw ramp tokens (e.g. var(--neutral-100)) don't "
                "respect data-theme; use semantic tokens "
                "(var(--colour-bg) / --colour-surface)."
            )

    def test_dark_mode_chrome_is_actually_dark(self, browser: Any, server: str) -> None:
        """Sanity check: dark-mode header / body / footer all read
        with luminance < 0.5. Catches a regression where the flip
        happens but lands on a still-light value."""
        page = _new_page(browser, server, dark=True)
        bg = page.evaluate("window.pdfViewerGates.chromeBackgrounds()")
        for band in ("host", "header", "body", "footer"):
            lum = _resolved_luminance(bg[band])
            assert lum < 0.5, f"dark mode {band!r} luminance {lum:.2f} ≥ 0.5; resolved {bg[band]!r}"
        page.close()

    def test_body_distinct_from_header_and_footer(self, browser: Any, server: str) -> None:
        """The body bg must differ from the header/footer surface in
        both themes — otherwise the chrome bands and content area
        merge visually and the viewer reads as one flat panel."""
        for theme in ("light", "dark"):
            page = _new_page(browser, server, dark=(theme == "dark"))
            bg = page.evaluate("window.pdfViewerGates.chromeBackgrounds()")
            assert bg["body"] != bg["header"], (
                f"{theme}: body bg {bg['body']!r} equals header bg — "
                "no visual separation between chrome and content"
            )
            assert bg["body"] != bg["footer"], f"{theme}: body bg {bg['body']!r} equals footer bg"
            page.close()


# ---------------------------------------------------------------------------
# Gate 7 — focus visibility (#942 cycle 1f)
# ---------------------------------------------------------------------------


def _focus_signature(page: Any, selector: str) -> dict[str, str]:
    """Read every focus-relevant computed style off ``selector`` —
    used to compare unfocused vs focused state. If at least one
    property differs, the element has a visible focus indicator.
    If ALL match, focus is invisible (regression)."""
    return page.evaluate(
        """(sel) => {
            const el = document.querySelector(sel);
            if (!el) return null;
            const cs = getComputedStyle(el);
            return {
                outlineStyle: cs.outlineStyle,
                outlineWidth: cs.outlineWidth,
                outlineColor: cs.outlineColor,
                boxShadow: cs.boxShadow,
                borderColor: cs.borderColor,
                background: cs.backgroundColor,
            };
        }""",
        selector,
    )


class TestFocusVisibility:
    """Every interactive element in the chrome must show a focus
    indicator when reached by Tab. The default UA stylesheet draws
    a focus ring; component CSS often nukes it with ``outline: none``
    without providing a replacement (``box-shadow``, custom outline,
    border colour change). Without a visible indicator, keyboard-only
    users can't tell where focus lives — a hard accessibility gate.

    Strategy: snapshot the computed styles before focus, focus the
    element via ``page.focus()``, snapshot again. Assert at least
    one focus-related property changed.
    """

    _SELECTORS = [
        ".dz-pdf-viewer-back",
        "#harness-prev",
        "#harness-next",
    ]

    def test_back_link_focus_visible(self, browser: Any, server: str) -> None:
        page = _new_page(browser, server)
        sel = ".dz-pdf-viewer-back"
        before = _focus_signature(page, sel)
        page.focus(sel)
        page.wait_for_timeout(20)
        after = _focus_signature(page, sel)
        assert before != after, (
            f"focus on {sel!r} produced no visible style change; "
            f"computed styles before == after: {before}. "
            "Replace `outline: none` with a focus indicator "
            "(e.g. box-shadow: 0 0 0 1px var(--colour-brand))."
        )
        page.close()

    def test_prev_nav_focus_visible(self, browser: Any, server: str) -> None:
        page = _new_page(browser, server)
        sel = "#harness-prev"
        before = _focus_signature(page, sel)
        page.focus(sel)
        page.wait_for_timeout(20)
        after = _focus_signature(page, sel)
        assert before != after, f"focus on {sel!r} produced no visible style change; {before}"
        page.close()

    def test_next_nav_focus_visible(self, browser: Any, server: str) -> None:
        page = _new_page(browser, server)
        sel = "#harness-next"
        before = _focus_signature(page, sel)
        page.focus(sel)
        page.wait_for_timeout(20)
        after = _focus_signature(page, sel)
        assert before != after, f"focus on {sel!r} produced no visible style change; {before}"
        page.close()

    def test_focus_visible_in_dark_mode(self, browser: Any, server: str) -> None:
        """Focus indicators must remain visible in dark mode too —
        the brand colour token is theme-independent so a brand-tinted
        ring works in both themes, but a fix that uses an undefined
        token (or a literal dark colour) would fail this gate."""
        page = _new_page(browser, server, dark=True)
        for sel in self._SELECTORS:
            before = _focus_signature(page, sel)
            page.focus(sel)
            page.wait_for_timeout(20)
            after = _focus_signature(page, sel)
            assert before != after, f"dark mode: focus on {sel!r} invisible — {before}"
        page.close()

    def test_focus_visible_in_forced_colors(self, browser: Any, server: str) -> None:
        """Windows High Contrast / Forced Colors mode: ``box-shadow``
        is suppressed by user-agent default. A focus indicator
        relying solely on box-shadow disappears for these users.
        Component must provide an ``outline`` fallback inside
        ``@media (forced-colors: active)``.

        Playwright emulates forced colours via the
        ``forced_colors`` context option. We rebuild the page with
        that option on and re-check the focus signature: outline
        MUST be present (system colour), box-shadow may or may not
        be."""
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 800},
            forced_colors="active",
        )
        page = ctx.new_page()
        page.goto(f"{server}?variant=both")
        page.wait_for_function(
            "window.pdfViewerGates && window.pdfViewerGates.widgetMounted().bridgePresent",
            timeout=5000,
        )
        for sel in self._SELECTORS:
            page.focus(sel)
            page.wait_for_timeout(20)
            sig = _focus_signature(page, sel)
            has_outline = sig["outlineStyle"] not in ("none", "") and sig["outlineWidth"] not in (
                "0px",
                "",
            )
            assert has_outline, (
                f"forced-colors mode: focus on {sel!r} has no outline; "
                f"sig={sig}. Add `@media (forced-colors: active)` block "
                "with outline so Windows High Contrast users see focus."
            )
        ctx.close()

    def test_focus_uses_real_ring_indicator(self, browser: Any, server: str) -> None:
        """Stricter accessibility contract: focus must produce either
        a non-``none`` outline OR a non-``none`` box-shadow — not
        just a subtle background tint. Aligns the PDF viewer chrome
        with the framework convention (``outline: none; box-shadow:
        0 0 0 1px var(--colour-brand)``) already used by
        ``.dz-workspace-context-select``, ``.dz-toggle-item``, etc."""
        page = _new_page(browser, server)
        for sel in self._SELECTORS:
            page.focus(sel)
            page.wait_for_timeout(20)
            sig = _focus_signature(page, sel)
            has_outline = sig["outlineStyle"] not in ("none", "") and sig["outlineWidth"] not in (
                "0px",
                "",
            )
            has_shadow = sig["boxShadow"] not in ("none", "")
            assert has_outline or has_shadow, (
                f"focus on {sel!r} has neither outline nor box-shadow ring; "
                f"sig={sig}. Subtle background changes alone don't meet "
                "WCAG focus-visibility expectations."
            )
        page.close()


# ---------------------------------------------------------------------------
# Gate 8 — production embed layout (#942 cycle 1h)
# ---------------------------------------------------------------------------


class TestEmbedLayout:
    """The chrome's body slot ships a ``<embed type="application/pdf">``
    in production but the harness uses a ``<div>`` stub for visual
    stability across browsers (each ships its own PDF renderer
    chrome). The stub passes layout assertions; that doesn't prove
    the real ``<embed>`` lays out the same way.

    These gates run against ``?embed=1``, which swaps in the actual
    ``<embed type="application/pdf" src="about:blank">``. The empty
    src renders a blank plugin frame but the layout box is real —
    the gates pin that box to the same dimensions the stub had."""

    def test_embed_element_replaces_stub(self, browser: Any, server: str) -> None:
        """Sanity: ?embed=1 inserts <embed>, removes the div stub."""
        page = _new_page(browser, server, embed=True)
        embed_count = page.locator("#harness-body-embed").count()
        stub_count = page.locator("#harness-body-stub").count()
        assert embed_count == 1, f"expected 1 embed, found {embed_count}"
        assert stub_count == 0, f"stub should be removed, found {stub_count}"
        page.close()

    def test_embed_fills_body_container(self, browser: Any, server: str) -> None:
        """The <embed> must occupy the entire body slot —
        width: 100% / height: 100% from .dz-pdf-viewer-embed CSS.
        If the embed renders smaller than the container (some
        browsers default <embed> to 300×150), there'd be a
        background gap visible behind it."""
        page = _new_page(browser, server, embed=True)
        body_rect = page.evaluate("document.getElementById('harness-body').getBoundingClientRect()")
        embed_rect = page.evaluate(
            "document.getElementById('harness-body-embed').getBoundingClientRect()"
        )
        assert embed_rect["width"] == pytest.approx(body_rect["width"], abs=1), (
            f"embed width {embed_rect['width']} ≠ body width {body_rect['width']}"
        )
        assert embed_rect["height"] == pytest.approx(body_rect["height"], abs=1), (
            f"embed height {embed_rect['height']} ≠ body height {body_rect['height']}"
        )
        page.screenshot(path=str(SCREENSHOT_DIR / "real-embed.png"))
        page.close()

    def test_embed_variant_preserves_chrome_layout(self, browser: Any, server: str) -> None:
        """Three-band stack invariant must still hold when the body
        slot contains a real <embed> rather than the div stub.
        Catches the class of bug where the embed plugin frame
        nudges the layout (rare but possible across browsers)."""
        page = _new_page(browser, server, embed=True)
        rects = page.evaluate("window.pdfViewerGates.chromeRectangles()")
        host = rects["host"]
        header = rects["header"]
        body = rects["body"]
        footer = rects["footer"]
        assert header["bottom"] == pytest.approx(body["top"], abs=1)
        assert body["bottom"] == pytest.approx(footer["top"], abs=1)
        assert footer["bottom"] == pytest.approx(host["bottom"], abs=1)
        page.close()


# ---------------------------------------------------------------------------
# Gate 9 — panel slot (#942 cycle 2a)
# ---------------------------------------------------------------------------


def _panel_visible(page: Any) -> bool:
    """A panel is visible when its bounding-rect left edge is
    on-screen — hidden state has it translated off-screen via
    ``transform: translateX(100%)``."""
    return bool(
        page.evaluate(
            """() => {
                const panel = document.getElementById('harness-panel');
                if (!panel) return false;
                const rect = panel.getBoundingClientRect();
                return rect.left < window.innerWidth - 10;
            }"""
        )
    )


class TestPanelSlot:
    """Cycle 2a — optional right-side panel for related-entity content.
    CSS-only show/hide via a hidden checkbox toggled by the bridge
    keyboard handler. Panel structure is always rendered in the
    harness; production renders it conditionally on ``panel_html``
    (covered by tests/unit/test_pdf_viewer_component.py)."""

    def test_panel_hidden_by_default(self, browser: Any, server: str) -> None:
        page = _new_page(browser, server)
        assert not _panel_visible(page), "panel must start hidden (translateX(100%))"
        page.close()

    def test_p_key_opens_panel(self, browser: Any, server: str) -> None:
        page = _new_page(browser, server)
        assert not _panel_visible(page)
        page.keyboard.press("p")
        page.wait_for_timeout(250)
        assert _panel_visible(page), "p key must toggle the panel open"
        page.screenshot(path=str(SCREENSHOT_DIR / "panel-open.png"))
        page.close()

    def test_p_key_closes_panel_when_open(self, browser: Any, server: str) -> None:
        page = _new_page(browser, server)
        page.keyboard.press("p")
        page.wait_for_timeout(250)
        assert _panel_visible(page)
        page.keyboard.press("p")
        page.wait_for_timeout(250)
        assert not _panel_visible(page), "second p press must close the panel"
        page.close()

    def test_escape_closes_panel_before_navigating_back(self, browser: Any, server: str) -> None:
        """Esc with panel open: close the panel, DON'T navigate back.
        Esc with panel closed: navigate to back URL. Matches the
        dialog/modal convention users expect."""
        page = _new_page(browser, server)
        page.evaluate("window.location.hash = 'sentinel'")
        page.wait_for_timeout(20)
        page.keyboard.press("p")
        page.wait_for_timeout(250)
        assert _panel_visible(page)
        page.keyboard.press("Escape")
        page.wait_for_timeout(250)
        assert not _panel_visible(page), "first Esc must close the panel"
        assert "#sentinel" in str(page.url), (
            f"Esc with open panel must NOT navigate back; it closes the panel first. url={page.url}"
        )
        page.keyboard.press("Escape")
        page.wait_for_timeout(50)
        assert page.url.endswith("#back"), "second Esc must navigate to back URL"
        page.close()

    def test_close_button_closes_panel(self, browser: Any, server: str) -> None:
        """Native checkbox+label binding: clicking the close
        affordance flips the toggle without any JS."""
        page = _new_page(browser, server)
        page.keyboard.press("p")
        page.wait_for_timeout(250)
        assert _panel_visible(page)
        page.locator("#harness-panel-close").click()
        page.wait_for_timeout(250)
        assert not _panel_visible(page), "close-button click must hide the panel"
        page.close()

    def test_p_in_input_does_not_toggle(self, browser: Any, server: str) -> None:
        """Editable suppression must extend to the panel toggle —
        typing 'p' into a search field shouldn't yank the panel
        open."""
        page = _new_page(browser, server)
        page.locator("#harness-text-input").click()
        page.locator("#harness-text-input").fill("")
        page.keyboard.type("ppp")
        page.wait_for_timeout(250)
        assert not _panel_visible(page), "typing 'p' into an input must NOT toggle the panel"
        page.close()

    def test_modifier_p_does_not_toggle(self, browser: Any, server: str) -> None:
        """Cmd+P / Ctrl+P are the browser's print shortcuts — the
        viewer must not hijack them."""
        page = _new_page(browser, server)
        page.keyboard.press("Meta+p")
        page.wait_for_timeout(50)
        assert not _panel_visible(page), "Cmd+P must pass through to the browser"
        page.keyboard.press("Control+p")
        page.wait_for_timeout(50)
        assert not _panel_visible(page), "Ctrl+P must pass through to the browser"
        page.close()

    def test_panel_geometry_when_open(self, browser: Any, server: str) -> None:
        """When open: anchored to the trailing edge, full-height of
        the body, 360px wide on desktop."""
        page = _new_page(browser, server)
        page.keyboard.press("p")
        page.wait_for_timeout(250)
        rect = page.evaluate("document.getElementById('harness-panel').getBoundingClientRect()")
        body_rect = page.evaluate(
            "document.querySelector('.dz-pdf-viewer-body').getBoundingClientRect()"
        )
        viewport = page.viewport_size
        assert rect["right"] == pytest.approx(viewport["width"], abs=1)
        assert rect["width"] == pytest.approx(360, abs=2)
        assert rect["top"] == pytest.approx(body_rect["top"], abs=1)
        assert rect["bottom"] == pytest.approx(body_rect["bottom"], abs=1)
        page.close()

    def test_panel_full_width_on_mobile(self, browser: Any, server: str) -> None:
        """At ≤768px the panel goes full-width (drawer pattern)."""
        page = browser.new_page(viewport={"width": 480, "height": 800})
        page.goto(f"{server}?variant=both")
        page.wait_for_function(
            "window.pdfViewerGates && window.pdfViewerGates.widgetMounted().bridgePresent",
            timeout=5000,
        )
        page.keyboard.press("p")
        page.wait_for_timeout(250)
        rect = page.evaluate("document.getElementById('harness-panel').getBoundingClientRect()")
        assert rect["width"] == pytest.approx(480, abs=2)
        page.screenshot(path=str(SCREENSHOT_DIR / "panel-mobile.png"))
        page.close()


# ---------------------------------------------------------------------------
# Gate 10 — panel focus management (#942 cycle 2b)
# ---------------------------------------------------------------------------


class TestPanelFocusManagement:
    """When the panel opens, focus moves INTO the panel so keyboard
    / screen-reader users know it appeared. When it closes, focus
    restores to the element that was active when it opened. Tab
    inside the open panel doesn't leak to the chrome behind
    (achieved via ``inert`` on header/footer/embed)."""

    def test_close_button_is_focusable_button_element(self, browser: Any, server: str) -> None:
        """Close affordance must be a real ``<button>`` (not a
        ``<label>``) so it's tabbable and ``focus()`` works on it.
        Caught the cycle 2a footgun where the label-based close
        silently no-op'd ``closeBtn.focus()``."""
        page = _new_page(browser, server)
        tag_name = page.evaluate("document.getElementById('harness-panel-close').tagName")
        assert tag_name == "BUTTON", f"close affordance must be <button>, got <{tag_name.lower()}>"
        page.close()

    def test_focus_moves_to_close_on_open(self, browser: Any, server: str) -> None:
        page = _new_page(browser, server)
        page.keyboard.press("p")
        page.wait_for_timeout(250)
        active_class = page.evaluate("document.activeElement.className")
        assert "panel-close" in active_class, (
            f"focus must move to close button on panel open; active class={active_class!r}"
        )
        page.close()

    def test_focus_restores_on_close(self, browser: Any, server: str) -> None:
        """Focus snapshot before open → restored after close. Test
        sets up a known-focusable element (the back link), opens
        the panel, closes it, asserts focus returned to back link."""
        page = _new_page(browser, server)
        page.focus(".dz-pdf-viewer-back")
        page.wait_for_timeout(20)
        page.keyboard.press("p")
        page.wait_for_timeout(250)
        assert "panel-close" in page.evaluate("document.activeElement.className")
        page.keyboard.press("p")
        page.wait_for_timeout(250)
        active_class = page.evaluate("document.activeElement.className")
        assert "dz-pdf-viewer-back" in active_class, (
            f"focus must restore to back link after panel close; active class={active_class!r}"
        )
        page.close()

    def test_background_is_inert_when_panel_open(self, browser: Any, server: str) -> None:
        """Header / footer / embed are marked ``inert`` when the
        panel is open so Tab from inside the panel doesn't leak
        back to the chrome bands behind it."""
        page = _new_page(browser, server)
        page.keyboard.press("p")
        page.wait_for_timeout(250)
        bands = page.evaluate(
            """() => {
                const sels = [
                    ".dz-pdf-viewer-header",
                    ".dz-pdf-viewer-footer",
                    ".dz-pdf-viewer-embed",
                ];
                return sels.map(s => {
                    const el = document.querySelector(s);
                    return el ? el.inert : null;
                });
            }"""
        )
        # Embed may be null in the harness (it's a div stub by
        # default, no .dz-pdf-viewer-embed selector match), so
        # filter to non-null and assert all true.
        observed = [b for b in bands if b is not None]
        assert observed and all(observed), (
            f"all background bands present must be inert when panel open: {bands}"
        )
        page.close()

    def test_background_inert_clears_on_close(self, browser: Any, server: str) -> None:
        """Closing the panel must remove ``inert`` so the chrome
        becomes interactive again."""
        page = _new_page(browser, server)
        page.keyboard.press("p")
        page.wait_for_timeout(250)
        page.keyboard.press("p")
        page.wait_for_timeout(250)
        bands = page.evaluate(
            """() => {
                const sels = [
                    ".dz-pdf-viewer-header",
                    ".dz-pdf-viewer-footer",
                ];
                return sels.map(s => {
                    const el = document.querySelector(s);
                    return el ? el.inert : null;
                });
            }"""
        )
        assert not any(b for b in bands if b is not None), (
            f"background bands must NOT be inert after panel close: {bands}"
        )
        page.close()
