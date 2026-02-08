"""Visual regression screenshot capture and comparison.

Captures screenshots at each viewport size and compares against stored
baselines using pixel-level diffing via Pillow (optional dependency).
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("dazzle.testing.viewport_screenshot")

BASELINES_DIR = ".dazzle/viewport_baselines"


@dataclass
class ScreenshotResult:
    """Result of a single screenshot capture + comparison."""

    page_path: str
    viewport: str
    screenshot_path: Path | None = None
    baseline_path: Path | None = None
    diff_path: Path | None = None
    is_new_baseline: bool = False
    pixel_diff_pct: float = 0.0
    passed: bool = True


@dataclass
class VisualRegressionReport:
    """Aggregated visual regression results."""

    screenshots: list[ScreenshotResult]
    new_baselines: int = 0
    regressions: int = 0
    unchanged: int = 0


def _safe_filename(page_path: str, viewport_name: str) -> str:
    """Generate a deterministic filename from page path and viewport."""
    slug = page_path.strip("/").replace("/", "_") or "root"
    return f"{slug}_{viewport_name}.png"


def capture_screenshot(
    page: Any,
    page_path: str,
    viewport_name: str,
    output_dir: Path,
) -> Path:
    """Capture a full-page screenshot.

    Parameters
    ----------
    page:
        Playwright page object.
    page_path:
        URL path (e.g. ``"/dashboard"``).
    viewport_name:
        Viewport name (e.g. ``"mobile"``).
    output_dir:
        Directory to save the screenshot.

    Returns
    -------
    Path
        Path to the saved screenshot file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = _safe_filename(page_path, viewport_name)
    filepath = output_dir / filename
    page.screenshot(path=str(filepath), full_page=True)
    return filepath


def get_baseline_path(
    project_path: Path,
    page_path: str,
    viewport_name: str,
) -> Path:
    """Get the expected baseline screenshot path.

    Parameters
    ----------
    project_path:
        Project root directory.
    page_path:
        URL path.
    viewport_name:
        Viewport name.

    Returns
    -------
    Path
        Path where the baseline would be stored.
    """
    return project_path / BASELINES_DIR / _safe_filename(page_path, viewport_name)


def save_as_baseline(screenshot_path: Path, baseline_path: Path) -> None:
    """Copy a screenshot to become the new baseline.

    Parameters
    ----------
    screenshot_path:
        Path to the current screenshot.
    baseline_path:
        Path where the baseline should be stored.
    """
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(screenshot_path), str(baseline_path))


def _file_hash(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def compare_screenshots(
    current: Path,
    baseline: Path,
    diff_output: Path,
    threshold: float = 0.01,
) -> tuple[bool, float]:
    """Compare two screenshots using pixel-level diff.

    Uses Pillow if available, falls back to hash comparison.

    Parameters
    ----------
    current:
        Path to the current screenshot.
    baseline:
        Path to the baseline screenshot.
    diff_output:
        Path to save the visual diff image.
    threshold:
        Maximum allowed pixel difference percentage (0.0 - 1.0).

    Returns
    -------
    tuple[bool, float]
        ``(passed, pixel_diff_pct)`` — passed is True if diff <= threshold.
    """
    try:
        from PIL import Image, ImageChops

        img_current = Image.open(current)
        img_baseline = Image.open(baseline)

        # Resize if dimensions differ
        if img_current.size != img_baseline.size:
            img_baseline = img_baseline.resize(img_current.size)  # type: ignore[assignment]

        diff = ImageChops.difference(img_current.convert("RGB"), img_baseline.convert("RGB"))
        diff_pixels = sum(1 for px in list(diff.getdata()) if any(int(c) > 0 for c in px))
        total_pixels = img_current.size[0] * img_current.size[1]
        diff_pct = diff_pixels / total_pixels if total_pixels > 0 else 0.0

        # Save diff image
        diff_output.parent.mkdir(parents=True, exist_ok=True)
        diff.save(str(diff_output))

        return diff_pct <= threshold, diff_pct

    except ImportError:
        # Pillow not available — fall back to hash comparison
        logger.debug("Pillow not installed, falling back to hash comparison")
        current_hash = _file_hash(current)
        baseline_hash = _file_hash(baseline)
        identical = current_hash == baseline_hash
        return identical, 0.0 if identical else 1.0


def run_visual_regression(
    page: Any,
    page_path: str,
    viewport_name: str,
    project_path: Path,
    *,
    update_baselines: bool = False,
    threshold: float = 0.01,
) -> ScreenshotResult:
    """Capture a screenshot and compare against baseline.

    Parameters
    ----------
    page:
        Playwright page object.
    page_path:
        URL path of the current page.
    viewport_name:
        Current viewport name.
    project_path:
        Project root directory.
    update_baselines:
        If True, save current screenshot as the new baseline.
    threshold:
        Pixel diff threshold for pass/fail.

    Returns
    -------
    ScreenshotResult
        Result of the capture and comparison.
    """
    output_dir = project_path / ".dazzle" / "viewport_screenshots"
    screenshot_path = capture_screenshot(page, page_path, viewport_name, output_dir)
    baseline_path = get_baseline_path(project_path, page_path, viewport_name)

    if update_baselines or not baseline_path.exists():
        save_as_baseline(screenshot_path, baseline_path)
        return ScreenshotResult(
            page_path=page_path,
            viewport=viewport_name,
            screenshot_path=screenshot_path,
            baseline_path=baseline_path,
            is_new_baseline=True,
            passed=True,
        )

    diff_dir = project_path / ".dazzle" / "viewport_diffs"
    diff_path = diff_dir / _safe_filename(page_path, viewport_name)

    passed, diff_pct = compare_screenshots(screenshot_path, baseline_path, diff_path, threshold)

    return ScreenshotResult(
        page_path=page_path,
        viewport=viewport_name,
        screenshot_path=screenshot_path,
        baseline_path=baseline_path,
        diff_path=diff_path if not passed else None,
        pixel_diff_pct=diff_pct,
        passed=passed,
    )
