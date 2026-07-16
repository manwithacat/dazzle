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
        # Nu rejects autocomplete="username" on type=email; "email" is the
        # spec-clean token here and password managers pair it with
        # current-password just the same.
        'autocomplete="email" placeholder="you@company.com">'
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
    Blueprint(
        "saas-shell",
        "SaaS app shell",
        "The modern SaaS/admin frame: persistent left navigation, a sticky "
        "top bar with the collapse toggle, and a ROUTED main workspace — nav "
        "links swap only the main slot, so the shell, sidebar state, and "
        "scroll survive every navigation. Collapse persists via a cookie the "
        "server reads, so first paint is always correct.",
        '<div class="dz-app-shell" data-dz-sidebar="open">'
        '<aside class="dz-app-sidebar" id="dz-app-sidebar">'
        '<div class="dz-sidebar">'
        '<div class="dz-sidebar-brand"><span class="dz-sidebar-brand-text">Acme Ops</span></div>'
        '<nav class="dz-sidebar-nav" aria-label="Primary">'
        '<ul class="dz-sidebar-nav-list">'
        '<li><a class="dz-sidebar-nav-link" aria-current="page" href="#" '
        'hx-get="/mock/shell/dashboard" hx-target="#main-content" hx-swap="innerHTML">'
        '<span class="dz-sidebar-nav-icon">{svg:layout-dashboard}</span>'
        '<span class="dz-sidebar-nav-label">Dashboard</span></a></li>'
        '<li><a class="dz-sidebar-nav-link" href="#" '
        'hx-get="/mock/shell/invoices" hx-target="#main-content" hx-swap="innerHTML">'
        '<span class="dz-sidebar-nav-icon">{svg:receipt}</span>'
        '<span class="dz-sidebar-nav-label">Invoices</span></a></li>'
        '<li><a class="dz-sidebar-nav-link" href="#">'
        '<span class="dz-sidebar-nav-icon">{svg:users}</span>'
        '<span class="dz-sidebar-nav-label">Customers</span></a></li>'
        "</ul></nav>"
        '<div class="dz-sidebar-footer">'
        '<div class="dz-sidebar-user-block">'
        '<span class="dz-sidebar-user-name">Ada Lovelace</span></div></div>'
        "</div></aside>"
        '<div class="dz-app-content">'
        '<header class="dz-app-header">'
        '<div class="dz-topbar">'
        '<div class="dz-topbar-leading">'
        '<button type="button" class="dz-sidebar-toggle" data-dz-sidebar-toggle '
        'aria-expanded="true" aria-controls="dz-app-sidebar" aria-label="Toggle navigation">'
        '<span class="dz-sidebar-toggle__icon" aria-hidden="true"></span></button>'
        "</div>"
        '<div class="dz-topbar-title"><span class="dz-topbar-title-text">Acme Ops</span></div>'
        '<div class="dz-topbar-trailing">'
        '<button type="button" class="dz-button" data-dz-variant="primary">New invoice</button>'
        "</div></div></header>"
        '<main class="dz-app-main" id="main-content">'
        '<div class="dz-stack" data-dz-gap="md"><h1>Dashboard</h1>'
        '<div class="dz-auto-grid" style="--dz-grid-min: 10rem">'
        '<div class="dz-card dz-card-body"><div class="dz-card-label">Outstanding</div>'
        '<div class="dz-card-value">£12,450</div></div>'
        '<div class="dz-card dz-card-body"><div class="dz-card-label">Paid</div>'
        '<div class="dz-card-value">£48,900</div></div></div></div>'
        "</main></div></div>",
        composes=("app-shell", "stack", "auto-grid", "card", "button"),
        notes="Routing is one attribute per link: <code>hx-get</code> the page "
        "fragment, <code>hx-target=&quot;#main-content&quot;</code> — the "
        "server returns only the workspace body, and everything else (shell, "
        "sidebar collapse state, focus, scroll) persists. In Dazzle this is "
        "the workspace pattern: every example app's views render inside this "
        "shell. The collapse toggle writes the <code>dz_sidebar</code> cookie "
        "so the SERVER renders <code>data-dz-sidebar</code> correctly on the "
        "next full page load — state-in-DOM at SSR, no client hydration flash.",
    ),
    Blueprint(
        "record-page",
        "Record full page",
        "The owned-URL home for a record after a drawer peek. Same asset as the "
        "drawer hypermedia peek (Aurora Substation), but a full document: KPI "
        "grid, tabs, activity, and primary actions — shareable, refreshable, "
        "Back-friendly. Peek is GET ?peek=1 fragment; this page is GET /records/{id}.",
        '<main class="dz-stack" data-dz-gap="lg">'
        '<p class="hm-demo-muted" style="margin:0">'
        '<a href="../#drawer">← Gallery · Drawer</a>'
        " · full page (not a widened drawer)</p>"
        '<div class="dz-cluster" data-dz-justify="between">'
        "<div>"
        '<div class="dz-card-label">Asset</div>'
        '<h1 style="margin:0.25rem 0 0;letter-spacing:-0.02em">Aurora Substation</h1>'
        "</div>"
        '<div class="dz-cluster" data-dz-gap="sm">'
        '<span class="dz-badge" data-dz-tone="success">'
        '<span class="dz-badge-icon">{svg:circle-check}</span>Online</span>'
        '<button type="button" class="dz-button" data-dz-variant="outline">'
        "{svg:clipboard-list}Work orders</button>"
        '<button type="button" class="dz-button" data-dz-variant="primary">'
        "Edit asset</button>"
        "</div></div>"
        '<div class="dz-auto-grid" style="--dz-grid-min:11rem">'
        '<div class="dz-card dz-card-body">'
        '<div class="dz-card-label">Region</div>'
        '<div class="dz-card-value">North</div>'
        '<div class="dz-card-delta">Grid cluster A</div></div>'
        '<div class="dz-card dz-card-body">'
        '<div class="dz-card-label">Load</div>'
        '<div class="dz-card-value">82%</div>'
        '<div class="dz-card-delta">{svg:trending-up} +4% today</div></div>'
        '<div class="dz-card dz-card-body">'
        '<div class="dz-card-label">Open WOs</div>'
        '<div class="dz-card-value">2</div>'
        '<div class="dz-card-delta">{svg:triangle-alert} needs dispatch</div></div>'
        '<div class="dz-card dz-card-body">'
        '<div class="dz-card-label">Commissioned</div>'
        '<div class="dz-card-value" style="font-size:var(--text-xl)">2019</div>'
        '<div class="dz-card-delta">Last inspection 14 June</div></div>'
        "</div>"
        '<div class="dz-tabs" data-dz-tabs>'
        '<div class="dz-tabs__list" role="tablist" aria-label="Record sections">'
        '<button type="button" class="dz-tabs__tab" aria-current="true" '
        'data-dz-tab-target="rec-overview">Overview</button>'
        '<button type="button" class="dz-tabs__tab" '
        'data-dz-tab-target="rec-activity">Activity</button>'
        '<button type="button" class="dz-tabs__tab" '
        'data-dz-tab-target="rec-related">Related</button>'
        "</div>"
        '<div id="rec-overview" class="dz-tabs__panel" role="tabpanel">'
        '<div class="dz-stack" data-dz-gap="md">'
        '<div class="dz-alert" data-dz-tone="warning" role="alert">'
        '<span class="dz-alert__icon">{svg:triangle-alert}</span>'
        '<div class="dz-alert__body">'
        '<div class="dz-alert__title">Two open work orders</div>'
        '<div class="dz-alert__description">'
        "Full page owns the complete record shell — history, related tables, "
        "and edit flows that do not fit a peek drawer."
        "</div></div></div>"
        '<div class="dz-stack" data-dz-gap="sm">'
        '<div><div class="dz-card-label">Primary contact</div>'
        "<div>Maya Reyes · Operations</div></div>"
        '<div><div class="dz-card-label">Feeder</div>'
        "<div>N-GRID-14 · 33 kV</div></div>"
        "</div></div></div>"
        '<div id="rec-activity" class="dz-tabs__panel" role="tabpanel" hidden>'
        '<p class="hm-demo-muted">Inspection notes, status changes, and work-order '
        "events land here on the full page — not in the peek fragment.</p></div>"
        '<div id="rec-related" class="dz-tabs__panel" role="tabpanel" hidden>'
        '<p class="hm-demo-muted">Related assets, contracts, and tickets would '
        "compose as list-region / grid guests on this route.</p></div>"
        "</div>"
        "</main>",
        composes=(
            "stack",
            "cluster",
            "auto-grid",
            "card",
            "badge",
            "button",
            "alert",
            "tabs",
        ),
        notes="Paired with the <strong>Drawer</strong> hypermedia peek: the drawer "
        "loads <code>GET …?peek=1</code> into <code>drawer__body</code>; this "
        "Blueprint is the owned document for the same record. "
        "<strong>Open full page</strong> is navigation (a real <code>href</code>), "
        "not a CSS maximize of the dialog. Expand/Restore is a separate job "
        "(<code>data-dz-drawer-expand</code> toggles resting width ↔ "
        "<code>xl</code>) — do not label it “full page.” "
        "See <code>stems/host-chrome-symmetry.md</code> › Peek vs full page.",
    ),
    # ── Story-driven ops motifs (docs/guides/story-to-composition.md) ──
    Blueprint(
        "ops-queue",
        "Ops work queue",
        "The agent job page: KPI pressure strip, a dual-lock review queue with "
        "attention rows and inline actions, plus a mutation toast — not a CRUD "
        "table of every entity. Mirrors support_tickets ticket_queue.",
        '<main class="dz-stack" data-dz-gap="lg">'
        '<div class="dz-cluster" data-dz-justify="between">'
        "<div>"
        '<div class="dz-card-label">Workspace</div>'
        '<h1 style="margin:0.25rem 0 0;letter-spacing:-0.02em">Ticket queue</h1>'
        "</div>"
        '<div class="dz-cluster" data-dz-gap="sm">'
        '<span class="dz-badge" data-dz-tone="warning">'
        '<span class="dz-badge-icon">{svg:triangle-alert}</span>3 critical</span>'
        '<button type="button" class="dz-button" data-dz-variant="outline">Filters</button>'
        "</div></div>"
        '<div class="dz-metrics-grid" data-dz-tile-count="3">'
        '<div class="dz-metric-tile" data-dz-metric-key="open">'
        '<div class="dz-metric-label">Open</div>'
        '<div class="dz-metric-value">18</div></div>'
        '<div class="dz-metric-tile" data-dz-metric-key="wip" data-dz-tone="accent">'
        '<div class="dz-metric-label">In progress</div>'
        '<div class="dz-metric-value">7</div></div>'
        '<div class="dz-metric-tile" data-dz-metric-key="critical" data-dz-tone="destructive">'
        '<div class="dz-metric-label">Critical</div>'
        '<div class="dz-metric-value">3</div></div>'
        "</div>"
        '<div class="dz-stack" data-dz-gap="sm" aria-label="Open tickets">'
        '<div class="dz-queue-row dz-attn-both dz-attn-tone-critical" '
        'data-dz-queue-row data-dz-attn="critical">'
        '<div class="dz-queue-row-main">'
        '<div class="dz-queue-row-headline">'
        '<span class="dz-queue-row-title">Billing charge failed — Acme</span>'
        '<span class="dz-badge" data-dz-tone="destructive">critical</span></div>'
        '<p class="dz-queue-row-attn">SLA breaches at 16:00 — assign now.</p>'
        '<span class="dz-queue-row-date">opened 2h ago</span></div>'
        '<div class="dz-cluster" data-dz-gap="xs">'
        '<button type="button" class="dz-button" data-dz-variant="primary" data-dz-size="sm">'
        "Claim</button>"
        '<button type="button" class="dz-button" data-dz-variant="outline" data-dz-size="sm" '
        'data-dz-dialog-open="ops-peek">Peek</button>'
        "</div></div>"
        '<div class="dz-queue-row " data-dz-queue-row>'
        '<div class="dz-queue-row-main">'
        '<div class="dz-queue-row-headline">'
        '<span class="dz-queue-row-title">SSO login loop — Globex</span>'
        '<span class="dz-badge" data-dz-tone="warning">high</span></div>'
        '<span class="dz-queue-row-date">opened 5h ago</span></div>'
        '<div class="dz-cluster" data-dz-gap="xs">'
        '<button type="button" class="dz-button" data-dz-variant="primary" data-dz-size="sm">'
        "Claim</button>"
        '<button type="button" class="dz-button" data-dz-variant="outline" data-dz-size="sm">'
        "Open</button>"
        "</div></div>"
        '<div class="dz-queue-row " data-dz-queue-row>'
        '<div class="dz-queue-row-main">'
        '<div class="dz-queue-row-headline">'
        '<span class="dz-queue-row-title">Export CSV empty — Initech</span>'
        '<span class="dz-badge" data-dz-tone="neutral">medium</span></div>'
        '<span class="dz-queue-row-date">opened yesterday</span></div>'
        '<div class="dz-cluster" data-dz-gap="xs">'
        '<button type="button" class="dz-button" data-dz-variant="primary" data-dz-size="sm">'
        "Claim</button>"
        "</div></div>"
        "</div>"
        # Mutation feedback — page-chrome toast (decision 0011), not client state.
        '<div id="dz-toast" class="dz-toast-stack" data-dz-toast-stack aria-live="polite">'
        '<div class="dz-toast" data-dz-toast-level="success" '
        'data-dz-remove-after="8000" role="status">'
        '<div class="dz-toast__body">'
        '<div class="dz-toast__title">Ticket claimed</div>'
        '<div class="dz-toast__message">Billing charge failed — Acme is yours.</div>'
        '<div class="dz-toast__actions">'
        '<button type="button" class="dz-button" data-dz-variant="ghost" data-dz-size="sm">'
        "View</button></div></div></div></div>"
        "</main>"
        '<dialog class="dz-dialog" id="ops-peek" aria-labelledby="ops-peek-title" closedby="any">'
        '<form method="dialog">'
        '<div class="dz-dialog__header">'
        '<h2 class="dz-dialog__title" id="ops-peek-title">Billing charge failed</h2>'
        '<button type="submit" class="dz-dialog__close" aria-label="Close dialog">'
        "{svg:x}</button></div>"
        '<div class="dz-dialog__body">'
        "<p>Peek fragment — enough to claim or escalate without leaving the queue. "
        "Full record is a separate owned URL.</p></div>"
        '<div class="dz-dialog__footer">'
        '<button type="submit" class="dz-button" data-dz-variant="outline">Close</button>'
        '<button type="submit" class="dz-button" data-dz-variant="primary" value="claim">'
        "Claim</button></div></form></dialog>",
        composes=(
            "stack",
            "cluster",
            "metrics",
            "queue",
            "badge",
            "button",
            "toast",
            "dialog",
        ),
        notes="Job page, not entity admin: metrics answer “how bad?”, queue rows "
        "answer “what next?”, toast answers “what just happened?”. Dual-lock "
        "roots: <code>data-dz-metric-key</code>, <code>data-dz-queue-row</code>, "
        "<code>data-dz-toast-level</code>. Dazzle expression: "
        "<code>display: metrics</code> + <code>display: queue</code> on "
        "<code>ticket_queue</code>.",
    ),
    Blueprint(
        "triage-drawer",
        "Triage with drawer",
        "Master list as a work queue beside a detail drawer: select a row, "
        "hx-get a peek fragment into the dialog body, keep the queue mounted. "
        "Full page remains a real navigation target.",
        '<div class="dz-sidebar-layout" style="--dz-sidebar-width: 22rem">'
        '<div class="dz-stack" data-dz-gap="sm" aria-label="Triage queue">'
        '<div class="dz-cluster" data-dz-justify="between">'
        '<h1 style="margin:0;font-size:var(--text-lg)">Triage</h1>'
        '<span class="dz-badge" data-dz-tone="accent">12 open</span></div>'
        '<div class="dz-queue-row " data-dz-queue-row>'
        '<div class="dz-queue-row-main">'
        '<div class="dz-queue-row-headline">'
        '<span class="dz-queue-row-title">INV-441 · Acme overdue</span></div>'
        '<span class="dz-queue-row-date">due today</span></div>'
        '<button type="button" class="dz-button" data-dz-variant="outline" data-dz-size="sm" '
        'data-dz-dialog-open="triage-drawer">Open</button></div>'
        '<div class="dz-queue-row dz-attn-both dz-attn-tone-warning" '
        'data-dz-queue-row data-dz-attn="warning">'
        '<div class="dz-queue-row-main">'
        '<div class="dz-queue-row-headline">'
        '<span class="dz-queue-row-title">INV-390 · Globex dispute</span></div>'
        '<p class="dz-queue-row-attn">Customer waiting 3 days.</p></div>'
        '<button type="button" class="dz-button" data-dz-variant="outline" data-dz-size="sm" '
        'data-dz-dialog-open="triage-drawer">Open</button></div>'
        '<div class="dz-queue-row " data-dz-queue-row>'
        '<div class="dz-queue-row-main">'
        '<div class="dz-queue-row-headline">'
        '<span class="dz-queue-row-title">INV-512 · Initech credit</span></div>'
        '<span class="dz-queue-row-date">due Fri</span></div>'
        '<button type="button" class="dz-button" data-dz-variant="outline" data-dz-size="sm" '
        'data-dz-dialog-open="triage-drawer">Open</button></div>'
        "</div>"
        '<main class="dz-stack" data-dz-gap="md">'
        '<h2 style="margin:0">Reading pane</h2>'
        '<p class="hm-demo-muted" style="margin:0">On wide screens the queue docks; '
        "on a phone it stacks. The drawer is the hypermedia peek — same fragment "
        "contract as the record page, different chrome.</p>"
        '<div class="dz-card dz-card-body">'
        '<div class="dz-card-label">Hint</div>'
        "<div>Open a row to load the triage drawer. Prefer peek for decide-now; "
        "navigate to the full record for history and edit.</div></div>"
        "</main></div>"
        '<dialog class="dz-dialog" id="triage-drawer" '
        'aria-labelledby="triage-drawer-title" closedby="any">'
        '<form method="dialog">'
        '<div class="dz-dialog__header">'
        '<h2 class="dz-dialog__title" id="triage-drawer-title">INV-441 · Acme</h2>'
        '<button type="submit" class="dz-dialog__close" aria-label="Close dialog">'
        "{svg:x}</button></div>"
        '<div class="dz-dialog__body">'
        '<div class="dz-stack" data-dz-gap="md">'
        '<div class="dz-cluster" data-dz-gap="sm">'
        '<span class="dz-badge" data-dz-tone="warning">overdue</span>'
        '<span class="dz-badge" data-dz-tone="neutral">Net 30</span></div>'
        "<p>£1,250.00 · last contact 2 days ago. Approve write-off or send "
        "reminder without losing the queue context.</p>"
        '<div class="dz-alert" data-dz-tone="accent" role="status">'
        '<span class="dz-alert__icon">{svg:info}</span>'
        '<div class="dz-alert__body">'
        '<div class="dz-alert__title">Peek, not full page</div>'
        '<div class="dz-alert__description">'
        "Esc / backdrop close; full record is a real link below."
        "</div></div></div></div></div>"
        '<div class="dz-dialog__footer">'
        '<a class="dz-button" data-dz-variant="outline" href="../blueprints/record-page">'
        "Open full page</a>"
        '<button type="submit" class="dz-button" data-dz-variant="primary" value="remind">'
        "Send reminder</button>"
        "</div></form></dialog>",
        composes=(
            "sidebar-layout",
            "stack",
            "cluster",
            "queue",
            "badge",
            "button",
            "card",
            "dialog",
            "alert",
        ),
        notes="Compose queue + dialog; do not invent a client triage store. "
        "Selection is an exchange (button opens dialog; production wires "
        "<code>hx-get</code> into <code>dialog__body</code>). Full page is "
        "navigation — see record-page Blueprint and "
        "<code>stems/host-chrome-symmetry.md</code>.",
    ),
    Blueprint(
        "manager-sla-strip",
        "Manager SLA strip",
        "Metrics-first team home: KPI tiles, a status-list readiness strip, "
        "and a critical work queue — the manager job, not a personal assigned "
        "list. Mirrors support_tickets manager_ops.",
        '<main class="dz-stack" data-dz-gap="lg">'
        '<div class="dz-cluster" data-dz-justify="between">'
        "<div>"
        '<div class="dz-card-label">Manager</div>'
        '<h1 style="margin:0.25rem 0 0;letter-spacing:-0.02em">Team ops</h1>'
        "</div>"
        '<span class="dz-badge" data-dz-tone="success">'
        '<span class="dz-badge-icon">{svg:circle-check}</span>Within SLA band</span>'
        "</div>"
        '<div class="dz-metrics-grid" data-dz-tile-count="4">'
        '<div class="dz-metric-tile" data-dz-metric-key="open">'
        '<div class="dz-metric-label">Open</div>'
        '<div class="dz-metric-value">24</div></div>'
        '<div class="dz-metric-tile" data-dz-metric-key="wip" data-dz-tone="accent">'
        '<div class="dz-metric-label">In progress</div>'
        '<div class="dz-metric-value">11</div></div>'
        '<div class="dz-metric-tile" data-dz-metric-key="critical" data-dz-tone="destructive">'
        '<div class="dz-metric-label">Critical</div>'
        '<div class="dz-metric-value">2</div></div>'
        '<div class="dz-metric-tile" data-dz-metric-key="resolved" data-dz-tone="positive">'
        '<div class="dz-metric-label">Resolved</div>'
        '<div class="dz-metric-value">9</div></div>'
        "</div>"
        '<div class="dz-stack" data-dz-gap="sm">'
        '<h2 style="margin:0;font-size:var(--text-base)">SLA readiness</h2>'
        '<ul class="dz-status-list">'
        '<li class="dz-status-list-entry" data-dz-status-entry data-dz-state="accent">'
        '<span class="dz-status-list-icon" aria-hidden="true">{svg:clock}</span>'
        '<div class="dz-status-list-text">'
        '<div class="dz-status-list-title">Ticket response SLA</div>'
        '<div class="dz-status-list-caption">'
        "Warning 2h · breach 4h · critical 8h (business hours)</div></div>"
        '<span class="dz-status-list-pill">accent</span></li>'
        '<li class="dz-status-list-entry" data-dz-status-entry data-dz-state="warning">'
        '<span class="dz-status-list-icon" aria-hidden="true">{svg:triangle-alert}</span>'
        '<div class="dz-status-list-text">'
        '<div class="dz-status-list-title">Critical open</div>'
        '<div class="dz-status-list-caption">'
        "Priority critical tickets must stay assigned</div></div>"
        '<span class="dz-status-list-pill">warning</span></li>'
        '<li class="dz-status-list-entry" data-dz-status-entry data-dz-state="warning">'
        '<span class="dz-status-list-icon" aria-hidden="true">{svg:user}</span>'
        '<div class="dz-status-list-text">'
        '<div class="dz-status-list-title">Unassigned open</div>'
        '<div class="dz-status-list-caption">'
        "Open tickets with no assignee block first response</div></div>"
        '<span class="dz-status-list-pill">warning</span></li>'
        '<li class="dz-status-list-entry" data-dz-status-entry data-dz-state="positive">'
        '<span class="dz-status-list-icon" aria-hidden="true">{svg:circle-check}</span>'
        '<div class="dz-status-list-text">'
        '<div class="dz-status-list-title">Resolved pending close</div>'
        '<div class="dz-status-list-caption">'
        "Awaiting customer confirmation or agent close</div></div>"
        '<span class="dz-status-list-pill">positive</span></li>'
        "</ul></div>"
        '<div class="dz-stack" data-dz-gap="sm">'
        '<h2 style="margin:0;font-size:var(--text-base)">Critical queue</h2>'
        '<div class="dz-queue-row dz-attn-both dz-attn-tone-critical" '
        'data-dz-queue-row data-dz-attn="critical">'
        '<div class="dz-queue-row-main">'
        '<div class="dz-queue-row-headline">'
        '<span class="dz-queue-row-title">Production outage — North region</span></div>'
        '<p class="dz-queue-row-attn">Unassigned · breach in 40m</p></div>'
        '<button type="button" class="dz-button" data-dz-variant="primary" data-dz-size="sm">'
        "Reassign</button></div>"
        '<div class="dz-queue-row " data-dz-queue-row>'
        '<div class="dz-queue-row-main">'
        '<div class="dz-queue-row-headline">'
        '<span class="dz-queue-row-title">Payment webhook storm</span></div>'
        '<span class="dz-queue-row-date">assigned · Ada</span></div>'
        '<button type="button" class="dz-button" data-dz-variant="outline" data-dz-size="sm">'
        "Escalate</button></div>"
        "</div></main>",
        composes=("stack", "cluster", "metrics", "status-list", "queue", "badge", "button"),
        notes="Manager default workspace shape: metrics → readiness strip → "
        "focused queues. Avoid landing managers on empty “my assigned” lists "
        "when seed data assigns to agents (TR-52 class). Dual-lock roots: "
        "metric tiles, <code>data-dz-status-entry</code>, "
        "<code>data-dz-queue-row</code>.",
    ),
]
