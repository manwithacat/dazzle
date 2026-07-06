"""Blueprints — full-page layout motifs, the shadcn-Blocks analogue.

Where a Hyperpart is one component + its contracts, a **Blueprint** is a
whole page composed ONLY of published Hyperparts and Layout primitives —
the thing you copy when you're starting a page, not a widget. Each renders
to its own gallery sub-page (`blueprints/<id>.html`); the page IS the
snippet (a view-source disclosure shows the same string), so the docs
can't drift from the demo.

Layout responsiveness is intrinsic (the L1 primitives wrap on their own
minimums, no media queries), which is what makes a Blueprint testable at
any viewport — see tests/test_blueprints.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Blueprint:
    id: str
    title: str
    blurb: str
    partial: str  # the full page BODY — rendered live AND shown as the snippet
    composes: tuple[str, ...] = field(default_factory=tuple)  # Hyperpart ids used
    notes: str = ""


BLUEPRINTS: list[Blueprint] = [
    Blueprint(
        "workspace-drawer",
        "Workspace with drawer",
        "The app-shell motif: a sidebar of navigation, a content pane with a "
        "header cluster and a KPI grid, and a detail drawer on the native "
        "<dialog>. The sidebar wraps under the content on narrow screens — "
        "no media query anywhere on this page.",
        # ── the page body (dz- source; the build reprefixes) ──
        '<div class="dz-sidebar-layout" style="--dz-sidebar-width: 14rem">'
        # side: navigation
        '<nav class="dz-stack" data-dz-gap="xs" aria-label="Workspace">'
        '<button class="dz-button" data-dz-variant="primary">Dashboard</button>'
        '<button class="dz-button" data-dz-variant="ghost">Invoices</button>'
        '<button class="dz-button" data-dz-variant="ghost">Customers</button>'
        '<button class="dz-button" data-dz-variant="ghost">Reports</button>'
        '<button class="dz-button" data-dz-variant="ghost">Settings</button>'
        "</nav>"
        # content
        '<main class="dz-stack" data-dz-gap="lg">'
        '<div class="dz-cluster" data-dz-justify="between">'
        "<h1>Dashboard</h1>"
        '<div class="dz-cluster" data-dz-gap="sm">'
        '<button class="dz-button" data-dz-variant="outline">Export</button>'
        '<button class="dz-button" data-dz-variant="primary" '
        'data-dz-dialog-open="bp-drawer">New invoice…</button>'
        "</div></div>"
        '<div class="dz-auto-grid" style="--dz-grid-min: 12rem">'
        '<div class="dz-card dz-card-body">'
        '<div class="dz-card-label">Outstanding</div>'
        '<div class="dz-card-value">£12,450</div>'
        '<div class="dz-card-delta">{svg:trending-up} +4.2% this week</div></div>'
        '<div class="dz-card dz-card-body">'
        '<div class="dz-card-label">Paid this month</div>'
        '<div class="dz-card-value">£48,900</div>'
        '<div class="dz-card-delta">{svg:trending-up} +12.5%</div></div>'
        '<div class="dz-card dz-card-body">'
        '<div class="dz-card-label">Overdue</div>'
        '<div class="dz-card-value">3</div>'
        '<div class="dz-card-delta">{svg:triangle-alert} needs attention</div></div>'
        "</div>"
        '<div class="dz-center" data-dz-measure="prose">'
        "<p>Body copy sits in a centred reading measure inside the content "
        "pane — the same primitives compose at page scale and inside a card. "
        "Resize the window: the sidebar wraps under the content when the pane "
        "would get too narrow, and the KPI grid packs from three columns to "
        "one, with no breakpoints defined anywhere.</p>"
        "</div>"
        "</main>"
        "</div>"
        # the drawer: native <dialog>, opened by the header button
        '<dialog class="dz-dialog" id="bp-drawer" '
        'aria-labelledby="bp-drawer-title" closedby="any">'
        '<form method="dialog">'
        '<div class="dz-dialog__header">'
        '<h2 class="dz-dialog__title" id="bp-drawer-title">New invoice</h2>'
        '<button type="submit" class="dz-dialog__close" aria-label="Close dialog">'
        "{svg:x}</button></div>"
        '<div class="dz-dialog__body"><p>A form would live here — the drawer '
        "is the dialog Hyperpart unchanged: platform focus trap, Esc and "
        "backdrop close for free.</p></div>"
        '<div class="dz-dialog__footer">'
        '<button type="submit" class="dz-button" data-dz-variant="outline">Cancel</button>'
        '<button type="submit" class="dz-button" data-dz-variant="primary" '
        'value="confirm">Create</button>'
        "</div></form></dialog>",
        composes=(
            "sidebar-layout",
            "stack",
            "cluster",
            "auto-grid",
            "center",
            "card",
            "button",
            "dialog",
        ),
        notes="Every class on this page is a published Hyperpart or Layout "
        "primitive — there is no page-specific CSS. The responsive behaviour "
        "is owned by the layout primitives (the sidebar's "
        "<code>--dz-sidebar-content-min</code> and the grid's "
        "<code>--dz-grid-min</code>), so the same composition works inside a "
        "narrower container without edits.",
    ),
]
