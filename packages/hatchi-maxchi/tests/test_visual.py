"""Visual-domain regression — gallery screenshots vs committed baselines.

Above-fold (1280x900) captures of the gallery in light and dark, compared
pixel-wise with a tolerance that absorbs cross-platform antialiasing but
fails on real palette / layout drift.

Update baselines after an INTENDED visual change:
    HM_UPDATE_BASELINES=1 python -m pytest tests/test_visual.py
and commit the PNGs (review the diff images first).
"""

import os
from pathlib import Path

import pytest

BASELINES = Path(__file__).resolve().parent / "baselines"
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
        BASELINES.mkdir(exist_ok=True)
        baseline_path.write_bytes(png_bytes)
        pytest.skip(f"baseline written: {baseline_path.name} — commit it")

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


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_gallery_visual(page, theme) -> None:  # type: ignore[no-untyped-def]
    if theme == "dark":
        page.evaluate("hmTheme('dark')")
    page.wait_for_timeout(300)
    page.evaluate("document.fonts && document.fonts.ready")
    png = page.screenshot()
    _compare(f"gallery-{theme}", png)
