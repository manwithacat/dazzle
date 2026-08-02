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
    Probe(
        id="switch.toggles_checked",
        stem="switch",
        page="hyperparts/switch.html",
        category="interaction",
        severity="medium",
        claim=(
            "Clicking a switch track toggles the checkbox checked state "
            "(settings must flip Email notifications off then on again)"
        ),
        kind="checkbox_toggle",
        params={
            "input": (
                "input[data-switch], input[data-dz-switch], "
                ".switch input[type=checkbox], .dz-switch input[type=checkbox]"
            ),
            "scope": ".hm-preview",
            # first switch is checked in gallery demo
            "start_checked": True,
        },
        fix_surface="partial",
        intent="exclusive",
    ),
    # Cycle 1485 — controls primitive page (checkbox + switch on one demo row).
    # Reuses checkbox_toggle runner; radio intentionally omitted (single-option
    # demos stay checked — exclusive radio needs a multi-option name= group).
    Probe(
        id="controls.checkbox_toggles",
        stem="controls",
        page="hyperparts/controls.html",
        category="interaction",
        severity="medium",
        claim=(
            "Clicking a designed checkbox flips native checked state both ways "
            "(selection controls must not be label-only paint)"
        ),
        kind="checkbox_toggle",
        params={
            "input": (
                "input.checkbox[type=checkbox], input.dz-checkbox[type=checkbox], "
                "input[type=checkbox].checkbox"
            ),
            "scope": ".hm-preview",
            "start_checked": True,
        },
        fix_surface="css",
        intent="exclusive",
    ),
    Probe(
        id="controls.switch_toggles",
        stem="controls",
        page="hyperparts/controls.html",
        category="interaction",
        severity="medium",
        claim=(
            "Clicking the controls-page switch checkbox flips checked both ways "
            "(primitive switch class shares semantics with dedicated switch page)"
        ),
        kind="checkbox_toggle",
        params={
            "input": (
                "input.switch[type=checkbox], input.dz-switch[type=checkbox], "
                "input[type=checkbox].switch"
            ),
            "scope": ".hm-preview",
            "start_checked": True,
        },
        fix_surface="css",
        intent="exclusive",
    ),
    # Cycle 1491 — slider live readout (controller writes range value into
    # [data-range-value] / [data-dz-range-value] on input, group-scoped).
    Probe(
        id="slider.updates_readout",
        stem="slider",
        page="hyperparts/slider.html",
        category="interaction",
        severity="high",
        claim=(
            "Changing the range input updates the group's live value readout "
            "(settings must show the new number without a page reload)"
        ),
        kind="range_value_readout",
        params={
            "input": (
                'input[type="range"][data-slider], '
                'input[type="range"][data-dz-slider], '
                "input.form-slider[type=range], input.dz-form-slider[type=range]"
            ),
            "readout": (
                "[data-range-value], [data-dz-range-value], "
                ".form-slider-value, .dz-form-slider-value"
            ),
            "scope": ".hm-preview",
            "set_value": "30",
        },
        fix_surface="controller",
        intent="exclusive",
    ),
    # Cycle 1499 — toolbar toggle (aria-pressed) + segmented toggle-group.
    Probe(
        id="toggle.pressed_flips",
        stem="toggle",
        page="hyperparts/toggle.html",
        category="interaction",
        severity="high",
        claim=(
            "Clicking a toolbar toggle flips aria-pressed both ways "
            "(Bold/Italic mode must stay live without a page reload)"
        ),
        kind="aria_pressed_toggle",
        params={
            "button": (
                "button[data-toggle], button[data-dz-toggle], button.toggle, button.dz-toggle"
            ),
            "scope": ".hm-preview",
            # Bold starts pressed in the gallery demo.
            "prefer_label_contains": "Bold",
        },
        fix_surface="controller",
        intent="exclusive",
    ),
    Probe(
        id="toggle_group.radio_exclusive",
        stem="toggle-group",
        page="hyperparts/toggle-group.html",
        category="interaction",
        severity="high",
        claim=(
            "Selecting a second toggle-group segment checks only that radio "
            "(List then Board leaves only Board checked — native exclusive group)"
        ),
        kind="radio_group_select",
        params={
            "root": (
                "fieldset.toggle-group, fieldset.dz-toggle-group, "
                ".toggle-group[role=radiogroup], .dz-toggle-group[role=radiogroup]"
            ),
            "radio": 'input[type="radio"]',
            "activate_label_contains": "Board",
            "expect_checked_label_contains": "Board",
            "scope": ".hm-preview",
        },
        fix_surface="css",
        intent="exclusive",
    ),
    # Cycle 1507 — carousel stage advance (controller moves data-active + status).
    Probe(
        id="carousel.advance_next",
        stem="carousel",
        page="hyperparts/carousel.html",
        category="interaction",
        severity="high",
        claim=(
            "Clicking Next advances the clamp carousel from slide 1 to 2 "
            "(data-carousel-index, active slide, and live status must update)"
        ),
        kind="carousel_advance",
        params={
            # Prefer clamp strip (not ambient loop) so ends/status stay deterministic.
            "root": (
                '[data-carousel-wrap="none"], [data-dz-carousel-wrap="none"], '
                ".carousel[data-carousel-wrap=none], .dz-carousel[data-dz-carousel-wrap=none]"
            ),
            "next": "[data-carousel-next], [data-dz-carousel-next]",
            "active_slide": (
                ".carousel__slide[data-active], .carousel__slide[data-dz-active], "
                ".dz-carousel__slide[data-active], .dz-carousel__slide[data-dz-active]"
            ),
            "status": "[data-carousel-status], [data-dz-carousel-status]",
            "expect_index_after": "1",
            "expect_status_contains": "2 of",
            "scope": ".hm-preview",
        },
        fix_surface="controller",
        intent="exclusive",
    ),
    # Cycle 1513 — combobox progressive enhance + pick commits select value.
    Probe(
        id="combobox.enhance_and_select",
        stem="combobox",
        page="hyperparts/combobox.html",
        category="interaction",
        severity="high",
        claim=(
            "Native select[data-combobox] enhances on pointerdown; picking High "
            "writes select value=high, shows High in the overlay input, and closes "
            "the listbox (data-open cleared)"
        ),
        kind="combobox_select",
        params={
            "select": "select[data-combobox], select[data-dz-combobox]",
            "root": (
                ".combobox[data-enhanced], .combobox[data-dz-enhanced], "
                ".dz-combobox[data-enhanced], .dz-combobox[data-dz-enhanced]"
            ),
            "option": (
                '.combobox-option[data-value="high"], .dz-combobox-option[data-value="high"]'
            ),
            "input": ".combobox-input, .dz-combobox-input",
            "expect_value": "high",
            "expect_label": "High",
            "scope": ".hm-preview",
        },
        fix_surface="controller",
        intent="exclusive",
    ),
    # Cycle 1520 — wizard forward after required stage validates.
    Probe(
        id="wizard.forward_after_valid",
        stem="wizard",
        page="hyperparts/wizard.html",
        category="interaction",
        severity="high",
        claim=(
            "After filling the required field on step 0, clicking the step-1 "
            "stepper advances data-step to 1, shows stage 1, and marks step 1 current "
            "(forward is validity-gated one step at a time)"
        ),
        kind="wizard_step_forward",
        params={
            "root": "[data-wizard], [data-dz-wizard]",
            "step_attr": "data-step",  # also tries data-dz-step
            "required_input": "#hm-wiz-name, input[required]",
            "fill_value": "Acme launch",
            "step_to": "1",
            "step_button": (
                '[data-step-to="1"], [data-dz-step-to="1"], '
                'button.form-stepper-button[data-step-to="1"], '
                'button.dz-form-stepper-button[data-dz-step-to="1"]'
            ),
            "stage": '[data-stage="1"], [data-dz-stage="1"]',
            "expect_step_after": "1",
            "scope": ".hm-preview",
        },
        fix_surface="controller",
        intent="exclusive",
    ),
    # Cycle 1535 — toast stack: dismiss seeded toast + client showToast append.
    # Live page (not iframe host); mirrors test_behaviour toast_stack_host.
    Probe(
        id="toast.dismiss_and_client_fire",
        stem="toast",
        page="hyperparts/toast-live.html",
        category="interaction",
        severity="high",
        claim=(
            "Dismissing a stack toast removes it after leave motion; dispatching "
            "showToast appends a new toast with the detail title (stack host must "
            "honor dismiss + client fire — not a static markup demo)"
        ),
        kind="toast_dismiss_and_fire",
        params={
            "stack": "#toast.toast-stack, #dz-toast.dz-toast-stack",
            "toast": ".toast, .dz-toast",
            "dismiss": (
                ".toast__close[data-toast-dismiss], .dz-toast__close[data-dz-toast-dismiss]"
            ),
            "title": ".toast__title, .dz-toast__title",
            "fire_title": "Host test",
            "leave_ms": 450,
            "scope": "",  # whole page — live stage has no .hm-preview
        },
        fix_surface="controller",
        intent="exclusive",
    ),
    # Cycle 1536 — tags chips: seed enhance + Enter add + × remove (submit value).
    # Mirrors test_behaviour test_tags_seed_and_add_chip / test_tags_remove_chip.
    Probe(
        id="tags.seed_add_and_remove",
        stem="tags",
        page="hyperparts/tags.html",
        category="interaction",
        severity="high",
        claim=(
            "Seeded comma value enhances into chips; Enter adds a new chip and "
            "rewrites the native comma-joined value; Remove × drops a chip "
            "(chips UI must own submit contract — not a static demo)"
        ),
        kind="tags_seed_add_remove",
        params={
            "native": "input[data-tags], input[data-dz-tags]",
            "root": (
                ".tags[data-enhanced], .dz-tags[data-dz-enhanced], "
                ".tags[data-dz-enhanced], .dz-tags[data-enhanced]"
            ),
            "chip": ".tags-chip, .dz-tags-chip",
            "entry": ".tags-entry, .dz-tags-entry",
            "seed_count": 2,
            "add_value": "frontend",
            "expect_after_add": "urgent,backend,frontend",
            "remove_label": "Remove urgent",
            "expect_after_remove": "backend,frontend",
            "scope": ".hm-preview",
        },
        fix_surface="controller",
        intent="exclusive",
    ),
    # Cycle 1537 — search-select: focus open + typeahead row + confirm-hold dismiss.
    # Mirrors test_behaviour test_search_select_opens_on_focus_and_survives_row_click.
    Probe(
        id="search_select.open_typeahead_select_hold",
        stem="search-select",
        page="hyperparts/search-select.html",
        category="interaction",
        severity="high",
        claim=(
            "Focus opens the typeahead panel; typing filters mock rows; selecting "
            "a row shows confirm and holds the panel past blur grace; after "
            "confirm-hold the panel auto-dismisses (not a static markup demo)"
        ),
        kind="search_select_typeahead_select",
        params={
            "root": (
                ".search-select, .dz-search-select, "
                "[data-widget='search_select'], [data-dz-widget='search_select']"
            ),
            "input": (
                "input[type=text].search-select-input, "
                "input[type=text].dz-search-select-input, "
                ".search-select input[type=text], .dz-search-select input[type=text]"
            ),
            "panel": (
                ".search-select-results, .dz-search-select-results, "
                "[role=listbox][aria-label='Suggestions']"
            ),
            "row": ".search-result-row, .dz-search-result-row",
            "query": "auro",
            "expect_row_text": "Aurora",
            "expect_confirm_text": "Selected",
            "debounce_ms": 450,
            "post_select_ms": 300,
            "hold_mid_ms": 1000,
            "hold_rest_ms": 1200,
            "scope": ".hm-preview",
        },
        fix_surface="controller",
        intent="exclusive",
    ),
    # Cycle 1539 — money minor carrier sync + blur normalize (require_mutation
    # after hyperpart investigate queue=0). Mirrors test_money_field_syncs_…
    Probe(
        id="money.sync_minor_and_blur_normalize",
        stem="money",
        page="hyperparts/money.html",
        category="interaction",
        severity="high",
        claim=(
            "Typing a major amount rewrites the hidden minor carrier; blur "
            "normalizes display to scale decimals; empty blur clears the carrier "
            "(money submit contract is integer minor — not a static demo)"
        ),
        kind="money_sync_minor_blur",
        params={
            "root": "[data-money], [data-dz-money], .money, .dz-money",
            "display": (
                "input[inputmode=decimal], input[inputmode='decimal'], input.form-input[type=text]"
            ),
            "minor": "input[name=amount_minor], input[type=hidden][name$=_minor]",
            "seed_minor": "1500",
            "type_value": "12.5",
            "expect_minor_typed": "1250",
            "expect_display_blur": "12.50",
            "scope": ".hm-preview",
        },
        fix_surface="controller",
        intent="exclusive",
    ),
    # Cycle 1545 — app-shell live: hamburger flips data-sidebar open↔closed.
    # Live page (not iframe host); mirrors test_app_shell_sidebar_toggle.
    Probe(
        id="app_shell.sidebar_toggle",
        stem="app-shell",
        page="hyperparts/app-shell-live.html",
        category="interaction",
        severity="high",
        claim=(
            "Hamburger sidebar toggle flips data-sidebar open↔closed and "
            "aria-expanded on the toggle (live shell chrome — not a static iframe demo)"
        ),
        kind="app_shell_sidebar_toggle",
        params={
            "shell": ".app-shell, .dz-app-shell, [data-app-shell], [data-dz-app-shell]",
            "toggle": (
                "[data-sidebar-toggle], [data-dz-sidebar-toggle], "
                "button.app-shell__menu, button.dz-app-shell__menu"
            ),
            "attr": "data-sidebar",
            "open_value": "open",
            "closed_value": "closed",
            "scope": "",  # whole live page
        },
        fix_surface="controller",
        intent="exclusive",
    ),
    # Cycle 1553 — confirm: hx-confirm opens designed dialog; accept issues request.
    # Mirrors test_behaviour.test_confirm_dialog_intercepts_hx_confirm.
    Probe(
        id="confirm.intercept_and_accept",
        stem="confirm",
        page="hyperparts/confirm.html",
        category="interaction",
        severity="high",
        claim=(
            "Clicking hx-delete[hx-confirm] opens the designed alert-dialog with "
            "the confirm text; accepting closes the dialog and issues the request "
            "(MOCK_HTMX toast) — not a silent window.confirm fallback"
        ),
        kind="confirm_intercept_accept",
        params={
            "trigger": (
                ".hm-preview [hx-delete][hx-confirm], .hm-preview button[hx-delete][hx-confirm]"
            ),
            "dialog": (
                "dialog.alert-dialog, dialog.dz-alert-dialog, dialog[class*='alert-dialog']"
            ),
            "message": (
                ".alert-dialog__message, .dz-alert-dialog__message, "
                "dialog.alert-dialog p, dialog.dz-alert-dialog p"
            ),
            "accept": (
                "[data-confirm-accept], [data-dz-confirm-accept], "
                "dialog.alert-dialog button[data-variant=destructive], "
                "dialog.dz-alert-dialog button[data-dz-variant=destructive]"
            ),
            "toast": ".hm-toast, .toast, .dz-toast",
            "settle_ms": 150,
            "scope": "",  # dialog is body-appended; toast may be outside preview
        },
        fix_surface="controller",
        intent="exclusive",
    ),
    # Cycle 1559 — master-detail: list click moves aria-current + MOCK_HTMX detail.
    # Mirrors test_behaviour.test_master_detail_selection_and_instance_isolation (select half).
    Probe(
        id="master_detail.select_item",
        stem="master-detail",
        page="hyperparts/master-detail.html",
        category="interaction",
        severity="high",
        claim=(
            "Clicking a master-detail list item moves aria-current exclusively to "
            "that item and loads its detail card into the sibling pane "
            "(INV-002 · Globex via MOCK_HTMX) — selection state is controller-owned"
        ),
        kind="master_detail_select",
        params={
            "root": (
                "[data-dz-master-detail], .dz-master-detail, [data-master-detail], .master-detail"
            ),
            "item": (
                ".dz-master-detail__item, .master-detail__item, "
                "a.dz-master-detail__item, a.master-detail__item"
            ),
            "detail": (
                ".dz-master-detail__detail, .master-detail__detail, "
                "[data-dz-master-detail-detail-body], [data-master-detail-detail-body]"
            ),
            "activate_hx_suffix": "inv-002",
            "expect_label_contains": "Globex",
            "expect_detail_contains": "Globex",
            "settle_ms": 200,
            "scope": ".hm-preview",
        },
        fix_surface="controller",
        intent="exclusive",
    ),
    # Cycle 1565 — pagination: page-2 hx-get swaps list body via MOCK_HTMX.
    # Catalog expand under require_mutation (discover uncovered=0).
    Probe(
        id="pagination.page_two_loads_rows",
        stem="pagination",
        page="hyperparts/pagination.html",
        category="interaction",
        severity="high",
        claim=(
            "Clicking page 2 loads the MOCK_HTMX page-2 row slice into the list "
            "body (INV-004 · Umbrella) — pagination is an Exchange footer, not a "
            "dead chrome decoration"
        ),
        kind="pagination_page_load",
        params={
            "root": ("[data-pagination], [data-dz-pagination], .pagination, .dz-pagination"),
            "page_btn": (
                '.pagination-page[hx-get$="/mock/pagination/2"], '
                '.dz-pagination-page[hx-get$="/mock/pagination/2"], '
                'button.pagination-page:has-text("2"), '
                'button.dz-pagination-page:has-text("2")'
            ),
            "body": (
                "#hm-pag-body, .hm-pag-list, [data-pagination-body], [data-dz-pagination-body]"
            ),
            "expect_body_contains": "Umbrella",
            "settle_ms": 200,
            "scope": ".hm-preview",
        },
        fix_surface="controller",
        intent="exclusive",
    ),
    # Cycle 1570 — date-range: changing From fires hx-get into out slot (MOCK_HTMX search).
    Probe(
        id="date_range.change_fires_search",
        stem="date-range",
        page="hyperparts/date-range.html",
        category="interaction",
        severity="high",
        claim=(
            "Changing the From date input fires the bar's hx-get exchange into "
            "the out slot (MOCK_HTMX /mock/search results) — date-range is a "
            "filter Exchange footer, not dead chrome"
        ),
        kind="date_range_change",
        params={
            "root": (
                "[data-date-range], [data-dz-date-range], .date-range-picker, "
                ".date-range-bar, .dz-date-range"
            ),
            "from_input": (
                'input[name="date_from"], input#hm-dr-from, .date-range-input[name="date_from"]'
            ),
            "out": ("#hm-dr-out, [data-date-range-out], [data-dz-date-range-out]"),
            "set_value": "2026-07-15",
            "expect_out_contains": "result",
            "settle_ms": 250,
            "scope": ".hm-preview",
        },
        fix_surface="controller",
        intent="exclusive",
    ),
    # Cycle 1576 — search-box: typing fires debounced hx-get into results (MOCK_HTMX).
    # Catalog expand under require_mutation (discover uncovered=0). Mirrors
    # test_behaviour.test_search_box_coaching_hides_on_type_via_pure_css exchange half.
    Probe(
        id="search_box.type_fires_results",
        stem="search-box",
        page="hyperparts/search-box.html",
        category="interaction",
        severity="high",
        claim=(
            "Typing a query into the search-box input fires the debounced hx-get "
            "into the results slot (MOCK_HTMX /mock/search → Aurora) — FTS search "
            "is a live Exchange, not a static empty coaching panel"
        ),
        kind="search_box_type_results",
        params={
            "root": (
                "[data-search-box], [data-dz-search-box], .search-box-region, "
                ".dz-search-box-region, .search-box, .dz-search-box"
            ),
            "input": (
                "input[type=search].search-box-input, "
                "input[type=search].dz-search-box-input, "
                "input[type=search][name=q], input#hm-search-input"
            ),
            "results": ("#hm-search-results, .search-box-results, .dz-search-box-results"),
            "query": "substation",
            "expect_results_contains": "Aurora",
            "debounce_ms": 400,
            "scope": ".hm-preview",
        },
        fix_surface="partial",
        intent="exclusive",
    ),
    # Cycle 1582 — confirm-panel: required checklist arms primary (optional does not).
    # Catalog expand under require_mutation (discover uncovered=0). Mirrors
    # test_behaviour.test_confirm_gate_arms_primary_only_when_required_boxes_checked.
    Probe(
        id="confirm_panel.required_gate_arms_primary",
        stem="confirm-panel",
        page="hyperparts/confirm-panel.html",
        category="interaction",
        severity="high",
        claim=(
            "Checking all required consent boxes arms the primary action "
            "(drops aria-disabled, promotes data-confirm-href → href); optional "
            "boxes alone never arm; unchecking a required box re-disarms — "
            "irreversible-action gate is state-in-DOM, not a JS counter"
        ),
        kind="confirm_panel_required_gate",
        params={
            "root": (
                "[data-confirm-gate], [data-dz-confirm-gate], "
                "ul.confirm-checklist, .confirm-checklist"
            ),
            "primary": (".confirm-primary, a.confirm-primary, [data-confirm-href]"),
            "required_input": (
                "input[data-required='true'], input[data-dz-required='true'], "
                "input.confirm-checkbox[data-required='true']"
            ),
            "optional_input": (
                "li[data-required='false'] input[type=checkbox], "
                "input.confirm-checkbox:not([data-required='true'])"
            ),
            "expect_href": "#go-live",
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


def _run_checkbox_toggle(page: Any, probe: Probe) -> dict[str, Any]:
    """Click a checkbox/switch input; assert checked flips both ways."""
    params = probe.params
    input_sel = params["input"]
    start = params.get("start_checked")
    settle = int(params.get("settle_ms", 80))

    scope = _probe_scope(page, params)
    inp = None
    for part in input_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = scope.locator(part).first
        if loc.count() > 0:
            inp = loc
            break
    if inp is None:
        return {"verdict": "ERROR", "detail": f"input not found ({input_sel})"}

    checked0 = bool(inp.is_checked())
    if start is not None and checked0 != bool(start):
        # still exercise toggle; note mismatch
        pass

    inp.click(force=True)
    page.wait_for_timeout(settle)
    checked1 = bool(inp.is_checked())
    if checked1 == checked0:
        return {
            "verdict": "FAIL",
            "detail": f"click did not flip checked (stayed {checked0})",
            "dom_hint": input_sel,
        }

    inp.click(force=True)
    page.wait_for_timeout(settle)
    checked2 = bool(inp.is_checked())
    if checked2 != checked0:
        return {
            "verdict": "FAIL",
            "detail": f"second click did not restore checked={checked0} (got {checked2})",
            "dom_hint": input_sel,
        }
    return {
        "verdict": "PASS",
        "detail": f"toggled {checked0}→{checked1}→{checked2}",
        "checked_sequence": [checked0, checked1, checked2],
    }


def _run_range_value_readout(page: Any, probe: Probe) -> dict[str, Any]:
    """Set a range input value; assert sibling group readout text matches.

    Mirrors packages/hatchi-maxchi/tests/test_behaviour.py::test_slider_updates_value_readout
    for the autonomous gallery_probes catalog (cycle 1491).
    """
    params = probe.params
    input_sel = params["input"]
    readout_sel = params["readout"]
    target = str(params.get("set_value", "30"))
    settle = int(params.get("settle_ms", 80))

    scope = _probe_scope(page, params)
    inp = None
    for part in input_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = scope.locator(part).first
        if loc.count() > 0:
            inp = loc
            break
    if inp is None:
        return {"verdict": "ERROR", "detail": f"range input not found ({input_sel})"}

    out = None
    for part in readout_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = scope.locator(part).first
        if loc.count() > 0:
            out = loc
            break
    if out is None:
        return {"verdict": "ERROR", "detail": f"readout not found ({readout_sel})"}

    before = (out.inner_text() or "").strip()
    # Playwright fill on range + input event so delegated controllers fire.
    inp.evaluate(
        """(el, v) => {
            el.value = String(v);
            el.dispatchEvent(new Event('input', { bubbles: true }));
        }""",
        target,
    )
    page.wait_for_timeout(settle)
    after = (out.inner_text() or "").strip()
    if after != target:
        return {
            "verdict": "FAIL",
            "detail": (f"readout stayed {after!r} after set_value={target!r} (was {before!r})"),
            "dom_hint": f"{input_sel} → {readout_sel}",
        }
    return {
        "verdict": "PASS",
        "detail": f"readout {before!r}→{after!r}",
        "value": after,
    }


def _run_aria_pressed_toggle(page: Any, probe: Probe) -> dict[str, Any]:
    """Click a [data-toggle] button; assert aria-pressed flips both ways."""
    params = probe.params
    button_sel = params["button"]
    prefer = (params.get("prefer_label_contains") or "").strip()
    settle = int(params.get("settle_ms", 80))

    scope = _probe_scope(page, params)
    btn = None
    for part in button_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = scope.locator(part)
        if prefer:
            filtered = loc.filter(has_text=prefer)
            if filtered.count() > 0:
                btn = filtered.first
                break
        if loc.count() > 0:
            btn = loc.first
            break
    if btn is None:
        return {"verdict": "ERROR", "detail": f"toggle button not found ({button_sel})"}

    pressed0 = btn.get_attribute("aria-pressed")
    if pressed0 not in ("true", "false"):
        return {
            "verdict": "FAIL",
            "detail": f"aria-pressed missing/invalid before click: {pressed0!r}",
            "dom_hint": button_sel,
        }

    btn.click()
    page.wait_for_timeout(settle)
    pressed1 = btn.get_attribute("aria-pressed")
    if pressed1 == pressed0:
        return {
            "verdict": "FAIL",
            "detail": f"click did not flip aria-pressed (stayed {pressed0!r})",
            "dom_hint": button_sel,
        }
    expect1 = "false" if pressed0 == "true" else "true"
    if pressed1 != expect1:
        return {
            "verdict": "FAIL",
            "detail": f"after first click aria-pressed={pressed1!r}, expected {expect1!r}",
            "dom_hint": button_sel,
        }

    btn.click()
    page.wait_for_timeout(settle)
    pressed2 = btn.get_attribute("aria-pressed")
    if pressed2 != pressed0:
        return {
            "verdict": "FAIL",
            "detail": (
                f"second click did not restore aria-pressed={pressed0!r} (got {pressed2!r})"
            ),
            "dom_hint": button_sel,
        }
    return {
        "verdict": "PASS",
        "detail": f"aria-pressed {pressed0}→{pressed1}→{pressed2}",
        "pressed_sequence": [pressed0, pressed1, pressed2],
    }


def _run_radio_group_select(page: Any, probe: Probe) -> dict[str, Any]:
    """Click a radio in a toggle-group; assert exclusive checked state."""
    params = probe.params
    root_sel = params["root"]
    radio_sel = params.get("radio", 'input[type="radio"]')
    activate = params.get("activate_label_contains") or "Board"
    expect = params.get("expect_checked_label_contains") or activate
    settle = int(params.get("settle_ms", 80))

    scope = _probe_scope(page, params)
    root = None
    for part in root_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = scope.locator(part).first
        if loc.count() > 0:
            root = loc
            break
    if root is None:
        return {"verdict": "ERROR", "detail": f"toggle-group root not found ({root_sel})"}

    radios = root.locator(radio_sel)
    n = radios.count()
    if n < 2:
        return {
            "verdict": "ERROR",
            "detail": f"need ≥2 radios in group, found {n}",
            "dom_hint": radio_sel,
        }

    target = None
    for i in range(n):
        r = radios.nth(i)
        # label text is typically on the wrapping <label>
        label = r.evaluate(
            """(el) => {
              const lab = el.closest('label');
              return lab ? (lab.innerText || lab.textContent || '') : '';
            }"""
        )
        if activate.lower() in (label or "").lower():
            target = r
            break
    if target is None:
        return {
            "verdict": "ERROR",
            "detail": f"radio with label containing {activate!r} not found",
        }

    target.click(force=True)
    page.wait_for_timeout(settle)

    checked_labels: list[str] = []
    for i in range(n):
        r = radios.nth(i)
        if r.is_checked():
            label = r.evaluate(
                """(el) => {
                  const lab = el.closest('label');
                  return lab ? (lab.innerText || lab.textContent || '') : '';
                }"""
            )
            checked_labels.append(_norm_label(label or ""))

    if len(checked_labels) != 1:
        return {
            "verdict": "FAIL",
            "detail": f"expected exactly 1 checked radio, got {checked_labels!r}",
            "dom_hint": root_sel,
        }
    if expect.lower() not in checked_labels[0].lower():
        return {
            "verdict": "FAIL",
            "detail": f"checked={checked_labels[0]!r}, expected ≈{expect!r}",
            "dom_hint": root_sel,
        }
    return {
        "verdict": "PASS",
        "detail": f"exclusive checked={checked_labels[0]!r}",
        "checked_label": checked_labels[0],
    }


def _run_carousel_advance(page: Any, probe: Probe) -> dict[str, Any]:
    """Click carousel Next; assert index, active slide, and status advance.

    Mirrors packages/hatchi-maxchi/tests/test_behaviour.py carousel clamp
    next-step for the autonomous gallery_probes catalog (cycle 1507).
    """
    params = probe.params
    root_sel = params["root"]
    next_sel = params.get("next", "[data-carousel-next], [data-dz-carousel-next]")
    active_sel = params.get(
        "active_slide",
        (
            ".carousel__slide[data-active], .carousel__slide[data-dz-active], "
            ".dz-carousel__slide[data-active], .dz-carousel__slide[data-dz-active]"
        ),
    )
    status_sel = params.get("status", "[data-carousel-status], [data-dz-carousel-status]")
    expect_index = str(params.get("expect_index_after", "1"))
    expect_status = params.get("expect_status_contains") or "2 of"
    settle = int(params.get("settle_ms", 120))

    scope = _probe_scope(page, params)
    root = None
    for part in root_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = scope.locator(part).first
        if loc.count() > 0:
            root = loc
            break
    if root is None:
        return {"verdict": "ERROR", "detail": f"carousel root not found ({root_sel})"}

    next_btn = None
    for part in next_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = root.locator(part).first
        if loc.count() > 0:
            next_btn = loc
            break
    if next_btn is None:
        return {"verdict": "ERROR", "detail": f"next control not found ({next_sel})"}

    index_before = (
        root.get_attribute("data-carousel-index")
        or root.get_attribute("data-dz-carousel-index")
        or "0"
    )
    status_el = None
    for part in status_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = root.locator(part).first
        if loc.count() > 0:
            status_el = loc
            break
    status_before = (status_el.inner_text() if status_el else "") or ""
    active_before = root.locator(active_sel).count()

    if next_btn.is_disabled():
        return {
            "verdict": "FAIL",
            "detail": f"next disabled at index={index_before!r} (cannot advance)",
            "dom_hint": next_sel,
        }

    next_btn.click()
    page.wait_for_timeout(settle)

    index_after = (
        root.get_attribute("data-carousel-index")
        or root.get_attribute("data-dz-carousel-index")
        or ""
    )
    status_after = (status_el.inner_text() if status_el else "") or ""
    active_after = root.locator(active_sel).count()

    if index_after != expect_index:
        return {
            "verdict": "FAIL",
            "detail": (
                f"index stayed {index_after!r} after next "
                f"(was {index_before!r}, expected {expect_index!r})"
            ),
            "dom_hint": root_sel,
        }
    if active_after != 1:
        return {
            "verdict": "FAIL",
            "detail": (
                f"expected exactly 1 active slide after next, got {active_after} "
                f"(before={active_before})"
            ),
            "dom_hint": active_sel,
        }
    if expect_status.lower() not in status_after.lower():
        return {
            "verdict": "FAIL",
            "detail": (
                f"status {status_after!r} missing {expect_status!r} (was {status_before!r})"
            ),
            "dom_hint": status_sel,
        }
    return {
        "verdict": "PASS",
        "detail": (
            f"index {index_before!r}→{index_after!r}; "
            f"status {status_before.strip()!r}→{status_after.strip()!r}"
        ),
        "index_before": index_before,
        "index_after": index_after,
        "status_after": status_after.strip(),
    }


def _run_combobox_select(page: Any, probe: Probe) -> dict[str, Any]:
    """Enhance native select[data-combobox], pick an option, assert commit+close.

    Mirrors packages/hatchi-maxchi/tests/test_behaviour.py
    ``test_combobox_click_option_closes_listbox`` for gallery catalog (cycle 1513).
    Gallery demos use unprefixed classes; product emits ``dz-`` / ``data-dz-*``.
    """
    params = probe.params
    select_sel = params.get("select", "select[data-combobox], select[data-dz-combobox]")
    root_sel = params.get(
        "root",
        (
            ".combobox[data-enhanced], .combobox[data-dz-enhanced], "
            ".dz-combobox[data-enhanced], .dz-combobox[data-dz-enhanced]"
        ),
    )
    option_sel = params.get(
        "option",
        '.combobox-option[data-value="high"], .dz-combobox-option[data-value="high"]',
    )
    input_sel = params.get("input", ".combobox-input, .dz-combobox-input")
    expect_value = str(params.get("expect_value", "high"))
    expect_label = str(params.get("expect_label", "High"))
    settle = int(params.get("settle_ms", 120))

    scope = _probe_scope(page, params)
    sel = None
    for part in select_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = scope.locator(part).first
        if loc.count() > 0:
            sel = loc
            break
    if sel is None:
        return {"verdict": "ERROR", "detail": f"select not found ({select_sel})"}

    sel.dispatch_event("pointerdown")
    page.wait_for_timeout(settle)

    root = None
    for part in root_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = scope.locator(part).first
        if loc.count() > 0:
            root = loc
            break
    if root is None:
        return {
            "verdict": "FAIL",
            "detail": f"enhanced combobox root not found after pointerdown ({root_sel})",
            "dom_hint": root_sel,
        }

    open_attr = root.get_attribute("data-open")
    if open_attr is None:
        open_attr = root.get_attribute("data-dz-open")
    if open_attr is None:
        return {
            "verdict": "FAIL",
            "detail": "combobox did not open after pointerdown (no data-open)",
            "dom_hint": root_sel,
        }

    opt = None
    for part in option_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = root.locator(part).first
        if loc.count() > 0:
            opt = loc
            break
    if opt is None:
        return {
            "verdict": "FAIL",
            "detail": f"option not found ({option_sel})",
            "dom_hint": option_sel,
        }

    opt.click()
    page.wait_for_timeout(settle)

    value_after = sel.input_value()
    if value_after != expect_value:
        return {
            "verdict": "FAIL",
            "detail": f"select value={value_after!r}, expected {expect_value!r}",
            "dom_hint": select_sel,
        }

    input_el = None
    for part in input_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = root.locator(part).first
        if loc.count() > 0:
            input_el = loc
            break
    if input_el is None:
        return {"verdict": "FAIL", "detail": f"overlay input not found ({input_sel})"}
    label_after = input_el.input_value()
    if expect_label.lower() not in (label_after or "").lower():
        return {
            "verdict": "FAIL",
            "detail": f"input label={label_after!r}, expected ≈{expect_label!r}",
            "dom_hint": input_sel,
        }

    open_after = root.get_attribute("data-open") or root.get_attribute("data-dz-open")
    if open_after is not None:
        return {
            "verdict": "FAIL",
            "detail": f"listbox still open after pick (data-open={open_after!r})",
            "dom_hint": root_sel,
        }

    return {
        "verdict": "PASS",
        "detail": f"selected value={value_after!r} label={label_after!r}; listbox closed",
        "value": value_after,
        "label": label_after,
    }


def _run_wizard_step_forward(page: Any, probe: Probe) -> dict[str, Any]:
    """Fill required field on current wizard stage, click next stepper, assert advance.

    Gallery demos use unprefixed ``data-wizard`` / ``data-step`` / ``data-step-to``;
    product emits ``data-dz-*``. Forward is one step at a time and validity-gated
    (see ``controllers/dz-wizard.js`` / bundled unprefixed twin).
    """
    params = probe.params
    root_sel = params.get("root", "[data-wizard], [data-dz-wizard]")
    required_sel = params.get("required_input", "input[required]")
    fill_value = str(params.get("fill_value", "Acme launch"))
    step_btn_sel = params.get(
        "step_button",
        '[data-step-to="1"], [data-dz-step-to="1"]',
    )
    stage_sel = params.get("stage", '[data-stage="1"], [data-dz-stage="1"]')
    expect_step = str(params.get("expect_step_after", "1"))
    settle = int(params.get("settle_ms", 150))

    scope = _probe_scope(page, params)
    root = None
    for part in root_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = scope.locator(part).first
        if loc.count() > 0:
            root = loc
            break
    if root is None:
        return {"verdict": "ERROR", "detail": f"wizard root not found ({root_sel})"}

    def _step_attr() -> str:
        return root.get_attribute("data-step") or root.get_attribute("data-dz-step") or ""

    step_before = _step_attr()
    inp = None
    for part in required_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = root.locator(part).first
        if loc.count() > 0:
            inp = loc
            break
    if inp is None:
        return {
            "verdict": "ERROR",
            "detail": f"required input not found ({required_sel})",
            "dom_hint": required_sel,
        }
    inp.fill(fill_value)

    btn = None
    for part in step_btn_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = root.locator(part).first
        if loc.count() > 0:
            btn = loc
            break
    if btn is None:
        return {
            "verdict": "ERROR",
            "detail": f"step button not found ({step_btn_sel})",
            "dom_hint": step_btn_sel,
        }
    btn.click()
    page.wait_for_timeout(settle)

    step_after = _step_attr()
    if step_after != expect_step:
        return {
            "verdict": "FAIL",
            "detail": (
                f"data-step stayed {step_after!r} after forward "
                f"(was {step_before!r}, expected {expect_step!r}) — "
                "validity gate or stepper controller may be broken"
            ),
            "dom_hint": root_sel,
        }

    stage = None
    for part in stage_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = root.locator(part).first
        if loc.count() > 0:
            stage = loc
            break
    if stage is None:
        return {
            "verdict": "FAIL",
            "detail": f"target stage not found after advance ({stage_sel})",
            "dom_hint": stage_sel,
        }
    # Playwright: hidden attribute present → get_attribute returns "" or "true"
    if stage.get_attribute("hidden") is not None:
        # Some browsers expose empty string; treat any present attr as hidden=True
        # unless explicitly false — wizard uses native boolean hidden.
        is_hidden = stage.evaluate("el => el.hidden === true")
        if is_hidden:
            return {
                "verdict": "FAIL",
                "detail": f"stage still hidden after advance to step {expect_step}",
                "dom_hint": stage_sel,
            }

    return {
        "verdict": "PASS",
        "detail": f"data-step {step_before!r}→{step_after!r}; stage visible after valid fill",
        "step_before": step_before,
        "step_after": step_after,
    }


def _run_toast_dismiss_and_fire(page: Any, probe: Probe) -> dict[str, Any]:
    """Dismiss one stack toast, then client-fire showToast and assert append.

    Mirrors packages/hatchi-maxchi/tests/test_behaviour.py
    test_toast_stack_host_pause_dismiss_and_client_fire for the autonomous
    gallery_probes catalog (cycle 1535). Live page only (toast-live.html).
    """
    params = probe.params
    stack_sel = params.get("stack", "#toast.toast-stack, #dz-toast.dz-toast-stack")
    toast_sel = params.get("toast", ".toast, .dz-toast")
    dismiss_sel = params.get(
        "dismiss",
        ".toast__close[data-toast-dismiss], .dz-toast__close[data-dz-toast-dismiss]",
    )
    title_sel = params.get("title", ".toast__title, .dz-toast__title")
    fire_title = str(params.get("fire_title", "Host test"))
    leave_ms = int(params.get("leave_ms", 450))
    settle = int(params.get("settle_ms", 120))

    scope = _probe_scope(page, params)
    stack = None
    for part in stack_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = scope.locator(part).first
        if loc.count() > 0:
            stack = loc
            break
    if stack is None:
        return {"verdict": "ERROR", "detail": f"toast stack not found ({stack_sel})"}

    initial = scope.locator(toast_sel).count()
    if initial < 1:
        return {
            "verdict": "FAIL",
            "detail": "demo stack ships no toast to dismiss",
            "dom_hint": toast_sel,
        }

    # evaluate click avoids fixed-position intercept flakes (same as behaviour test)
    removed = page.evaluate(
        """(sel) => {
          const close = document.querySelector(sel);
          if (!close) return false;
          close.click();
          return true;
        }""",
        dismiss_sel.split(",")[0].strip(),
    )
    if not removed:
        # try full selector list via first match
        removed = page.evaluate(
            """(sels) => {
              for (const sel of sels) {
                const close = document.querySelector(sel.trim());
                if (close) { close.click(); return true; }
              }
              return false;
            }""",
            dismiss_sel.split(","),
        )
    if not removed:
        return {
            "verdict": "FAIL",
            "detail": f"dismiss control not found ({dismiss_sel})",
            "dom_hint": dismiss_sel,
        }

    page.wait_for_timeout(leave_ms)
    after_dismiss = scope.locator(toast_sel).count()
    if after_dismiss != initial - 1:
        return {
            "verdict": "FAIL",
            "detail": (
                f"dismiss left {after_dismiss} toasts (was {initial}, expected "
                f"{initial - 1}) — leave motion or dismiss handler broken"
            ),
            "dom_hint": toast_sel,
        }

    page.evaluate(
        """(title) => {
          document.dispatchEvent(new CustomEvent('showToast', {
            detail: {
              title: title,
              message: 'Client-fired toast',
              type: 'warning',
              duration: '30s',
            },
          }));
        }""",
        fire_title,
    )
    page.wait_for_timeout(settle)
    after_fire = scope.locator(toast_sel).count()
    if after_fire != after_dismiss + 1:
        return {
            "verdict": "FAIL",
            "detail": (
                f"showToast left {after_fire} toasts (expected {after_dismiss + 1}) — "
                "client fire path may be broken"
            ),
            "dom_hint": stack_sel,
        }
    titled = scope.locator(title_sel).filter(has_text=fire_title).count()
    if titled < 1:
        return {
            "verdict": "FAIL",
            "detail": f"fired toast missing title {fire_title!r}",
            "dom_hint": title_sel,
        }

    return {
        "verdict": "PASS",
        "detail": (f"dismiss {initial}→{after_dismiss}; showToast +1 title={fire_title!r}"),
        "initial": initial,
        "after_dismiss": after_dismiss,
        "after_fire": after_fire,
    }


def _run_tags_seed_add_remove(page: Any, probe: Probe) -> dict[str, Any]:
    """Seed enhance → Enter add chip → × remove; native value stays comma-joined.

    Mirrors packages/hatchi-maxchi/tests/test_behaviour.py
    test_tags_seed_and_add_chip + test_tags_remove_chip for the autonomous
    gallery_probes catalog (cycle 1536). Gallery dual-lock uses unprefixed
    data-tags / .tags-*; product dist uses data-dz-tags / .dz-tags-*.
    """
    params = probe.params
    native_sel = params.get("native", "input[data-tags], input[data-dz-tags]")
    root_sel = params.get(
        "root",
        (
            ".tags[data-enhanced], .dz-tags[data-dz-enhanced], "
            ".tags[data-dz-enhanced], .dz-tags[data-enhanced]"
        ),
    )
    chip_sel = params.get("chip", ".tags-chip, .dz-tags-chip")
    entry_sel = params.get("entry", ".tags-entry, .dz-tags-entry")
    seed_count = int(params.get("seed_count", 2))
    add_value = str(params.get("add_value", "frontend"))
    expect_after_add = str(params.get("expect_after_add", "urgent,backend,frontend"))
    remove_label = str(params.get("remove_label", "Remove urgent"))
    expect_after_remove = str(params.get("expect_after_remove", "backend,frontend"))
    settle = int(params.get("settle_ms", 100))

    scope = _probe_scope(page, params)
    native = None
    for part in native_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = scope.locator(part).first
        if loc.count() > 0:
            native = loc
            break
    if native is None:
        return {"verdict": "ERROR", "detail": f"tags native input not found ({native_sel})"}

    # Seeded values should enhance on DOM ready; pointerdown covers empty/late paths.
    page.wait_for_timeout(settle)
    root = scope.locator(root_sel).first
    if root.count() < 1:
        native.dispatch_event("pointerdown")
        page.wait_for_timeout(settle)
        root = scope.locator(root_sel).first
    if root.count() < 1:
        return {
            "verdict": "FAIL",
            "detail": f"tags root not enhanced ({root_sel})",
            "dom_hint": root_sel,
        }

    chips = scope.locator(chip_sel)
    initial = chips.count()
    if initial < seed_count:
        return {
            "verdict": "FAIL",
            "detail": (
                f"seed enhance left {initial} chips (expected ≥{seed_count}) — "
                "SSR comma value may not paint chips"
            ),
            "dom_hint": chip_sel,
        }

    entry = scope.locator(entry_sel).first
    if entry.count() < 1:
        return {
            "verdict": "FAIL",
            "detail": f"tags entry not found ({entry_sel})",
            "dom_hint": entry_sel,
        }
    entry.fill(add_value)
    page.keyboard.press("Enter")
    page.wait_for_timeout(settle // 2 if settle >= 50 else 50)
    after_add = chips.count()
    if after_add != initial + 1:
        return {
            "verdict": "FAIL",
            "detail": (
                f"Enter add left {after_add} chips (was {initial}, expected "
                f"{initial + 1}) — chip create path broken"
            ),
            "dom_hint": entry_sel,
        }
    native_val = native.input_value()
    if native_val != expect_after_add:
        return {
            "verdict": "FAIL",
            "detail": (
                f"native value after add {native_val!r} != {expect_after_add!r} — "
                "submit contract drift"
            ),
            "dom_hint": native_sel,
        }

    remove_btn = scope.get_by_role("button", name=remove_label)
    if remove_btn.count() < 1:
        # aria-label fallback
        remove_btn = scope.locator(f'button[aria-label="{remove_label}"]')
    if remove_btn.count() < 1:
        return {
            "verdict": "FAIL",
            "detail": f"remove control not found ({remove_label!r})",
            "dom_hint": "button[aria-label]",
        }
    remove_btn.first.click()
    page.wait_for_timeout(settle // 2 if settle >= 50 else 50)
    after_remove = chips.count()
    if after_remove != after_add - 1:
        return {
            "verdict": "FAIL",
            "detail": (
                f"remove left {after_remove} chips (was {after_add}, expected "
                f"{after_add - 1}) — × dismiss broken"
            ),
            "dom_hint": chip_sel,
        }
    native_val2 = native.input_value()
    if native_val2 != expect_after_remove:
        return {
            "verdict": "FAIL",
            "detail": (f"native value after remove {native_val2!r} != {expect_after_remove!r}"),
            "dom_hint": native_sel,
        }

    return {
        "verdict": "PASS",
        "detail": (
            f"seed={initial}; add {add_value!r} → {after_add}; "
            f"remove {remove_label!r} → {after_remove} value={native_val2!r}"
        ),
        "seed_chips": initial,
        "after_add": after_add,
        "after_remove": after_remove,
    }


def _run_search_select_typeahead_select(page: Any, probe: Probe) -> dict[str, Any]:
    """Focus → typeahead filter → select row → confirm-hold → auto-dismiss.

    Mirrors packages/hatchi-maxchi/tests/test_behaviour.py
    test_search_select_opens_on_focus_and_survives_row_click for the autonomous
    gallery_probes catalog (cycle 1537). Gallery MOCK_HTMX serves /mock/typeahead
    on file://.
    """
    params = probe.params
    root_sel = params.get(
        "root",
        (
            ".search-select, .dz-search-select, "
            "[data-widget='search_select'], [data-dz-widget='search_select']"
        ),
    )
    input_sel = params.get(
        "input",
        (
            "input[type=text].search-select-input, "
            "input[type=text].dz-search-select-input, "
            ".search-select input[type=text], .dz-search-select input[type=text]"
        ),
    )
    panel_sel = params.get(
        "panel",
        ".search-select-results, .dz-search-select-results",
    )
    row_sel = params.get("row", ".search-result-row, .dz-search-result-row")
    query = str(params.get("query", "auro"))
    expect_row = str(params.get("expect_row_text", "Aurora"))
    expect_confirm = str(params.get("expect_confirm_text", "Selected"))
    debounce_ms = int(params.get("debounce_ms", 450))
    post_select_ms = int(params.get("post_select_ms", 300))
    hold_mid_ms = int(params.get("hold_mid_ms", 1000))
    hold_rest_ms = int(params.get("hold_rest_ms", 1200))

    scope = _probe_scope(page, params)
    root = None
    for part in root_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = scope.locator(part).first
        if loc.count() > 0:
            root = loc
            break
    if root is None:
        return {"verdict": "ERROR", "detail": f"search-select root not found ({root_sel})"}

    panel = None
    for part in panel_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = root.locator(part).first
        if loc.count() > 0:
            panel = loc
            break
    if panel is None:
        # fall back to scope (results id may live under root)
        for part in panel_sel.split(","):
            part = part.strip()
            if not part:
                continue
            loc = scope.locator(part).first
            if loc.count() > 0:
                panel = loc
                break
    if panel is None:
        return {"verdict": "ERROR", "detail": f"results panel not found ({panel_sel})"}

    inp = None
    for part in input_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = root.locator(part).first
        if loc.count() > 0:
            inp = loc
            break
    if inp is None:
        return {"verdict": "ERROR", "detail": f"typeahead input not found ({input_sel})"}

    # Resting: panel hidden (CSS) until focus opens.
    if panel.is_visible():
        # Some demos leave prompt visible — only fail if open without focus and has open attr
        open_attr = root.get_attribute("data-open") or root.get_attribute("data-dz-open")
        if open_attr is not None:
            return {
                "verdict": "FAIL",
                "detail": "panel already open at rest (data-open set before focus)",
                "dom_hint": root_sel,
            }

    inp.focus()
    page.wait_for_timeout(80)
    if not panel.is_visible():
        return {
            "verdict": "FAIL",
            "detail": "panel not visible after focus",
            "dom_hint": panel_sel,
        }

    inp.fill(query)
    page.wait_for_timeout(debounce_ms)
    panel_text = panel.inner_text()
    if expect_row.lower() not in panel_text.lower():
        return {
            "verdict": "FAIL",
            "detail": (
                f"typeahead missing {expect_row!r} after query {query!r} "
                f"(panel text starts {panel_text[:80]!r})"
            ),
            "dom_hint": row_sel,
        }
    rows = root.locator(row_sel)
    if rows.count() < 1:
        rows = scope.locator(row_sel)
    if rows.count() < 1:
        return {
            "verdict": "FAIL",
            "detail": f"no result rows after filter ({row_sel})",
            "dom_hint": row_sel,
        }

    rows.first.click()
    page.wait_for_timeout(post_select_ms)
    panel_text2 = panel.inner_text()
    if expect_confirm.lower() not in panel_text2.lower():
        return {
            "verdict": "FAIL",
            "detail": (
                f"select confirm missing {expect_confirm!r} "
                f"(panel {panel_text2[:80]!r}) — select exchange or blur grace"
            ),
            "dom_hint": panel_sel,
        }
    if not panel.is_visible():
        return {
            "verdict": "FAIL",
            "detail": "panel hidden immediately after select — confirm-hold broken",
            "dom_hint": panel_sel,
        }

    page.wait_for_timeout(hold_mid_ms)
    if not panel.is_visible():
        return {
            "verdict": "FAIL",
            "detail": (
                f"panel closed mid-hold (~{hold_mid_ms}ms) — confirm-hold must outlast blur grace"
            ),
            "dom_hint": panel_sel,
        }

    page.wait_for_timeout(hold_rest_ms)
    if panel.is_visible():
        return {
            "verdict": "FAIL",
            "detail": (
                f"panel still open after hold (~{hold_mid_ms + hold_rest_ms}ms) — "
                "auto-dismiss after confirm-hold broken"
            ),
            "dom_hint": panel_sel,
        }

    return {
        "verdict": "PASS",
        "detail": (f"focus→filter {query!r}→select confirm {expect_confirm!r}; hold then dismiss"),
        "query": query,
    }


def _run_app_shell_sidebar_toggle(page: Any, probe: Probe) -> dict[str, Any]:
    """Hamburger flips data-sidebar open↔closed + aria-expanded on toggle.

    Mirrors packages/hatchi-maxchi/tests/test_behaviour.py
    test_app_shell_sidebar_toggle for gallery catalog (cycle 1545). Live page
    only (app-shell-live.html — framed gallery page is not the interaction host).
    """
    params = probe.params
    shell_sel = params.get(
        "shell",
        ".app-shell, .dz-app-shell, [data-app-shell], [data-dz-app-shell]",
    )
    toggle_sel = params.get(
        "toggle",
        "[data-sidebar-toggle], [data-dz-sidebar-toggle]",
    )
    attr = str(params.get("attr", "data-sidebar"))
    open_value = str(params.get("open_value", "open"))
    closed_value = str(params.get("closed_value", "closed"))
    settle = int(params.get("settle_ms", 80))

    scope = _probe_scope(page, params)
    shell = None
    for part in shell_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = scope.locator(part).first
        if loc.count() > 0:
            shell = loc
            break
    if shell is None:
        return {"verdict": "ERROR", "detail": f"app-shell root not found ({shell_sel})"}

    toggle = None
    for part in toggle_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = scope.locator(part).first
        if loc.count() > 0:
            toggle = loc
            break
    if toggle is None:
        return {"verdict": "ERROR", "detail": f"sidebar toggle not found ({toggle_sel})"}

    initial = shell.get_attribute(attr)
    if initial is None:
        # dual-lock product prefix
        alt = shell.get_attribute("data-dz-sidebar")
        if alt is not None:
            attr = "data-dz-sidebar"
            initial = alt
    if initial != open_value:
        return {
            "verdict": "FAIL",
            "detail": f"expected initial {attr}={open_value!r}, got {initial!r}",
            "dom_hint": shell_sel,
        }

    toggle.click()
    page.wait_for_timeout(settle)
    after_close = shell.get_attribute(attr)
    if after_close != closed_value:
        return {
            "verdict": "FAIL",
            "detail": (f"toggle close left {attr}={after_close!r} (expected {closed_value!r})"),
            "dom_hint": toggle_sel,
        }
    aria = toggle.get_attribute("aria-expanded")
    if aria is not None and aria not in ("false", "0"):
        return {
            "verdict": "FAIL",
            "detail": f"aria-expanded after close={aria!r} (expected false)",
            "dom_hint": toggle_sel,
        }

    toggle.click()
    page.wait_for_timeout(settle)
    after_open = shell.get_attribute(attr)
    if after_open != open_value:
        return {
            "verdict": "FAIL",
            "detail": (f"toggle open left {attr}={after_open!r} (expected {open_value!r})"),
            "dom_hint": toggle_sel,
        }

    return {
        "verdict": "PASS",
        "detail": f"{attr} {open_value}→{closed_value}→{open_value}; toggle ok",
    }


def _run_money_sync_minor_blur(page: Any, probe: Probe) -> dict[str, Any]:
    """Major input → minor carrier; blur normalize; empty clears carrier.

    Mirrors packages/hatchi-maxchi/tests/test_behaviour.py
    test_money_field_syncs_minor_carrier_and_normalizes (cycle 1539).
    """
    params = probe.params
    root_sel = params.get("root", "[data-money], [data-dz-money], .money, .dz-money")
    display_sel = params.get(
        "display",
        "input[inputmode=decimal], input[inputmode='decimal']",
    )
    minor_sel = params.get(
        "minor",
        "input[name=amount_minor], input[type=hidden][name$=_minor]",
    )
    seed_minor = str(params.get("seed_minor", "1500"))
    type_value = str(params.get("type_value", "12.5"))
    expect_minor_typed = str(params.get("expect_minor_typed", "1250"))
    expect_display_blur = str(params.get("expect_display_blur", "12.50"))
    settle = int(params.get("settle_ms", 50))

    scope = _probe_scope(page, params)
    root = None
    for part in root_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = scope.locator(part).first
        if loc.count() > 0:
            root = loc
            break
    if root is None:
        return {"verdict": "ERROR", "detail": f"money root not found ({root_sel})"}

    display = None
    for part in display_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = root.locator(part).first
        if loc.count() > 0:
            display = loc
            break
    if display is None:
        return {"verdict": "ERROR", "detail": f"display input not found ({display_sel})"}

    minor = None
    for part in minor_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = root.locator(part).first
        if loc.count() > 0:
            minor = loc
            break
    if minor is None:
        return {"verdict": "ERROR", "detail": f"minor carrier not found ({minor_sel})"}

    got_seed = minor.input_value()
    if got_seed != seed_minor:
        return {
            "verdict": "FAIL",
            "detail": f"seed minor {got_seed!r} != {seed_minor!r}",
            "dom_hint": minor_sel,
        }

    display.fill(type_value)
    page.wait_for_timeout(settle)
    got_typed = minor.input_value()
    if got_typed != expect_minor_typed:
        return {
            "verdict": "FAIL",
            "detail": (
                f"after type {type_value!r} minor={got_typed!r} "
                f"(expected {expect_minor_typed!r}) — input sync broken"
            ),
            "dom_hint": minor_sel,
        }

    display.evaluate("el => el.blur()")
    page.wait_for_timeout(settle)
    got_disp = display.input_value()
    if got_disp != expect_display_blur:
        return {
            "verdict": "FAIL",
            "detail": (
                f"blur display {got_disp!r} != {expect_display_blur!r} — scale normalize broken"
            ),
            "dom_hint": display_sel,
        }

    display.fill("")
    display.evaluate("el => el.blur()")
    page.wait_for_timeout(settle)
    got_clear = minor.input_value()
    if got_clear != "":
        return {
            "verdict": "FAIL",
            "detail": f"empty blur left minor={got_clear!r} (expected clear)",
            "dom_hint": minor_sel,
        }

    return {
        "verdict": "PASS",
        "detail": (
            f"seed {seed_minor}; type {type_value!r}→minor {expect_minor_typed}; "
            f"blur {expect_display_blur!r}; empty clears carrier"
        ),
    }


def _run_confirm_intercept_accept(page: Any, probe: Probe) -> dict[str, Any]:
    """hx-confirm opens designed dialog; accept issues request (MOCK_HTMX toast).

    Mirrors packages/hatchi-maxchi/tests/test_behaviour.py
    test_confirm_dialog_intercepts_hx_confirm for the gallery catalog (cycle 1553).
    """
    params = probe.params
    trigger_sel = str(params.get("trigger", "[hx-delete][hx-confirm]"))
    dialog_sel = str(params.get("dialog", "dialog.alert-dialog, dialog.dz-alert-dialog"))
    message_sel = str(params.get("message", ".alert-dialog__message, .dz-alert-dialog__message"))
    accept_sel = str(params.get("accept", "[data-confirm-accept], [data-dz-confirm-accept]"))
    toast_sel = str(params.get("toast", ".hm-toast, .toast, .dz-toast"))
    settle = int(params.get("settle_ms", 150))

    # Prefer preview-scoped trigger when present; dialog/toast are body-level.
    preview = page.locator(".hm-preview").first
    trigger = None
    for part in trigger_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = page.locator(part).first
        if loc.count() > 0:
            trigger = loc
            break
    if trigger is None and preview.count() > 0:
        trigger = preview.locator("button[hx-delete][hx-confirm], [hx-delete][hx-confirm]").first
    if trigger is None or trigger.count() == 0:
        return {"verdict": "ERROR", "detail": f"confirm trigger not found ({trigger_sel})"}

    question = trigger.get_attribute("hx-confirm") or ""
    if not question.strip():
        return {"verdict": "ERROR", "detail": "hx-confirm attribute empty"}

    trigger.click()
    page.wait_for_timeout(settle)

    dialog = page.locator(dialog_sel).first
    if dialog.count() == 0:
        return {"verdict": "FAIL", "detail": f"designed dialog not found ({dialog_sel})"}
    is_open = dialog.evaluate("el => !!el.open")
    if not is_open:
        return {"verdict": "FAIL", "detail": "designed dialog did not open"}

    msg = dialog.locator(message_sel).first
    if msg.count() == 0:
        msg_text = dialog.inner_text().strip()
    else:
        msg_text = msg.inner_text().strip()
    if question.strip() not in msg_text and msg_text != question.strip():
        return {
            "verdict": "FAIL",
            "detail": f"dialog message {msg_text!r} != hx-confirm {question!r}",
        }

    accept = dialog.locator(accept_sel).first
    if accept.count() == 0:
        accept = page.locator(accept_sel).first
    if accept.count() == 0:
        return {"verdict": "ERROR", "detail": f"accept button not found ({accept_sel})"}
    accept.click()
    page.wait_for_timeout(settle)

    still_open = dialog.evaluate("el => !!el.open") if dialog.count() > 0 else False
    if still_open:
        return {"verdict": "FAIL", "detail": "dialog still open after accept"}

    toast = page.locator(toast_sel).first
    if toast.count() == 0:
        return {
            "verdict": "FAIL",
            "detail": (
                "no MOCK_HTMX toast after accept — issueRequest may have been dropped "
                f"({toast_sel})"
            ),
        }

    return {
        "verdict": "PASS",
        "detail": f"open dialog with {question!r}; accept → toast + closed",
    }


def _run_master_detail_select(page: Any, probe: Probe) -> dict[str, Any]:
    """Click a master-detail list item; assert exclusive aria-current + detail.

    Mirrors packages/hatchi-maxchi/tests/test_behaviour.py::
    test_master_detail_selection_and_instance_isolation (selection half) for the
    autonomous gallery_probes catalog (cycle 1559).
    """
    params = probe.params
    root_sel = params["root"]
    item_sel = params["item"]
    detail_sel = params.get("detail", ".master-detail__detail, .dz-master-detail__detail")
    hx_suffix = str(params.get("activate_hx_suffix", "inv-002"))
    expect_label = str(params.get("expect_label_contains", "Globex"))
    expect_detail = str(params.get("expect_detail_contains", expect_label))
    settle = int(params.get("settle_ms", 200))

    scope = _probe_scope(page, params)
    root = None
    for part in root_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = scope.locator(part).first
        if loc.count() > 0:
            root = loc
            break
    if root is None:
        return {"verdict": "ERROR", "detail": f"master-detail root not found ({root_sel})"}

    # Prefer hx-get suffix match (stable across gallery dialect); fall back to label.
    target = None
    for part in item_sel.split(","):
        part = part.strip()
        if not part:
            continue
        cand = root.locator(f'{part}[hx-get$="{hx_suffix}"]').first
        if cand.count() > 0:
            target = cand
            break
        # some builds use full path without trailing-only match if hx is relative
        cand = root.locator(part).filter(has_text=expect_label).first
        if cand.count() > 0:
            target = cand
            break
    if target is None:
        return {
            "verdict": "ERROR",
            "detail": (f"list item not found (hx-get$={hx_suffix!r} or label≈{expect_label!r})"),
            "dom_hint": item_sel,
        }

    # Snapshot prior current (seed item) so we can prove it cleared.
    current_sel = ", ".join(
        f'{p.strip()}[aria-current="true"]' for p in item_sel.split(",") if p.strip()
    )
    prior = root.locator(current_sel)
    prior_n = prior.count()
    prior_label = _norm_label(prior.first.inner_text()) if prior_n else ""

    target.click()
    page.wait_for_timeout(settle)

    currents = root.locator(current_sel)
    n_cur = currents.count()
    if n_cur != 1:
        return {
            "verdict": "FAIL",
            "detail": (
                f"expected exactly 1 aria-current item after click, got {n_cur} "
                f"(prior={prior_label!r})"
            ),
            "dom_hint": item_sel,
        }
    got_label = _norm_label(currents.first.inner_text())
    if expect_label.lower() not in got_label.lower():
        return {
            "verdict": "FAIL",
            "detail": (
                f"aria-current on {got_label!r}, expected ≈{expect_label!r} (prior={prior_label!r})"
            ),
            "current_label": got_label,
        }

    # Detail pane should hold the MOCK_HTMX card for the selected id.
    detail = None
    for part in detail_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = root.locator(part).first
        if loc.count() > 0:
            detail = loc
            break
        # detail may be sibling outside root if scope was item-only — try page
        loc = scope.locator(part).first
        if loc.count() > 0:
            detail = loc
            break
    if detail is None:
        return {
            "verdict": "FAIL",
            "detail": f"detail pane not found ({detail_sel})",
            "current_label": got_label,
        }
    detail_text = _norm_label(detail.inner_text())
    if expect_detail.lower() not in detail_text.lower():
        return {
            "verdict": "FAIL",
            "detail": (
                f"detail pane missing {expect_detail!r} after select "
                f"(got {detail_text[:120]!r}) — selection ok but MOCK_HTMX/hx-get failed"
            ),
            "current_label": got_label,
            "detail_text": detail_text[:200],
        }

    return {
        "verdict": "PASS",
        "detail": (
            f"current={got_label!r} (was {prior_label!r}); detail contains {expect_detail!r}"
        ),
        "current_label": got_label,
        "prior_label": prior_label,
    }


def _run_pagination_page_load(page: Any, probe: Probe) -> dict[str, Any]:
    """Click a page-N control; assert list body receives MOCK_HTMX rows.

    Gallery pagination demo swaps only the row body (footer chrome stays);
    MOCK_HTMX serves ``/mock/pagination/{n}`` fragments (see hatchi-maxchi.js).
    """
    params = probe.params
    root_sel = params.get(
        "root", "[data-pagination], [data-dz-pagination], .pagination, .dz-pagination"
    )
    page_btn_sel = params.get(
        "page_btn",
        '.pagination-page[hx-get$="/mock/pagination/2"], button.pagination-page:has-text("2")',
    )
    body_sel = params.get("body", "#hm-pag-body, .hm-pag-list")
    expect = str(params.get("expect_body_contains", "Umbrella"))
    settle = int(params.get("settle_ms", 200))

    scope = _probe_scope(page, params)
    root = None
    for part in root_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = scope.locator(part).first
        if loc.count() > 0:
            root = loc
            break
    if root is None:
        return {"verdict": "ERROR", "detail": f"pagination root not found ({root_sel})"}

    btn = None
    for part in page_btn_sel.split(","):
        part = part.strip()
        if not part:
            continue
        # Prefer under root, then whole scope (page numbers live in footer).
        for host in (root, scope):
            cand = host.locator(part).first
            if cand.count() > 0:
                btn = cand
                break
        if btn is not None:
            break
    if btn is None:
        return {
            "verdict": "ERROR",
            "detail": f"page button not found ({page_btn_sel})",
            "dom_hint": page_btn_sel,
        }

    prior_body = None
    for part in body_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = scope.locator(part).first
        if loc.count() > 0:
            prior_body = loc
            break
    prior_text = _norm_label(prior_body.inner_text()) if prior_body is not None else ""

    btn.click()
    page.wait_for_timeout(settle)

    body = None
    for part in body_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = scope.locator(part).first
        if loc.count() > 0:
            body = loc
            break
    if body is None:
        return {
            "verdict": "FAIL",
            "detail": f"list body not found after click ({body_sel})",
        }
    got = _norm_label(body.inner_text())
    if expect.lower() not in got.lower():
        return {
            "verdict": "FAIL",
            "detail": (
                f"body missing {expect!r} after page click "
                f"(prior={prior_text[:80]!r} got={got[:120]!r}) — "
                "MOCK_HTMX / hx-get page exchange failed"
            ),
            "body_text": got[:200],
            "prior_text": prior_text[:200],
        }

    return {
        "verdict": "PASS",
        "detail": f"page click → body contains {expect!r} (was {prior_text[:40]!r}…)",
        "body_snippet": got[:120],
    }


def _run_date_range_change(page: Any, probe: Probe) -> dict[str, Any]:
    """Change From date; assert hx-get lands MOCK_HTMX results in out slot."""
    params = probe.params
    root_sel = params.get(
        "root",
        "[data-date-range], [data-dz-date-range], .date-range-picker, .date-range-bar",
    )
    from_sel = params.get(
        "from_input",
        'input[name="date_from"], input#hm-dr-from',
    )
    out_sel = params.get("out", "#hm-dr-out")
    set_value = str(params.get("set_value", "2026-07-15"))
    expect = str(params.get("expect_out_contains", "result"))
    settle = int(params.get("settle_ms", 250))

    scope = _probe_scope(page, params)
    root = None
    for part in root_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = scope.locator(part).first
        if loc.count() > 0:
            root = loc
            break
    if root is None:
        return {"verdict": "ERROR", "detail": f"date-range root not found ({root_sel})"}

    inp = None
    for part in from_sel.split(","):
        part = part.strip()
        if not part:
            continue
        cand = root.locator(part).first
        if cand.count() > 0:
            inp = cand
            break
    if inp is None:
        return {
            "verdict": "ERROR",
            "detail": f"from input not found ({from_sel})",
            "dom_hint": from_sel,
        }

    # Playwright fill on type=date; then change event for htmx.
    inp.fill(set_value)
    inp.dispatch_event("change")
    page.wait_for_timeout(settle)

    out = None
    for part in out_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = scope.locator(part).first
        if loc.count() > 0:
            out = loc
            break
        loc = root.locator(part).first
        if loc.count() > 0:
            out = loc
            break
    if out is None:
        return {"verdict": "FAIL", "detail": f"out slot not found ({out_sel})"}

    # Unhide may still leave attribute; text content is the exchange signal.
    got = _norm_label(out.inner_text())
    if expect.lower() not in got.lower():
        return {
            "verdict": "FAIL",
            "detail": (
                f"out slot missing {expect!r} after date change "
                f"(got {got[:120]!r}) — MOCK_HTMX / hx-get filter exchange failed"
            ),
            "out_text": got[:200],
            "set_value": set_value,
        }

    return {
        "verdict": "PASS",
        "detail": f"date From={set_value!r} → out contains {expect!r}",
        "out_snippet": got[:120],
    }


def _run_search_box_type_results(page: Any, probe: Probe) -> dict[str, Any]:
    """Type into search-box; assert debounced hx-get lands MOCK_HTMX results.

    Gallery search-box demo: input hx-get=/mock/search with delay:250ms →
    #hm-search-results. MOCK_HTMX returns Aurora/Beacon substation rows.
    Mirrors test_behaviour.test_search_box_coaching_hides_on_type_via_pure_css
    (exchange half) for autonomous catalog (cycle 1576).
    """
    params = probe.params
    root_sel = params.get(
        "root",
        ("[data-search-box], [data-dz-search-box], .search-box-region, .dz-search-box-region"),
    )
    input_sel = params.get(
        "input",
        "input[type=search], input.search-box-input, input.dz-search-box-input",
    )
    results_sel = params.get(
        "results",
        "#hm-search-results, .search-box-results, .dz-search-box-results",
    )
    query = str(params.get("query", "substation"))
    expect = str(params.get("expect_results_contains", "Aurora"))
    debounce = int(params.get("debounce_ms", 400))

    scope = _probe_scope(page, params)
    root = None
    for part in root_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = scope.locator(part).first
        if loc.count() > 0:
            root = loc
            break
    if root is None:
        return {"verdict": "ERROR", "detail": f"search-box root not found ({root_sel})"}

    inp = None
    for part in input_sel.split(","):
        part = part.strip()
        if not part:
            continue
        cand = root.locator(part).first
        if cand.count() > 0:
            inp = cand
            break
    if inp is None:
        return {
            "verdict": "ERROR",
            "detail": f"search input not found ({input_sel})",
            "dom_hint": input_sel,
        }

    results = None
    for part in results_sel.split(","):
        part = part.strip()
        if not part:
            continue
        for host in (root, scope):
            loc = host.locator(part).first
            if loc.count() > 0:
                results = loc
                break
        if results is not None:
            break
    if results is None:
        return {
            "verdict": "ERROR",
            "detail": f"results slot not found ({results_sel})",
            "dom_hint": results_sel,
        }

    prior = _norm_label(results.inner_text())
    # fill triggers input; htmx listens on input changed delay:250ms + search.
    inp.fill(query)
    inp.dispatch_event("input")
    page.wait_for_timeout(debounce)

    got = _norm_label(results.inner_text())
    if expect.lower() not in got.lower():
        return {
            "verdict": "FAIL",
            "detail": (
                f"results missing {expect!r} after query {query!r} "
                f"(prior={prior[:60]!r} got={got[:120]!r}) — "
                "MOCK_HTMX / debounced hx-get FTS exchange failed"
            ),
            "results_text": got[:200],
            "prior_text": prior[:200],
            "query": query,
        }

    return {
        "verdict": "PASS",
        "detail": f"query {query!r} → results contain {expect!r}",
        "results_snippet": got[:120],
    }


def _run_confirm_panel_required_gate(page: Any, probe: Probe) -> dict[str, Any]:
    """Arm confirm-panel primary only when all required boxes are checked.

    Gallery confirm-panel: primary ships aria-disabled with destination in
    data-confirm-href; controller promotes href when required count is met.
    Optional boxes must not arm. Unchecking a required box re-disarms.
    Mirrors test_behaviour.test_confirm_gate_arms_primary_only_when_required_boxes_checked
    (cycle 1582 catalog expand).
    """
    params = probe.params
    root_sel = params.get(
        "root",
        "[data-confirm-gate], [data-dz-confirm-gate], ul.confirm-checklist",
    )
    primary_sel = params.get("primary", ".confirm-primary, a.confirm-primary")
    required_sel = params.get(
        "required_input",
        "input[data-required='true'], input[data-dz-required='true']",
    )
    optional_sel = params.get(
        "optional_input",
        "li[data-required='false'] input[type=checkbox]",
    )
    expect_href = str(params.get("expect_href", "#go-live"))

    scope = _probe_scope(page, params)
    root = None
    for part in root_sel.split(","):
        part = part.strip()
        if not part:
            continue
        loc = scope.locator(part).first
        if loc.count() > 0:
            root = loc
            break
    if root is None:
        return {"verdict": "ERROR", "detail": f"confirm-gate root not found ({root_sel})"}

    primary = None
    for part in primary_sel.split(","):
        part = part.strip()
        if not part:
            continue
        cand = root.locator(part).first
        if cand.count() > 0:
            primary = cand
            break
    if primary is None:
        return {
            "verdict": "ERROR",
            "detail": f"confirm primary not found ({primary_sel})",
            "dom_hint": primary_sel,
        }

    def _armed() -> tuple[bool, str | None]:
        disabled = primary.get_attribute("aria-disabled")
        href = primary.get_attribute("href")
        # Armed when aria-disabled is absent/false and href is the parked destination.
        is_disabled = disabled in ("true", "True", "")
        if disabled is None:
            is_disabled = False
        return (not is_disabled and href == expect_href), href

    # Initial: disarmed
    armed0, href0 = _armed()
    if armed0 or primary.get_attribute("aria-disabled") != "true":
        return {
            "verdict": "FAIL",
            "detail": (
                f"primary should start disarmed (aria-disabled=true, no href); "
                f"got aria-disabled={primary.get_attribute('aria-disabled')!r} href={href0!r}"
            ),
        }

    # Optional alone must not arm
    opt = None
    for part in optional_sel.split(","):
        part = part.strip()
        if not part:
            continue
        cand = root.locator(part).first
        if cand.count() > 0:
            opt = cand
            break
    if opt is not None:
        opt.check()
        page.wait_for_timeout(50)
        armed_opt, href_opt = _armed()
        if armed_opt:
            return {
                "verdict": "FAIL",
                "detail": (
                    f"optional box alone armed primary (href={href_opt!r}) — "
                    "only data-required=true boxes may gate"
                ),
            }

    required = root.locator(required_sel)
    n_req = required.count()
    if n_req < 2:
        return {
            "verdict": "ERROR",
            "detail": f"expected ≥2 required inputs, found {n_req} ({required_sel})",
        }

    # One of two still disarmed
    required.nth(0).check()
    page.wait_for_timeout(50)
    armed1, href1 = _armed()
    if armed1:
        return {
            "verdict": "FAIL",
            "detail": (
                f"one of {n_req} required boxes armed primary (href={href1!r}) — "
                "gate must wait for full required count"
            ),
        }

    # All required → armed
    for i in range(1, n_req):
        required.nth(i).check()
    page.wait_for_timeout(80)
    armed_all, href_all = _armed()
    if not armed_all:
        return {
            "verdict": "FAIL",
            "detail": (
                f"all {n_req} required checked but primary not armed "
                f"(aria-disabled={primary.get_attribute('aria-disabled')!r} "
                f"href={href_all!r} expect={expect_href!r})"
            ),
        }

    # Uncheck first required → re-disarm
    required.nth(0).uncheck()
    page.wait_for_timeout(80)
    armed_back, href_back = _armed()
    if armed_back or primary.get_attribute("aria-disabled") != "true":
        return {
            "verdict": "FAIL",
            "detail": (
                f"unchecking a required box did not re-disarm "
                f"(aria-disabled={primary.get_attribute('aria-disabled')!r} href={href_back!r})"
            ),
        }

    return {
        "verdict": "PASS",
        "detail": (
            f"optional alone disarmed; {n_req}/{n_req} required → href={expect_href!r}; "
            "uncheck re-disarms"
        ),
        "required_count": n_req,
        "href": href_all,
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
    "checkbox_toggle": _run_checkbox_toggle,
    "range_value_readout": _run_range_value_readout,
    "aria_pressed_toggle": _run_aria_pressed_toggle,
    "radio_group_select": _run_radio_group_select,
    "carousel_advance": _run_carousel_advance,
    "combobox_select": _run_combobox_select,
    "wizard_step_forward": _run_wizard_step_forward,
    "toast_dismiss_and_fire": _run_toast_dismiss_and_fire,
    "tags_seed_add_remove": _run_tags_seed_add_remove,
    "search_select_typeahead_select": _run_search_select_typeahead_select,
    "money_sync_minor_blur": _run_money_sync_minor_blur,
    "app_shell_sidebar_toggle": _run_app_shell_sidebar_toggle,
    "confirm_intercept_accept": _run_confirm_intercept_accept,
    "master_detail_select": _run_master_detail_select,
    "pagination_page_load": _run_pagination_page_load,
    "date_range_change": _run_date_range_change,
    "search_box_type_results": _run_search_box_type_results,
    "confirm_panel_required_gate": _run_confirm_panel_required_gate,
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
