"""On-demand property vision score (#1567 slice 2) — advisory, not a gate.

Screenshots a rendered property page (1440x1024 fold) and scores it against
SITESPEC_VISION_DIMENSIONS, resolving the chosen family's exemplar references so
the report anchors family_fidelity to real captures. Heavy parts (Playwright
capture, judge client) are injectable; subscription-billed.

Note: this version scores the page image alone (family_fidelity is prompt-anchored,
not side-by-side multi-image); the resolved exemplar paths are returned in the
report so the author can eyeball the comparison. Side-by-side judging would need a
multi-image score_image call — future work if wanted.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from dazzle.core.model_defaults import DEFAULT_JUDGMENT_MODEL
from dazzle.core.sitespec_vision_rubric import SITESPEC_VISION_DIMENSIONS
from dazzle.qa.taste_panel import JudgeScore, PanelImage, score_image

__all__ = ["exemplars_for", "score_property"]

DEFAULT_MANIFEST = Path(".dazzle/composition/references/sitespec/sitespec_references_manifest.json")


def exemplars_for(family: str, manifest_path: Path | None = None) -> list[Path]:
    """Exemplar screenshot paths for a family. FileNotFoundError if the manifest
    hasn't been captured; KeyError if the family has no captured references."""
    path = manifest_path or DEFAULT_MANIFEST
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found — run: python scripts/taste/capture_sitespec_references.py"
        )
    manifest = json.loads(path.read_text(encoding="utf-8"))
    refs = [Path(r["screenshot"]) for r in manifest.get("references", []) if r["family"] == family]
    refs = [r for r in refs if r.exists()]
    if not refs:
        raise KeyError(
            f"no captured exemplars for family {family!r} — run: "
            f"python scripts/taste/capture_sitespec_references.py --family {family}"
        )
    return refs


def _default_capture(url: str, out_png: Path) -> Path:
    """Screenshot a live page at the 1440x1024 marketing fold via Playwright
    (import-local so the dependency only loads on the real path)."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1024})
        page.goto(url, wait_until="networkidle")
        page.screenshot(path=str(out_png), full_page=False)
        browser.close()
    return out_png


def score_property(
    url: str,
    family: str,
    *,
    judges: int = 3,
    model: str = DEFAULT_JUDGMENT_MODEL,
    out_dir: Path = Path(".dazzle/qa/property-vision"),
    capture: Callable[[str, Path], Path] = _default_capture,
    score_fn: Callable[..., list[JudgeScore]] = score_image,
    client: Any | None = None,
    manifest_path: Path | None = None,
) -> dict[str, object]:
    """Screenshot `url`, score vs the sitespec vision rubric + family exemplars.

    Raises FileNotFoundError/KeyError for missing exemplars (usage errors) BEFORE
    any capture or billed call.
    """
    exemplars = exemplars_for(family, manifest_path=manifest_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    png = capture(url, out_dir / "property.png")
    image = PanelImage(
        image_id=f"property-{family}", source="dazzle", label=url, path=png, theme="light"
    )

    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    for j in range(judges):
        for js in score_fn(
            image, judge=j, model=model, client=client, dimensions=SITESPEC_VISION_DIMENSIONS
        ):
            totals[js.dimension] = totals.get(js.dimension, 0.0) + js.score
            counts[js.dimension] = counts.get(js.dimension, 0) + 1
    means = {d: round(totals[d] / counts[d], 2) for d in totals}
    return {
        "url": url,
        "family": family,
        "judges": judges,
        "model": model,
        "scores": means,
        "image": str(png),
        "exemplars": [str(e) for e in exemplars],
    }
