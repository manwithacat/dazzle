#!/usr/bin/env python3
"""shadcn/ui ↔ HaTchi-MaXchi Hyperpart parity inventory.

Pins the public shadcn component catalogue (docs index as of 2026-07)
against monorepo Hyperparts (``site/registry.py``), CSS modules, and
contracts. Emits a greppable map the /improve loop can seed from.

Usage (monorepo root)::

    python packages/hatchi-maxchi/tools/shadcn_parity.py
    python packages/hatchi-maxchi/tools/shadcn_parity.py --write
    python packages/hatchi-maxchi/tools/shadcn_parity.py --json
    python packages/hatchi-maxchi/tools/shadcn_parity.py --gaps-only

Statuses
--------
parity
    Named Hyperpart (or deliberate HM equivalent) covers the job.
partial
    Covered by composition / form primitives / related part — not 1:1.
gap
    No first-class Hyperpart; placeholder HMC row should exist for the loop.
n/a
    shadcn surface we refuse (React-only / SPA chrome) — not a Hyperpart target.

Source: https://ui.shadcn.com/docs/components (base catalogue).
Re-audit when shadcn ships a "New" wave — bump SHADCN_CATALOGUE_DATE.
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
SITE_REGISTRY = PKG / "site" / "registry.py"
COMPONENTS = PKG / "components"
CONTRACTS = PKG / "contracts"
OUT = PKG / "SHADCN_PARITY.md"

# Pinned catalogue — ui.shadcn.com/docs/components "All Components" (2026-07).
SHADCN_CATALOGUE_DATE = "2026-07-12"
SHADCN_SOURCE = "https://ui.shadcn.com/docs/components"

# (shadcn_id, status, hm_map, notes)
# status ∈ parity | partial | gap | n/a
# hm_map: comma-separated registry ids / contract stems / "form:" / "layout:"
_MAP: list[tuple[str, str, str, str]] = [
    # ── Core / actions ─────────────────────────────────────────────
    ("accordion", "parity", "accordion", "Gallery Hyperpart; dual-lock optional"),
    ("alert", "parity", "alert", "Feedback surface"),
    (
        "alert-dialog",
        "partial",
        "confirm,confirm-panel,dialog",
        "HM splits native confirm vs confirm-gate vs dialog — map job, not name",
    ),
    (
        "aspect-ratio",
        "parity",
        "aspect-ratio",
        "Gallery Hyperpart — CSS aspect-ratio + data-dz-ratio presets",
    ),
    (
        "attachment",
        "partial",
        "form:file-upload,pdf",
        "File upload + PDF viewer exist; no dedicated attachment chip list",
    ),
    ("avatar", "parity", "avatar", "Gallery"),
    ("badge", "parity", "badge", "Gallery + tone system"),
    ("breadcrumb", "parity", "breadcrumb", "Gallery"),
    (
        "bubble",
        "gap",
        "",
        "Chat bubble — shadcn New; no HM chat message surface",
    ),
    ("button", "parity", "button", "Gallery + data-dz-variant"),
    (
        "button-group",
        "partial",
        "toggle-group,toolbar,controls",
        "Compose toggle-group / toolbar; no dedicated button-group id",
    ),
    (
        "calendar",
        "partial",
        "date-range",
        "Date-range + CalendarGrid emit exist; no full month-picker Hyperpart",
    ),
    ("card", "parity", "card", "Gallery + dashboard-card chrome"),
    (
        "carousel",
        "parity",
        "carousel",
        "Gallery Hyperpart — SSR strip + data-dz-active slide; controller deferred",
    ),
    (
        "chart",
        "partial",
        "bar-chart,time-series,radar,sparkline,histogram,box-plot,funnel,heatmap,bullet,bar-track,chart-legend",
        "HM owns server-SVG chart family; shadcn is Recharts client wrapper",
    ),
    (
        "checkbox",
        "partial",
        "field,form",
        "Native form field; not a named Hyperpart (deliberate)",
    ),
    (
        "collapsible",
        "partial",
        "accordion",
        "Accordion covers disclosure; single collapsible root optional",
    ),
    ("combobox", "parity", "combobox", "schema+DOM dual-lock"),
    ("command", "parity", "command", "DOM-only dual-lock"),
    (
        "context-menu",
        "partial",
        "menu",
        "menu Hyperpart; right-click affordance not dual-locked",
    ),
    (
        "data-table",
        "partial",
        "grid,list-region,table",
        "grid + list-region + grid-edit dual-locks; not named data-table",
    ),
    (
        "date-picker",
        "partial",
        "date-range",
        "Native date + date-range Hyperpart; flatpickr retired",
    ),
    ("dialog", "parity", "dialog", "DOM-only dual-lock"),
    ("direction", "n/a", "", "RTL dir helper — page/theme concern, not a part"),
    ("drawer", "parity", "drawer", "Gallery; sheet maps here"),
    (
        "dropdown-menu",
        "partial",
        "menu",
        "menu Hyperpart covers dropdown job",
    ),
    ("empty", "parity", "empty-state", "empty-state Hyperpart"),
    ("field", "parity", "field,form-chrome", "field-triad + form chrome"),
    (
        "hover-card",
        "parity",
        "hover-card",
        "Gallery Hyperpart — CSS :hover/:focus-within panel",
    ),
    (
        "input",
        "partial",
        "field,form",
        "Native inputs via field triad — not a decorative Input part",
    ),
    (
        "input-group",
        "partial",
        "form-chrome",
        "Addon/prefix chrome lives in form-chrome",
    ),
    (
        "input-otp",
        "partial",
        "two-factor",
        "two-factor Hyperpart; general OTP input not extracted",
    ),
    (
        "item",
        "parity",
        "item",
        "Gallery Hyperpart — media + title + description + actions row",
    ),
    (
        "kbd",
        "parity",
        "kbd",
        "Gallery Hyperpart; styles in hm-core.css (.dz-kbd)",
    ),
    (
        "label",
        "partial",
        "field",
        "Label is part of field triad, not standalone",
    ),
    ("marker", "gap", "", "shadcn New — map/marker chrome"),
    (
        "menubar",
        "parity",
        "menubar",
        "Gallery Hyperpart — horizontal File/Edit/View via native details",
    ),
    (
        "message",
        "gap",
        "",
        "Chat message row — shadcn New; no HM messaging surface",
    ),
    (
        "message-scroller",
        "gap",
        "",
        "Chat transcript scroller — shadcn New",
    ),
    (
        "native-select",
        "partial",
        "field,combobox",
        "Native select via forms; combobox enhances",
    ),
    (
        "navigation-menu",
        "gap",
        "app-shell",
        "Top nav mega-menu; app-shell covers sidebar nav only",
    ),
    ("pagination", "parity", "pagination", "Gallery Hyperpart"),
    ("popover", "parity", "popover", "Gallery"),
    ("progress", "parity", "progress,progress-region", "Bar + stage chips"),
    (
        "radio-group",
        "partial",
        "field,toggle-group",
        "Native radios / toggle-group; not named radio-group",
    ),
    (
        "resizable",
        "partial",
        "master-detail,grid-resize",
        "master-detail + grid-resize cover split panes; no generic Resizable",
    ),
    (
        "scroll-area",
        "partial",
        "layout,mobile-scroll",
        "Scroll containment CSS; no ScrollArea part",
    ),
    (
        "select",
        "partial",
        "combobox,field",
        "combobox dual-lock + native select",
    ),
    ("separator", "parity", "separator", "Gallery"),
    (
        "sheet",
        "partial",
        "drawer",
        "Drawer is the sheet/side-panel Hyperpart",
    ),
    (
        "sidebar",
        "parity",
        "app-shell,sidebar-layout",
        "app-shell dual-lock + layout primitive",
    ),
    ("skeleton", "parity", "skeleton", "Gallery"),
    ("slider", "parity", "slider", "DOM-only dual-lock"),
    (
        "sonner",
        "partial",
        "fragments",
        "Toast stack in fragments/htmx states — not named sonner",
    ),
    (
        "spinner",
        "partial",
        "htmx-states",
        "dz-spinner-* in htmx-states; not a gallery Hyperpart",
    ),
    (
        "switch",
        "parity",
        "switch",
        "Gallery Hyperpart — progressive checkbox + data-dz-switch; dual-lock later",
    ),
    (
        "table",
        "partial",
        "grid,list-region,table",
        "grid dual-lock + list-region + CSS table",
    ),
    ("tabs", "parity", "tabs", "DOM-only dual-lock"),
    (
        "textarea",
        "partial",
        "field,form",
        "Native textarea via field triad",
    ),
    (
        "toast",
        "partial",
        "fragments",
        "Toast stack exists; dual-lock not first-class",
    ),
    (
        "toggle",
        "parity",
        "toggle",
        "Gallery Hyperpart — button + aria-pressed; distinct from switch/toggle-group",
    ),
    ("toggle-group", "parity", "toggle-group", "Gallery"),
    ("tooltip", "parity", "tooltip", "Gallery"),
    (
        "typography",
        "partial",
        "layout",
        "Prose via layout/text primitives; no Typography Hyperpart",
    ),
]


@dataclass(frozen=True)
class Row:
    shadcn: str
    status: str
    hm_map: str
    notes: str
    hm_present: bool  # at least one mapped Hyperpart id exists


def _hyperpart_ids() -> set[str]:
    if not SITE_REGISTRY.is_file():
        return set()
    text = SITE_REGISTRY.read_text(encoding="utf-8")
    return set(re.findall(r'Hyperpart\(\s*"([a-z0-9-]+)"', text))


def _css_stems() -> set[str]:
    if not COMPONENTS.is_dir():
        return set()
    return {p.stem for p in COMPONENTS.glob("*.css")}


def _contract_stems() -> set[str]:
    if not CONTRACTS.is_dir():
        return set()
    return {
        p.stem
        for p in CONTRACTS.glob("*.py")
        if p.stem not in ("__init__", "_kit") and not p.name.startswith("AUTHORING")
    }


def inventory() -> list[Row]:
    parts = _hyperpart_ids()
    rows: list[Row] = []
    for shadcn, status, hm_map, notes in _MAP:
        tokens = [t.strip() for t in hm_map.split(",") if t.strip()]
        present = any(
            t in parts
            or t.replace("_", "-") in parts
            or t.startswith("form:")
            or t.startswith("layout:")
            for t in tokens
        )
        # gap with empty map is never present
        if status == "gap" and not tokens:
            present = False
        rows.append(
            Row(
                shadcn=shadcn,
                status=status,
                hm_map=hm_map or "—",
                notes=notes,
                hm_present=present,
            )
        )
    return rows


def summary(rows: list[Row]) -> dict[str, int]:
    out = {"parity": 0, "partial": 0, "gap": 0, "n/a": 0, "total": len(rows)}
    for r in rows:
        out[r.status] = out.get(r.status, 0) + 1
    return out


def render_md(rows: list[Row]) -> str:
    s = summary(rows)
    parts = sorted(_hyperpart_ids())
    lines = [
        "# shadcn/ui ↔ HaTchi-MaXchi parity",
        "",
        "Auto-generated by `tools/shadcn_parity.py`. Do not hand-edit the tables.",
        "",
        "Regenerate: `python packages/hatchi-maxchi/tools/shadcn_parity.py --write`",
        "",
        f"**Catalogue pin:** {SHADCN_CATALOGUE_DATE} · source: {SHADCN_SOURCE}",
        "",
        "Goal: **parity at minimum** — every shadcn surface UX developers expect",
        "has a Hyperpart (or an explicit refuse/n-a). The /improve loop promotes",
        "`gap` → `partial` → `parity` via strategy `shadcn_parity` + dual-locks.",
        "",
        "## Summary",
        "",
        "| Status | Count |",
        "|--------|------:|",
        f"| **parity** | {s['parity']} |",
        f"| **partial** | {s['partial']} |",
        f"| **gap** (placeholders) | {s['gap']} |",
        f"| **n/a** | {s['n/a']} |",
        f"| **total shadcn** | {s['total']} |",
        f"| HM Hyperparts (registry) | {len(parts)} |",
        "",
        "## Mapping",
        "",
        "| shadcn | status | HM map | notes |",
        "|--------|--------|--------|-------|",
    ]
    for r in rows:
        lines.append(f"| `{r.shadcn}` | **{r.status}** | `{r.hm_map}` | {r.notes} |")

    gaps = [r for r in rows if r.status == "gap"]
    lines.extend(
        [
            "",
            "## Gaps (improve-loop placeholders)",
            "",
            "Each row is a candidate `HMC-NNN` scope `shadcn_parity <id>`.",
            "Playbook: `.claude/commands/improve/strategies/shadcn_parity.md`.",
            "",
            "| # | shadcn | suggested Hyperpart id | notes |",
            "|--:|--------|------------------------|-------|",
        ]
    )
    for i, r in enumerate(gaps, 1):
        suggested = r.shadcn  # default id
        lines.append(f"| {i} | `{r.shadcn}` | `{suggested}` | {r.notes} |")

    lines.extend(
        [
            "",
            "## Status definitions",
            "",
            "| status | meaning |",
            "|--------|---------|",
            "| parity | First-class Hyperpart (or intentional equivalent name) |",
            "| partial | Job covered by composition / forms / related part |",
            "| gap | Missing surface — seed PENDING backlog row |",
            "| n/a | Explicitly not a Hyperpart target |",
            "",
            "## Improve loop",
            "",
            "```bash",
            "python packages/hatchi-maxchi/tools/shadcn_parity.py --gaps-only",
            "/improve hm-convergence shadcn_parity",
            "```",
            "",
            "Prefer promoting **gap** rows that have a Dazzle emission path or",
            "clear gallery partial. Dual-lock after the surface exists",
            "(`dual_lock_expand`).",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--gaps-only", action="store_true")
    args = ap.parse_args()

    rows = inventory()
    if args.gaps_only:
        rows = [r for r in rows if r.status == "gap"]

    if args.json:
        print(json.dumps([asdict(r) for r in rows], indent=2))
        print(json.dumps(summary(inventory()), indent=2), file=sys.stderr)
        return 0

    md = render_md(inventory() if not args.gaps_only else inventory())
    if args.gaps_only:
        # still show full map on --write; gaps-only is stdout filter for agents
        s = summary(inventory())
        print(f"# Gaps only ({s['gap']})\n")
        for r in [x for x in inventory() if x.status == "gap"]:
            print(f"- `{r.shadcn}`: {r.notes}")
        return 0

    if args.write:
        OUT.write_text(md, encoding="utf-8")
        print(f"wrote {OUT}", file=sys.stderr)
        print(json.dumps(summary(inventory())), file=sys.stderr)
    else:
        print(md, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
