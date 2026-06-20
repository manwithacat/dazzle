"""Visual smoke test for onboarding overlays (v0.71.x).

Renders each of the 8 step kinds into a standalone HTML harness with
the framework CSS bundle loaded, then drives Playwright against it
to check:

- Console errors (none expected)
- Element renders are non-empty bounding boxes
- The overlay actually paints (computed background-color isn't
  transparent / default — confirms the CSS classes resolved)
- The dismiss button is reachable + has a non-zero size (no
  invisible UI)
- The CTA, when set, has a brand-coloured background (so users can
  tell it's actionable)
- Screenshots land under ``tests/visual/_artifacts/`` for human
  review; CI doesn't gate on them but a local run produces
  inspectable PNGs.

Marked ``@pytest.mark.visual`` so it doesn't run in the standard
unit suite. Run explicitly with ``pytest tests/visual/ -m visual``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Playwright is an opt-in test dep; the default CI runner doesn't
# install it. Use importorskip so collection short-circuits cleanly
# when the module is missing — the @pytest.mark.visual gate only
# applies AFTER collection, so the bare `from playwright...` import
# below would crash pytest collection before the marker fires.
sync_playwright_module = pytest.importorskip("playwright.sync_api")
sync_playwright = sync_playwright_module.sync_playwright
Page = sync_playwright_module.Page

from dazzle.core.ir.onboarding import (  # noqa: E402  (after importorskip)
    GuideCompleteOn,
    GuideCompleteOnKind,
    GuideStep,
    GuideStepKind,
)
from dazzle.page.runtime.css_loader import get_bundled_css  # noqa: E402
from dazzle.render.onboarding.renderer import render_step  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = REPO_ROOT / "tests" / "visual" / "_artifacts"

# All kinds the renderer claims to support — driven from the IR enum
# so adding a new kind auto-extends the parametrisation.
_ALL_KINDS = [
    GuideStepKind.POPOVER,
    GuideStepKind.SPOTLIGHT,
    GuideStepKind.INLINE_CARD,
    GuideStepKind.EMPTY_STATE,
    GuideStepKind.BANNER,
    GuideStepKind.CHECKLIST_ITEM,
    GuideStepKind.BLOCKING_TASK,
    GuideStepKind.NUDGE,
]


def _build_step(kind: GuideStepKind) -> GuideStep:
    return GuideStep(
        name="welcome",
        kind=kind,
        title="Welcome — create your first task",
        body=("Tasks let you track work across the team. Click below to get started."),
        target="surface.task_list",
        placement="bottom" if kind != GuideStepKind.NUDGE else "5000",
        cta_label="New Task",
        cta_target="surface.task_create",
        complete_on=GuideCompleteOn(kind=GuideCompleteOnKind.CLICK),
    )


def _harness_html(overlay_html: str) -> str:
    """Wrap an overlay HTML fragment in a minimal page that loads the
    framework CSS bundle. No layout chrome — just enough to verify
    the overlay paints."""
    css = get_bundled_css()
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Onboarding visual harness</title>
<style>{css}</style>
</head>
<body>
<main class="dz-page">
<h1 style="margin: 2rem">Onboarding visual harness</h1>
<div style="padding: 2rem; min-height: 60vh; background: var(--colour-bg, white);">
{overlay_html}
</div>
</main>
</body>
</html>
"""


@pytest.fixture(scope="module")
def _harness_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("onboarding_harness")


@pytest.fixture(scope="module")
def _browser():
    """One shared headless Chromium for the whole module — launching
    per-test triples wall-clock for no benefit."""
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.mark.visual
@pytest.mark.parametrize("kind", _ALL_KINDS, ids=lambda k: k.value)
def test_step_kind_renders_visibly(
    kind: GuideStepKind,
    _browser,
    _harness_dir: Path,
) -> None:
    """Each step kind paints a visible element with a non-zero bounding
    box, computed styles different from defaults, and no console
    errors. Screenshot captured to ``tests/visual/_artifacts/``."""
    step = _build_step(kind)
    overlay_html = render_step(step, guide_name="workspace_setup")
    page_html = _harness_html(overlay_html)
    harness_file = _harness_dir / f"{kind.value}.html"
    harness_file.write_text(page_html)

    console_errors: list[str] = []
    page_errors: list[str] = []
    page: Page = _browser.new_page(viewport={"width": 1280, "height": 800})

    def _on_console(msg) -> None:
        if msg.type == "error":
            console_errors.append(f"{msg.type}: {msg.text}")

    page.on("console", _on_console)
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))

    page.goto(harness_file.as_uri())
    page.wait_for_load_state("networkidle")

    # Locate the overlay.
    overlay = page.locator("dz-onboarding-step")
    assert overlay.count() == 1, (
        f"{kind}: expected exactly one rendered overlay; got {overlay.count()}"
    )

    # ── Bounding box: real layout space taken.
    # blocking_task uses `display: contents` on the outer custom
    # element so the inner <dialog> carries the layout. Target the
    # dialog directly for that kind; everything else uses the outer.
    if kind == GuideStepKind.BLOCKING_TASK:
        sized = overlay.locator("dialog")
    else:
        sized = overlay
    box = sized.bounding_box()
    assert box is not None, f"{kind}: overlay has no bounding box (display:none?)"
    assert box["width"] > 50, f"{kind}: overlay too narrow ({box['width']}px)"
    assert box["height"] > 20, f"{kind}: overlay too short ({box['height']}px)"

    # ── Computed background — verify the CSS rule reached the element.
    # Walk outer → first child → grandchild, accepting the first
    # non-transparent background we find. Spotlight has a backdrop
    # scrim as its first child; other kinds have the bg on the outer
    # element OR on the dialog/card inside. Either path proves the
    # CSS landed.
    bg = overlay.evaluate("""el => {
        const candidates = [el, el.firstElementChild, el.querySelector('dialog')];
        for (const c of candidates) {
            if (!c) continue;
            const v = getComputedStyle(c).backgroundColor;
            if (v && v !== 'rgba(0, 0, 0, 0)' && v !== 'transparent') return v;
        }
        return 'rgba(0, 0, 0, 0)';
    }""")
    assert bg not in ("rgba(0, 0, 0, 0)", "transparent"), (
        f"{kind}: neither outer nor first-child nor dialog has a "
        f"styled background — CSS class probably not loaded ({bg!r})"
    )

    # ── Dismiss button shape per kind.
    # blocking_task has no dismiss by design (CTA-only exit).
    # checklist_item hides its per-item dismiss by default — parent
    # guide owns dismissal; deployments opt individual items in via
    # the parent's `[data-allow-dismiss]`.
    if kind not in (GuideStepKind.BLOCKING_TASK, GuideStepKind.CHECKLIST_ITEM):
        dismiss = overlay.locator('button[aria-label="Dismiss"]')
        assert dismiss.count() == 1, f"{kind}: dismiss button missing"
        dismiss_box = dismiss.bounding_box()
        assert dismiss_box is not None, f"{kind}: dismiss has no bounding box"
        assert dismiss_box["width"] >= 16 and dismiss_box["height"] >= 16, (
            f"{kind}: dismiss button too small ({dismiss_box['width']}x{dismiss_box['height']})"
        )
    elif kind == GuideStepKind.CHECKLIST_ITEM:
        # Dismiss exists in DOM but is hidden by default.
        dismiss = overlay.locator('button[aria-label="Dismiss"]')
        assert dismiss.count() == 1
        display = dismiss.evaluate("el => getComputedStyle(el).display")
        assert display == "none", (
            f"checklist_item dismiss should be hidden by default; got display={display!r}"
        )

    # ── CTA must be visible + have a brand-coloured fill.
    cta = overlay.locator('a[hx-post*="complete"]')
    assert cta.count() == 1, f"{kind}: CTA anchor missing"
    cta_bg = cta.evaluate("el => getComputedStyle(el).backgroundColor")
    assert cta_bg not in ("rgba(0, 0, 0, 0)", "transparent"), (
        f"{kind}: CTA has transparent background — not visually actionable ({cta_bg!r})"
    )

    # ── Screenshot for human review
    page.screenshot(path=str(ARTIFACTS_DIR / f"{kind.value}.png"), full_page=True)
    page.close()

    # ── No console errors / unhandled exceptions
    assert console_errors == [], f"{kind}: console errors: {console_errors}"
    assert page_errors == [], f"{kind}: page errors: {page_errors}"


@pytest.mark.visual
def test_no_kind_overlaps_the_viewport_edges(_browser, _harness_dir: Path) -> None:
    """Every kind sits inside the visible viewport — no clipped overlays."""
    issues: list[str] = []
    for kind in _ALL_KINDS:
        step = _build_step(kind)
        overlay_html = render_step(step, guide_name="workspace_setup")
        harness_file = _harness_dir / f"viewport_{kind.value}.html"
        harness_file.write_text(_harness_html(overlay_html))
        page: Page = _browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(harness_file.as_uri())
        page.wait_for_load_state("networkidle")
        # blocking_task uses display:contents on the outer — target dialog.
        if kind == GuideStepKind.BLOCKING_TASK:
            box = page.locator("dz-onboarding-step dialog").bounding_box()
        else:
            box = page.locator("dz-onboarding-step").bounding_box()
        page.close()
        if box is None:
            issues.append(f"{kind.value}: no bounding box")
            continue
        if box["x"] < 0 or box["y"] < 0:
            issues.append(f"{kind.value}: overlay clipped at top/left {box}")
        if box["x"] + box["width"] > 1280 + 1:
            issues.append(
                f"{kind.value}: overlay clipped at right edge (x+w={box['x'] + box['width']:.0f})"
            )
        if box["y"] + box["height"] > 800 + 1:
            issues.append(
                f"{kind.value}: overlay clipped at bottom (y+h={box['y'] + box['height']:.0f})"
            )
    assert issues == [], "\n".join(issues)
