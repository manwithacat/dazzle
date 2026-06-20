"""Visual smoke for the v0.71.12 site-primitive migration (#1113).

The DaisyUI + Tailwind CDN tags that used to style `stat-value`,
`stat-title`, `alert alert-{level}`, `bg-base-100` were removed; the
emitters now produce native `.dz-stats-grid` / `.dz-stat` /
`.dz-stat-value` / `.dz-stat-title` and `.dz-toast[data-dz-toast-level]`
classes defined in `static/css/site-sections.css`. This test renders
each primitive into a standalone HTML page that loads the bundled
Dazzle CSS, captures one PNG per primitive for human review, and
asserts:

- The element renders with a non-zero bounding box (CSS classes
  resolved against the bundle).
- Computed background-color isn't `rgba(0,0,0,0)` (the class actually
  paints — catches the failure mode where the class name is
  emitted but no rule exists).
- For toasts: the left border tone matches the requested level.
- No console errors on load.

Run with `pytest tests/visual/ -m visual`.
"""

from __future__ import annotations

from html import escape as _escape
from pathlib import Path

import pytest

# Playwright is an opt-in test dep; the default CI runner doesn't
# install it. importorskip short-circuits collection cleanly — the
# `@pytest.mark.visual` marker fires too late to dodge an
# unconditional top-level import. Same shape as
# test_onboarding_visual_smoke.py.
sync_playwright_module = pytest.importorskip("playwright.sync_api")
sync_playwright = sync_playwright_module.sync_playwright
Page = sync_playwright_module.Page

from dazzle.page.runtime.css_loader import get_bundled_css  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = REPO_ROOT / "tests" / "visual" / "_artifacts"


def _harness_html(body_inner: str, *, body_class: str = "dz-site") -> str:
    """Wrap a fragment in a minimal page that loads the framework CSS."""
    css = get_bundled_css()
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Site primitive visual harness</title>
<style>{css}</style>
</head>
<body class="{body_class}">
<main style="max-width: 64rem; margin: 2rem auto; padding: 0 2rem;">
{body_inner}
</main>
</body>
</html>
"""


@pytest.fixture(scope="module")
def _harness_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("site_primitive_harness")


@pytest.fixture(scope="module")
def _browser():
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


def _bg_is_painted(bg: str) -> bool:
    """A computed background is 'painted' if it isn't transparent /
    fully default. `rgba(0, 0, 0, 0)` is the browser default for an
    unstyled element."""
    bg = bg.replace(" ", "")
    return bg not in {"rgba(0,0,0,0)", "transparent", ""}


@pytest.mark.visual
def test_stats_grid_paints(_browser, _harness_dir: Path) -> None:
    """`.dz-stats-grid` + `.dz-stat` row of three KPIs renders with
    a surface background and tabular stat values."""
    fragment = (
        '<div class="dz-stats-grid">'
        '  <div class="dz-stat">'
        '    <div class="dz-stat-value">99.9%</div>'
        '    <div class="dz-stat-title">Uptime</div>'
        "  </div>"
        '  <div class="dz-stat">'
        '    <div class="dz-stat-value">142ms</div>'
        '    <div class="dz-stat-title">p95 latency</div>'
        "  </div>"
        '  <div class="dz-stat">'
        '    <div class="dz-stat-value">1,284</div>'
        '    <div class="dz-stat-title">Active users</div>'
        "  </div>"
        "</div>"
    )
    harness = _harness_dir / "stats.html"
    harness.write_text(_harness_html(fragment))

    errors: list[str] = []
    page: Page = _browser.new_page(viewport={"width": 1280, "height": 600})
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto(harness.as_uri())
    page.wait_for_load_state("networkidle")

    grid = page.locator(".dz-stats-grid")
    assert grid.count() == 1
    box = grid.bounding_box()
    assert box is not None and box["width"] > 0 and box["height"] > 0

    bg = grid.evaluate("(el) => getComputedStyle(el).backgroundColor")
    assert _bg_is_painted(bg), f"dz-stats-grid not painted (got {bg!r})"

    # Three stat children with the expected text.
    assert page.locator(".dz-stat").count() == 3
    assert page.locator(".dz-stat-value").count() == 3
    assert page.locator(".dz-stat-title").count() == 3
    assert "99.9%" in page.content()
    assert "Uptime" in page.content()

    # Stat values should use tabular figures (CSS guarantees consistent
    # column widths) — checked via computed style.
    fv = page.locator(".dz-stat-value").first.evaluate(
        "(el) => getComputedStyle(el).fontVariantNumeric"
    )
    assert "tabular-nums" in fv, f"expected tabular-nums on dz-stat-value, got {fv!r}"

    page.screenshot(path=str(ARTIFACTS_DIR / "stats.png"))
    page.close()
    assert errors == [], f"console errors: {errors}"


@pytest.mark.visual
@pytest.mark.parametrize("level", ["info", "success", "warning", "error"])
def test_toast_level_tones_paint(level: str, _browser, _harness_dir: Path) -> None:
    """`.dz-toast[data-dz-toast-level=<level>]` paints with the expected
    border-left tone (info=brand, success=success, warning=warning,
    error=danger). Verified via computed style — and per-level
    screenshots land under _artifacts/ for human review."""
    fragment = (
        '<div style="display:flex;flex-direction:column;gap:1rem;align-items:flex-start;">'
        f'  <div class="dz-toast" data-dz-toast-level="{_escape(level, quote=True)}">'
        f"    <span>Toast example — {_escape(level)} level</span>"
        "  </div>"
        "</div>"
    )
    harness = _harness_dir / f"toast_{level}.html"
    harness.write_text(_harness_html(fragment))

    errors: list[str] = []
    page: Page = _browser.new_page(viewport={"width": 800, "height": 200})
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto(harness.as_uri())
    page.wait_for_load_state("networkidle")

    toast = page.locator(f'.dz-toast[data-dz-toast-level="{level}"]')
    assert toast.count() == 1
    box = toast.bounding_box()
    assert box is not None and box["width"] > 0 and box["height"] > 0

    bg = toast.evaluate("(el) => getComputedStyle(el).backgroundColor")
    assert _bg_is_painted(bg), f"toast {level} not painted (got {bg!r})"

    # The left border must be 4px and the colour must vary by level.
    bl_width = toast.evaluate("(el) => getComputedStyle(el).borderLeftWidth")
    bl_color = toast.evaluate("(el) => getComputedStyle(el).borderLeftColor")
    assert bl_width == "4px", f"expected 4px left border, got {bl_width!r}"
    assert _bg_is_painted(bl_color), f"left border colour transparent for {level}"

    page.screenshot(path=str(ARTIFACTS_DIR / f"toast_{level}.png"))
    page.close()
    assert errors == [], f"console errors: {errors}"


@pytest.mark.visual
def test_site_body_background_paints_without_daisyui(_browser, _harness_dir: Path) -> None:
    """`.dz-site` on <body> paints `var(--colour-bg)` directly — no
    DaisyUI `bg-base-100` needed. Confirms the CDN tag drop didn't
    leave site/task-surface pages on a transparent background."""
    fragment = (
        '<div style="padding: 2rem; border: 1px dashed gray;">'
        "<p>If this page is painted, .dz-site is doing its job.</p>"
        "</div>"
    )
    harness = _harness_dir / "site_bg.html"
    harness.write_text(_harness_html(fragment, body_class="dz-site"))

    errors: list[str] = []
    page: Page = _browser.new_page(viewport={"width": 1024, "height": 400})
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto(harness.as_uri())
    page.wait_for_load_state("networkidle")

    body_bg = page.evaluate("() => getComputedStyle(document.body).backgroundColor")
    assert _bg_is_painted(body_bg), f"body background not painted (got {body_bg!r})"

    page.screenshot(path=str(ARTIFACTS_DIR / "site_bg.png"))
    page.close()
    assert errors == [], f"console errors: {errors}"
