"""Visual-domain regression — gallery screenshots vs committed baselines.

Above-fold (1280x900) captures of the gallery in light and dark, compared
pixel-wise with a tolerance that absorbs same-platform rendering noise but
fails on real palette / layout drift.

Baselines are **per-platform** (``baselines/linux/``, ``baselines/darwin/``)
because Chromium's font rasterisation differs enough across OSes (~4% of
pixels) to swamp a tight threshold. CI compares against the linux set; local
runs compare against your platform's set (and skip-write it if absent).

Update baselines after an INTENDED visual change:
    HM_UPDATE_BASELINES=1 python -m pytest tests/test_visual.py   # yours
    gh workflow run update-baselines.yml                          # linux set
and commit the PNGs (review the diff images first).
"""

import os
import sys
from pathlib import Path

import pytest

BASELINES = Path(__file__).resolve().parent / "baselines" / sys.platform
OUT = Path(__file__).resolve().parent / ".diff"

# A pixel "differs" when any channel deviates by more than this (0-255);
# the test fails when more than MAX_DIFF_RATIO of pixels differ.
CHANNEL_TOLERANCE = 12
MAX_DIFF_RATIO = 0.01


def _compare(name: str, png_bytes: bytes) -> None:
    Image = pytest.importorskip("PIL.Image")
    ImageChops = pytest.importorskip("PIL.ImageChops")
    import io

    baseline_path = BASELINES / f"{name}.png"
    if os.environ.get("HM_UPDATE_BASELINES") == "1" or not baseline_path.exists():
        BASELINES.mkdir(parents=True, exist_ok=True)
        baseline_path.write_bytes(png_bytes)
        pytest.skip(f"baseline written: {sys.platform}/{baseline_path.name} — commit it")

    baseline = Image.open(baseline_path).convert("RGB")
    current = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    assert baseline.size == current.size, (
        f"{name}: size changed {baseline.size} -> {current.size} "
        "(viewport drift or layout change — update baselines if intended)"
    )
    diff = ImageChops.difference(baseline, current)
    histo = diff.convert("L").point(lambda v: 255 if v > CHANNEL_TOLERANCE else 0)
    differing = sum(1 for v in histo.getdata() if v)
    ratio = differing / (baseline.size[0] * baseline.size[1])
    if ratio > MAX_DIFF_RATIO:
        OUT.mkdir(exist_ok=True)
        (OUT / f"{name}.current.png").write_bytes(png_bytes)
        histo.save(OUT / f"{name}.mask.png")
        raise AssertionError(
            f"{name}: {ratio:.2%} of pixels differ (> {MAX_DIFF_RATIO:.0%}) — "
            f"see tests/.diff/{name}.*.png; if the change is intended, "
            "regenerate with HM_UPDATE_BASELINES=1 and commit"
        )


import sys as _sys  # noqa: E402  (path bootstrap must precede registry import)

_PKG = Path(__file__).resolve().parents[1]
for _p in (str(_PKG), str(_PKG / "site"), str(_PKG / "tools")):
    if _p not in _sys.path:
        _sys.path.insert(0, _p)

from conftest import goto_part  # noqa: E402
from registry import HYPERPARTS  # noqa: E402

_PART_IDS = [h.id for h in HYPERPARTS]


@pytest.mark.parametrize("part_id", _PART_IDS)
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_part_visual(page, part_id, theme) -> None:  # type: ignore[no-untyped-def]
    """Atomic per-part baseline — a part's change churns ITS baseline only
    (spec 2026-07-10-hm-docs-pedagogy-atomic-testing)."""
    goto_part(page, part_id)
    if theme == "dark":
        page.evaluate("hmTheme('dark')")
    page.wait_for_timeout(300)
    page.evaluate("document.fonts && document.fonts.ready")
    _compare(f"part-{part_id}-{theme}", page.screenshot())


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_gallery_visual(page, theme) -> None:  # type: ignore[no-untyped-def]
    if theme == "dark":
        page.evaluate("hmTheme('dark')")
    page.wait_for_timeout(300)
    page.evaluate("document.fonts && document.fonts.ready")
    png = page.screenshot()
    _compare(f"gallery-{theme}", png)
