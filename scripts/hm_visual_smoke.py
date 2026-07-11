#!/usr/bin/env python3
"""Subscription-path HM visual smoke — Playwright only, no vision API.

Renders dual-locked Hyperpart exemplars (HM contract ``render()`` or
catalogue HTML) into a static page, screenshots with Playwright, and
writes PNGs + a manifest under a run directory.

Cognitive review (optional) is left to a host-harness subagent that
**Reads** the PNGs in-session (subscription) — same cost model as
``visual_tier2_subagent`` / ``dazzle qa capture``. This script never
calls a metered vision LLM.

Usage (from monorepo root):

    # dual-locked exemplars that ship render()
    # default out: .dazzle/hm-visual-smoke/ (gitignored) + last-run pointer
    python scripts/hm_visual_smoke.py

    # also include Dazzle dual-lock emission HTML (requires package)
    python scripts/hm_visual_smoke.py --dazzle-emit

    # custom output directory
    python scripts/hm_visual_smoke.py --out /tmp/hm-visual --dazzle-emit

Requires: playwright + chromium (``playwright install chromium``).

Phase D policy: this path is the **default** taste capture. Metered
``dazzle qa component-vision`` / ``taste-panel`` are optional only when API
credits are intentional — they never gate CI/ship.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HM = REPO / "packages" / "hatchi-maxchi"
DIST_CSS = HM / "dist" / "hatchi-maxchi.css"
DIST_JS = HM / "dist" / "hatchi-maxchi.js"

# Contract stems with a render() used for stable exemplar HTML.
EXEMPLAR_PARTS = ("money", "combobox", "tags", "grid_edit")


def _load_hm(rel: str):
    if str(HM) not in sys.path:
        sys.path.insert(0, str(HM))
    path = HM / rel
    spec = importlib.util.spec_from_file_location(f"hm_{path.stem}", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _build_page(sections: list[tuple[str, str]]) -> str:
    """HTML document embedding local dist CSS/JS + one section per part."""
    css_href = DIST_CSS.resolve().as_uri()
    js_href = DIST_JS.resolve().as_uri()
    body_parts = []
    for name, html in sections:
        body_parts.append(
            f'<section id="part-{name}" style="padding:24px;margin:16px 0;'
            f'border:1px solid #e5e7eb;border-radius:8px">'
            f'<h2 style="font:600 14px/1.4 system-ui">{name}</h2>'
            f'<div class="hm-exemplar">{html}</div></section>'
        )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>HM visual smoke</title>
  <link rel="stylesheet" href="{css_href}">
  <style>
    body {{ margin: 0; padding: 16px; background: #fafafa;
            font-family: system-ui, sans-serif; color: #111; }}
  </style>
</head>
<body>
  <h1 style="font:600 18px/1.3 system-ui">HM dual-lock exemplars (subscription smoke)</h1>
  {"".join(body_parts)}
  <script src="{js_href}" defer></script>
</body>
</html>
"""


def _collect_exemplar_sections() -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    for stem in EXEMPLAR_PARTS:
        mod = _load_hm(f"contracts/{stem}.py")
        if not hasattr(mod, "render") or not hasattr(mod, "EXEMPLARS"):
            continue
        exemplars = list(mod.EXEMPLARS)
        if not exemplars:
            continue
        # First exemplar only — stable, cheap; full set can be added later.
        html = mod.render(exemplars[0])
        sections.append((stem, html))
    return sections


def _collect_dazzle_emit_sections() -> list[tuple[str, str]]:
    """Real Dazzle dual-lock emission paths (no app server)."""
    import uuid

    from dazzle.http.runtime.handlers.list_handlers import build_data_table
    from dazzle.render.fragment.primitives.forms import MoneyField, TagsField, WidgetCombobox
    from dazzle.render.fragment.renderer import FragmentRenderer
    from dazzle.render.fragment.renderer._data_row import render_data_table_rows

    r = FragmentRenderer()
    out: list[tuple[str, str]] = []
    out.append(
        (
            "dazzle-money-fixed",
            r.render(
                MoneyField(
                    name="amount",
                    label="Amount",
                    currency_code="GBP",
                    scale="2",
                    symbol="£",
                    currency_fixed=True,
                    minor_initial="1500",
                )
            ),
        )
    )
    out.append(
        (
            "dazzle-tags",
            r.render(
                TagsField(name="labels", label="Labels", placeholder="Add…", initial_value="a,b")
            ),
        )
    )
    out.append(
        (
            "dazzle-combobox",
            r.render(
                WidgetCombobox(
                    name="priority",
                    label="Priority",
                    options=(("low", "Low"), ("high", "High")),
                    placeholder="Select…",
                    initial_value="low",
                )
            ),
        )
    )
    table = {
        "columns": [{"key": "title", "label": "Title", "type": "text"}],
        "entity_name": "Ticket",
        "api_endpoint": "/tickets",
        "table_id": "t-smoke",
        "detail_url_template": "/app/ticket/{id}",
    }
    row = {"id": str(uuid.uuid4()), "title": "confirm-smoke"}
    out.append(("dazzle-confirm-hx", render_data_table_rows(build_data_table(table, [row]))))
    from dazzle.page.runtime.pdf_viewer_renderer import render_pdf_viewer_component

    out.append(
        (
            "dazzle-pdf",
            render_pdf_viewer_component(src="/files/smoke.pdf", back_url="/app", title="Smoke"),
        )
    )
    from types import SimpleNamespace

    from dazzle.page.runtime.experience_renderer import _render_form_step_body

    form = SimpleNamespace(
        sections=[{"title": "A", "fields": []}, {"title": "B", "fields": []}],
        initial_values={},
        fields=[],
        entity_name="Ticket",
        mode="create",
        method="post",
        action_url="/api/tickets",
    )
    out.append(
        (
            "dazzle-wizard",
            _render_form_step_body(SimpleNamespace(transitions=[]), SimpleNamespace(form=form)),
        )
    )
    from dazzle.page.runtime.dual_pane_master_detail import render_master_detail_shell

    out.append(
        (
            "dazzle-master-detail",
            render_master_detail_shell(
                list_region="contact_list",
                list_title="Contacts",
                list_endpoint="/api/workspaces/contacts/regions/contact_list",
                detail_region="contact_detail",
                detail_title="Detail",
                detail_endpoint_base="/api/workspaces/contacts/regions/contact_detail",
            ),
        )
    )
    return out


def _screenshot(html_path: Path, png_path: Path, *, width: int = 1280, height: int = 1600) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
        page.screenshot(path=str(png_path), full_page=True)
        browser.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output directory (default: .dazzle/hm-visual-smoke/ — gitignored)",
    )
    ap.add_argument(
        "--dazzle-emit",
        action="store_true",
        help="include real Dazzle dual-lock emission HTML sections",
    )
    args = ap.parse_args(argv)

    if not DIST_CSS.is_file() or not DIST_JS.is_file():
        print(
            "error: missing HM dist — run: (cd packages/hatchi-maxchi && python build.py)",
            file=sys.stderr,
        )
        return 2

    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    # Default under .dazzle/ so improve agents can re-Read the last run without
    # polluting git (both .dazzle/ and dev_docs/ are gitignored).
    out = args.out or (REPO / ".dazzle" / "hm-visual-smoke")
    out.mkdir(parents=True, exist_ok=True)

    sections = _collect_exemplar_sections()
    if args.dazzle_emit:
        sections.extend(_collect_dazzle_emit_sections())
    if not sections:
        print("error: no sections to render", file=sys.stderr)
        return 2

    html = _build_page(sections)
    html_path = out / "index.html"
    html_path.write_text(html, encoding="utf-8")
    png_path = out / "full_page.png"
    try:
        _screenshot(html_path, png_path)
    except Exception as e:
        print(f"error: playwright screenshot failed: {e}", file=sys.stderr)
        print("hint: uv run playwright install chromium", file=sys.stderr)
        return 3

    # Per-section crops via full page only for v1 — manifest lists parts.
    manifest = {
        "created_at": ts,
        "out": str(out),
        "html": str(html_path),
        "full_page_png": str(png_path),
        "parts": [name for name, _ in sections],
        "dazzle_emit": bool(args.dazzle_emit),
        "billing": "subscription-playwright-only",
        "ship_gate": False,
        "review_hint": (
            "Dispatch a host-harness subagent to Read full_page_png (and "
            "optional crops). Do NOT call dazzle qa component-vision / taste-panel "
            "unless API credits are intentionally available. Dual-locks + gate "
            "suite remain the only ship-blocking visual floor."
        ),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    # Stable last-run pointer for improve backlog / cycle tooling (gitignored).
    last_path = REPO / ".dazzle" / "hm-visual-last.json"
    last_path.parent.mkdir(parents=True, exist_ok=True)
    last_path.write_text(
        json.dumps(
            {
                "created_at": ts,
                "out": str(out),
                "full_page_png": str(png_path),
                "parts": manifest["parts"],
                "dazzle_emit": manifest["dazzle_emit"],
                "billing": manifest["billing"],
                "ship_gate": False,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {html_path}")
    print(f"wrote {png_path}")
    print(f"wrote {out / 'manifest.json'}")
    print(f"wrote {last_path.relative_to(REPO)}")
    print(f"parts: {', '.join(manifest['parts'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
