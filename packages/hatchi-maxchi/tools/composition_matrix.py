#!/usr/bin/env python3
"""Host × guest composition matrix — structural coherence for L2 shells.

When an L2 overlay host (drawer / dialog) nests L1 Hyperparts, two failure
modes show up as *visual incongruity* even when each guest is “correct” alone:

1. **Chrome asymmetry** — form_shell vs exchange_shell differ in form scope
   but must keep the same header/body/footer BEM flex children.
2. **Guest fork** — almost-DOM (input.switch, legend-in-toggle-group,
   form-field-as-meta) that looks “close enough” until compared to the
   standalone gallery partial.

This tool is the machine half of that check:

- Catalog of host chrome shells + minimal honest guest fragments
- Compatibility matrix (compatible | incompatible with reason)
- ``assemble(host, guest)`` → HTML
- ``validate_cell`` / ``validate_all`` → structural claims (no browser)
- ``--write-catalog`` → ``COMPOSITION_MATRIX.md``

Gallery demos and ``stems/host-chrome-symmetry.md`` are expressions of the
same doctrine. Run::

    python packages/hatchi-maxchi/tools/composition_matrix.py --list
    python packages/hatchi-maxchi/tools/composition_matrix.py --validate
    python packages/hatchi-maxchi/tools/composition_matrix.py --validate --json
    python packages/hatchi-maxchi/tools/composition_matrix.py --write-catalog

Exit: 0 all PASS/SKIP; 1 any FAIL.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PKG = Path(__file__).resolve().parents[1]
SCHEMA = "hm.composition_matrix.v1"
CATALOG_MD = PKG / "COMPOSITION_MATRIX.md"

# ── Host chrome shells ───────────────────────────────────────────────────
# Placeholders: {title_id} {title} {body_id} {body} {close_label}


@dataclass(frozen=True)
class HostShell:
    """Overlay host chrome shape (drawer/dialog form vs exchange)."""

    id: str
    host: str  # drawer | dialog
    kind: str  # form_shell | exchange_shell
    template: str
    notes: str = ""


# form_shell: one method=dialog wrap — body must not introduce nested forms.
_DRAWER_FORM = (
    '<dialog class="dz-drawer" id="hm-matrix-drawer" data-dz-side="right" '
    'data-dz-width="md" aria-labelledby="{title_id}" closedby="any">'
    '<form method="dialog">'
    '<div class="dz-drawer__header">'
    '<h2 class="dz-drawer__title" id="{title_id}">{title}</h2>'
    '<button type="submit" class="dz-drawer__close" aria-label="{close_label}">×</button>'
    "</div>"
    '<div class="dz-drawer__body" id="{body_id}" tabindex="0">{body}</div>'
    '<div class="dz-drawer__footer">'
    '<button type="submit" class="dz-button" data-dz-variant="ghost">Cancel</button>'
    '<button type="submit" class="dz-button" data-dz-variant="primary">Apply</button>'
    "</div></form></dialog>"
)

# exchange_shell: body is an HTMX target; close forms are scoped only.
_DRAWER_EXCHANGE = (
    '<dialog class="dz-drawer" id="hm-matrix-drawer-x" data-dz-side="right" '
    'data-dz-width="md" aria-labelledby="{title_id}" closedby="any">'
    '<div class="dz-drawer__header">'
    '<h2 class="dz-drawer__title" id="{title_id}">{title}</h2>'
    '<form method="dialog">'
    '<button type="submit" class="dz-drawer__close" aria-label="{close_label}">×</button>'
    "</form></div>"
    '<div class="dz-drawer__body" id="{body_id}" tabindex="0" aria-live="polite">{body}</div>'
    '<div class="dz-drawer__footer">'
    '<form method="dialog">'
    '<button type="submit" class="dz-button" data-dz-variant="ghost">Close</button>'
    "</form>"
    '<a class="dz-button" data-dz-variant="primary" href="#full">Open full page</a>'
    "</div></dialog>"
)

_DIALOG_FORM = (
    '<dialog class="dz-dialog" id="hm-matrix-dialog" aria-labelledby="{title_id}" closedby="any">'
    '<form method="dialog">'
    '<div class="dz-dialog__header">'
    '<h2 class="dz-dialog__title" id="{title_id}">{title}</h2>'
    '<button type="submit" class="dz-dialog__close" aria-label="{close_label}">×</button>'
    "</div>"
    '<div class="dz-dialog__body" id="{body_id}">{body}</div>'
    '<div class="dz-dialog__footer">'
    '<button type="submit" class="dz-button" data-dz-variant="outline">Cancel</button>'
    '<button type="submit" class="dz-button" data-dz-variant="primary">Confirm</button>'
    "</div></form></dialog>"
)

_DIALOG_EXCHANGE = (
    '<dialog class="dz-dialog" id="hm-matrix-dialog-x" aria-labelledby="{title_id}" closedby="any">'
    '<div class="dz-dialog__header">'
    '<h2 class="dz-dialog__title" id="{title_id}">{title}</h2>'
    '<form method="dialog">'
    '<button type="submit" class="dz-dialog__close" aria-label="{close_label}">×</button>'
    "</form></div>"
    '<div class="dz-dialog__body" id="{body_id}" aria-live="polite">{body}</div>'
    '<div class="dz-dialog__footer">'
    '<form method="dialog">'
    '<button type="submit" class="dz-button" data-dz-variant="outline">Close</button>'
    "</form>"
    '<button type="button" class="dz-button" data-dz-variant="primary">Continue</button>'
    "</div></dialog>"
)

HOSTS: dict[str, HostShell] = {
    "drawer.form_shell": HostShell(
        id="drawer.form_shell",
        host="drawer",
        kind="form_shell",
        template=_DRAWER_FORM,
        notes="One method=dialog wraps chrome when body has no nested forms.",
    ),
    "drawer.exchange_shell": HostShell(
        id="drawer.exchange_shell",
        host="drawer",
        kind="exchange_shell",
        template=_DRAWER_EXCHANGE,
        notes="Scoped close forms; body is exchange target (may receive forms).",
    ),
    "dialog.form_shell": HostShell(
        id="dialog.form_shell",
        host="dialog",
        kind="form_shell",
        template=_DIALOG_FORM,
        notes="Dialog form_shell — same chrome parts as gallery dialog demo.",
    ),
    "dialog.exchange_shell": HostShell(
        id="dialog.exchange_shell",
        host="dialog",
        kind="exchange_shell",
        template=_DIALOG_EXCHANGE,
        notes="Dialog exchange_shell — HTMX body with scoped close forms.",
    ),
}


# ── Guest fragments (minimal honest DOM) ─────────────────────────────────


@dataclass(frozen=True)
class Guest:
    id: str
    fragment: str
    # Structural claims on the *assembled* HTML (host + guest).
    require_substrings: tuple[str, ...] = ()
    forbid_substrings: tuple[str, ...] = ()
    # Extra validators (assembled html) → error message or None
    checks: tuple[str, ...] = ()  # names into CHECKS registry
    # CSS selector of the guest root (gallery-unprefixed OK for Playwright)
    root_selector: str = ""
    notes: str = ""


GUESTS: dict[str, Guest] = {
    "field": Guest(
        id="field",
        fragment=(
            '<div class="dz-form-field">'
            '<label class="dz-form-label" for="mx-q">Search</label>'
            '<input class="dz-form-input" id="mx-q" type="search" name="q" '
            'aria-describedby="mx-q-hint">'
            '<p class="dz-form-hint" id="mx-q-hint">Help text.</p></div>'
        ),
        require_substrings=(
            'class="dz-form-field"',
            'class="dz-form-label"',
            'class="dz-form-input"',
            'class="dz-form-hint"',
        ),
        checks=("field_has_control",),
        root_selector=".dz-form-field, .form-field",
        notes="label + control + hint triad",
    ),
    "switch": Guest(
        id="switch",
        fragment=(
            '<label class="dz-switch">'
            '<input type="checkbox" name="mx-sw" data-dz-switch>'
            '<span class="dz-switch__track" aria-hidden="true"></span>'
            "<span>Notify me</span></label>"
        ),
        require_substrings=(
            'class="dz-switch"',
            "data-dz-switch",
            'class="dz-switch__track"',
        ),
        checks=("switch_uses_track_anatomy",),
        root_selector=".dz-switch, .switch",
        notes="label.switch + track — not controls pill",
    ),
    "controls": Guest(
        id="controls",
        fragment=(
            '<label class="hm-inline"><input type="checkbox" class="dz-checkbox" checked> '
            "Checkbox</label>"
            '<label class="hm-inline"><input type="radio" class="dz-radio" checked> Radio</label>'
        ),
        require_substrings=('class="dz-checkbox"', 'class="dz-radio"'),
        root_selector=".dz-checkbox, .checkbox",
        notes="native designed checkbox/radio",
    ),
    "toggle-group": Guest(
        id="toggle-group",
        fragment=(
            '<div class="dz-stack" data-dz-gap="xs">'
            '<div class="dz-form-label" id="mx-tg-label">View</div>'
            '<fieldset class="dz-toggle-group" role="radiogroup" '
            'aria-labelledby="mx-tg-label">'
            '<label><input type="radio" name="mx-view" checked><span>List</span></label>'
            '<label><input type="radio" name="mx-view"><span>Board</span></label>'
            "</fieldset></div>"
        ),
        require_substrings=('class="dz-toggle-group"', "<span>List</span>"),
        checks=("toggle_group_no_inner_legend",),
        root_selector=".dz-toggle-group, .toggle-group",
        notes="label outside fieldset",
    ),
    "badge": Guest(
        id="badge",
        fragment=(
            '<span class="dz-badge" data-dz-tone="success">'
            '<span class="dz-badge-icon"></span>Online</span>'
        ),
        require_substrings=('class="dz-badge"', "data-dz-tone"),
        root_selector=".dz-badge, .badge",
    ),
    "card": Guest(
        id="card",
        fragment=(
            '<div class="dz-auto-grid" style="--dz-grid-min:7rem">'
            '<div class="dz-card dz-card-body">'
            '<div class="dz-card-label">Region</div>'
            '<div class="dz-card-value">North</div></div>'
            '<div class="dz-card dz-card-body">'
            '<div class="dz-card-label">Load</div>'
            '<div class="dz-card-value">82%</div></div>'
            "</div>"
        ),
        require_substrings=(
            'class="dz-card dz-card-body"',
            'class="dz-card-label"',
            'class="dz-card-value"',
        ),
        forbid_substrings=('card-value" style="font-size',),
        checks=("card_not_overridden_value",),
        root_selector=".dz-card, .card",
        notes="one KPI card per metric",
    ),
    "alert": Guest(
        id="alert",
        fragment=(
            '<div class="dz-alert" data-dz-tone="warning" role="alert">'
            '<span class="dz-alert__icon"></span>'
            '<div class="dz-alert__body">'
            '<div class="dz-alert__title">Notice</div>'
            '<div class="dz-alert__description">Detail.</div></div></div>'
        ),
        require_substrings=('class="dz-alert"', 'role="alert"'),
        root_selector=".dz-alert, .alert",
    ),
    "button": Guest(
        id="button",
        fragment=(
            '<div class="hm-demo-row">'
            '<button type="button" class="dz-button" data-dz-variant="primary">Save</button>'
            '<button type="button" class="dz-button" data-dz-variant="outline">Cancel</button>'
            "</div>"
        ),
        require_substrings=('class="dz-button"', "data-dz-variant"),
        root_selector=".dz-button, .button",
    ),
    "menu": Guest(
        id="menu",
        fragment=(
            '<details class="dz-menu">'
            '<summary class="dz-button" data-dz-variant="outline">Actions</summary>'
            '<div class="dz-menu__panel">'
            '<button type="button" class="dz-menu__item">Edit</button>'
            '<button type="button" class="dz-menu__item">Duplicate</button>'
            '<hr class="dz-menu__separator">'
            '<button type="button" class="dz-menu__item" data-dz-tone="destructive">'
            "Delete</button>"
            "</div></details>"
        ),
        require_substrings=(
            'class="dz-menu"',
            'class="dz-menu__panel"',
            'class="dz-menu__item"',
        ),
        root_selector=".dz-menu, .menu",
        notes="details menu — opens inside body; light-dismiss is guest concern",
    ),
    "tabs": Guest(
        id="tabs",
        fragment=(
            '<div class="dz-tabs" data-dz-tabs>'
            '<div class="dz-tabs__list" role="tablist">'
            '<button type="button" class="dz-tabs__tab" aria-current="true" '
            'data-dz-tab-target="mx-tab-a">Overview</button>'
            '<button type="button" class="dz-tabs__tab" '
            'data-dz-tab-target="mx-tab-b">Activity</button>'
            "</div>"
            '<div id="mx-tab-a" class="dz-tabs__panel" role="tabpanel">'
            "Overview panel.</div>"
            '<div id="mx-tab-b" class="dz-tabs__panel" role="tabpanel" hidden>'
            "Activity panel.</div>"
            "</div>"
        ),
        require_substrings=(
            'class="dz-tabs"',
            'class="dz-tabs__tab"',
            'class="dz-tabs__panel"',
            "data-dz-tabs",
        ),
        root_selector=".dz-tabs, .tabs",
        notes="selection-strip honest: buttons + panels",
    ),
    "separator": Guest(
        id="separator",
        fragment=(
            '<p class="hm-demo-muted">Section A</p>'
            '<hr class="dz-separator">'
            '<p class="hm-demo-muted">Section B</p>'
        ),
        require_substrings=('class="dz-separator"',),
        root_selector=".dz-separator, .separator",
    ),
    "empty-state": Guest(
        id="empty-state",
        fragment=(
            '<div class="dz-empty-state" data-dz-empty-state>'
            '<span class="dz-empty-state__icon" aria-hidden="true"></span>'
            '<h3 class="dz-empty-state__title">No results</h3>'
            '<p class="dz-empty-state__description">Adjust filters and try again.</p>'
            '<div class="dz-empty-state__action">'
            '<button type="button" class="dz-button" data-dz-variant="primary">'
            "Clear filters</button>"
            "</div></div>"
        ),
        require_substrings=(
            'class="dz-empty-state"',
            'class="dz-empty-state__title"',
        ),
        root_selector=".dz-empty-state, .empty-state",
    ),
    "popover": Guest(
        id="popover",
        fragment=(
            '<details class="dz-popover">'
            '<summary class="dz-button" data-dz-variant="outline">Details</summary>'
            '<div class="dz-popover__panel">'
            '<div class="hm-demo-title">Dimensions</div>'
            '<p class="hm-demo-muted">Filters, previews, quick forms.</p>'
            "</div></details>"
        ),
        require_substrings=(
            'class="dz-popover"',
            'class="dz-popover__panel"',
        ),
        root_selector=".dz-popover, .popover",
    ),
    "kbd": Guest(
        id="kbd",
        fragment=(
            '<div class="hm-demo-row">'
            '<kbd class="dz-kbd">⌘K</kbd>'
            '<kbd class="dz-kbd">Esc</kbd>'
            "</div>"
        ),
        require_substrings=('class="dz-kbd"',),
        root_selector=".dz-kbd, .kbd",
    ),
    "skeleton": Guest(
        id="skeleton",
        fragment=(
            '<div class="dz-stack" data-dz-gap="sm" aria-hidden="true" data-dz-skeleton>'
            '<div class="dz-skeleton" data-dz-shape="text"></div>'
            '<div class="dz-skeleton" data-dz-shape="block"></div>'
            "</div>"
        ),
        require_substrings=('class="dz-skeleton"', "data-dz-shape"),
        root_selector=".dz-skeleton, .skeleton",
    ),
    # ── Refusal probes (document why NOT to compose) ────────────────────
    "nested-form": Guest(
        id="nested-form",
        fragment=(
            '<form action="/save" method="post">'
            '<div class="dz-form-field">'
            '<label class="dz-form-label" for="mx-n">Name</label>'
            '<input class="dz-form-input" id="mx-n" name="name">'
            "</div>"
            '<button type="submit" class="dz-button" data-dz-variant="primary">Save</button>'
            "</form>"
        ),
        require_substrings=("<form", 'class="dz-form-input"'),
        root_selector="form",
        notes="body-local form — only exchange_shell (no nested form in form_shell)",
    ),
    "nested-dialog": Guest(
        id="nested-dialog",
        fragment=(
            '<dialog class="dz-dialog" id="mx-nested">'
            '<div class="dz-dialog__body">Nested modal</div></dialog>'
        ),
        require_substrings=('class="dz-dialog"',),
        root_selector="dialog.dz-dialog, dialog.dialog",
        notes="refusal probe — never nest overlay chrome in a host body",
    ),
    "command": Guest(
        id="command",
        fragment=(
            '<dialog class="dz-command" id="mx-cmd">'
            '<input class="dz-command__input" type="search" placeholder="Jump to…">'
            "</dialog>"
        ),
        require_substrings=('class="dz-command"',),
        root_selector=".dz-command, .command",
        notes="refusal probe — command palette is its own L1 overlay, not a guest",
    ),
}


# Explicit incompatibilities: (host_id, guest_id) → reason.
# Anything not listed is compatible unless auto-rules fire.
INCOMPATIBLE: dict[tuple[str, str], str] = {}

# Nested overlays — never guests of another overlay shell
for _h in HOSTS:
    INCOMPATIBLE[(_h, "nested-dialog")] = (
        "do not nest dialog chrome inside another overlay body — open a sibling dialog"
    )
    INCOMPATIBLE[(_h, "command")] = (
        "command palette is its own L1 overlay (addressing + focus trap); not a body guest"
    )

# form_shell cannot wrap a body that introduces <form>
for _h, host in HOSTS.items():
    if host.kind == "form_shell":
        INCOMPATIBLE[(_h, "nested-form")] = (
            "form_shell already wraps method=dialog — nested <form> is invalid HTML; "
            "use exchange_shell"
        )


def cell_policy(host_id: str, guest_id: str) -> tuple[bool, str]:
    """Return (compatible, reason). Reason set when incompatible."""
    if (host_id, guest_id) in INCOMPATIBLE:
        return False, INCOMPATIBLE[(host_id, guest_id)]
    # Auto: form_shell + any guest fragment containing <form
    host = HOSTS.get(host_id)
    guest = GUESTS.get(guest_id)
    if host and guest and host.kind == "form_shell":
        if re.search(r"<form\b", guest.fragment, re.I):
            return (
                False,
                "form_shell incompatible with guest that contains <form> (use exchange_shell)",
            )
    return True, ""


# Back-compat name used by tests
def _compat_map() -> dict[tuple[str, str], bool]:
    return {(h, g): cell_policy(h, g)[0] for h in HOSTS for g in GUESTS}


COMPAT: dict[tuple[str, str], bool] = {}  # filled at module load end


# ── Checks ───────────────────────────────────────────────────────────────


def _check_field_has_control(html: str) -> str | None:
    if "dz-form-input" not in html and "dz-form-field" in html:
        return "form-field without a control (do not use field as read-only meta)"
    if re.search(
        r'class="dz-form-field"[^>]*>\s*'
        r'(?:<span class="dz-form-label"|<label class="dz-form-label")[^>]*>.*?'
        r'class="dz-form-hint"',
        html,
        re.S,
    ) and not re.search(r'class="dz-form-input"', html):
        return "form-field with label+hint only — use card-label/value for meta"
    return None


def _check_switch_track(html: str) -> str | None:
    if re.search(r'<input[^>]*class="[^"]*\bdz-switch\b', html):
        return "input.dz-switch is the controls pill — use label.dz-switch + track"
    if "data-dz-switch" in html and "dz-switch__track" not in html:
        return "switch missing dz-switch__track"
    return None


def _check_toggle_no_legend(html: str) -> str | None:
    m = re.search(
        r'<fieldset[^>]*class="[^"]*\bdz-toggle-group\b[^"]*"[^>]*>(.*?)</fieldset>',
        html,
        re.S,
    )
    if m and re.search(r"<legend\b", m.group(1), re.I):
        return "legend inside dz-toggle-group — label outside + aria-labelledby"
    return None


def _check_card_value(html: str) -> str | None:
    if re.search(r'class="dz-card-value"[^>]*style="[^"]*font-size', html):
        return "card-value font-size override — use honest KPI scale or a different part"
    return None


CHECKS: dict[str, Callable[[str], str | None]] = {
    "field_has_control": _check_field_has_control,
    "switch_uses_track_anatomy": _check_switch_track,
    "toggle_group_no_inner_legend": _check_toggle_no_legend,
    "card_not_overridden_value": _check_card_value,
}


# ── Host chrome structural rules (on every assembled cell) ───────────────


def _host_chrome_errors(host: HostShell, html: str) -> list[str]:
    errs: list[str] = []
    prefix = f"dz-{host.host}__"
    for part in ("header", "body", "footer"):
        cls = f"{prefix}{part}"
        if cls not in html:
            errs.append(f"missing chrome part class {cls}")
    if host.kind == "form_shell":
        if 'method="dialog"' not in html:
            errs.append("form_shell requires method=dialog")
        n = len(re.findall(r'method="dialog"', html))
        if n != 1:
            errs.append(f"form_shell expects exactly 1 method=dialog form, found {n}")
    if host.kind == "exchange_shell":
        n = len(re.findall(r'method="dialog"', html))
        if n < 1:
            errs.append("exchange_shell needs scoped method=dialog close form(s)")
        if not re.search(
            rf'class="[^"]*{re.escape(prefix)}header[^"]*"[\s\S]*?method="dialog"',
            html,
        ):
            errs.append("exchange_shell: close form should sit in the header")
    return errs


def assemble(
    host_id: str,
    guest_id: str,
    *,
    title: str = "Matrix",
    body_id: str = "hm-matrix-body",
) -> str:
    host = HOSTS[host_id]
    guest = GUESTS[guest_id]
    return host.template.format(
        title_id=f"{body_id}-title",
        title=title,
        body_id=body_id,
        body=guest.fragment,
        close_label="Close",
    )


# Cells exercised under Playwright for layout coherence (subset keeps CI fast).
PLAYWRIGHT_CELLS: tuple[tuple[str, str], ...] = (
    ("drawer.form_shell", "field"),
    ("drawer.form_shell", "switch"),
    ("drawer.form_shell", "toggle-group"),
    ("drawer.form_shell", "card"),
    ("drawer.form_shell", "tabs"),
    ("drawer.form_shell", "menu"),
    ("drawer.exchange_shell", "nested-form"),
    ("drawer.exchange_shell", "empty-state"),
    ("dialog.form_shell", "alert"),
    ("dialog.exchange_shell", "button"),
)


@dataclass
class CellResult:
    host_id: str
    guest_id: str
    status: str  # PASS | FAIL | SKIP
    errors: list[str] = field(default_factory=list)
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "host": self.host_id,
            "guest": self.guest_id,
            "status": self.status,
            "errors": self.errors,
            "notes": self.notes,
        }


def validate_cell(host_id: str, guest_id: str) -> CellResult:
    if host_id not in HOSTS or guest_id not in GUESTS:
        return CellResult(host_id, guest_id, "FAIL", ["unknown host or guest"])

    ok, reason = cell_policy(host_id, guest_id)
    if not ok:
        return CellResult(
            host_id,
            guest_id,
            "SKIP",
            notes=reason or "incompatible",
        )

    host = HOSTS[host_id]
    guest = GUESTS[guest_id]
    html = assemble(host_id, guest_id)
    errors: list[str] = []
    errors.extend(_host_chrome_errors(host, html))

    for s in guest.require_substrings:
        if s not in html:
            errors.append(f"missing required substring: {s!r}")
    for s in guest.forbid_substrings:
        if s and s in html:
            errors.append(f"forbidden substring present: {s!r}")
    for name in guest.checks:
        fn = CHECKS.get(name)
        if not fn:
            errors.append(f"unknown check {name}")
            continue
        msg = fn(html)
        if msg:
            errors.append(msg)

    # Belt-and-braces: form_shell must not assemble nested forms
    if host.kind == "form_shell":
        body_forms = len(re.findall(r"<form\b", guest.fragment, re.I))
        if body_forms:
            errors.append(
                "form_shell incompatible with guest that contains <form> (use exchange_shell)"
            )

    status = "FAIL" if errors else "PASS"
    return CellResult(host_id, guest_id, status, errors)


def validate_all() -> list[CellResult]:
    return [validate_cell(h, g) for h in HOSTS for g in GUESTS]


def validate_gallery_drawer_source() -> list[str]:
    """Extra: pin the live drawer partial + mock against host/guest claims."""
    errors: list[str] = []
    reg = (PKG / "site" / "registry.py").read_text(encoding="utf-8")
    m = re.search(
        r'Hyperpart\(\s*"drawer"[\s\S]*?(?=\n\s*Hyperpart\()',
        reg,
    )
    if not m:
        return ["could not locate drawer Hyperpart in registry.py"]
    partial_src = m.group(0)

    if 'id="hm-drawer-demo"' not in partial_src:
        errors.append("filters drawer (form_shell demo) missing")
    if 'id="hm-drawer-lazy"' not in partial_src:
        errors.append("lazy drawer (exchange_shell demo) missing")

    if re.search(r'<input[^>]*class="[^"]*\bdz-switch\b', partial_src):
        errors.append("drawer filters still use input.dz-switch (controls pill)")
    if "data-dz-switch" not in partial_src or "dz-switch__track" not in partial_src:
        errors.append("drawer filters missing switch Hyperpart track anatomy")

    tg = re.search(
        r'<fieldset class="dz-toggle-group"[\s\S]*?</fieldset>',
        partial_src,
    )
    if tg and re.search(r"<legend\b", tg.group(0), re.I):
        errors.append("toggle-group still has legend inside fieldset")

    if re.search(r'<header class="dz-drawer__header"', partial_src):
        errors.append("prefer div.dz-drawer__header for shell symmetry (header element optional)")

    mock_src = (PKG / "site" / "build_site.py").read_text(encoding="utf-8")
    md = re.search(
        r'"/mock/drawer/detail"\s*:\s*([\s\S]*?)(?=\n\s*"/mock/)',
        mock_src,
    )
    if not md:
        errors.append("could not locate /mock/drawer/detail")
    else:
        frag = md.group(1)
        if "dz-form-field" in frag and "dz-form-input" not in frag:
            errors.append("mock uses form-field without control (read-only meta fork)")
        if re.search(r'card-value"[^>]*style="[^"]*font-size', frag):
            if frag.count("font-size:var(--text-base)") >= 1:
                errors.append("mock overrides card-value to text-base (KPI scale fork)")
        if "dz-card" not in frag:
            errors.append("mock missing card guests")
        if 'role="alert"' not in frag:
            errors.append("mock alert should use role=alert (match Alert hyperpart)")

    return errors


def write_catalog(path: Path = CATALOG_MD) -> Path:
    """Write human/agent catalog of the matrix (like GALLERY_PROBES.md)."""
    lines = [
        "# HM composition matrix",
        "",
        "Auto-generated by `tools/composition_matrix.py --write-catalog`.",
        "Do not hand-edit — update `HOSTS` / `GUESTS` / `INCOMPATIBLE` in the tool.",
        "",
        "Stem: [`stems/host-chrome-symmetry.md`](stems/host-chrome-symmetry.md)",
        "",
        "Run:",
        "",
        "```bash",
        "python packages/hatchi-maxchi/tools/composition_matrix.py --validate",
        "python packages/hatchi-maxchi/tools/composition_matrix.py --list",
        "```",
        "",
        "## Hosts (chrome shells)",
        "",
        "| id | host | kind | notes |",
        "|----|------|------|-------|",
    ]
    for h in HOSTS.values():
        notes = h.notes.replace("|", "\\|")
        lines.append(f"| `{h.id}` | {h.host} | {h.kind} | {notes} |")

    lines += [
        "",
        "## Guests",
        "",
        "| id | notes |",
        "|----|-------|",
    ]
    for g in GUESTS.values():
        notes = (g.notes or "—").replace("|", "\\|")
        lines.append(f"| `{g.id}` | {notes} |")

    lines += [
        "",
        "## Incompatible cells (declared refusals)",
        "",
        "| host | guest | reason |",
        "|------|-------|--------|",
    ]
    for (h, g), reason in sorted(INCOMPATIBLE.items()):
        lines.append(f"| `{h}` | `{g}` | {reason.replace('|', '\\|')} |")

    # Summary grid (compact)
    lines += [
        "",
        "## Compatibility grid",
        "",
        "Legend: `Y` compatible (structural validate) · `N` incompatible (reason above)",
        "",
    ]
    guests = list(GUESTS)
    # header row — short guest ids
    header = "| host \\ guest | " + " | ".join(f"`{g}`" for g in guests) + " |"
    sep = "|---|" + "|".join(["---"] * len(guests)) + "|"
    lines.append(header)
    lines.append(sep)
    for h in HOSTS:
        cells = []
        for g in guests:
            ok, _ = cell_policy(h, g)
            cells.append("Y" if ok else "N")
        lines.append(f"| `{h}` | " + " | ".join(cells) + " |")

    lines += [
        "",
        "## Playwright coherence subset",
        "",
        "Browser layout checks (non-zero box, primary body colour) run for:",
        "",
    ]
    for h, g in PLAYWRIGHT_CELLS:
        lines.append(f"- `{h}` × `{g}`")
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--list", action="store_true", help="list hosts, guests, cells")
    p.add_argument("--validate", action="store_true", help="run matrix + gallery pins")
    p.add_argument("--json", action="store_true", help="JSON report on stdout")
    p.add_argument("--assemble", nargs=2, metavar=("HOST", "GUEST"), help="print HTML")
    p.add_argument(
        "--write-catalog",
        action="store_true",
        help=f"write {CATALOG_MD.name}",
    )
    p.add_argument(
        "--incompatible",
        action="store_true",
        help="list only incompatible cells with reasons",
    )
    args = p.parse_args(argv)

    if args.write_catalog:
        out = write_catalog()
        print(f"wrote {out}")
        return 0

    if args.assemble:
        print(assemble(args.assemble[0], args.assemble[1]))
        return 0

    if args.incompatible:
        for (h, g), reason in sorted(INCOMPATIBLE.items()):
            print(f"N  {h} × {g}\n   {reason}")
        # also show auto form-shell rules via cell_policy
        for h in HOSTS:
            for g in GUESTS:
                if (h, g) in INCOMPATIBLE:
                    continue
                ok, reason = cell_policy(h, g)
                if not ok:
                    print(f"N  {h} × {g}\n   {reason}")
        return 0

    if args.list:
        print("Hosts:")
        for h in HOSTS.values():
            print(f"  {h.id:28} {h.kind:16} {h.notes}")
        print("Guests:")
        for g in GUESTS.values():
            note = f" — {g.notes}" if g.notes else ""
            print(f"  {g.id}{note}")
        n_ok = sum(1 for h in HOSTS for g in GUESTS if cell_policy(h, g)[0])
        n_no = len(HOSTS) * len(GUESTS) - n_ok
        print(f"Cells: {len(HOSTS) * len(GUESTS)} ({n_ok} compatible, {n_no} incompatible)")
        return 0

    if not args.validate and not args.json:
        p.print_help()
        return 2

    cells = validate_all()
    gallery_errs = validate_gallery_drawer_source()
    fails = [c for c in cells if c.status == "FAIL"]
    report = {
        "schema": SCHEMA,
        "cells": [c.as_dict() for c in cells],
        "incompatible": [
            {"host": h, "guest": g, "reason": r} for (h, g), r in sorted(INCOMPATIBLE.items())
        ],
        "gallery_drawer_pins": gallery_errs,
        "playwright_cells": [list(c) for c in PLAYWRIGHT_CELLS],
        "summary": {
            "pass": sum(1 for c in cells if c.status == "PASS"),
            "fail": len(fails),
            "skip": sum(1 for c in cells if c.status == "SKIP"),
            "gallery_pin_errors": len(gallery_errs),
        },
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for c in cells:
            if c.status == "SKIP":
                print(f"SKIP  {c.host_id} × {c.guest_id}  — {c.notes}")
            else:
                extra = f"  {'; '.join(c.errors)}" if c.errors else ""
                print(f"{c.status:4}  {c.host_id} × {c.guest_id}{extra}")
        if gallery_errs:
            print("\nGallery drawer pins:")
            for e in gallery_errs:
                print(f"  FAIL  {e}")
        s = report["summary"]
        print(
            f"\n{s['pass']} pass, {s['fail']} fail, {s['skip']} skip, "
            f"{s['gallery_pin_errors']} gallery pin error(s)"
        )

    return 1 if fails or gallery_errs else 0


# Populate COMPAT after all defs
COMPAT = _compat_map()

if __name__ == "__main__":
    sys.exit(main())
