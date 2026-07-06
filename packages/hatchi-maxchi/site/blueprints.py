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
    Blueprint(
        "master-detail",
        "Master–detail page",
        "The triage motif at page scale: a persistent record list beside a "
        "reading-measure detail pane. Selection is a hypermedia exchange — "
        "the item hx-gets its card into the pane; the composite wraps in a "
        "sidebar layout so the list docks beside the detail on wide screens "
        "and stacks above it on narrow ones.",
        '<div class="dz-sidebar-layout" style="--dz-sidebar-width: 18rem">'
        '<div class="dz-master-detail">'
        '<ul class="dz-master-detail__list" aria-label="Invoices">'
        '<li><a class="dz-master-detail__item" href="#" aria-current="true" '
        'hx-get="/mock/master-detail/inv-001" hx-target="next .dz-master-detail__detail">'
        "INV-001 · Acme</a></li>"
        '<li><a class="dz-master-detail__item" href="#" '
        'hx-get="/mock/master-detail/inv-002" hx-target="next .dz-master-detail__detail">'
        "INV-002 · Globex</a></li>"
        '<li><a class="dz-master-detail__item" href="#" '
        'hx-get="/mock/master-detail/inv-003" hx-target="next .dz-master-detail__detail">'
        "INV-003 · Initech</a></li></ul>"
        '<div class="dz-master-detail__detail">'
        '<div class="dz-card dz-card-body"><div class="dz-card-label">INV-001 · Acme</div>'
        '<div class="dz-card-value">£1,250.00</div>'
        '<div class="dz-card-delta">Paid · 2 days ago</div></div></div></div>'
        '<main class="dz-center" data-dz-measure="prose">'
        '<div class="dz-stack" data-dz-gap="md">'
        "<h1>Invoice INV-001</h1>"
        "<p>The reading pane holds whatever the selected record needs — notes, "
        "an activity feed, a form. It keeps a comfortable measure regardless of "
        "how wide the screen gets, and drops below the list on a phone.</p>"
        '<div class="dz-cluster" data-dz-gap="sm">'
        '<span class="dz-badge" data-dz-tone="success">'
        '<span class="dz-badge-icon">{svg:circle-check}</span>Paid</span>'
        '<span class="dz-badge" data-dz-tone="neutral">Net 30</span>'
        "</div></div></main>"
        "</div>",
        composes=("sidebar-layout", "master-detail", "center", "stack", "cluster", "badge", "card"),
        notes="The master–detail composite is unchanged from its Hyperpart — "
        "the Blueprint only places it: the sidebar layout gives the LIST the "
        "fixed-ish pane and the reading measure caps the detail column. Two "
        "selections' worth of state live on the server; the page holds none.",
    ),
    Blueprint(
        "dashboard",
        "Dashboard",
        "KPI tiles in a packing grid, a capacity list with progress bars, and "
        "a status cluster — the at-a-glance motif. Column count is entirely "
        "intrinsic: the grid packs whatever fits above its minimum tile width.",
        '<main class="dz-stack" data-dz-gap="lg">'
        '<div class="dz-cluster" data-dz-justify="between">'
        "<h1>Operations</h1>"
        '<span class="dz-badge" data-dz-tone="success">'
        '<span class="dz-badge-icon">{svg:circle-check}</span>All systems normal</span>'
        "</div>"
        '<div class="dz-auto-grid" style="--dz-grid-min: 11rem">'
        '<div class="dz-card dz-card-body"><div class="dz-card-label">Requests</div>'
        '<div class="dz-card-value">1.2M</div>'
        '<div class="dz-card-delta">{svg:trending-up} +8% today</div></div>'
        '<div class="dz-card dz-card-body"><div class="dz-card-label">P95 latency</div>'
        '<div class="dz-card-value">184ms</div>'
        '<div class="dz-card-delta">{svg:trending-up} within budget</div></div>'
        '<div class="dz-card dz-card-body"><div class="dz-card-label">Error rate</div>'
        '<div class="dz-card-value">0.02%</div>'
        '<div class="dz-card-delta">{svg:circle-check} nominal</div></div>'
        '<div class="dz-card dz-card-body"><div class="dz-card-label">Queue depth</div>'
        '<div class="dz-card-value">37</div>'
        '<div class="dz-card-delta">{svg:triangle-alert} draining</div></div>'
        "</div>"
        '<div class="dz-stack" data-dz-gap="sm">'
        "<h2>Capacity</h2>"
        '<div class="dz-progress" role="progressbar" aria-label="Storage used" '
        'aria-valuenow="62" aria-valuemin="0" aria-valuemax="100">'
        '<div class="dz-progress__bar" style="--dz-progress-value:62%"></div></div>'
        '<div class="dz-progress" data-dz-tone="success" role="progressbar" '
        'aria-label="Compute reserved" aria-valuenow="38" aria-valuemin="0" '
        'aria-valuemax="100">'
        '<div class="dz-progress__bar" style="--dz-progress-value:38%"></div></div>'
        "</div></main>",
        composes=("stack", "cluster", "auto-grid", "card", "badge", "progress"),
        notes="The KPI grid's <code>--dz-grid-min</code> is the only tuning "
        "knob on the page. The progress bars demonstrate the public "
        "custom-property knob (<code>--dz-progress-value</code>) at page "
        "scale — inline per-record values, CSS owns the mapping.",
    ),
    Blueprint(
        "auth",
        "Auth page",
        "The centred single-card motif: a sign-in form in a reading measure, "
        "vertically composed with the stack. The same card works for sign-up, "
        "reset, and 2FA steps.",
        '<main class="dz-center" data-dz-measure="prose">'
        '<div class="dz-stack" data-dz-gap="lg">'
        "<h1>Sign in</h1>"
        '<div class="dz-card dz-card-body">'
        '<form class="dz-stack" data-dz-gap="md" action="#" method="post">'
        '<div class="dz-form-field">'
        '<label class="dz-form-label" for="bp-auth-email">Email'
        '<span class="dz-form-required">*</span></label>'
        '<input class="dz-form-input" id="bp-auth-email" type="email" required '
        'autocomplete="username" placeholder="you@company.com">'
        "</div>"
        '<div class="dz-form-field">'
        '<label class="dz-form-label" for="bp-auth-password">Password'
        '<span class="dz-form-required">*</span></label>'
        '<input class="dz-form-input" id="bp-auth-password" type="password" required '
        'autocomplete="current-password" aria-describedby="bp-auth-password-hint">'
        '<p class="dz-form-hint" id="bp-auth-password-hint">At least 12 characters.</p>'
        "</div>"
        '<div class="dz-cluster" data-dz-justify="between">'
        '<button type="submit" class="dz-button" data-dz-variant="primary">Sign in</button>'
        '<a class="dz-link" href="#">Forgot password?</a>'
        "</div></form></div>"
        "</div></main>",
        composes=("center", "stack", "cluster", "card", "field", "button"),
        notes="The card is the only surface; the page owns no chrome. The "
        "form reuses the <code>dz-form-*</code> field triad (label / input / "
        "hint) — error states key off <code>aria-invalid</code> exactly as "
        "the field Hyperpart documents.",
    ),
]
