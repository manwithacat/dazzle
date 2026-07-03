"""HaTchi-MaXchi Hyperpart registry — the copy-paste catalogue.

A **Hyperpart** is the htmx-native unit of reuse: a *partial* (server-
rendered markup + classes) plus its *exchange contract(s)* (the endpoint
request/response the server must satisfy), plus an optional *controller*
(vanilla JS, only where the platform lacks a primitive). It is NOT a React
component — there is no client state graph; state lives on the server and
htmx swaps the markup. Naming it distinctly is deliberate: it stops an
agent coder importing React priors (client state, composition trees) into
a server-owned partial.

Single source for the static gallery AND the agent-facing reference. Each
entry: a title, blurb, the canonical partial (rendered live AND shown as
the copy-paste snippet — the same string, so docs can't drift from the
demo), its exchange contracts, and optional wiring notes.

Icon/SVG placeholders (``{icon:name}``) are expanded by the builder from
the vendored Lucide registry so snippets stay readable.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Exchange:
    """One hypermedia exchange contract.

    A partial carries *affordances* — the `hx-*` controls that initiate a
    request. An Exchange declares, for one affordance, the request the
    server must handle and the response fragment it must return. This is
    the "endpoint response contract" half of a Hyperpart: the thing shadcn
    never had to standardise (React resolves state on the client), and the
    thing that makes a component agent-buildable — the server side is a
    checkable contract, not prose. Vocabulary grounded in *Hypermedia
    Systems* (Gross/Stepanek/Akşimşek): the request/response round-trip is
    a "hypermedia exchange".

    The `method`/`endpoint` fields are machine-checked against the `hx-*`
    attributes in the partial's markup (a Hyperpart that makes a request
    it doesn't declare — or declares one it doesn't make — fails CI). The
    prose fields document the contract for the agent/developer consuming it.
    """

    method: str  # GET / POST / PUT / PATCH / DELETE — matches the hx-<method> attr
    endpoint: str  # the URL the affordance targets — matches hx-<method>="…"
    trigger: str  # what fires it (the hx-trigger semantics), human-readable
    response: str  # the fragment contract the server MUST return
    swap: str  # where/how the response lands (target selector + swap mode)


@dataclass(frozen=True)
class Hyperpart:
    id: str
    title: str
    group: str
    blurb: str
    partial: str  # the markup — rendered live AND shown as the snippet
    notes: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)
    # The endpoint response contracts this partial's affordances require.
    # Every hx-{get,post,put,patch,delete} in `partial` must have a matching
    # Exchange (gated by tests/test_contract.py). hx-confirm is a client
    # affordance (no server round-trip of its own), so it is exempt.
    exchanges: tuple[Exchange, ...] = field(default_factory=tuple)
    # ── The Hyperpart manifest: the other code items that make up this
    #    unit, physically distributed by the build (CSS concatenated in
    #    layer order, JS bundled) but logically ONE Hyperpart. `partial`
    #    and `exchanges` above are inline; these point outward. Styles are
    #    NOT hand-listed (a component's CSS is genuinely many-to-many across
    #    files) — they're discovered from `HYPERPART: <id>` marker comments
    #    at each CSS block, so the marker at the code site is the source of
    #    truth. `controller`/`mock` are clean 1:1 and declared here.
    #    tools/hyperpart.py assembles the full anatomy; test_hyperpart_cohesion
    #    keeps the manifest and the markers honest.
    controller: str | None = None  # a controllers/*.js file, if it needs client behaviour
    mock: str | None = None  # the gallery mock endpoint (interactive Hyperparts)


# Groups order the gallery nav.
GROUPS = ["Actions", "Feedback", "Navigation", "Overlays", "Forms", "Data"]

HYPERPARTS: list[Hyperpart] = [
    # ── Actions ──────────────────────────────────────────────────────
    Hyperpart(
        "button",
        "Button",
        "Actions",
        "Primary, outline, ghost, destructive — chromatic accent CTAs.",
        '<div class="hm-demo-row">'
        '<button class="dz-button dz-button-primary">Save changes</button>'
        '<button class="dz-button dz-button-outline">Cancel</button>'
        '<button class="dz-button dz-button-ghost">Learn more</button>'
        '<button class="dz-button dz-button-destructive">Delete</button>'
        "</div>",
    ),
    Hyperpart(
        "badge",
        "Badge",
        "Feedback",
        "Colour + icon + text — status never relies on colour alone (WCAG 1.4.1).",
        '<div class="hm-demo-row">'
        '<span class="dz-badge" data-dz-tone="success" role="status"><span class="dz-badge-icon">{svg:circle-check}</span>Approved</span>'
        '<span class="dz-badge" data-dz-tone="warning" role="status"><span class="dz-badge-icon">{svg:triangle-alert}</span>Pending</span>'
        '<span class="dz-badge" data-dz-tone="destructive" role="status"><span class="dz-badge-icon">{svg:circle-x}</span>Rejected</span>'
        '<span class="dz-badge" data-dz-tone="neutral" role="status">Draft</span>'
        "</div>",
        tags=("identity",),
    ),
    Hyperpart(
        "alert",
        "Alert",
        "Feedback",
        "Tone-wash surfaces — an identity layer shadcn has no vocabulary for.",
        '<div class="dz-alert" data-dz-tone="warning" role="alert" style="max-width:34rem">'
        '<span class="dz-alert__icon">{svg:triangle-alert}</span>'
        '<div class="dz-alert__body"><div class="dz-alert__title">Payment method expiring</div>'
        '<div class="dz-alert__description">Your card ending 4242 expires next month.</div></div></div>',
        tags=("identity",),
    ),
    Hyperpart(
        "card",
        "Card",
        "Data",
        "Bordered surface with a resting stacked shadow; tabular KPIs.",
        '<div class="dz-card" style="padding:1.5rem;max-width:16rem">'
        '<div style="font-size:var(--text-sm);color:var(--colour-text-muted)">Total Revenue</div>'
        '<div style="font-size:var(--text-2xl);font-weight:var(--weight-bold);font-variant-numeric:tabular-nums">£1,250.00</div>'
        '<div style="font-size:var(--text-sm);color:var(--colour-success);display:flex;align-items:center;gap:.25rem">'
        '<span style="width:.875rem;height:.875rem">{svg:trending-up}</span> +12.5% this month</div></div>',
    ),
    # ── Overlays (interactive — need the mock htmx / dialog) ─────────
    Hyperpart(
        "command",
        "Command palette",
        "Overlays",
        "The hx-get palette — the htmx4 flagship. Press ⌘K.",
        '<button class="dz-button dz-button-outline" data-hm-open-command>Open palette <kbd class="dz-kbd">⌘K</kbd></button>'
        # `closedby="any"` = native light-dismiss (backdrop tap + Esc) where
        # supported (recent Chromium); dz-command.js provides the cross-browser
        # floor. The close button is the always-visible dismiss affordance —
        # essential on touch, where there is no Esc key.
        '<dialog class="dz-command" aria-label="Command palette" closedby="any">'
        # input + close share a flex bar; results follow. `next
        # .dz-command__results` resolves by DOM order (forward scan), so the
        # wrapper is fine. Flex layout (not absolute positioning) keeps the
        # close button reliably placed — abspos against a modal <dialog> is
        # fragile on Safari/iPadOS (it landed at its static position there).
        '<div class="dz-command__bar">'
        '<input class="dz-command__input" type="search" placeholder="Search workspaces and records…" '
        'hx-get="/mock/command" hx-trigger="input changed delay:150ms, focus once" '
        'hx-target="next .dz-command__results">'
        '<button type="button" class="dz-command__close" data-hm-close-command '
        'aria-label="Close command palette">{svg:x}</button></div>'
        '<div class="dz-command__results" role="listbox" aria-label="Results"></div></dialog>',
        notes="In Dazzle the input's hx-get hits <code>/app/command</code>, which returns "
        "persona-scoped results. Here a mock htmx returns a canned list so the demo works "
        "with no server.",
        tags=("interactive", "htmx"),
        exchanges=(
            Exchange(
                method="GET",
                endpoint="/app/command",
                trigger="the search input, on `input` (debounced 150ms) and first `focus`",
                response='zero or more result rows — `<a>`/`<button class="dz-command__item" '
                'role="option">` grouped by `<div class="dz-command__group">` headers; '
                'empty query or no matches returns `<div class="dz-command__empty">`',
                swap="innerHTML of the sibling `.dz-command__results` listbox",
            ),
        ),
        controller="controllers/dz-command.js",
        mock="/mock/command",
    ),
    Hyperpart(
        "confirm",
        "Confirm dialog",
        "Overlays",
        "Designed replacement for window.confirm — every hx-confirm upgrades automatically.",
        '<button class="dz-button dz-button-destructive" hx-delete="/mock/noop" '
        'hx-confirm="Delete this invoice? This cannot be undone.">Delete invoice</button>',
        notes="dz-confirm.js intercepts <code>htmx:confirm</code> (a client affordance — no "
        "server round-trip). On approval it issues the underlying request. No per-button "
        "wiring — any element with <code>hx-confirm</code> gets the designed dialog.",
        tags=("interactive", "htmx"),
        exchanges=(
            Exchange(
                method="DELETE",
                endpoint="/app/invoices/{id}",
                trigger="the button, after the user approves the designed confirm dialog",
                response="the server deletes the resource and returns the replacement markup "
                "for the affected region (e.g. the row's removal, or an empty-state)",
                swap="per the button's `hx-target`/`hx-swap` (row removal by default)",
            ),
        ),
        controller="controllers/dz-confirm.js",
    ),
    Hyperpart(
        "menu",
        "Menu",
        "Overlays",
        "Details-based dropdown — the hypermedia answer, no JS for open state.",
        '<details class="dz-menu"><summary class="dz-button dz-button-outline">Actions ▾</summary>'
        '<div class="dz-menu__panel">'
        '<button class="dz-menu__item">{icon:pencil} Edit</button>'
        '<button class="dz-menu__item">{icon:copy} Duplicate</button>'
        '<hr class="dz-menu__separator">'
        '<button class="dz-menu__item" data-dz-tone="destructive">{icon:trash-2} Delete</button></div></details>',
        tags=("interactive",),
    ),
    Hyperpart(
        "popover",
        "Popover",
        "Overlays",
        "Free-content panel, details-based; body can lazy-load via htmx.",
        '<details class="dz-popover"><summary class="dz-button dz-button-outline">Details</summary>'
        '<div class="dz-popover__panel"><div style="font-weight:var(--weight-semibold);font-size:var(--text-sm);margin-bottom:.25rem">Dimensions</div>'
        '<p style="margin:0;font-size:var(--text-sm);color:var(--colour-text-muted)">Filters, previews, quick forms.</p></div></details>',
        tags=("interactive",),
    ),
    Hyperpart(
        "tooltip",
        "Tooltip",
        "Overlays",
        "CSS-only attribute tooltip — zero JS.",
        '<button class="dz-button dz-button-outline" data-dz-tooltip="Saved 2 minutes ago">Hover me</button>',
    ),
    # ── Forms ────────────────────────────────────────────────────────
    Hyperpart(
        "controls",
        "Selection controls",
        "Forms",
        "Designed checkbox / radio / switch on native inputs — semantics free.",
        '<div class="hm-demo-row">'
        '<label class="hm-inline"><input type="checkbox" class="dz-checkbox" checked> Checkbox</label>'
        '<label class="hm-inline"><input type="radio" class="dz-radio" checked> Radio</label>'
        '<label class="hm-inline"><input type="checkbox" class="dz-switch" checked> Switch</label>'
        "</div>",
    ),
    Hyperpart(
        "toggle-group",
        "Toggle group",
        "Navigation",
        "Segmented control on native radios.",
        '<fieldset class="dz-toggle-group" role="radiogroup">'
        '<label><input type="radio" name="hm-view" checked><span>{icon:list} List</span></label>'
        '<label><input type="radio" name="hm-view"><span>{icon:kanban} Board</span></label>'
        '<label><input type="radio" name="hm-view"><span>{icon:calendar} Calendar</span></label></fieldset>',
    ),
    # ── Navigation / Data ────────────────────────────────────────────
    Hyperpart(
        "breadcrumb",
        "Breadcrumb",
        "Navigation",
        "CSS-generated chevrons; clean list markup.",
        '<nav class="dz-breadcrumb" aria-label="Breadcrumb"><ol>'
        '<li><a href="#">Home</a></li><li><a href="#">Invoices</a></li>'
        '<li aria-current="page">INV-0042</li></ol></nav>',
    ),
    Hyperpart(
        "avatar",
        "Avatar",
        "Data",
        "Initials or image; stacked groups.",
        '<div class="hm-demo-row">'
        '<span class="dz-avatar-group"><span class="dz-avatar">JD</span><span class="dz-avatar">AK</span><span class="dz-avatar">+3</span></span>'
        '<span class="dz-avatar" data-dz-size="lg">HM</span></div>',
    ),
    Hyperpart(
        "progress",
        "Progress",
        "Feedback",
        "Toned determinate bar.",
        '<div style="max-width:20rem;display:flex;flex-direction:column;gap:.75rem">'
        '<div class="dz-progress" role="progressbar" aria-label="Storage used" aria-valuenow="62" aria-valuemin="0" aria-valuemax="100"><div class="dz-progress__bar" style="width:62%"></div></div>'
        '<div class="dz-progress" data-dz-tone="success" role="progressbar" aria-label="Upload progress" aria-valuenow="100" aria-valuemin="0" aria-valuemax="100"><div class="dz-progress__bar" style="width:100%"></div></div></div>',
    ),
    Hyperpart(
        "empty-state",
        "Empty state",
        "Feedback",
        "Icon + one sentence + primary action — never a bare 'No X'.",
        '<div class="dz-card" style="padding:1.5rem;max-width:22rem"><div class="dz-empty-state">'
        '<span class="dz-empty-state__icon">{svg:inbox}</span>'
        '<h3 class="dz-empty-state__title">No invoices yet</h3>'
        '<p class="dz-empty-state__description">Create your first invoice to get started.</p>'
        '<div class="dz-empty-state__action"><a class="dz-button dz-button-primary" href="#">New Invoice</a></div></div></div>',
    ),
]
