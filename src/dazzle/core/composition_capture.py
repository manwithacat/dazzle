"""Composition capture — Playwright screenshot pipeline for visual evaluation.

Captures section-level screenshots from a running Dazzle app, applies
preprocessing for token efficiency, and returns metadata for downstream
LLM visual analysis.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .ir.sitespec import SiteSpec

logger = logging.getLogger(__name__)

# ── Data Models ──────────────────────────────────────────────────────


@dataclass
class ElementGeometry:
    """Bounding box for a single DOM element."""

    x: float
    y: float
    width: float
    height: float


@dataclass
class SectionGeometry:
    """Layout geometry for a section and its key child elements."""

    section: ElementGeometry
    content: ElementGeometry | None = None
    media: ElementGeometry | None = None
    viewport_height: int = 0


@dataclass
class CapturedSection:
    """A captured screenshot of a single page section."""

    section_type: str
    path: str
    width: int
    height: int
    tokens_est: int
    geometry: SectionGeometry | None = None


@dataclass
class CapturedPage:
    """Capture results for a single page."""

    route: str
    viewport: str
    sections: list[CapturedSection] = field(default_factory=list)
    full_page: str | None = None
    total_tokens_est: int = 0
    viewport_height: int = 0


# ── Token Estimation ─────────────────────────────────────────────────


def estimate_tokens(width: int, height: int) -> int:
    """Estimate Claude vision token cost for an image.

    Claude's token cost model: width * height / 750, with images
    internally rescaled so the longest edge is at most 1568px.
    """
    # Simulate Claude's internal rescaling
    max_edge = max(width, height)
    if max_edge > 1568:
        scale = 1568 / max_edge
        width = int(width * scale)
        height = int(height * scale)
    return max(1, int(width * height / 750))


# ── Image Preprocessing ──────────────────────────────────────────────


def preprocess_standard(img_path: Path, *, max_edge: int = 1568) -> Path:
    """Resize image to optimal dimensions for Claude vision.

    Pre-resizes to just under Claude's internal 1568px limit to avoid
    quality loss from double-resampling.

    Args:
        img_path: Path to source PNG image.
        max_edge: Maximum edge length in pixels.

    Returns:
        Path to the preprocessed image (``*-opt.png`` suffix).
    """
    try:
        from PIL import Image
    except ImportError:
        logger.warning("Pillow not available — skipping preprocessing")
        return img_path

    img: Image.Image = Image.open(img_path)
    w, h = img.size

    if max(w, h) > max_edge:
        scale = max_edge / max(w, h)
        new_w, new_h = int(w * scale), int(h * scale)
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    out_path = img_path.with_stem(img_path.stem + "-opt")
    img.save(out_path, optimize=True)
    return out_path


# ── Playwright Capture ───────────────────────────────────────────────

# Default viewports matching Dazzle's viewport testing infrastructure
DEFAULT_VIEWPORTS: dict[str, dict[str, int]] = {
    "desktop": {"width": 1280, "height": 720},
    "mobile": {"width": 375, "height": 812},
}


async def capture_page_sections(
    base_url: str,
    sitespec: SiteSpec,
    *,
    output_dir: Path,
    viewports: list[str] | None = None,
    routes_filter: list[str] | None = None,
    preprocess: bool = True,
) -> list[CapturedPage]:
    """Capture section-level screenshots from a running Dazzle app.

    Uses Playwright's async API to navigate to each page, locate
    ``section.dz-section.dz-section-{type}`` elements, and capture
    clipped screenshots of each section.

    Args:
        base_url: Running app URL (e.g. ``http://localhost:3000``).
        sitespec: Loaded SiteSpec for page/section structure.
        output_dir: Directory to store screenshot files.
        viewports: Viewport names to capture (default: ``["desktop"]``).
        routes_filter: If set, only capture these routes.
        preprocess: If True, apply standard preprocessing to images.

    Returns:
        List of CapturedPage results with file paths and metadata.

    Raises:
        ImportError: If Playwright is not installed.
    """
    try:
        import playwright  # noqa: F401
    except ImportError:
        raise ImportError(
            "Playwright is required for composition capture. "
            "Install with: pip install playwright && playwright install chromium"
        )

    from dazzle.testing.browser_gate import get_browser_gate

    vp_names = viewports or ["desktop"]
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[CapturedPage] = []

    async with get_browser_gate().async_browser() as browser:
        for vp_name in vp_names:
            vp_size = DEFAULT_VIEWPORTS.get(vp_name, DEFAULT_VIEWPORTS["desktop"])
            context = await browser.new_context(
                viewport={
                    "width": vp_size["width"],
                    "height": vp_size["height"],
                }
            )
            page = await context.new_page()
            page.set_default_timeout(15000)

            for spec_page in sitespec.pages:
                route = spec_page.route
                if routes_filter and route not in routes_filter:
                    continue

                captured = await _capture_single_page(
                    page=page,
                    base_url=base_url,
                    route=route,
                    spec_page=spec_page,
                    viewport_name=vp_name,
                    output_dir=output_dir,
                    preprocess=preprocess,
                )
                results.append(captured)

            await context.close()

    return results


async def _capture_single_page(
    *,
    page: Any,
    base_url: str,
    route: str,
    spec_page: Any,
    viewport_name: str,
    output_dir: Path,
    preprocess: bool,
) -> CapturedPage:
    """Capture sections for a single page."""
    url = base_url.rstrip("/") + route
    vp_height = page.viewport_size.get("height", 0) if page.viewport_size else 0
    result = CapturedPage(route=route, viewport=viewport_name, viewport_height=vp_height)

    try:
        await page.goto(url, wait_until="networkidle", timeout=15000)
        # Extra wait for dynamic content (icons, lazy images)
        await page.wait_for_timeout(1500)
    except Exception as e:
        logger.warning("Failed to navigate to %s: %s", url, e)
        return result

    # Capture full page screenshot
    slug = route.strip("/").replace("/", "-") or "index"
    full_path = output_dir / f"{slug}-{viewport_name}-full.png"
    try:
        await page.screenshot(path=str(full_path), full_page=True)
        result.full_page = str(full_path)
    except Exception as e:
        logger.warning("Full page screenshot failed for %s: %s", route, e)

    # Capture each section
    for section in spec_page.sections:
        sec_type = section.type.value if hasattr(section.type, "value") else str(section.type)
        captured = await _capture_section(
            page=page,
            section_type=sec_type,
            slug=slug,
            viewport_name=viewport_name,
            output_dir=output_dir,
            preprocess=preprocess,
        )
        if captured:
            result.sections.append(captured)
            result.total_tokens_est += captured.tokens_est

    return result


async def _extract_child_bbox(element: Any, selector: str) -> ElementGeometry | None:
    """Query a child element and return its bounding box, or None."""
    try:
        child = await element.query_selector(selector)
        if not child:
            return None
        box = await child.bounding_box()
        if not box:
            return None
        return ElementGeometry(x=box["x"], y=box["y"], width=box["width"], height=box["height"])
    except Exception:
        return None


# Selectors for key child elements within sections.
_CONTENT_SELECTOR = ".dz-section-content"
_MEDIA_SELECTORS = (
    ".dz-hero-media",
    ".dz-split-image",
    "img.dz-hero-image",
)


async def _capture_section(
    *,
    page: Any,
    section_type: str,
    slug: str,
    viewport_name: str,
    output_dir: Path,
    preprocess: bool,
) -> CapturedSection | None:
    """Capture a single section screenshot by CSS selector."""
    selector = f"section.dz-section.dz-section-{section_type}"

    try:
        element = await page.query_selector(selector)
        if not element:
            logger.debug("Section %s not found on page", section_type)
            return None

        bbox = await element.bounding_box()
        if not bbox:
            return None

        # Extract geometry for the section and its key children
        vp_height = page.viewport_size.get("height", 0) if page.viewport_size else 0
        section_geo = ElementGeometry(
            x=bbox["x"], y=bbox["y"], width=bbox["width"], height=bbox["height"]
        )
        content_geo = await _extract_child_bbox(element, _CONTENT_SELECTOR)
        media_geo: ElementGeometry | None = None
        for media_sel in _MEDIA_SELECTORS:
            media_geo = await _extract_child_bbox(element, media_sel)
            if media_geo:
                break
        geometry = SectionGeometry(
            section=section_geo,
            content=content_geo,
            media=media_geo,
            viewport_height=vp_height,
        )

        # Add vertical padding for context
        vp_width = page.viewport_size["width"]
        clip = {
            "x": 0,
            "y": max(0, bbox["y"] - 20),
            "width": vp_width,
            "height": bbox["height"] + 40,
        }

        filename = f"{slug}-{viewport_name}-{section_type}.png"
        filepath = output_dir / filename
        await page.screenshot(path=str(filepath), clip=clip)

        width = int(clip["width"])
        height = int(clip["height"])

        # Preprocess if requested
        if preprocess:
            opt_path = preprocess_standard(filepath)
            if opt_path != filepath:
                # Re-read dimensions from preprocessed image
                try:
                    from PIL import Image

                    with Image.open(opt_path) as img:
                        width, height = img.size
                except ImportError:
                    pass
                filepath = opt_path

        tokens = estimate_tokens(width, height)

        return CapturedSection(
            section_type=section_type,
            path=str(filepath),
            width=width,
            height=height,
            tokens_est=tokens,
            geometry=geometry,
        )

    except Exception as e:
        logger.warning("Failed to capture section %s: %s", section_type, e)
        return None
