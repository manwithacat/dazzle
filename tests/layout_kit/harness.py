"""Playwright harness: production CSS + HTML fixture → measured snapshot.

LAYER: L2
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

# Optional at import time — tests that need the kit importorskip playwright.
try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None  # type: ignore[assignment, misc]

_REPO = Path(__file__).resolve().parents[2]
_DAZZLE_CSS = _REPO / "src" / "dazzle" / "page" / "runtime" / "static" / "dist" / "dazzle.min.css"


class LayoutState(StrEnum):
    """Interactive state applied after load."""

    RESTING = "resting"
    HOVER = "hover"
    FOCUS_WITHIN = "focus-within"


@dataclass(frozen=True, slots=True)
class Box:
    """getBoundingClientRect subset (document / viewport coordinates)."""

    x: float
    y: float
    width: float
    height: float
    top: float
    right: float
    bottom: float
    left: float

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Box:
        return cls(
            x=float(d["x"]),
            y=float(d["y"]),
            width=float(d["width"]),
            height=float(d["height"]),
            top=float(d["top"]),
            right=float(d["right"]),
            bottom=float(d["bottom"]),
            left=float(d["left"]),
        )


@dataclass
class LayoutSnapshot:
    """Serializable geometry dump for assertions and debug."""

    boxes: dict[str, Box] = field(default_factory=dict)
    styles: dict[str, dict[str, str]] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)
    state: LayoutState = LayoutState.RESTING
    html_path: Path | None = None


def dazzle_css_path() -> Path:
    """Bundled production CSS (same file the app serves)."""
    return _DAZZLE_CSS


def wrap_fixture_html(
    body_html: str,
    *,
    css: str | None = None,
    css_paths: list[Path] | None = None,
    stage_width: int = 960,
    extra_head: str = "",
) -> str:
    """Document shell: design-system CSS + stage + body fragment."""
    chunks: list[str] = []
    if css is not None:
        chunks.append(css)
    for p in css_paths or []:
        chunks.append(p.read_text(encoding="utf-8"))
    if not chunks:
        path = dazzle_css_path()
        if path.is_file():
            chunks.append(path.read_text(encoding="utf-8"))
    css_blob = "\n".join(chunks)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/>
<style>{css_blob}</style>
<style>
  body {{ margin: 0; font-family: system-ui, sans-serif; }}
  .stage {{ width: {stage_width}px; padding: 1.5rem; box-sizing: border-box; }}
</style>
{extra_head}
</head><body>
<div class="stage">
{body_html}
</div>
</body></html>
"""


def render_layout(
    *,
    html: str,
    state: LayoutState = LayoutState.RESTING,
    hover_selector: str | None = None,
    focus_selector: str | None = None,
    viewport: tuple[int, int] = (1100, 800),
    measure_js: str | None = None,
    tmp_name: str = "layout-kit-fixture.html",
) -> LayoutSnapshot:
    """Load full HTML document in headless Chromium; return measured snapshot.

    ``html`` should be a complete document (use :func:`wrap_fixture_html`).
    Optional ``measure_js`` is a browser function body that returns a dict
    merged into ``snapshot.raw``.
    """
    if sync_playwright is None:
        raise RuntimeError("playwright is not installed")

    path = Path("/tmp") / tmp_name
    path.write_text(html, encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})
        page.goto(path.as_uri())

        if state is LayoutState.HOVER:
            sel = hover_selector or ".dz-tr-row"
            page.hover(sel)
        elif state is LayoutState.FOCUS_WITHIN:
            sel = focus_selector or hover_selector or ".dz-tr-row"
            page.focus(sel)

        raw: dict[str, Any] = {}
        if measure_js:
            raw = page.evaluate(measure_js) or {}
        browser.close()

    return LayoutSnapshot(raw=raw, state=state, html_path=path)


def measure_selectors(
    page: Any,
    selectors: dict[str, str],
    *,
    style_props: tuple[str, ...] = (),
) -> tuple[dict[str, Box], dict[str, dict[str, str]]]:
    """Measure named selectors on an already-open Playwright page."""
    data = page.evaluate(
        """({ selectors, styleProps }) => {
          const boxes = {};
          const styles = {};
          for (const [name, sel] of Object.entries(selectors)) {
            const el = document.querySelector(sel);
            if (!el) continue;
            const r = el.getBoundingClientRect();
            boxes[name] = {
              x: r.x, y: r.y, width: r.width, height: r.height,
              top: r.top, right: r.right, bottom: r.bottom, left: r.left,
            };
            if (styleProps.length) {
              const cs = getComputedStyle(el);
              styles[name] = Object.fromEntries(styleProps.map(p => [p, cs[p]]));
            }
          }
          return { boxes, styles };
        }""",
        {"selectors": selectors, "styleProps": list(style_props)},
    )
    boxes = {k: Box.from_dict(v) for k, v in (data.get("boxes") or {}).items()}
    styles = dict(data.get("styles") or {})
    return boxes, styles
