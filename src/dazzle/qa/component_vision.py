"""On-demand component vision score (#1567) — advisory, not a gate.

Renders a showcase region, screenshots it, and scores the image with the taste
vision panel. Subscription/API-billed; exit-0 always at the CLI. The heavy parts
(screenshot capture, judge client) are injectable so the glue is unit-testable.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from dazzle.core.model_defaults import DEFAULT_JUDGMENT_MODEL
from dazzle.qa.taste_panel import JudgeScore, PanelImage, score_image
from dazzle.testing.ux_catalogue import generate_catalogue_css, render_region_by_name

__all__ = ["score_component_region"]


def _default_capture(html: str, out_png: Path) -> Path:
    """Screenshot rendered HTML at 1440x1024 via Playwright (import-local so the
    dependency only loads on the real path, never in unit tests)."""
    from playwright.sync_api import sync_playwright

    doc = (
        "<!doctype html><html><head><style>"
        f"{generate_catalogue_css()}"
        f"</style></head><body>{html}</body></html>"
    )
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1024})
        page.set_content(doc, wait_until="networkidle")
        page.screenshot(path=str(out_png), full_page=False)
        browser.close()
    return out_png


def score_component_region(
    name: str,
    *,
    judges: int = 3,
    model: str = DEFAULT_JUDGMENT_MODEL,
    out_dir: Path = Path(".dazzle/qa/component-vision"),
    capture: Callable[[str, Path], Path] = _default_capture,
    score_fn: Callable[..., list[JudgeScore]] = score_image,
    client: Any | None = None,
) -> dict[str, object]:
    """Render `name`, screenshot it, score it. Raises KeyError on an unknown region.

    Returns an advisory report: per-dimension mean scores + the image path. Never a
    gate — the CLI always exits 0 on a successful score.
    """
    html = render_region_by_name(name)  # KeyError if unknown — surfaces as a usage error
    out_dir.mkdir(parents=True, exist_ok=True)
    png = capture(html, out_dir / f"{name}.png")
    image = PanelImage(image_id=name, source="dazzle", label=name, path=png, theme="light")

    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    for j in range(judges):
        for js in score_fn(image, judge=j, model=model, client=client):
            totals[js.dimension] = totals.get(js.dimension, 0.0) + js.score
            counts[js.dimension] = counts.get(js.dimension, 0) + 1
    means = {d: round(totals[d] / counts[d], 2) for d in totals}
    return {"region": name, "judges": judges, "model": model, "scores": means, "image": str(png)}
