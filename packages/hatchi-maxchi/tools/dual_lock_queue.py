#!/usr/bin/env python3
"""Rank the next dual-lock / Hyperpart contract promotions for /improve.

Source of truth for **coverage status**: monorepo
``tests/unit/hm_contract_registry.py`` + ``packages/hatchi-maxchi/contracts/``.

Source of truth for **emission readiness**: Dazzle
``src/dazzle/render/fragment/renderer/_emit*.py`` method names + HM
component CSS + site registry Hyperparts.

Usage (monorepo root)::

    python packages/hatchi-maxchi/tools/dual_lock_queue.py
    python packages/hatchi-maxchi/tools/dual_lock_queue.py --json
    python packages/hatchi-maxchi/tools/dual_lock_queue.py --top 5
    python packages/hatchi-maxchi/tools/dual_lock_queue.py --write   # → DUAL_LOCK_QUEUE.md

The /improve hm-convergence lane's ``dual_lock_expand`` strategy consumes
this queue: one cycle promotes the top actionable candidate (or a small
batch of 1–2 siblings) to schema+DOM (or DOM-only when no ingest model).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
REPO = PKG.parent.parent
REGISTRY = REPO / "tests" / "unit" / "hm_contract_registry.py"
RENDERER = REPO / "src" / "dazzle" / "render" / "fragment" / "renderer"
COMPONENTS = PKG / "components"
SITE_REGISTRY = PKG / "site" / "registry.py"
OUT = PKG / "DUAL_LOCK_QUEUE.md"

# Known primitive → preferred dual-lock stem (snake). Extend as emitters land.
_EMIT_TO_STEM: dict[str, str] = {
    "_emit_list_region": "list_region",
    "_emit_grid_region": "grid_region",
    "_emit_calendar_grid": "calendar",
    "_emit_tree": "tree",
    "_emit_diagram": "diagram",
    "_emit_pipeline_steps": "pipeline",
    "_emit_date_range_picker": "date_range",
    "_emit_search_box": "search_box",
    "_emit_pagination": "pagination",
    "_emit_empty_state": "empty_state",
    "_emit_skeleton": "skeleton",
    "_emit_cohort_strip_region": "cohort_strip",
    "_emit_day_timeline_region": "day_timeline",
    "_emit_task_inbox_region": "task_inbox",
    "_emit_entity_card_region": "entity_card",
    "_emit_dashboard_card": "dashboard_card",
    "_emit_workspace_overflow": "menu",  # details.dz-menu More ⋯ (#1491)
    "_emit_badge": "badge",
    "_emit_button": "button",
    "_emit_card": "card",
    "_emit_drawer": "drawer",
    "_emit_toolbar": "toolbar",
    "_emit_card_picker": "card_picker",
    "_emit_add_card_row": "add_card_row",
    "_emit_bulk_action_toolbar": "bulk_actions",
    "_emit_workspace_toolbar": "workspace_toolbar",
    "_emit_list_filter_bar": "filter_bar",
    "_emit_skip_link": "skip_link",
    "_emit_topbar": "topbar",
    "_emit_sidebar": "sidebar",
    "_emit_related_cards": "related_group",
    "_emit_related_files": "related_group",
    "_emit_surface": "surface",
    "_emit_stack": "stack",
    "_emit_row": "cluster",  # Row → .dz-cluster Hyperpart
    "_emit_heading": "heading",
    "_emit_split": "split",
    "_emit_text": "text",
    "_emit_icon": "icon",
    "_emit_link": "link",
    "_emit_inline_edit": "inline_edit",
    "_emit_grid": "layout_grid",  # layout Grid → .dz-grid (not data table grid)
    "_emit_region": "region",
    "_emit_interactive": "interactive",
    "_emit_field": "form_field",
    "_emit_form_stack": "form_stack",
    "_emit_submit": "submit",
    "_emit_form_section": "form_section",
    "_emit_form_stepper": "form_stepper",
    "_emit_kpi": "kpi",
    "_emit_file_upload": "file_upload",
    "_emit_ref_picker": "ref_picker",
    "_emit_rich_text": "rich_text",
    "_emit_csv_export_button": "csv_export_button",
    "_emit_sort_header": "sort_header",
    "_emit_column_visibility_menu": "column_visibility_menu",
    "_emit_metrics_grid": "metrics_grid",
    "_emit_nav_item": "nav_item",
    "_emit_nav_group": "nav_group",
    "_emit_workspace_context_selector": "workspace_context",
    "_emit_detail_grid": "detail_grid",
    "_emit_action_grid": "action_grid_region",
    "_emit_pivot_table": "pivot_table",
    "_emit_dashboard_grid": "dashboard_grid",
}


@dataclass(frozen=True)
class Candidate:
    stem: str
    kind: str  # schema_promote | contract_none | emitter_uncontracted | gallery_uncontracted
    priority: int  # lower = sooner
    dual_lock: str  # current status
    has_contract: bool
    has_css: bool
    has_gallery: bool
    emitters: list[str]
    reason: str
    suggested_action: str


def _extract_list(list_name: str, text: str) -> list[str]:
    m = re.search(rf"{list_name}: list\[.*?\] = \[(.*?)\]\n\n", text, re.S)
    if not m:
        m = re.search(rf"{list_name}: list\[.*?\] = \[(.*?)\]\n", text, re.S)
    if not m:
        return []
    return re.findall(r"contracts/([\w]+)\.py", m.group(1))


def _emitters() -> dict[str, str]:
    """method_name → relative file."""
    out: dict[str, str] = {}
    if not RENDERER.is_dir():
        return out
    for p in sorted(RENDERER.glob("_render_*.py")):
        rel = str(p.relative_to(REPO))
        for m in re.finditer(r"def (_emit_\w+)\(", p.read_text(encoding="utf-8")):
            out[m.group(1)] = rel
    return out


def _gallery_ids() -> set[str]:
    if not SITE_REGISTRY.is_file():
        return set()
    text = SITE_REGISTRY.read_text(encoding="utf-8")
    return set(re.findall(r'Hyperpart\(\s*"([a-z0-9-]+)"', text))


def _gallery_with_contracts() -> set[str]:
    if not SITE_REGISTRY.is_file():
        return set()
    text = SITE_REGISTRY.read_text(encoding="utf-8")
    contracted: set[str] = set()
    for m in re.finditer(
        r'Hyperpart\(\s*"([a-z0-9-]+)"[\s\S]*?contracts=\(([^)]*)\)',
        text,
    ):
        if "contracts/" in m.group(2):
            contracted.add(m.group(1))
    return contracted


def _css_stems() -> set[str]:
    if not COMPONENTS.is_dir():
        return set()
    return {p.stem.replace("-", "_") for p in COMPONENTS.glob("*.css")}


def inventory() -> list[Candidate]:
    reg_text = REGISTRY.read_text(encoding="utf-8") if REGISTRY.is_file() else ""
    schema = set(_extract_list("CONTRACT_MODELS", reg_text))
    dom_only = set(_extract_list("DOM_ONLY_CONTRACTS", reg_text))
    deferred = set(_extract_list("DOM_ONLY_DEFERRED", reg_text))
    locked = schema | dom_only | deferred

    contracts = {
        p.stem
        for p in (PKG / "contracts").glob("*.py")
        if p.stem not in ("__init__", "_kit") and not p.name.startswith("AUTHORING")
    }
    emitters = _emitters()
    gallery = _gallery_ids()
    gallery_c = _gallery_with_contracts()
    css = _css_stems()

    cands: list[Candidate] = []

    # 1) Contract exists, dual-lock none (e.g. code)
    for stem in sorted(contracts - locked):
        has_css = stem in css or stem.replace("_", "-") in {g.replace("-", "_") for g in gallery}
        hy = stem.replace("_", "-")
        related = [m for m, _ in emitters.items() if hy.replace("-", "_") in m or stem in m]
        cands.append(
            Candidate(
                stem=stem,
                kind="contract_none",
                priority=10 if related else 40,
                dual_lock="none",
                has_contract=True,
                has_css=has_css,
                has_gallery=hy in gallery,
                emitters=related,
                reason="Contract module exists but not in CONTRACT_MODELS / DOM_ONLY_CONTRACTS",
                suggested_action=(
                    "DOM-only dual-lock if a stable Dazzle emission path exists; "
                    "else schema+DOM once an ingest model lands; "
                    "else document BLOCKED (gallery-only) in backlog."
                ),
            )
        )

    # 2) DOM-only that could gain schema (has BaseModel in contract)
    for stem in sorted(dom_only):
        path = PKG / "contracts" / f"{stem}.py"
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if "BaseModel" not in text:
            continue
        # already has model but only DOM-locked — rare promote path
        if stem in schema:
            continue
        # skip pure DOM contracts without model classes
        if not re.search(r"^class \w+\(BaseModel\)", text, re.M):
            continue
        cands.append(
            Candidate(
                stem=stem,
                kind="schema_promote",
                priority=20,
                dual_lock="DOM-only",
                has_contract=True,
                has_css=stem in css,
                has_gallery=stem.replace("_", "-") in gallery,
                emitters=[],
                reason="DOM-only contract already carries a Pydantic model — promote to schema+DOM",
                suggested_action="Add CONTRACT_MODELS row(s) + ingest seam copy + schema parity gate.",
            )
        )

    # 3) Known emitters without contracts (product dual-lock expansion)
    for method, stem in _EMIT_TO_STEM.items():
        if stem in locked or stem in contracts:
            continue
        if method not in emitters:
            continue
        hy = stem.replace("_", "-")
        cands.append(
            Candidate(
                stem=stem,
                kind="emitter_uncontracted",
                priority=15 if stem in css or hy in gallery else 25,
                dual_lock="missing",
                has_contract=False,
                has_css=stem in css or hy.replace("-", "_") in css,
                has_gallery=hy in gallery,
                emitters=[method],
                reason=f"Stable FragmentRenderer path {method} with no dual-lock contract",
                suggested_action=(
                    "Scaffold contracts/<stem>.py (model + DOM_CONTRACT + render), "
                    "ingest seam + sole-emitter, CONTRACT_MODELS + DOM test, Tier 0 ship."
                ),
            )
        )

    # 4) Gallery Hyperparts without contracts= (CSS surface backlog)
    for gid in sorted(gallery - gallery_c):
        stem = gid.replace("-", "_")
        if stem in locked or stem in contracts:
            continue
        if any(c.stem == stem for c in cands):
            continue
        # skip pure layout primitives already covered elsewhere
        cands.append(
            Candidate(
                stem=stem,
                kind="gallery_uncontracted",
                priority=50 if stem not in css else 35,
                dual_lock="missing",
                has_contract=False,
                has_css=stem in css,
                has_gallery=True,
                emitters=[],
                reason="Registry Hyperpart has no contracts= and no dual-lock row",
                suggested_action=(
                    "Optional: scaffold root-only DOM contract when a Dazzle emission "
                    "path exists; otherwise leave as CSS-only gallery surface."
                ),
            )
        )

    cands.sort(key=lambda c: (c.priority, c.stem))
    return cands


def render_md(cands: list[Candidate], *, top: int | None) -> str:
    rows = cands if top is None else cands[:top]
    lines = [
        "# Dual-lock promotion queue",
        "",
        "Auto-generated by `tools/dual_lock_queue.py`. Do not hand-edit.",
        "",
        "Regenerate: `python packages/hatchi-maxchi/tools/dual_lock_queue.py --write`",
        "",
        "Consumed by: `/improve hm-convergence` → strategy `dual_lock_expand`.",
        "",
        "## How to run a cycle",
        "",
        "1. `python packages/hatchi-maxchi/tools/dual_lock_queue.py --top 5`",
        "2. Pick the **lowest priority** row that is not BLOCKED (prefer "
        "`emitter_uncontracted` / `contract_none` with emitters).",
        "3. Follow `.claude/commands/improve/strategies/dual_lock_expand.md`.",
        "4. Ship with Tier 0; re-run this tool — the promoted stem must leave the queue.",
        "",
        "| # | stem | kind | pri | dual-lock | contract | css | gallery | emitters | action |",
        "|--:|------|------|----:|-----------|:--------:|:---:|:-------:|----------|--------|",
    ]
    for i, c in enumerate(rows, 1):
        em = ", ".join(c.emitters) if c.emitters else "—"
        lines.append(
            f"| {i} | `{c.stem}` | {c.kind} | {c.priority} | {c.dual_lock} | "
            f"{'yes' if c.has_contract else 'no'} | "
            f"{'yes' if c.has_css else 'no'} | "
            f"{'yes' if c.has_gallery else 'no'} | `{em}` | {c.suggested_action} |"
        )
    lines.extend(
        [
            "",
            "## Kind legend",
            "",
            "| kind | meaning |",
            "|------|---------|",
            "| `contract_none` | `contracts/<stem>.py` exists, not dual-locked |",
            "| `schema_promote` | DOM-only contract already has a Pydantic model |",
            "| `emitter_uncontracted` | FragmentRenderer `_emit_*` ready, no contract |",
            "| `gallery_uncontracted` | Registry Hyperpart without `contracts=` |",
            "",
            f"**Queue depth:** {len(cands)} candidates (showing {len(rows)}).",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="JSON array to stdout")
    ap.add_argument("--top", type=int, default=None, help="Limit rows")
    ap.add_argument("--write", action="store_true", help=f"Write {OUT.name}")
    args = ap.parse_args()

    cands = inventory()
    if args.json:
        payload = [asdict(c) for c in (cands if args.top is None else cands[: args.top])]
        print(json.dumps(payload, indent=2))
        return 0

    md = render_md(cands, top=args.top)
    if args.write:
        OUT.write_text(md, encoding="utf-8")
        print(f"wrote {OUT}", file=sys.stderr)
    else:
        print(md, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
