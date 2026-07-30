#!/usr/bin/env python3
"""HM gallery interaction probes — deterministic UX contracts for Hyperparts.

Autonomous improve of HaTchi-MaXchi needs more than static screenshots:
many real gallery bugs are **interaction** defects (e.g. menubar: open Edit
does not close File). This tool is the machine half of that loop:

1. **Catalog** — declarative probes keyed by stem + claim
2. **Discover** — static scan for multi-``<details>`` roots that need exclusive-open
3. **Run** — Playwright against local ``site/`` (or a base URL)
4. **Report** — JSON findings agents / improve can drain
5. **Observe** — map a human observation card onto a probe (or FAIL with
   ``NO_PROBE`` so we know what to author next)

Does **not** call metered vision APIs. Cognitive review of FAIL screenshots
is optional host-Read (subscription), same policy as ``hm_visual_smoke``.

Usage (monorepo root or package)::

    python packages/hatchi-maxchi/tools/gallery_probes.py --list
    python packages/hatchi-maxchi/tools/gallery_probes.py --discover
    python packages/hatchi-maxchi/tools/gallery_probes.py --run
    python packages/hatchi-maxchi/tools/gallery_probes.py --run --stem menubar
    python packages/hatchi-maxchi/tools/gallery_probes.py --run --json
    python packages/hatchi-maxchi/tools/gallery_probes.py \\
        --validate-observation '{"stem":"menubar","claim":"exclusive open"}'

Exit codes: 0 all PASS/SKIP; 1 any FAIL; 2 harness ERROR.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PKG = Path(__file__).resolve().parents[1]
SITE = PKG / "site"
DEFAULT_OUT = PKG.parents[1] / ".dazzle" / "hm-gallery-probes"  # monorepo .dazzle/
if not (PKG.parents[1] / "src" / "dazzle").is_dir():
    DEFAULT_OUT = PKG / ".dazzle" / "hm-gallery-probes"

SCHEMA = "hm.gallery_probes.v1"


# ── Catalog ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Probe:
    """One interaction contract for a gallery Hyperpart."""

    id: str
    stem: str
    page: str  # path under site/, e.g. hyperparts/menubar.html
    category: str  # interaction | layout | a11y | …
    severity: str  # blocker | high | medium | low
    claim: str
    kind: str  # runner dispatch key
    params: dict[str, Any] = field(default_factory=dict)
    fix_surface: str = "controller"  # controller | css | partial | gallery-only | contract
    # exclusive = only one open; multi_open = intentional multi-expand (tree);
    # hover = CSS/hover reveal (tooltip pseudo, not details)
    intent: str = "exclusive"


# Built-in probes. Author more here (or later: probes/*.toml discovery).
PROBES: tuple[Probe, ...] = (
    Probe(
        id="menubar.exclusive_open",
        stem="menubar",
        page="hyperparts/menubar.html",
        category="interaction",
        severity="high",
        claim=(
            "Opening a second menubar item closes the previously open item "
            "(exclusive open — File then Edit leaves only Edit open)"
        ),
        kind="exclusive_details_open",
        params={
            "root": "[data-dz-menubar], .dz-menubar, .menubar, [data-menubar]",
            "item": "details.dz-menubar__item, details.menubar__item",
            "trigger": "summary.dz-menubar__trigger, summary.menubar__trigger",
            "sequence": ["File", "Edit"],
            "expect_open_labels": ["Edit"],
            "scope": ".hm-preview",
        },
        fix_surface="controller",
        intent="exclusive",
    ),
    Probe(
        id="navigation_menu.exclusive_open",
        stem="navigation-menu",
        page="hyperparts/navigation-menu.html",
        category="interaction",
        severity="high",
        claim=(
            "Opening a second navigation-menu panel closes the previously open "
            "panel (exclusive open — Product then Resources leaves only Resources open)"
        ),
        kind="exclusive_details_open",
        params={
            "root": (
                "[data-dz-navigation-menu], .dz-navigation-menu, "
                ".navigation-menu, [data-navigation-menu]"
            ),
            "item": (
                "details.dz-navigation-menu__branch, details.navigation-menu__branch, "
                "[data-dz-navigation-menu] details, .navigation-menu details"
            ),
            "trigger": ("summary.dz-navigation-menu__trigger, summary.navigation-menu__trigger"),
            "sequence": ["Product", "Resources"],
            # summary text includes caret glyph — match by contains
            "expect_open_contains": ["Resources"],
            "scope": ".hm-preview",
        },
        fix_surface="controller",
        intent="exclusive",
    ),
    Probe(
        id="accordion.exclusive_open",
        stem="accordion",
        page="hyperparts/accordion.html",
        category="interaction",
        severity="medium",
        claim=(
            "Accordion items sharing the HTML name= attribute stay exclusive "
            "(open second trigger leaves only that panel open — zero JS)"
        ),
        kind="exclusive_details_open",
        params={
            "root": ".dz-accordion, .accordion",
            "item": "details.dz-accordion__item, details.accordion__item",
            "trigger": "summary.dz-accordion__trigger, summary.accordion__trigger",
            "sequence": [
                "Do I need a client framework?",
                "Can two panels be open at once?",
            ],
            "expect_open_contains": ["Can two panels be open at once?"],
        },
        fix_surface="partial",  # native name= on details
        intent="exclusive",
    ),
    Probe(
        id="tree.multi_open",
        stem="tree",
        page="hyperparts/tree.html",
        category="interaction",
        severity="medium",
        claim=(
            "Tree nodes stay multi-open by design — expanding Platform then "
            "Design systems leaves both open (native details forest, no exclusive controller)"
        ),
        kind="multi_details_open",
        params={
            "root": "[data-dz-tree], .dz-tree, .tree, [data-tree]",
            # single class branch only — avoid OR multi-match double-counting open nodes
            "item": "details.dz-tree-node, details.tree-node",
            "trigger": "summary.dz-tree-summary, summary.tree-summary",
            # Engineering is open by default; open two siblings under it
            "sequence": ["Platform", "Design systems"],
            "expect_open_contains_all": ["Engineering", "Platform", "Design systems"],
            "expect_min_open": 3,
            # ignore .hm-contract-live__preview twin forest
            "scope": ".hm-preview",
        },
        fix_surface="partial",
        intent="multi_open",
    ),
    Probe(
        id="menubar.dismiss_outside",
        stem="menubar",
        page="hyperparts/menubar.html",
        category="interaction",
        severity="high",
        claim=(
            "Clicking outside the menubar closes the open panel "
            "(app chrome must not leave File/Edit stuck open)"
        ),
        kind="details_dismiss_outside",
        params={
            "root": "[data-dz-menubar], .dz-menubar, .menubar, [data-menubar]",
            "item": "details.dz-menubar__item, details.menubar__item",
            "trigger": "summary.dz-menubar__trigger, summary.menubar__trigger",
            "open_label": "File",
            "scope": ".hm-preview",
        },
        fix_surface="controller",
        intent="exclusive",
    ),
    Probe(
        id="navigation_menu.dismiss_outside",
        stem="navigation-menu",
        page="hyperparts/navigation-menu.html",
        category="interaction",
        severity="high",
        claim=(
            "Clicking outside the navigation menu closes the open panel "
            "(mega panels must not stick after leaving the nav)"
        ),
        kind="details_dismiss_outside",
        params={
            "root": (
                "[data-dz-navigation-menu], .dz-navigation-menu, "
                ".navigation-menu, [data-navigation-menu]"
            ),
            "item": (
                "details.dz-navigation-menu__branch, details.navigation-menu__branch, "
                "[data-dz-navigation-menu] details, .navigation-menu details"
            ),
            "trigger": ("summary.dz-navigation-menu__trigger, summary.navigation-menu__trigger"),
            "open_label": "Product",
            "scope": ".hm-preview",
        },
        fix_surface="controller",
        intent="exclusive",
    ),
    Probe(
        id="popover.dismiss_outside",
        stem="popover",
        page="hyperparts/popover.html",
        category="interaction",
        severity="high",
        claim=(
            "Clicking outside an open popover closes it "
            "(details-light-dismiss spatial dismiss — free panels must not stick)"
        ),
        kind="details_dismiss_outside",
        params={
            "root": "details.popover, details.dz-popover, .popover, .dz-popover",
            "item": "details.popover, details.dz-popover",
            "trigger": "details.popover > summary, details.dz-popover > summary",
            "open_label": "Details",
            "scope": ".hm-preview",
        },
        fix_surface="controller",
        intent="exclusive",
    ),
    Probe(
        id="menu.dismiss_outside",
        stem="menu",
        page="hyperparts/menu.html",
        category="interaction",
        severity="high",
        claim=(
            "Clicking outside an open action menu closes it "
            "(details-light-dismiss spatial dismiss — local action menus must not stick)"
        ),
        kind="details_dismiss_outside",
        params={
            "root": "details.menu, details.dz-menu, .menu, .dz-menu",
            "item": "details.menu, details.dz-menu",
            "trigger": "details.menu > summary, details.dz-menu > summary",
            "open_label": "Actions",
            "scope": ".hm-preview",
        },
        fix_surface="controller",
        intent="exclusive",
    ),
    Probe(
        id="menubar.escape_dismiss",
        stem="menubar",
        page="hyperparts/menubar.html",
        category="interaction",
        severity="high",
        claim=(
            "Pressing Escape closes the open menubar panel "
            "(keyboard dismiss must match outside-click — File must not stick)"
        ),
        kind="details_escape_dismiss",
        params={
            "root": "[data-dz-menubar], .dz-menubar, .menubar, [data-menubar]",
            "item": "details.dz-menubar__item, details.menubar__item",
            "trigger": "summary.dz-menubar__trigger, summary.menubar__trigger",
            "open_label": "File",
            "scope": ".hm-preview",
        },
        fix_surface="controller",
        intent="exclusive",
    ),
    Probe(
        id="dialog.escape_closes",
        stem="dialog",
        page="hyperparts/dialog.html",
        category="interaction",
        severity="high",
        claim=(
            "Pressing Escape closes an open modal dialog "
            "(native <dialog> cancel — modal must not trap Escape)"
        ),
        kind="native_dialog_escape",
        params={
            "open_trigger": "[data-dialog-open], [data-dz-dialog-open]",
            "dialog": "dialog.dialog, dialog.dz-dialog",
            "scope": ".hm-preview",
            "open_settle_ms": 150,
        },
        fix_surface="controller",
        intent="exclusive",
    ),
    Probe(
        id="drawer.escape_closes",
        stem="drawer",
        page="hyperparts/drawer.html",
        category="interaction",
        severity="high",
        claim=(
            "Pressing Escape closes an open drawer "
            "(drawer is a side <dialog> — Escape must dismiss filters/record panels)"
        ),
        kind="native_dialog_escape",
        params={
            "open_trigger": "[data-dialog-open], [data-dz-dialog-open]",
            "dialog": "dialog.drawer, dialog.dz-drawer",
            "scope": ".hm-preview",
            "open_settle_ms": 150,
        },
        fix_surface="controller",
        intent="exclusive",
    ),
    Probe(
        id="command.escape_closes",
        stem="command",
        page="hyperparts/command.html",
        category="interaction",
        severity="high",
        claim=(
            "Pressing Escape closes an open command palette "
            "(dz-command owns Esc — type=search must not trap the first Escape)"
        ),
        kind="native_dialog_escape",
        params={
            "open_trigger": "[data-hm-open-command], [data-dz-open-command]",
            "dialog": "dialog.command, dialog.dz-command, [data-command]",
            "scope": ".hm-preview",
            "open_settle_ms": 150,
        },
        fix_surface="controller",
        intent="exclusive",
    ),
    Probe(
        id="menu.escape_dismiss",
        stem="menu",
        page="hyperparts/menu.html",
        category="interaction",
        severity="high",
        claim=(
            "Pressing Escape closes an open action menu "
            "(details-light-dismiss keyboard path — Actions must not stick)"
        ),
        kind="details_escape_dismiss",
        params={
            "root": "details.menu, details.dz-menu, .menu, .dz-menu",
            "item": "details.menu, details.dz-menu",
            "trigger": "details.menu > summary, details.dz-menu > summary",
            "open_label": "Actions",
            "scope": ".hm-preview",
        },
        fix_surface="controller",
        intent="exclusive",
    ),
    Probe(
        id="tooltip.hover_shows_hint",
        stem="tooltip",
        page="hyperparts/tooltip.html",
        category="interaction",
        severity="medium",
        claim=(
            "Hovering the tooltip host reveals the CSS ::after hint "
            "(data-tooltip rest state is closed; tip must appear on hover)"
        ),
        kind="css_tooltip_hover",
        params={
            # scoped to .hm-preview — first button is the live demo (not glossary terms)
            "host": "button[data-tooltip], button[data-dz-tooltip], [data-tooltip], [data-dz-tooltip]",
            "scope": ".hm-preview",
            "hover_settle_ms": 500,
            "expect_min_opacity": 0.85,
        },
        fix_surface="css",
        intent="hover",
    ),
    Probe(
        id="tooltip.force_open_shows_hint",
        stem="tooltip",
        page="hyperparts/tooltip.html",
        category="interaction",
        severity="medium",
        claim=(
            "data-tooltip-open / data-dz-tooltip-open forces the CSS ::after hint "
            "visible without hover (capture / docs still path)"
        ),
        kind="css_tooltip_force_open",
        params={
            "host": "button[data-tooltip], button[data-dz-tooltip], [data-tooltip], [data-dz-tooltip]",
            "scope": ".hm-preview",
            "expect_min_opacity": 0.85,
        },
        fix_surface="css",
        intent="hover",
    ),
    Probe(
        id="popover.escape_dismiss",
        stem="popover",
        page="hyperparts/popover.html",
        category="interaction",
        severity="high",
        claim=(
            "Pressing Escape closes an open popover "
            "(details-light-dismiss keyboard path — free panels must not stick)"
        ),
        kind="details_escape_dismiss",
        params={
            "root": "details.popover, details.dz-popover, .popover, .dz-popover",
            "item": "details.popover, details.dz-popover",
            "trigger": "details.popover > summary, details.dz-popover > summary",
            "open_label": "Details",
            "scope": ".hm-preview",
        },
        fix_surface="controller",
        intent="exclusive",
    ),
    Probe(
        id="hover_card.escape_closes",
        stem="hover-card",
        page="hyperparts/hover-card.html",
        category="interaction",
        severity="high",
        claim=(
            "Pressing Escape closes a click-opened hover-card "
            "(touch path uses data-open — Escape must clear it so previews do not stick)"
        ),
        kind="data_open_escape",
        params={
            "root": ("[data-dz-hover-card], [data-hover-card], .dz-hover-card, .hover-card"),
            "trigger": ".dz-hover-card__trigger, .hover-card__trigger",
            "scope": ".hm-preview",
        },
        fix_surface="controller",
        intent="hover",
    ),
    Probe(
        id="hover_card.dismiss_outside",
        stem="hover-card",
        page="hyperparts/hover-card.html",
        category="interaction",
        severity="high",
        claim=(
            "Clicking outside a click-opened hover-card closes it "
            "(spatial dismiss for touch/explicit open — previews must not stick)"
        ),
        kind="data_open_dismiss_outside",
        params={
            "root": ("[data-dz-hover-card], [data-hover-card], .dz-hover-card, .hover-card"),
            "trigger": ".dz-hover-card__trigger, .hover-card__trigger",
            "scope": ".hm-preview",
        },
        fix_surface="controller",
        intent="hover",
    ),
    Probe(
        id="tabs.exclusive_select",
        stem="tabs",
        page="hyperparts/tabs.html",
        category="interaction",
        severity="high",
        claim=(
            "Selecting a second tab reveals only its panel and moves aria-current "
            "(exclusive select — Overview then Activity leaves only Activity visible)"
        ),
        kind="tabs_exclusive_select",
        params={
            "root": "[data-dz-tabs], [data-tabs], .dz-tabs, .tabs",
            "tab": ".dz-tabs__tab, .tabs__tab, [data-tab-target], [data-dz-tab-target]",
            "activate_label": "Activity",
            "expect_current_label": "Activity",
            "expect_panel_visible_id": "hm-tab-activity",
            "expect_panel_hidden_id": "hm-tab-overview",
            "scope": ".hm-preview",
        },
        fix_surface="controller",
        intent="exclusive",
    ),
)


# ── Runner kinds ─────────────────────────────────────────────────────────


def _norm_label(text: str) -> str:
    return " ".join(text.split())


def _open_item_selector(item_sel: str) -> str:
    """Append ``[open]`` to each comma-separated selector branch.

    ``f\"{item_sel}[open]\"`` is wrong for multi-branch lists: only the last
    branch gets the attribute filter, so closed items still match earlier
    branches (false FAIL with open_count inflated).
    """
    parts = [p.strip() for p in item_sel.split(",") if p.strip()]
    return ", ".join(f"{p}[open]" for p in parts)


def _probe_scope(page: Any, params: dict[str, Any]) -> Any:
    """Prefer gallery demo scope so contract-live / code exemplars are ignored.

    Gallery pages often mount a second live partial under
    ``.hm-contract-live__preview`` (e.g. tree). Default scope ``.hm-preview``
    keeps open-counts honest. Set ``scope: null`` / empty to search whole page.
    """
    if "scope" in params and not params["scope"]:
        return page.locator("body")
    scope_sel = params.get("scope", ".hm-preview")
    scoped = page.locator(scope_sel).first
    if scoped.count() > 0:
        return scoped
    return page.locator("body")


def _open_labels(scope: Any, item_sel: str) -> list[str]:
    open_items = scope.locator(_open_item_selector(item_sel))
    n = open_items.count()
    # direct child summary only — nested forests (tree) have descendant summaries
    return [
        _norm_label(open_items.nth(i).locator(":scope > summary").inner_text()) for i in range(n)
    ]


def _labels_match_expect(
    open_labels: list[str],
    *,
    expect_exact: list[str] | None,
    expect_contains: list[str] | None,
) -> bool:
    if expect_contains:
        if len(open_labels) != len(expect_contains):
            return False
        for got, needle in zip(open_labels, expect_contains, strict=True):
            if needle.lower() not in got.lower():
                return False
        return True
    expect = expect_exact or []
    return open_labels == expect


def _run_exclusive_details_open(page: Any, probe: Probe) -> dict[str, Any]:
    """Click triggers in sequence; assert only the last item stays open."""
    params = probe.params
    item_sel = params["item"]
    trigger_sel = params["trigger"]
    sequence: list[str] = list(params["sequence"])
    expect_exact: list[str] | None = (
        list(params["expect_open_labels"]) if "expect_open_labels" in params else None
    )
    expect_contains: list[str] | None = (
        list(params["expect_open_contains"]) if "expect_open_contains" in params else None
    )
    if expect_exact is None and expect_contains is None:
        expect_exact = sequence[-1:]

    scope = _probe_scope(page, params)
    root_loc = scope.locator(params["root"])
    if root_loc.count() == 0:
        return {
            "verdict": "ERROR",
            "detail": f"root not found ({params['root']}) in scope",
        }

    n_items = scope.locator(item_sel).count()
    if n_items < len(sequence):
        return {
            "verdict": "ERROR",
            "detail": f"need ≥{len(sequence)} items, found {n_items}",
        }

    for label in sequence:
        trig = scope.locator(trigger_sel).filter(has_text=label).first
        if trig.count() == 0:
            return {"verdict": "ERROR", "detail": f"trigger not found: {label!r}"}
        trig.click()
        page.wait_for_timeout(80)

    open_labels = _open_labels(scope, item_sel)
    open_count = len(open_labels)

    if _labels_match_expect(
        open_labels, expect_exact=expect_exact, expect_contains=expect_contains
    ):
        return {
            "verdict": "PASS",
            "detail": f"open_labels={open_labels}",
            "open_count": open_count,
            "open_labels": open_labels,
        }
    expect_desc = expect_contains if expect_contains is not None else expect_exact
    return {
        "verdict": "FAIL",
        "detail": (
            f"expected open≈{expect_desc}, got open_count={open_count} open_labels={open_labels}"
        ),
        "open_count": open_count,
        "open_labels": open_labels,
        "dom_hint": item_sel,
    }


def _run_multi_details_open(page: Any, probe: Probe) -> dict[str, Any]:
    """Click triggers in sequence; assert multiple items stay open (tree forest)."""
    params = probe.params
    item_sel = params["item"]
    trigger_sel = params["trigger"]
    sequence: list[str] = list(params.get("sequence") or [])
    expect_all: list[str] = list(params.get("expect_open_contains_all") or sequence)
    min_open = int(params.get("expect_min_open") or len(expect_all) or 2)

    scope = _probe_scope(page, params)
    root_loc = scope.locator(params["root"])
    if root_loc.count() == 0:
        return {"verdict": "ERROR", "detail": f"root not found ({params['root']}) in scope"}

    n_items = scope.locator(item_sel).count()
    if n_items < min_open:
        return {
            "verdict": "ERROR",
            "detail": f"need ≥{min_open} items, found {n_items}",
        }

    for label in sequence:
        trig = scope.locator(trigger_sel).filter(has_text=label).first
        if trig.count() == 0:
            return {"verdict": "ERROR", "detail": f"trigger not found: {label!r}"}
        # open if closed (click summary toggles)
        trig.click()
        page.wait_for_timeout(80)

    open_labels = _open_labels(scope, item_sel)
    open_count = len(open_labels)
    joined = " ".join(open_labels).lower()
    missing = [n for n in expect_all if n.lower() not in joined]
    if open_count >= min_open and not missing:
        return {
            "verdict": "PASS",
            "detail": f"open_count={open_count} open_labels={open_labels}",
            "open_count": open_count,
            "open_labels": open_labels,
        }
    return {
        "verdict": "FAIL",
        "detail": (
            f"expected multi-open min={min_open} contains_all={expect_all}, "
            f"got open_count={open_count} open_labels={open_labels} missing={missing}"
        ),
        "open_count": open_count,
        "open_labels": open_labels,
        "dom_hint": item_sel,
    }


def _run_details_dismiss_outside(page: Any, probe: Probe) -> dict[str, Any]:
    """Open first trigger, click outside root, assert no open details remain."""
    params = probe.params
    item_sel = params["item"]
    trigger_sel = params["trigger"]
    open_label = params.get("open_label")  # optional filter text

    scope = _probe_scope(page, params)
    root = scope.locator(params["root"]).first
    if root.count() == 0:
        return {"verdict": "ERROR", "detail": f"root not found ({params['root']})"}

    trig = scope.locator(trigger_sel)
    if open_label:
        trig = trig.filter(has_text=open_label)
    trig = trig.first
    if trig.count() == 0:
        return {"verdict": "ERROR", "detail": "trigger not found"}
    trig.click()
    page.wait_for_timeout(80)
    before = _open_labels(scope, item_sel)
    if not before:
        return {"verdict": "ERROR", "detail": "failed to open panel before outside click"}

    # click page chrome well outside the component
    page.mouse.click(8, 8)
    page.wait_for_timeout(100)
    after = _open_labels(scope, item_sel)
    if not after:
        return {
            "verdict": "PASS",
            "detail": f"dismissed after outside click (was {before})",
            "open_labels_before": before,
            "open_labels": after,
        }
    return {
        "verdict": "FAIL",
        "detail": f"outside click left open_labels={after} (before={before})",
        "open_labels_before": before,
        "open_labels": after,
        "dom_hint": item_sel,
    }


def _run_details_escape_dismiss(page: Any, probe: Probe) -> dict[str, Any]:
    """Open first trigger, press Escape, assert no open details remain."""
    params = probe.params
    item_sel = params["item"]
    trigger_sel = params["trigger"]
    open_label = params.get("open_label")

    scope = _probe_scope(page, params)
    root = scope.locator(params["root"]).first
    if root.count() == 0:
        return {"verdict": "ERROR", "detail": f"root not found ({params['root']})"}

    trig = scope.locator(trigger_sel)
    if open_label:
        trig = trig.filter(has_text=open_label)
    trig = trig.first
    if trig.count() == 0:
        return {"verdict": "ERROR", "detail": "trigger not found"}
    trig.click()
    page.wait_for_timeout(80)
    before = _open_labels(scope, item_sel)
    if not before:
        return {"verdict": "ERROR", "detail": "failed to open panel before Escape"}

    page.keyboard.press("Escape")
    page.wait_for_timeout(100)
    after = _open_labels(scope, item_sel)
    if not after:
        return {
            "verdict": "PASS",
            "detail": f"dismissed after Escape (was {before})",
            "open_labels_before": before,
            "open_labels": after,
        }
    return {
        "verdict": "FAIL",
        "detail": f"Escape left open_labels={after} (before={before})",
        "open_labels_before": before,
        "open_labels": after,
        "dom_hint": item_sel,
    }


def _run_native_dialog_escape(page: Any, probe: Probe) -> dict[str, Any]:
    """Open a native <dialog> via trigger, Escape, assert ``dialog.open`` is false.

    Covers modal dialog + drawer (side dialog). ``dz-dialog`` defers
    ``showModal`` with ``setTimeout(0)`` so we settle longer than details probes.
    """
    params = probe.params
    open_sel = params["open_trigger"]
    dialog_sel = params["dialog"]
    settle = int(params.get("open_settle_ms", 150))

    scope = _probe_scope(page, params)
    # Prefer in-scope trigger; dialog element may be a sibling under .hm-preview
    open_btn = scope.locator(open_sel).first
    if open_btn.count() == 0:
        open_btn = page.locator(open_sel).first
    if open_btn.count() == 0:
        return {"verdict": "ERROR", "detail": f"open trigger not found ({open_sel})"}

    open_btn.click()
    page.wait_for_timeout(settle)

    # Evaluate open state on first matching dialog (preview-scoped when possible)
    is_open = page.evaluate(
        """(sel) => {
          const scoped = document.querySelector('.hm-preview');
          const root = scoped || document;
          const d = root.querySelector(sel) || document.querySelector(sel);
          return !!(d && d.open);
        }""",
        dialog_sel,
    )
    if not is_open:
        return {
            "verdict": "ERROR",
            "detail": f"dialog did not open after trigger click ({dialog_sel})",
        }

    page.keyboard.press("Escape")
    page.wait_for_timeout(120)
    still_open = page.evaluate(
        """(sel) => {
          const scoped = document.querySelector('.hm-preview');
          const root = scoped || document;
          const d = root.querySelector(sel) || document.querySelector(sel);
          return !!(d && d.open);
        }""",
        dialog_sel,
    )
    if not still_open:
        return {
            "verdict": "PASS",
            "detail": f"Escape closed {dialog_sel}",
        }
    return {
        "verdict": "FAIL",
        "detail": f"Escape left dialog open ({dialog_sel})",
        "dom_hint": dialog_sel,
    }


def _pseudo_after_opacity(page: Any, host: Any) -> float | None:
    """Computed opacity of host ElementHandle/Locator ::after (None if missing)."""
    # Prefer element-bound evaluate so we never sample glossary .hm-term tips.
    try:
        return host.evaluate(
            """(el) => {
              if (!el) return null;
              const st = getComputedStyle(el, '::after');
              const op = parseFloat(st.opacity);
              return Number.isFinite(op) ? op : null;
            }"""
        )
    except Exception:  # noqa: BLE001
        return None


def _run_css_tooltip_hover(page: Any, probe: Probe) -> dict[str, Any]:
    """Hover host; assert ::after opacity rises (CSS data-tooltip hint)."""
    params = probe.params
    host_sel = params["host"]
    settle = int(params.get("hover_settle_ms") or 500)
    min_op = float(params.get("expect_min_opacity") or 0.85)

    scope = _probe_scope(page, params)
    # Prefer preview-scoped host; fall back to first matching host_sel branch
    host = None
    for part in host_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = scope.locator(part).first
        if loc.count() > 0:
            host = loc
            break
    if host is None:
        return {"verdict": "ERROR", "detail": f"tooltip host not found ({host_sel})"}

    rest = _pseudo_after_opacity(page, host)
    if rest is None:
        return {"verdict": "ERROR", "detail": "host present but ::after opacity unreadable"}

    host.hover()
    # delay 300ms + duration-fast; poll until min opacity or settle budget
    hover = rest
    deadline_ms = settle
    step = 50
    waited = 0
    while waited < deadline_ms:
        page.wait_for_timeout(step)
        waited += step
        hover = _pseudo_after_opacity(page, host)
        if hover is not None and hover >= min_op:
            break
    if hover is None:
        return {"verdict": "ERROR", "detail": "lost host after hover"}
    if hover >= min_op:
        return {
            "verdict": "PASS",
            "detail": f"rest_opacity={rest:.2f} hover_opacity={hover:.2f} waited_ms={waited}",
            "rest_opacity": rest,
            "hover_opacity": hover,
        }
    return {
        "verdict": "FAIL",
        "detail": (
            f"hover ::after opacity {hover:.2f} < {min_op} "
            f"(rest={rest:.2f}) — tooltip CSS not revealing on hover"
        ),
        "rest_opacity": rest,
        "hover_opacity": hover,
        "dom_hint": host_sel,
    }


def _run_css_tooltip_force_open(page: Any, probe: Probe) -> dict[str, Any]:
    """Set data-*-tooltip-open on host; assert ::after visible without hover."""
    params = probe.params
    host_sel = params["host"]
    min_op = float(params.get("expect_min_opacity") or 0.85)

    scope = _probe_scope(page, params)
    host = None
    for part in host_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = scope.locator(part).first
        if loc.count() > 0:
            host = loc
            break
    if host is None:
        return {"verdict": "ERROR", "detail": f"tooltip host not found ({host_sel})"}

    rest = _pseudo_after_opacity(page, host)
    if rest is None:
        return {"verdict": "ERROR", "detail": "host present but ::after opacity unreadable"}

    # Prefer unprefixed open attr when host uses data-tooltip; dz when data-dz-
    tag = host.evaluate(
        """(el) => ({
          hasDz: el.hasAttribute('data-dz-tooltip'),
          hasPlain: el.hasAttribute('data-tooltip'),
        })"""
    )
    if tag.get("hasDz") and not tag.get("hasPlain"):
        open_attr = "data-dz-tooltip-open"
    else:
        open_attr = "data-tooltip-open"

    # Playwright locator.evaluate: (element, arg) => …
    host.evaluate("(el, attr) => { el.setAttribute(attr, ''); }", open_attr)
    # opacity still transitions (duration-fast) even with delay 0 — poll briefly
    forced: float | None = rest
    waited = 0
    while waited < 400:
        page.wait_for_timeout(40)
        waited += 40
        forced = _pseudo_after_opacity(page, host)
        if forced is not None and forced >= min_op:
            break
    host.evaluate("(el, attr) => { el.removeAttribute(attr); }", open_attr)
    if forced is None:
        return {"verdict": "ERROR", "detail": "lost host after force-open attr"}
    if forced >= min_op:
        return {
            "verdict": "PASS",
            "detail": f"rest_opacity={rest:.2f} force_open({open_attr})={forced:.2f}",
            "rest_opacity": rest,
            "force_opacity": forced,
            "open_attr": open_attr,
        }
    return {
        "verdict": "FAIL",
        "detail": (
            f"force-open attr {open_attr} ::after opacity {forced:.2f} < {min_op} "
            f"(rest={rest:.2f}) — missing [data-*-tooltip-open]::after rule"
        ),
        "rest_opacity": rest,
        "force_opacity": forced,
        "open_attr": open_attr,
        "dom_hint": host_sel,
    }


def _root_is_data_open(root: Any) -> bool:
    """True when hover-card-style open state is set (data-open / data-dz-open / is-open)."""
    return bool(
        root.evaluate(
            """(el) => !!(
              el && (
                el.hasAttribute('data-open') ||
                el.hasAttribute('data-dz-open') ||
                (el.classList && el.classList.contains('is-open'))
              )
            )"""
        )
    )


def _run_data_open_escape(page: Any, probe: Probe) -> dict[str, Any]:
    """Click trigger to set data-open, Escape, assert open attrs cleared."""
    params = probe.params
    root_sel = params["root"]
    trigger_sel = params["trigger"]
    settle = int(params.get("open_settle_ms", 100))

    scope = _probe_scope(page, params)
    root = scope.locator(root_sel).first
    if root.count() == 0:
        return {"verdict": "ERROR", "detail": f"root not found ({root_sel})"}
    trig = scope.locator(trigger_sel).first
    if trig.count() == 0:
        return {"verdict": "ERROR", "detail": f"trigger not found ({trigger_sel})"}

    if _root_is_data_open(root):
        # unexpected pre-open — still exercise dismiss
        pass
    else:
        trig.click()
        page.wait_for_timeout(settle)
        if not _root_is_data_open(root):
            return {
                "verdict": "ERROR",
                "detail": "click did not set data-open / data-dz-open / is-open",
            }

    page.keyboard.press("Escape")
    page.wait_for_timeout(100)
    if not _root_is_data_open(root):
        return {
            "verdict": "PASS",
            "detail": "Escape cleared data-open on hover-card root",
        }
    return {
        "verdict": "FAIL",
        "detail": "Escape left data-open / data-dz-open / is-open set",
        "dom_hint": root_sel,
    }


def _run_data_open_dismiss_outside(page: Any, probe: Probe) -> dict[str, Any]:
    """Click trigger to set data-open, outside click, assert open attrs cleared."""
    params = probe.params
    root_sel = params["root"]
    trigger_sel = params["trigger"]
    settle = int(params.get("open_settle_ms", 100))

    scope = _probe_scope(page, params)
    root = scope.locator(root_sel).first
    if root.count() == 0:
        return {"verdict": "ERROR", "detail": f"root not found ({root_sel})"}
    trig = scope.locator(trigger_sel).first
    if trig.count() == 0:
        return {"verdict": "ERROR", "detail": f"trigger not found ({trigger_sel})"}

    trig.click()
    page.wait_for_timeout(settle)
    if not _root_is_data_open(root):
        return {
            "verdict": "ERROR",
            "detail": "click did not set data-open / data-dz-open / is-open",
        }

    page.mouse.click(8, 8)
    page.wait_for_timeout(100)
    if not _root_is_data_open(root):
        return {
            "verdict": "PASS",
            "detail": "outside click cleared data-open on hover-card root",
        }
    return {
        "verdict": "FAIL",
        "detail": "outside click left data-open / data-dz-open / is-open set",
        "dom_hint": root_sel,
    }


def _run_tabs_exclusive_select(page: Any, probe: Probe) -> dict[str, Any]:
    """Click a tab; assert aria-current moves and only its panel is unhidden."""
    params = probe.params
    root_sel = params["root"]
    tab_sel = params["tab"]
    activate = params.get("activate_label") or params.get("sequence", ["Activity"])[-1]
    expect_current = params.get("expect_current_label") or activate
    visible_id = params.get("expect_panel_visible_id")
    hidden_id = params.get("expect_panel_hidden_id")
    settle = int(params.get("settle_ms", 120))

    scope = _probe_scope(page, params)
    root = scope.locator(root_sel).first
    if root.count() == 0:
        return {"verdict": "ERROR", "detail": f"tabs root not found ({root_sel})"}

    tab = root.locator(tab_sel).filter(has_text=activate).first
    if tab.count() == 0:
        return {"verdict": "ERROR", "detail": f"tab not found: {activate!r}"}

    tab.click()
    page.wait_for_timeout(settle)

    # Apply [aria-current="true"] to *each* comma branch (same footgun as
    # _open_item_selector — suffix only on the last branch matches every tab).
    current_sel = ", ".join(
        f'{p.strip()}[aria-current="true"]' for p in tab_sel.split(",") if p.strip()
    )
    current_text = root.locator(current_sel).first
    if current_text.count() == 0:
        return {
            "verdict": "FAIL",
            "detail": "no tab with aria-current=true after click",
            "dom_hint": tab_sel,
        }
    got_label = _norm_label(current_text.inner_text())
    if expect_current.lower() not in got_label.lower():
        return {
            "verdict": "FAIL",
            "detail": f"aria-current on {got_label!r}, expected ≈{expect_current!r}",
            "current_label": got_label,
        }

    # Panel visibility via id (gallery demos use stable hm-tab-* ids)
    issues: list[str] = []
    if visible_id:
        hid = page.evaluate(
            """(id) => {
              const el = document.getElementById(id);
              return el ? !!el.hidden : null;
            }""",
            visible_id,
        )
        if hid is None:
            issues.append(f"panel #{visible_id} missing")
        elif hid:
            issues.append(f"panel #{visible_id} still hidden")
    if hidden_id:
        hid = page.evaluate(
            """(id) => {
              const el = document.getElementById(id);
              return el ? !!el.hidden : null;
            }""",
            hidden_id,
        )
        if hid is None:
            issues.append(f"panel #{hidden_id} missing")
        elif not hid:
            issues.append(f"panel #{hidden_id} still visible (not exclusive)")

    if issues:
        return {
            "verdict": "FAIL",
            "detail": f"current={got_label!r}; " + "; ".join(issues),
            "current_label": got_label,
            "dom_hint": root_sel,
        }
    return {
        "verdict": "PASS",
        "detail": (f"current={got_label!r} visible={visible_id} hidden={hidden_id}"),
        "current_label": got_label,
    }


KIND_RUNNERS: dict[str, Callable[[Any, Probe], dict[str, Any]]] = {
    "exclusive_details_open": _run_exclusive_details_open,
    "multi_details_open": _run_multi_details_open,
    "details_dismiss_outside": _run_details_dismiss_outside,
    "details_escape_dismiss": _run_details_escape_dismiss,
    "native_dialog_escape": _run_native_dialog_escape,
    "css_tooltip_hover": _run_css_tooltip_hover,
    "css_tooltip_force_open": _run_css_tooltip_force_open,
    "data_open_escape": _run_data_open_escape,
    "data_open_dismiss_outside": _run_data_open_dismiss_outside,
    "tabs_exclusive_select": _run_tabs_exclusive_select,
}


# ── Discover (static) ────────────────────────────────────────────────────


_DETAILS_RE = re.compile(r"<details\b", re.I)
_NAME_ATTR_RE = re.compile(r"<details\b[^>]*\bname\s*=", re.I)


def discover_candidates() -> list[dict[str, Any]]:
    """Scan registry partials for multi-details roots needing an intent probe.

    Heuristic (cheap, no browser):
    - partial contains ≥2 ``<details``
    - not all details share a native ``name=`` (browser exclusivity → skip)
    - stem covered by **any** catalog probe (exclusive *or* multi_open intent)

    Uncovered stems need an authored probe that declares intent:
    exclusive (controller/name=) vs multi_open (tree forest).
    """
    sys.path.insert(0, str(SITE))
    try:
        from registry import HYPERPARTS  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        return [{"verdict": "ERROR", "detail": f"cannot import registry: {exc}"}]

    probes_by_stem: dict[str, list[Probe]] = {}
    for p in PROBES:
        probes_by_stem.setdefault(p.stem, []).append(p)

    rows: list[dict[str, Any]] = []
    for h in HYPERPARTS:
        partial = getattr(h, "partial", "") or ""
        n = len(_DETAILS_RE.findall(partial))
        if n < 2:
            continue
        named = len(_NAME_ATTR_RE.findall(partial))
        native_exclusive = named >= 2 and named == n
        if native_exclusive:
            continue
        page = f"hyperparts/{h.id}.html"
        has_controller = bool(getattr(h, "controller", None))
        stem_probes = probes_by_stem.get(h.id, [])
        in_catalog = bool(stem_probes)
        intents = sorted({p.intent for p in stem_probes}) if stem_probes else []
        if in_catalog:
            rec = "catalog_ok_multi_open" if "multi_open" in intents else "catalog_ok"
        elif not has_controller:
            rec = "author_probe_declare_intent"  # exclusive controller vs multi_open partial
        else:
            rec = "author_probe_verify_controller"
        rows.append(
            {
                "stem": h.id,
                "page": page,
                "details_count": n,
                "named_details": named,
                "native_exclusive": native_exclusive,
                "has_controller": has_controller,
                "controller": getattr(h, "controller", None),
                "in_probe_catalog": in_catalog,
                "intents": intents,
                "probe_ids": [p.id for p in stem_probes],
                "recommendation": rec,
            }
        )
    rows.sort(key=lambda r: (r.get("in_probe_catalog", False), r.get("stem", "")))
    return rows


def discover_report() -> dict[str, Any]:
    candidates = discover_candidates()
    uncovered = [c for c in candidates if not c.get("in_probe_catalog")]
    return {
        "schema": SCHEMA,
        "mode": "discover",
        "run_at": datetime.now(UTC).isoformat(),
        "candidates": candidates,
        "summary": {
            "total_multi_details": len(candidates),
            "uncovered": len(uncovered),
            "catalog_covered": len(candidates) - len(uncovered),
        },
        "uncovered_stems": [c["stem"] for c in uncovered],
    }


# ── Execution ────────────────────────────────────────────────────────────


def _page_url(base: str | None, page: str) -> str:
    if base:
        b = base.rstrip("/")
        path = page if page.startswith("/") else f"/{page}"
        if b.startswith("file://"):
            root = b[len("file://") :]
            return Path(root + path).as_uri()
        return b + path
    return (SITE / page).resolve().as_uri()


def run_probes(
    *,
    probes: list[Probe],
    out: Path,
    base: str | None = None,
    screenshot_on_fail: bool = True,
    quiet: bool = False,
) -> dict[str, Any]:
    """Run probes; return a report dict (also written under *out*)."""
    pw_mod = __import__("playwright.sync_api", fromlist=["sync_playwright"])
    out.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []

    with pw_mod.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        for probe in probes:
            url = _page_url(base, probe.page)
            row: dict[str, Any] = {
                "id": probe.id,
                "stem": probe.stem,
                "page": probe.page,
                "url": url,
                "category": probe.category,
                "severity": probe.severity,
                "claim": probe.claim,
                "kind": probe.kind,
                "fix_surface": probe.fix_surface,
            }
            runner = KIND_RUNNERS.get(probe.kind)
            if runner is None:
                row.update({"verdict": "ERROR", "detail": f"unknown kind {probe.kind!r}"})
                results.append(row)
                continue
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(150)
                outcome = runner(page, probe)
                row.update(outcome)
                if outcome.get("verdict") == "FAIL" and screenshot_on_fail:
                    png = out / f"{probe.id.replace('.', '_')}.png"
                    page.screenshot(path=str(png), full_page=False)
                    row["evidence_png"] = str(png.resolve())
            except Exception as exc:  # noqa: BLE001 — per-probe isolation
                row.update({"verdict": "ERROR", "detail": f"{type(exc).__name__}: {exc}"})
            results.append(row)
            if not quiet:
                print(f"{row.get('verdict', '?'):5} {probe.id}  {row.get('detail', '')[:100]}")
        browser.close()

    summary = {
        "pass": sum(1 for r in results if r.get("verdict") == "PASS"),
        "fail": sum(1 for r in results if r.get("verdict") == "FAIL"),
        "error": sum(1 for r in results if r.get("verdict") == "ERROR"),
        "skip": sum(1 for r in results if r.get("verdict") == "SKIP"),
        "total": len(results),
    }
    report = {
        "schema": SCHEMA,
        "run_at": datetime.now(UTC).isoformat(),
        "base": base or SITE.as_uri(),
        "site": str(SITE.resolve()),
        "results": results,
        "summary": summary,
    }
    report_path = out / "report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if not quiet:
        print(f"wrote {report_path}  summary={summary}")
    return report


def emit_findings(report: dict[str, Any]) -> str:
    """Markdown HMC-style rows for FAIL probes (paste into improve-backlog)."""
    lines = [
        "<!-- gallery_probes findings — auto from report.json FAILs -->",
        "",
    ]
    fails = [r for r in report.get("results", []) if r.get("verdict") == "FAIL"]
    if not fails:
        lines.append("_No FAIL probes._")
        return "\n".join(lines) + "\n"
    for r in fails:
        pid = str(r.get("id", "unknown")).replace(".", "-")
        lines.extend(
            [
                f"### HMC-probe-{pid}",
                "- **status:** PENDING",
                f"- **stem:** `{r.get('stem')}`",
                f"- **probe:** `{r.get('id')}`",
                f"- **severity:** {r.get('severity')}",
                f"- **fix_surface:** {r.get('fix_surface')}",
                f"- **claim:** {r.get('claim')}",
                f"- **detail:** {r.get('detail')}",
                f"- **evidence:** `{r.get('evidence_png', '')}`",
                "- **playbook:** `improve/strategies/gallery_probes.md`",
                "",
            ]
        )
    return "\n".join(lines)


def match_observation(obs: dict[str, Any]) -> list[Probe]:
    """Map a human observation card to catalog probes (stem + claim keywords)."""
    stem_raw = (obs.get("stem") or obs.get("page") or "").strip().lower()
    stem = stem_raw.replace("_", "-")
    claim = (obs.get("claim") or obs.get("one_line") or obs.get("description") or "").lower()
    hits: list[Probe] = []
    claim_keys = (
        "exclusive",
        "close",
        "menu",
        "open",
        "file",
        "edit",
        "panel",
        "accordion",
        "product",
        "resources",
        "multi",
        "stay",
        "tree",
        "expand",
        "collapse",
        "branch",
        "sibling",
    )
    for p in PROBES:
        p_stem = p.stem.lower()
        stem_hit = bool(stem) and (
            p_stem == stem or stem in p.page or stem.replace("-", "") == p_stem.replace("-", "")
        )
        if stem and not stem_hit and stem not in p.claim.lower():
            continue
        if claim:
            if stem_hit or any(k in claim and k in p.claim.lower() for k in claim_keys):
                hits.append(p)
        elif stem_hit:
            hits.append(p)
    if stem and not hits:
        hits = [p for p in PROBES if p.stem.lower() == stem or stem in p.page]
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[Probe] = []
    for p in hits:
        if p.id not in seen:
            seen.add(p.id)
            out.append(p)
    return out


def validate_observation(obs: dict[str, Any], *, out: Path, base: str | None) -> dict[str, Any]:
    """Run matching probes for a human observation; return validation envelope."""
    hits = match_observation(obs)
    if not hits:
        return {
            "schema": SCHEMA,
            "observation": obs,
            "verdict": "NO_PROBE",
            "detail": (
                "No catalog probe matches this observation. Author a Probe in "
                "packages/hatchi-maxchi/tools/gallery_probes.py PROBES, then re-run. "
                "Hint: python …/gallery_probes.py --discover"
            ),
            "results": [],
        }
    report = run_probes(probes=hits, out=out, base=base, quiet=True)
    verdicts = {r.get("verdict") for r in report["results"]}
    if "FAIL" in verdicts:
        overall = "CONFIRMED"
    elif "ERROR" in verdicts:
        overall = "HARNESS_ERROR"
    elif verdicts <= {"PASS", "SKIP"}:
        overall = "NOT_REPRO"
    else:
        overall = "PARTIAL"
    return {
        "schema": SCHEMA,
        "observation": obs,
        "verdict": overall,
        "matched_probes": [p.id for p in hits],
        "report": report,
    }


def list_probes() -> None:
    print(f"{'id':36} {'stem':18} severity  claim")
    for p in PROBES:
        print(f"{p.id:36} {p.stem:18} {p.severity:8}  {p.claim[:70]}")


def write_catalog() -> Path:
    path = PKG / "GALLERY_PROBES.md"
    lines = [
        "# HM gallery interaction probes",
        "",
        "Auto-generated by `tools/gallery_probes.py --write-catalog`.",
        "Do not hand-edit — update `PROBES` in `tools/gallery_probes.py`.",
        "",
        "Run:",
        "",
        "```bash",
        "python packages/hatchi-maxchi/tools/gallery_probes.py --discover",
        "python packages/hatchi-maxchi/tools/gallery_probes.py --run",
        "python scripts/hm_gallery_probes.py --run   # monorepo entrypoint",
        "```",
        "",
        "| id | stem | intent | severity | fix_surface | claim |",
        "|----|------|--------|----------|-------------|-------|",
    ]
    for p in PROBES:
        claim = p.claim.replace("|", "\\|")
        lines.append(
            f"| `{p.id}` | `{p.stem}` | {p.intent} | {p.severity} | {p.fix_surface} | {claim} |"
        )
    lines.extend(
        [
            "",
            "## Loop (autonomous improve)",
            "",
            "1. `--discover` → uncovered multi-details stems (must declare intent)",
            "2. Author `Probe` with `intent=exclusive|multi_open` + fix_surface",
            "3. `--run` → FAIL drains via `improve/strategies/gallery_probes.md`",
            "4. Human observation → `--validate-observation '{…}'`",
            "5. CI pin optional: `tests/test_behaviour.py` scenario for ship-grade contracts",
            "",
            "### Intent",
            "",
            "- **exclusive** — menubar / nav / accordion: only one panel open",
            "- **multi_open** — tree forests: expanding siblings must *not* close peers",
            "",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="List catalog probes")
    ap.add_argument(
        "--discover",
        action="store_true",
        help="Static scan for multi-details stems needing an intent probe (exclusive|multi_open)",
    )
    ap.add_argument("--run", action="store_true", help="Run probes")
    ap.add_argument("--stem", action="append", default=[], help="Filter by stem (repeatable)")
    ap.add_argument(
        "--id", action="append", default=[], dest="probe_ids", help="Filter by probe id"
    )
    ap.add_argument(
        "--base",
        default=None,
        help="Gallery base URL (default: local site/ file://). "
        "Example: file:///…/packages/hatchi-maxchi/site",
    )
    ap.add_argument(
        "--out", type=Path, default=DEFAULT_OUT, help="Output directory for report/PNGs"
    )
    ap.add_argument("--json", action="store_true", help="Print full report JSON to stdout")
    ap.add_argument(
        "--emit-findings",
        action="store_true",
        help="After --run, print HMC-style markdown for FAIL rows",
    )
    ap.add_argument(
        "--validate-observation",
        default=None,
        metavar="JSON",
        help='Human observation card as JSON string, e.g. \'{"stem":"menubar","claim":"…"}\'',
    )
    ap.add_argument(
        "--write-catalog",
        action="store_true",
        help="Write packages/hatchi-maxchi/GALLERY_PROBES.md from PROBES",
    )
    args = ap.parse_args(argv)

    if args.list:
        list_probes()
        return 0

    if args.write_catalog:
        path = write_catalog()
        print(f"wrote {path}")
        return 0

    if args.discover:
        report = discover_report()
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(
                f"multi-details candidates: {report['summary']['total_multi_details']}  "
                f"uncovered: {report['summary']['uncovered']}"
            )
            for c in report["candidates"]:
                flag = "CATALOG" if c.get("in_probe_catalog") else "NEED_PROBE"
                print(
                    f"  {flag:10} {c['stem']:24} details={c['details_count']}  "
                    f"ctrl={c.get('controller') or '—'}  → {c['recommendation']}"
                )
            if report["uncovered_stems"]:
                print("uncovered_stems:", ", ".join(report["uncovered_stems"]))
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "discover.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        # discover never fails the run — it is inventory
        return 0

    if args.validate_observation:
        obs = json.loads(args.validate_observation)
        envelope = validate_observation(obs, out=args.out / "observation", base=args.base)
        print(json.dumps(envelope, indent=2))
        if envelope["verdict"] == "CONFIRMED":
            return 1
        if envelope["verdict"] in {"HARNESS_ERROR", "NO_PROBE"}:
            return 2
        return 0

    if not args.run:
        ap.print_help()
        return 2

    probes = list(PROBES)
    if args.stem:
        stems = set(args.stem)
        probes = [p for p in probes if p.stem in stems]
    if args.probe_ids:
        ids = set(args.probe_ids)
        probes = [p for p in probes if p.id in ids]
    if not probes:
        print("no probes selected", file=sys.stderr)
        return 2

    report = run_probes(probes=probes, out=args.out, base=args.base)
    if args.emit_findings:
        findings = emit_findings(report)
        findings_path = args.out / "findings.md"
        findings_path.write_text(findings, encoding="utf-8")
        print(findings)
        print(f"wrote {findings_path}")
    if args.json:
        print(json.dumps(report, indent=2))
    if report["summary"]["error"]:
        return 2
    if report["summary"]["fail"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
