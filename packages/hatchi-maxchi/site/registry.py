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
    # The states the endpoint must handle (loading/empty/populated/error). A
    # coding agent needs these enumerated, not implied — an endpoint-backed
    # component is under-specified without its empty/error behaviour.
    states: tuple[str, ...] = ()


@dataclass(frozen=True)
class Guidance:
    """Structured, agent-optimised implementation guidance — replaces
    guidance-like prose in `notes` (narrative remarks stay in notes).
    Rendered on the part page for humans and serialised verbatim into
    agents/<id>.md for agents. Controller-bearing parts must carry at
    least seams + pitfalls (tests/test_hyperpart_cohesion.py, with a
    shrink-only PENDING_GUIDANCE allowlist during migration)."""

    seams: tuple[str, ...] = ()  # extension/composition points, by name
    pitfalls: tuple[str, ...] = ()  # mistakes the design already rejected
    do_dont: tuple[tuple[str, str], ...] = ()  # (do, don't) pairs
    a11y_keys: tuple[str, ...] = ()  # keyboard/AT behaviours to preserve
    composes_with: tuple[str, ...] = ()  # Hyperpart ids (cross-checked)


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
    # Composition (declarative, NOT a runtime include): the child Hyperpart
    # ids this one embeds — nested inline in `partial`, or loaded into a slot
    # via an Exchange. Drives the "Composed of" note + dependency-class
    # aggregation ("Composite" + the union of children's classes). The markup
    # in `partial` stays the source of truth; this only describes it.
    composes: tuple[str, ...] = field(default_factory=tuple)
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
    # Render the live demo as a STANDALONE page (hyperparts/{id}-live.html)
    # embedded via <iframe class="hm-hp-frame"> — fixed-position
    # compositions get their own browsing context, same treatment as the
    # Blueprint live pages. The iframe is GALLERY CHROME added by the
    # builder — never part of the partial, which stays the copyable snippet.
    framed: bool = False
    # OPTIONAL extension controllers riding this Hyperpart's seams (each a
    # controllers/*.js file). An extension adds behaviour a consumer can take
    # or leave — its absence never breaks the core partial (the grid works
    # without column-resize; resize needs the grid). Bundled like controllers.
    extensions: tuple[str, ...] = field(default_factory=tuple)
    mock: str | None = None  # the gallery mock endpoint (interactive Hyperparts)
    # Contract modules (contracts/<part>.py): typed ingestion model + DOM
    # contract + executable exemplar. One Hyperpart may carry several (the
    # base part + each data-bearing extension). Cohesion-gated: every
    # controller-bearing entry needs contracts or a PENDING_CONTRACTS entry.
    contracts: tuple[str, ...] = field(default_factory=tuple)
    # Structured agent guidance (see Guidance). None = not yet migrated.
    guidance: Guidance | None = None


# Groups order the gallery nav.
GROUPS = [
    "Actions",
    "Feedback",
    "Navigation",
    "Overlays",
    "Forms",
    "Data",
    "Layout",
    "Composites",
    "Primitives",
]

HYPERPARTS: list[Hyperpart] = [
    # ── Actions ──────────────────────────────────────────────────────
    Hyperpart(
        "button",
        "Button",
        "Actions",
        "Primary, outline, ghost, destructive — chromatic accent CTAs.",
        '<div class="hm-demo-row">'
        '<button class="dz-button" data-dz-variant="primary">Save changes</button>'
        '<button class="dz-button" data-dz-variant="outline">Cancel</button>'
        '<button class="dz-button" data-dz-variant="ghost">Learn more</button>'
        '<button class="dz-button" data-dz-variant="destructive">Delete</button>'
        "</div>",
    ),
    Hyperpart(
        "badge",
        "Badge",
        "Feedback",
        "Colour + icon + text — status never relies on colour alone (WCAG 1.4.1).",
        '<div class="hm-demo-row">'
        '<span class="dz-badge" data-dz-tone="success"><span class="dz-badge-icon">{svg:circle-check}</span>Approved</span>'
        '<span class="dz-badge" data-dz-tone="warning"><span class="dz-badge-icon">{svg:triangle-alert}</span>Pending</span>'
        '<span class="dz-badge" data-dz-tone="destructive"><span class="dz-badge-icon">{svg:circle-x}</span>Rejected</span>'
        '<span class="dz-badge" data-dz-tone="neutral">Draft</span>'
        "</div>",
        tags=("identity",),
    ),
    Hyperpart(
        "alert",
        "Alert",
        "Feedback",
        "Tone-wash surfaces — an identity layer shadcn has no vocabulary for.",
        '<div class="dz-alert hm-measure-lg" data-dz-tone="warning" role="alert">'
        '<span class="dz-alert__icon">{svg:triangle-alert}</span>'
        '<div class="dz-alert__body"><div class="dz-alert__title">Payment method expiring</div>'
        '<div class="dz-alert__description">Your card ending 4242 expires next month.</div></div></div>',
        tags=("identity",),
    ),
    Hyperpart(
        "card",
        "Card",
        "Data",
        "Bordered surface with a resting stacked shadow; tabular KPIs — "
        "semantic content classes, no inline styles.",
        '<div class="dz-card dz-card-body">'
        '<div class="dz-card-label">Total Revenue</div>'
        '<div class="dz-card-value">£1,250.00</div>'
        '<div class="dz-card-delta">{svg:trending-up} +12.5% this month</div></div>',
    ),
    Hyperpart(
        "pagination",
        "Pagination",
        "Data",
        "The footer beneath a data table — a summary and page buttons. Each "
        "button hx-gets a page into the list body (an Exchange, not a widget).",
        '<div class="hm-stack hm-measure-lg">'
        '<div id="hm-pag-body" class="hm-pag-list">'
        '<div class="hm-pag-row">INV-001 · Acme</div>'
        '<div class="hm-pag-row">INV-002 · Globex</div>'
        '<div class="hm-pag-row">INV-003 · Initech</div>'
        "</div>"
        '<nav class="dz-pagination" aria-label="Pagination">'
        '<span class="dz-pagination-summary">42 rows</span>'
        '<div class="dz-pagination-pages">'
        '<button class="dz-pagination-page" disabled aria-label="Previous page">‹</button>'
        '<button class="dz-pagination-page is-current" aria-current="page">1</button>'
        '<button class="dz-pagination-page" hx-get="/mock/pagination/2" '
        'hx-target="#hm-pag-body" hx-swap="innerHTML">2</button>'
        '<button class="dz-pagination-page" hx-get="/mock/pagination/3" '
        'hx-target="#hm-pag-body" hx-swap="innerHTML">3</button>'
        '<span class="dz-pagination-ellipsis" aria-hidden="true">…</span>'
        '<button class="dz-pagination-page" hx-get="/mock/pagination/9" '
        'hx-target="#hm-pag-body" hx-swap="innerHTML">9</button>'
        '<button class="dz-pagination-page" hx-get="/mock/pagination/2" '
        'hx-target="#hm-pag-body" hx-swap="innerHTML" aria-label="Next page">›</button>'
        "</div></nav></div>",
        notes="Each page button carries its own <code>hx-get</code>; here a mock htmx swaps "
        "a canned page into <code>#hm-pag-body</code>. In Dazzle the button hits the region "
        "endpoint (<code>?page=N&amp;page_size=…</code>) and the server returns the repainted "
        "list body (via <code>innerMorph</code>) plus the moved <code>is-current</code> marker.",
        tags=("htmx",),
        exchanges=(
            Exchange(
                method="GET",
                endpoint="/app/{region}?page={n}&page_size={size}",
                trigger="a page button, on click",
                response="the list body fragment for page n — the rows the region renders, "
                "with the current-page button marked `is-current` + `aria-current='page'`",
                swap="innerMorph of the region's body (`#{region}-body`)",
                states=("loading", "populated", "error"),
            ),
        ),
        mock="/mock/pagination",
    ),
    Hyperpart(
        "grid",
        "Data table",
        "Data",
        "A server-rendered data table on a real <table>, all HTML over the "
        "wire: search, sortable headers, filters, row selection (one page or "
        "every matching row), bulk actions, pagination, and deep-linkable "
        "URL-synced state. Optional extensions add column visibility, column "
        "resize, and inline cell editing. The wiring lives in the Agent "
        "Implementation Guidance below.",
        # Full width (no hm-measure cap): a data table demos its column
        # behaviour — resize needs room to move, and real tables run wide.
        '<div class="hm-stack">'
        # data-dz-grid-url: opt-in URL-synced state — the grid's query mirrors
        # into the address bar (deep-linkable, Back walks grid states).
        '<div class="dz-table" data-dz-grid data-dz-grid-url data-dz-bulk-count="0" '
        # data-dz-grid-edit-url: the inline-edit extension's commit base — the
        # entity's STANDARD update route (PUT {base}/{id}, single-field JSON).
        'data-dz-grid-page="1" data-dz-grid-edit-url="/mock/grid">'
        '<div class="dz-filter-bar">'
        '<div class="dz-filter-cell">'
        '<label class="dz-filter-label" for="hm-grid-search">Search</label>'
        '<input class="dz-filter-input" id="hm-grid-search" type="search" '
        'data-dz-grid-search name="q" placeholder="Name or plan…"></div>'
        '<div class="dz-filter-cell">'
        '<label class="dz-filter-label" for="hm-grid-filter-plan">Plan</label>'
        '<select class="dz-filter-select" id="hm-grid-filter-plan" data-dz-grid-filter="plan">'
        '<option value="">Any plan</option><option value="Free">Free</option>'
        '<option value="Pro">Pro</option><option value="Team">Team</option>'
        '<option value="Enterprise">Enterprise</option></select></div>'
        # `status` is a FILTER-ONLY field: the table renders no Status column, yet
        # the filter narrows on it — filters (like scopes) target any queryable
        # server field, not just displayed columns. Only `plan` is shown-and-filtered.
        "<!-- status is a filter-only field (no column): filters can narrow on any "
        "server field, not just displayed columns -->"
        '<div class="dz-filter-cell">'
        '<label class="dz-filter-label" for="hm-grid-filter-status">Status</label>'
        '<select class="dz-filter-select" id="hm-grid-filter-status" data-dz-grid-filter="status">'
        '<option value="">Any status</option><option value="Active">Active</option>'
        '<option value="Trialing">Trialing</option><option value="Churned">Churned</option>'
        "</select></div>"
        # Page size is a WINDOWING control (like a page click): it re-pages the
        # same matched set, so it lives outside the filter semantics — changing
        # it keeps an all-matching selection and resets to page 1.
        '<div class="dz-filter-cell">'
        '<label class="dz-filter-label" for="hm-grid-page-size">Per page</label>'
        '<select class="dz-filter-select" id="hm-grid-page-size" data-dz-grid-page-size>'
        '<option value="2">2</option><option value="4" selected>4</option>'
        '<option value="8">8</option></select></div>'
        # Column-visibility menu (dz-grid-cols.js extension): a native <details>
        # disclosure — no open/close JS. Checked = visible; the hidden set is
        # projected onto every [data-dz-col] cell and persists per grid id.
        '<details class="dz-table-col-menu">'
        '<summary class="dz-table-col-menu-trigger" '
        'aria-label="Toggle column visibility">Columns</summary>'
        '<div class="dz-table-col-menu-panel">'
        '<label class="dz-table-col-menu-item">'
        '<input type="checkbox" checked class="dz-table-col-menu-checkbox" '
        'data-dz-grid-col-toggle="first" aria-label="Show First name column">'
        "<span>First name</span></label>"
        '<label class="dz-table-col-menu-item">'
        '<input type="checkbox" checked class="dz-table-col-menu-checkbox" '
        'data-dz-grid-col-toggle="last" aria-label="Show Last name column">'
        "<span>Last name</span></label>"
        '<label class="dz-table-col-menu-item">'
        '<input type="checkbox" checked class="dz-table-col-menu-checkbox" '
        'data-dz-grid-col-toggle="plan" aria-label="Show Plan column">'
        "<span>Plan</span></label>"
        '<label class="dz-table-col-menu-item">'
        '<input type="checkbox" checked class="dz-table-col-menu-checkbox" '
        'data-dz-grid-col-toggle="signed" aria-label="Show Signed up column">'
        "<span>Signed up</span></label>"
        # #853 escape hatch: show every column + clear the stored preference.
        '<button type="button" class="dz-table-col-menu-reset" '
        "data-dz-grid-cols-reset>Show all columns</button>"
        "</div></details>"
        "</div>"
        '<div class="dz-bulk-actions">'
        '<span aria-live="polite" aria-atomic="true">'
        "<span data-dz-bulk-count-target>0</span> selected</span>"
        # All-matching escalation (GMail idiom): promote the page selection to
        # the WHOLE matched query. The total is mirrored from the footer's
        # server-stamped data-dz-grid-total; CSS hides the button once the
        # mode is active (its job is done — the header select-all exits it).
        '<button type="button" class="dz-bulk-matching" data-dz-grid-select-all-matching>'
        "Select all <span data-dz-grid-matching-total>…</span> matching</button>"
        # Two-request bulk pattern: the POST applies the action (JSON/204
        # response, nothing swapped); data-dz-grid-bulk-refresh tells the
        # controller to re-fetch rows + footer for the current query after the
        # request settles — the same GET path every other state change uses.
        '<button type="button" class="dz-bulk-delete" data-dz-grid-bulk-action="delete" '
        'data-dz-grid-bulk-refresh hx-swap="none" hx-post="/mock/grid/bulk" '
        'hx-confirm="Delete the selected customers? This cannot be undone.">Delete</button>'
        '<button type="button" class="dz-bulk-clear" data-dz-grid-clear>Clear</button>'
        "</div>"
        '<div class="dz-table-scroll">'
        # Loading overlay (#972): pure-CSS, keyed off htmx's native `.htmx-request`
        # on any descendant — no controller flag for idiomorph to strip on morph.
        '<div class="dz-table-loading" aria-hidden="true">'
        '<span class="dz-table-loading-spinner">{svg:loader-circle}</span></div>'
        '<div class="dz-table-scroll-x">'
        '<table class="dz-table-grid">'
        # Per-column <col> resize targets (dz-grid-resize.js): widths applied
        # to the col size header + cells together, and cols survive tbody swaps.
        "<colgroup>"
        '<col class="dz-table-col-select">'
        '<col data-dz-col="first"><col data-dz-col="last">'
        '<col data-dz-col="plan"><col data-dz-col="signed">'
        "</colgroup>"
        "<thead><tr>"
        '<th class="dz-table-th-select">'
        '<input type="checkbox" data-dz-grid-select-all aria-label="Select all rows"></th>'
        # Each data header carries data-dz-col (column-visibility hides header
        # + cells + col in lock-step) and an in-th resize handle (decorative;
        # pointer drag resizes col[data-col] — a drag never fires the sort).
        '<th class="dz-table-th" data-dz-col="first" aria-sort="none">'
        '<button type="button" class="dz-table-sort-button" data-dz-grid-sort="first">First name'
        '<span class="dz-table-sort-icon" aria-hidden="true">{svg:chevron-up}</span></button>'
        '<span class="dz-table-resize-handle" data-dz-grid-resize="first" aria-hidden="true">'
        "</span></th>"
        '<th class="dz-table-th" data-dz-col="last" aria-sort="none">'
        '<button type="button" class="dz-table-sort-button" data-dz-grid-sort="last">Last name'
        '<span class="dz-table-sort-icon" aria-hidden="true">{svg:chevron-up}</span></button>'
        '<span class="dz-table-resize-handle" data-dz-grid-resize="last" aria-hidden="true">'
        "</span></th>"
        '<th class="dz-table-th" data-dz-col="plan" aria-sort="none">'
        '<button type="button" class="dz-table-sort-button" data-dz-grid-sort="plan">Plan'
        '<span class="dz-table-sort-icon" aria-hidden="true">{svg:chevron-up}</span></button>'
        '<span class="dz-table-resize-handle" data-dz-grid-resize="plan" aria-hidden="true">'
        "</span></th>"
        '<th class="dz-table-th" data-dz-col="signed" aria-sort="none">'
        '<button type="button" class="dz-table-sort-button" data-dz-grid-sort="signed">Signed up'
        '<span class="dz-table-sort-icon" aria-hidden="true">{svg:chevron-up}</span></button>'
        '<span class="dz-table-resize-handle" data-dz-grid-resize="signed" aria-hidden="true">'
        "</span></th>"
        "</tr></thead>"
        # The tbody hydrates over the wire: hx-get on `load` fetches the rows,
        # innerMorph swaps them in (idiomorph keys on each row's stable `id`, so a
        # selection follows its ROW across a re-sort). Until then it holds a
        # skeleton placeholder (no data rows to select → no empty-state flash).
        '<tbody class="dz-table-body" data-dz-grid-body data-dz-grid-src="/mock/grid/rows" '
        'hx-get="/mock/grid/rows" hx-trigger="load, dz-grid:refresh" hx-swap="innerMorph">'
        '<tr class="dz-tr-row" aria-hidden="true">'
        '<td class="dz-tr-checkbox-cell"><span class="dz-skeleton" data-dz-shape="text"></span></td>'
        '<td class="dz-tr-cell"><span class="dz-skeleton" data-dz-shape="text"></span></td>'
        '<td class="dz-tr-cell"><span class="dz-skeleton" data-dz-shape="text"></span></td>'
        '<td class="dz-tr-cell"><span class="dz-skeleton" data-dz-shape="text"></span></td>'
        '<td class="dz-tr-cell"><span class="dz-skeleton" data-dz-shape="text"></span></td></tr>'
        '<tr class="dz-tr-row" aria-hidden="true">'
        '<td class="dz-tr-checkbox-cell"><span class="dz-skeleton" data-dz-shape="text"></span></td>'
        '<td class="dz-tr-cell"><span class="dz-skeleton" data-dz-shape="text"></span></td>'
        '<td class="dz-tr-cell"><span class="dz-skeleton" data-dz-shape="text"></span></td>'
        '<td class="dz-tr-cell"><span class="dz-skeleton" data-dz-shape="text"></span></td>'
        '<td class="dz-tr-cell"><span class="dz-skeleton" data-dz-shape="text"></span></td></tr>'
        '<tr class="dz-tr-row" aria-hidden="true">'
        '<td class="dz-tr-checkbox-cell"><span class="dz-skeleton" data-dz-shape="text"></span></td>'
        '<td class="dz-tr-cell"><span class="dz-skeleton" data-dz-shape="text"></span></td>'
        '<td class="dz-tr-cell"><span class="dz-skeleton" data-dz-shape="text"></span></td>'
        '<td class="dz-tr-cell"><span class="dz-skeleton" data-dz-shape="text"></span></td>'
        '<td class="dz-tr-cell"><span class="dz-skeleton" data-dz-shape="text"></span></td></tr>'
        "</tbody></table>"
        # Empty-state sibling (CSS `:has(tbody tr td)`-driven, zero JS): shown only
        # when the hydrated tbody has no data cells.
        '<div class="dz-table-empty">'
        '<span class="dz-table-empty-icon">{svg:inbox}</span>'
        '<p class="dz-table-empty-title">No customers found</p>'
        '<p class="dz-table-empty-hint">Adjust the filters to widen your search.</p>'
        "</div>"
        "</div></div>"  # close .dz-table-scroll-x + .dz-table-scroll
        # SR announcer: the footer is repainted wholesale, so screen readers
        # can't track it — dz-grid.js mirrors the result-window summary here
        # after every data change ("Showing 1-4 of 6"). Visually hidden.
        '<span class="dz-grid-announce" data-dz-grid-announce aria-live="polite" '
        'aria-atomic="true"></span>'
        # Pagination footer — server-rendered (summary + prev/next/page buttons).
        # Empty until the `load` exchange fills it alongside the first page of rows.
        '<nav class="dz-pagination" data-dz-grid-pagination aria-label="Pagination"></nav>'
        "</div></div>",  # close .dz-table (root) + .hm-stack
        notes="The tbody hydrates over the wire — <code>hx-get</code> on "
        "<code>load</code> fetches the rows, and <code>innerMorph</code> swaps them in. "
        "Each row carries a stable <code>id</code> (the idiomorph <em>morph key</em>) so a "
        "selection follows its <em>row</em> — not its DOM position — across a re-sort or "
        "paginate; <code>data-dz-grid-row-id</code> stays the bulk-action payload anchor, "
        "and the id encodes it so the two agree. Loading is pure-CSS "
        "(<code>.htmx-request</code> → the overlay, #972 — no controller flag idiomorph "
        "could strip). Selection is delegated + state-in-DOM: <code>dz-grid.js</code> counts "
        "the checked <code>[data-dz-grid-select]</code> boxes, writes the total to "
        "<code>data-dz-bulk-count</code>, and the CSS reveals the "
        "<code>.dz-bulk-actions</code> bar; the count / select-all tri-state re-sync on "
        "change and on <code>htmx:afterSwap</code>. Sorting is delegated + state-in-DOM "
        "too: a header button (<code>[data-dz-grid-sort]</code>) cycles its column "
        "none → ascending → descending → none (state on the th's <code>aria-sort</code>, "
        "one active column), rebuilds the tbody's request query, and fires "
        "<code>dz-grid:refresh</code> so the <em>server</em> returns the re-ordered rows "
        "— no client-side row rendering. Filters and search ride the same seam: a "
        "<code>[data-dz-grid-filter]</code> select (on change) and the "
        "<code>[data-dz-grid-search]</code> box (on input, debounced) each rebuild the "
        "query and <em>compose</em> with the active sort — all read from the DOM into one "
        "query; an empty result reveals the empty-state. Note the <strong>Status</strong> "
        "filter is a teaching case: the table renders no Status column, yet the filter "
        "narrows on it — filters (like scopes) can target <em>any</em> queryable server "
        "field, not only what's displayed (here only <strong>Plan</strong> is both shown "
        "and filtered). Bulk actions post the selection safely: the "
        "<code>[data-dz-grid-bulk-action]</code> Delete button (behind its confirm dialog) "
        "sends the action + selected ids + the <em>current query</em> — so the server "
        "re-scopes and re-validates rather than trusting client ids (§15). "
        "<strong>Select all matching</strong> escalates a page selection to the whole "
        "matched query (state on the root: <code>data-dz-grid-all-matching</code> + a "
        "<code>data-dz-grid-excluded</code> JSON list of unchecked exceptions) — rows on "
        "other pages arrive selected, the count shows the server-stamped matched total "
        "(the footer's <code>data-dz-grid-total</code>), and a bulk action sends "
        "<code>all_matching_selected=true</code> + <code>excluded_ids</code> so the "
        "server applies it to the matched set minus exclusions. A filter or search "
        "change drops the mode (the matched set changed); sort and paging keep it. The footer is "
        "<em>server-rendered</em>: the client intercepts a page click, adds <code>page=</code> "
        "to the query, and the server returns that page's rows plus the repainted footer "
        "(row slice + total from one query, so they can't disagree); sort / filter / search "
        "reset to page 1. The <strong>Per page</strong> select is a windowing control on the "
        "same seam (<code>[data-dz-grid-page-size]</code> → <code>page_size=</code>): it "
        "re-pages the same matched set, resets to page 1, and — unlike a filter/search "
        "change — keeps an all-matching selection. State is <strong>URL-synced</strong> "
        "(<code>data-dz-grid-url</code>, opt-in): the grid's query mirrors into the "
        "address bar as the same human-readable params the server sees — deep links "
        "restore on load (before the hydration fetch, so no double fetch), discrete "
        "actions push history entries (Back walks grid states), the debounced search "
        "replaces, and foreign URL params survive (the grid only touches its own keys). "
        "The all-matching selection is ephemeral and deliberately NOT in the URL. "
        "The three <strong>extensions</strong> are opt-in per grid, keyed off their own "
        "seams. <em>Column visibility</em> (<code>dz-grid-cols.js</code>): the Columns "
        "<code>&lt;details&gt;</code> menu's checkboxes "
        "(<code>[data-dz-grid-col-toggle]</code>) project a hidden set onto every "
        "<code>[data-dz-col]</code> cell — header, hydrated tds, and the colgroup's "
        "<code>&lt;col&gt;</code> — persisted per grid id in localStorage; re-fetched "
        "rows re-hide on swap; stale keys prune at init. <em>Column resize</em> "
        "(<code>dz-grid-resize.js</code>): a pointer drag on the in-th handle "
        "(<code>[data-dz-grid-resize]</code>) widens <code>col[data-dz-col]</code> live "
        "(snap-8, clamp 80–800px), persists per grid, and never fires the header's "
        "sort; the table stays <code>table-layout:auto</code>, so a width is a strong "
        "hint. <em>Inline edit</em> (<code>dz-grid-edit.js</code>): dblclick a cell's "
        "display span (<code>[data-dz-grid-edit]</code> + "
        "<code>data-dz-edit-kind/-value/-label/-options</code>) to open an in-cell "
        "editor; Enter commits, Escape cancels, Tab advances — the commit is a "
        "single-field JSON <strong>PUT to the entity's standard update route</strong> "
        "(<code>data-dz-grid-edit-url</code> on the root; no bespoke field endpoint), "
        "and a <code>dz-grid:refresh</code> re-renders the row server-side. An "
        "in-flight edit survives a tbody swap: the buffer lives on the grid root, "
        "outside the morph path. "
        "(The gallery mock approximates the "
        "<code>innerMorph</code> swap with an innerHTML replace — copy the snippet into a "
        "real htmx4 app, with the idiomorph extension for <code>hx-swap=&quot;innerMorph&quot;</code>, "
        "for true morph-preserved selection.)",
        tags=("data", "interactive", "htmx"),
        exchanges=(
            Exchange(
                method="GET",
                endpoint="/app/{region}/rows?q=&sort=&dir=&page=&page_size=",
                trigger="the tbody, on `load` and on `dz-grid:refresh` (fired by a sort "
                "click, a filter change, a debounced search keystroke, or a page "
                "control) — with `page=` added for pagination",
                response="the current page's `<tr>` rows for the query — each a `dz-tr-row` "
                "carrying a stable `id` (the idiomorph morph key) plus "
                "`data-dz-grid-row-id` (the bulk-action payload anchor) — plus the repainted "
                "pagination footer (via an OOB `<nav>` or a wrapping region swap); a "
                "zero-result query returns an empty tbody so the `:has(tbody tr td)`-driven "
                "empty-state shows",
                swap="innerMorph of the tbody (`[data-dz-grid-body]`) — idiomorph keys on "
                "each row's `id`, so a live selection follows its row across a re-sort — PLUS "
                "an out-of-band update of the pagination footer: append "
                '`<nav data-dz-grid-pagination data-dz-grid-total="N" hx-swap-oob="true">…</nav>` '
                "to the response (the stamped total feeds the all-matching affordance) "
                "(or target a wrapping region that contains both the tbody and the footer in "
                'one swap). The footer\'s current-page button carries `aria-current="page"` — '
                "the client reads it back as the authoritative (possibly server-clamped) page",
                states=("loading", "empty", "populated", "error"),
            ),
            Exchange(
                method="POST",
                endpoint="/app/{region}/bulk",
                trigger="a bulk-action button (e.g. Delete), after the user approves its "
                "confirm dialog; the controller injects the selection on `htmx:configRequest`",
                response="the server RE-VALIDATES permissions and RE-SCOPES the action to "
                "the echoed query (never trusting the client `selected_ids` alone) and "
                "applies it. Two patterns: with `data-dz-grid-bulk-refresh` on the button "
                "(this demo), the response swaps NOTHING (JSON/204) and the controller "
                "re-fetches rows + footer via the normal GET; without it, put `hx-target` "
                "on the button and return the refreshed `<tr>` rows directly. "
                "When `all_matching_selected=true`, the action applies to "
                "the WHOLE matched query minus `excluded_ids` — the server re-runs the "
                "echoed query itself, and MUST strip `page`/`page_size` first (they window "
                "the display, not the matched set — re-running them verbatim would apply "
                "the action to one page only); `selected_ids` is informational (visible "
                "state) only. NB form encoding: with no exclusions the `excluded_ids` key "
                "is ABSENT from the POST (not sent empty) — default it to the empty list",
                swap="innerMorph of the tbody (`[data-dz-grid-body]`) plus the OOB footer "
                "(its `data-dz-grid-total` re-stamps the matched total)",
                states=("populated", "empty", "error"),
            ),
            Exchange(
                method="PUT",
                endpoint="/app/{entity}/{id}",
                trigger="the inline-edit extension (dz-grid-edit.js): dblclick an "
                "editable cell's display span opens an in-cell editor; Enter (or a "
                "change, for bool/select/date) commits a raw fetch PUT to "
                "`{data-dz-grid-edit-url}/{rowId}` — NOT an htmx exchange",
                response="this is the entity's STANDARD update route, not a bespoke "
                "field endpoint: the body is a single-field JSON object "
                '(`{"plan": "Pro"}`), so an all-optional update schema + '
                "exclude-unset semantics make it a partial update, and the full "
                "update gate (permissions, scoping, validation) applies. Return "
                "2xx JSON on success; any non-2xx keeps the editor open with the "
                "response text as its error. The controller then fires "
                "`dz-grid:refresh` on the tbody, so the committed value renders "
                "SERVER-side (badges/dates re-render; no client patching)",
                swap="none (raw fetch) — the follow-up `dz-grid:refresh` re-fetches "
                "rows + footer via the tbody's normal GET",
                states=("populated", "error"),
            ),
        ),
        controller="controllers/dz-grid.js",
        # The optional extension controllers (promoted from Dazzle, 0.1.26):
        # column visibility, column resize, inline cell editing — each rides
        # the grid's seams; the core grid works without any of them.
        extensions=(
            "controllers/dz-grid-cols.js",
            "controllers/dz-grid-resize.js",
            "controllers/dz-grid-edit.js",
        ),
        mock="/mock/grid",
        contracts=("contracts/grid.py", "contracts/grid_edit.py"),
        guidance=Guidance(
            seams=(
                "column visibility: dz-grid-cols.js projects the hidden set onto "
                "[data-dz-col] cells after every swap — no per-cell bindings",
                "column resize: dz-grid-resize.js rides the header cells",
                "inline edit: dz-grid-edit.js reads the [data-dz-grid-edit] display "
                "span (kind/value/label/options) — contract in contracts/grid_edit.py",
                "row identity: a row's id IS the idiomorph morph key and encodes "
                "data-dz-row-id (the bulk payload anchor)",
            ),
            pitfalls=(
                "edit state in JS objects dies on morph — the typed buffer lives on "
                "the grid root (root._dzEdit) with before/after-swap hooks",
                "select options must be JSON [[value,label],…] — producers with "
                "dicts/tuples/bare strings normalise at ONE boundary (#1573)",
                "never patch committed values client-side — commit fires "
                "dz-grid:refresh so the server re-renders badges/dates",
            ),
            do_dont=(
                (
                    "keep selection state in the DOM (.checked on the row checkbox)",
                    "mirror selection into a JS array a tbody swap would orphan",
                ),
                (
                    "return full row fragments from the grid endpoint",
                    "return cell deltas the client must splice in",
                ),
            ),
            a11y_keys=(
                "Enter commits (text/date), Escape cancels an open editor",
                "Tab / Shift-Tab commit then advance to the next/previous editable "
                "cell, wrapping to the adjacent row",
                "row checkboxes carry aria-label 'Select {row}'",
            ),
            composes_with=("button", "badge"),
        ),
    ),
    # ── Overlays (interactive — need the mock htmx / dialog) ─────────
    Hyperpart(
        "command",
        "Command palette",
        "Overlays",
        "The hx-get palette — the htmx4 flagship. Press ⌘K.",
        '<button class="dz-button" data-dz-variant="outline" data-hm-open-command>Open palette <kbd class="dz-kbd">⌘K</kbd></button>'
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
        # type="search" is an implicit `searchbox` role: it validly supports
        # aria-controls (→ the listbox) + aria-autocomplete + the JS-set
        # aria-activedescendant, so the SR follows the active option. (role=
        # combobox / aria-expanded are NOT valid on an input per ARIA-in-HTML.)
        'aria-controls="dz-command-results" aria-autocomplete="list" '
        'hx-get="/mock/command" hx-trigger="input changed delay:150ms, focus once" '
        'hx-target="next .dz-command__results">'
        '<button type="button" class="dz-command__close" data-hm-close-command '
        'aria-label="Close command palette">{svg:x}</button></div>'
        '<div class="dz-command__results" id="dz-command-results" role="listbox" aria-label="Results"></div></dialog>',
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
                states=("loading", "empty", "populated", "error"),
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
        '<button class="dz-button" data-dz-variant="destructive" hx-delete="/mock/noop" '
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
        "Disclosure menu (`<details>`) — no JS for open state. A disclosure, "
        "not a full ARIA menu: no roving tabindex or typeahead.",
        '<details class="dz-menu"><summary class="dz-button" data-dz-variant="outline">Actions ▾</summary>'
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
        "Disclosure popover (`<details>`) — free-content panel; body can "
        "lazy-load via htmx. Not a focus-trapped/positioned popover.",
        '<details class="dz-popover"><summary class="dz-button" data-dz-variant="outline">Details</summary>'
        '<div class="dz-popover__panel"><div class="hm-demo-title">Dimensions</div>'
        '<p class="hm-demo-muted">Filters, previews, quick forms.</p></div></details>',
        tags=("interactive",),
    ),
    Hyperpart(
        "tooltip",
        "Tooltip",
        "Overlays",
        "CSS-only visual hint (`data-dz-tooltip`) — zero JS. A hint, not an "
        "accessible tooltip: keep it non-critical (no touch/SR/keyboard path).",
        '<button class="dz-button" data-dz-variant="outline" data-dz-tooltip="Saved 2 minutes ago">Hover me</button>',
    ),
    Hyperpart(
        "dialog",
        "Dialog",
        "Overlays",
        "Modal on the native <dialog> — one line of JS to open, close for free "
        "(Esc / backdrop / method=dialog submit). Focus-trapped by the platform.",
        '<button class="dz-button" data-dz-variant="primary" data-dz-dialog-open="hm-dialog-demo">'
        "Delete workspace…</button>"
        '<dialog class="dz-dialog" id="hm-dialog-demo" aria-labelledby="hm-dialog-demo-title" closedby="any">'
        '<form method="dialog">'
        '<div class="dz-dialog__header">'
        '<h2 class="dz-dialog__title" id="hm-dialog-demo-title">Delete workspace?</h2>'
        '<button type="submit" class="dz-dialog__close" aria-label="Close dialog">{svg:x}</button>'
        "</div>"
        '<div class="dz-dialog__body"><p>This permanently deletes the workspace and every '
        "record in it. This action cannot be undone.</p></div>"
        '<div class="dz-dialog__footer">'
        '<button type="submit" class="dz-button" data-dz-variant="outline">Cancel</button>'
        '<button type="submit" class="dz-button" data-dz-variant="destructive" value="confirm">Delete</button>'
        "</div></form></dialog>",
        notes="Opening is the only scripted behaviour (<code>dz-dialog.js</code> calls "
        "<code>showModal()</code> for a <code>[data-dz-dialog-open]</code> trigger); closing is "
        "native. The confirm button closes the dialog and sets <code>returnValue</code> — in a "
        "real app, carry the action on it (<code>hx-delete</code> …) or submit a form to the server.",
        tags=("interactive",),
        composes=("button",),
        controller="controllers/dz-dialog.js",
    ),
    Hyperpart(
        "drawer",
        "Drawer",
        "Overlays",
        "Edge-anchored panel on the native <dialog> — a drawer with a modal's "
        "guarantees (focus trap, inert background, Esc, backdrop). Built on the "
        "dialog: shares its opener, adds a side + slide. No drawer-specific JS.",
        '<button class="dz-button" data-dz-variant="outline" data-dz-dialog-open="hm-drawer-demo">'
        "Open filters</button>"
        '<dialog class="dz-drawer" id="hm-drawer-demo" data-dz-side="right" '
        'aria-labelledby="hm-drawer-demo-title" closedby="any">'
        '<form method="dialog">'
        '<div class="dz-drawer__header">'
        '<h2 class="dz-drawer__title" id="hm-drawer-demo-title">Filters</h2>'
        '<button type="submit" class="dz-drawer__close" aria-label="Close drawer">{svg:x}</button>'
        "</div>"
        '<div class="dz-drawer__body" tabindex="0" aria-label="Drawer content">'
        "<p>Drawer content scrolls independently of the page — filters, a record "
        "preview, or a quick form live here.</p></div>"
        '<div class="dz-drawer__footer">'
        '<button type="submit" class="dz-button" data-dz-variant="ghost">Reset</button>'
        '<button type="submit" class="dz-button" data-dz-variant="primary" value="apply">Apply</button>'
        "</div></form></dialog>"
        '<button class="dz-button" data-dz-variant="outline" '
        'hx-get="/mock/drawer/detail" hx-target="#hm-drawer-lazy-body" '
        'hx-swap="innerHTML" data-dz-dialog-open="hm-drawer-lazy">'
        "Open record</button>"
        '<dialog class="dz-drawer" id="hm-drawer-lazy" data-dz-width="md" '
        'closedby="any" aria-label="Record detail">'
        '<header class="dz-drawer__header">'
        '<h2 class="dz-drawer__title">Record detail</h2>'
        '<form method="dialog">'
        '<button type="submit" class="dz-drawer__close" aria-label="Close">{svg:x}</button>'
        "</form></header>"
        '<div id="hm-drawer-lazy-body" class="dz-drawer__body">'
        "<p>Loading…</p></div>"
        "</dialog>",
        notes="Opened by the shared <code>dz-dialog.js</code> "
        "(<code>[data-dz-dialog-open]</code>); close is native (method=dialog submit, Esc, "
        "backdrop). Anchor the edge with <code>data-dz-side=&quot;right|left&quot;</code>; the "
        "panel slides in via the native <code>@starting-style</code> transition, honouring "
        "<code>prefers-reduced-motion</code>. The second trigger shows the "
        "HYPERMEDIA drawer (the Dazzle row-peek contract): one button "
        "carries both an <code>hx-get</code> targeting the drawer body and "
        "<code>data-dz-dialog-open</code> — the exchange and the opener "
        "fire together. <code>data-dz-width=&quot;sm|md|lg|xl|full&quot;</code> "
        "picks a width preset on viewports that can afford it.",
        tags=("interactive",),
        composes=("dialog", "button"),
        exchanges=(
            Exchange(
                method="GET",
                endpoint="/app/records/{id}?peek=1",
                trigger="the opener button's click — the SAME click also fires "
                "the dz-dialog.js opener (`data-dz-dialog-open`), so the drawer "
                "shows while the body loads",
                response="the record's detail body HTML — swapped into the "
                "drawer's `dz-drawer__body` target",
                swap="innerHTML",
            ),
        ),
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
        "field",
        "Field",
        "Forms",
        "The label + control + help + error triad as one accessible unit. Error "
        "state derives from aria-invalid; help/error bind via aria-describedby.",
        '<div class="hm-stack hm-measure">'
        '<div class="dz-form-field">'
        '<label class="dz-form-label" for="hm-field-email">Billing email'
        '<span class="dz-form-required">*</span></label>'
        '<input class="dz-form-input" id="hm-field-email" type="email" required '
        'placeholder="you@company.com" aria-describedby="hm-field-email-hint">'
        '<p class="dz-form-hint" id="hm-field-email-hint">Receipts and renewal notices go here.</p>'
        "</div>"
        '<div class="dz-form-field">'
        '<label class="dz-form-label" for="hm-field-slug">Workspace slug</label>'
        '<input class="dz-form-input" id="hm-field-slug" value="Acme Corp" '
        'aria-invalid="true" aria-describedby="hm-field-slug-error">'
        '<p class="dz-form-error" id="hm-field-slug-error">Use lowercase letters, numbers and hyphens only.</p>'
        "</div></div>",
        notes="Reuses the <code>dz-form-*</code> family (label / hint / input / error). The "
        "invalid field needs no modifier class — the red border keys off "
        "<code>aria-invalid=&quot;true&quot;</code>, the same attribute assistive tech reads.",
        tags=("forms",),
        # The colour widget's hex-readout mirror rides the field family
        # (delegated input listener on .dz-form-color-input; Tier F4e —
        # replaced the last inline Alpine x-data straggler).
        extensions=("controllers/dz-color.js",),
    ),
    Hyperpart(
        "slider",
        "Slider",
        "Forms",
        "Native <input type=range> — styled track + thumb, both themes, with a "
        "live value readout via a tiny delegated controller.",
        '<div class="hm-stack hm-measure">'
        '<label class="dz-form-label" for="hm-slider-vol">Volume</label>'
        '<div class="dz-form-slider-group">'
        '<input id="hm-slider-vol" type="range" data-dz-slider class="dz-form-slider" '
        'min="0" max="100" step="1" value="70">'
        '<span data-dz-range-value class="dz-form-slider-value" aria-hidden="true">70</span>'
        "</div></div>",
        notes="The track + thumb are styled for both themes with a focus ring; the native "
        "range already announces its value to assistive tech, so the visible readout is "
        "<code>aria-hidden</code>. <code>dz-slider.js</code> writes the value into "
        "<code>[data-dz-range-value]</code> on input, scoped to each slider's own group so "
        "many coexist.",
        tags=("forms",),
        controller="controllers/dz-slider.js",
    ),
    Hyperpart(
        "confirm-panel",
        "Confirm panel",
        "Forms",
        "The irreversible-action consent gate: a checklist of obligations "
        "that must be ticked before the primary action arms, plus live and "
        "revoked summary states.",
        '<div class="hm-measure">'
        '<div class="dz-confirm-panel" data-dz-state-value="off">'
        '<ul data-dz-confirm-gate class="dz-confirm-checklist" '
        'data-dz-required-count="2">'
        '<li class="dz-confirm-row" data-dz-required="true">'
        '<input type="checkbox" class="dz-confirm-checkbox" '
        'data-dz-required="true" id="dz-confirm-1">'
        '<label for="dz-confirm-1" class="dz-confirm-row-label">'
        '<span class="dz-confirm-title">I have exported a backup of live data</span>'
        '<span class="dz-confirm-caption">Rollback needs a snapshot taken '
        "today.</span>"
        "</label></li>"
        '<li class="dz-confirm-row" data-dz-required="true">'
        '<input type="checkbox" class="dz-confirm-checkbox" '
        'data-dz-required="true" id="dz-confirm-2">'
        '<label for="dz-confirm-2" class="dz-confirm-row-label">'
        '<span class="dz-confirm-title">The billing owner has approved this '
        "change</span>"
        "</label></li>"
        '<li class="dz-confirm-row" data-dz-required="false">'
        '<input type="checkbox" class="dz-confirm-checkbox" id="dz-confirm-3">'
        '<label for="dz-confirm-3" class="dz-confirm-row-label">'
        '<span class="dz-confirm-title">Notify the team afterwards '
        "(optional)</span>"
        "</label></li>"
        '<li class="dz-confirm-actions">'
        '<a href="#" class="dz-confirm-secondary">Save draft</a>'
        '<a data-dz-confirm-href="#go-live" aria-disabled="true" '
        'class="dz-confirm-primary">Go live</a>'
        "</li></ul>"
        '<p class="dz-confirm-audit">This action is recorded in the audit '
        "log with your identity and timestamp.</p>"
        "</div>"
        '<div class="dz-confirm-panel" data-dz-state-value="live">'
        '<div class="dz-confirm-summary" data-dz-confirm-tone="success">'
        '<div class="dz-confirm-summary-title">Currently live</div>'
        '<div class="dz-confirm-summary-body">Enabled 12 May by '
        "j.reyes.</div>"
        "</div>"
        '<div class="dz-confirm-actions">'
        '<a href="#" class="dz-confirm-revoke">Revoke</a>'
        "</div></div>"
        "</div>",
        notes="The gate is state-in-DOM: the primary anchor ships with "
        "<code>aria-disabled=&quot;true&quot;</code> and its destination "
        "parked in <code>data-dz-confirm-href</code>; "
        "<code>dz-confirm-gate.js</code> recounts checked "
        "<code>data-dz-required=&quot;true&quot;</code> boxes on every "
        "change inside the <code>[data-dz-confirm-gate]</code> root and "
        "promotes the href / removes <code>aria-disabled</code> only when "
        "the count meets <code>data-dz-required-count</code>. Optional "
        "boxes never gate. Zero required boxes = always armed. The live "
        "and revoked branches swap the checklist for a "
        "<code>dz-confirm-summary</code> toned via "
        "<code>data-dz-confirm-tone=&quot;success|muted&quot;</code>.",
        tags=("forms",),
        controller="controllers/dz-confirm-gate.js",
    ),
    Hyperpart(
        "search-box",
        "Search box",
        "Forms",
        "The FTS search region: a debounced search input, an aria-live "
        "results panel, and a coaching line that hides — via pure CSS — "
        "the moment the user types.",
        '<div class="dz-search-box-region hm-measure">'
        '<div class="dz-search-box-input-row">'
        '<label for="hm-search-input" class="visually-hidden">Search records</label>'
        '<input id="hm-search-input" type="search" name="q" '
        'class="dz-search-box-input" placeholder="Search records…" '
        'autocomplete="off" '
        'hx-get="/mock/search" '
        'hx-trigger="input changed delay:250ms, search" '
        'hx-target="#hm-search-results" '
        'hx-swap="innerHTML">'
        "</div>"
        '<div id="hm-search-results" class="dz-search-box-results" '
        'role="region" aria-live="polite">'
        '<div class="dz-search-box-empty">Type a title or keyword</div>'
        "</div></div>",
        notes="No JS beyond htmx: the 250ms debounce is "
        "<code>hx-trigger=&quot;input changed delay:250ms, search&quot;</code>, "
        "the results land in an <code>aria-live=&quot;polite&quot;</code> "
        "region, and the coaching line is hidden by "
        "<code>:has(input:not(:placeholder-shown))</code> — no client "
        "state. Results are server-rendered "
        "<code>dz-search-box-result</code> rows (title + per-field "
        "<code>&lt;mark&gt;</code>-highlighted snippets, count line above); "
        "the no-results state reuses <code>dz-search-box-empty</code> with "
        "the <code>--no-results</code> modifier.",
        tags=("forms", "htmx"),
        exchanges=(
            Exchange(
                method="GET",
                endpoint="/app/fts/{entity}?q=&html=1",
                trigger="the input, debounced 250ms (and the native "
                "`search` event — Esc/clear on type=search)",
                response="the results fragment: a `dz-search-box-result-count` "
                "line + a `dz-search-box-result-list` of linked rows with "
                "`<mark>`-highlighted snippets; zero hits return the "
                "`--no-results` variant of the empty line (which the CSS "
                "toggle deliberately never hides). Empty queries aren't "
                "sent (min length 1)",
                swap="innerHTML",
            ),
        ),
    ),
    Hyperpart(
        "form-chrome",
        "Form chrome",
        "Forms",
        "The structural form pieces: titled sections, the validation-error "
        "summary, and the multi-section progress stepper.",
        '<div class="hm-stack hm-measure">'
        '<div class="dz-form-errors" role="alert">'
        '<svg class="dz-form-errors-icon" xmlns="http://www.w3.org/2000/svg" '
        'fill="none" viewBox="0 0 24 24" stroke="currentColor" '
        'stroke-width="2" aria-hidden="true">'
        '<path stroke-linecap="round" stroke-linejoin="round" '
        'd="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 '
        "0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 "
        '0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"/></svg>'
        '<div class="dz-form-errors-body">'
        '<h3 class="dz-form-errors-title">Validation Error</h3>'
        '<ul class="dz-form-errors-list" role="list">'
        "<li>Name is required</li>"
        "<li>Start date must be before end date</li>"
        "</ul></div></div>"
        '<ol class="dz-form-stepper" role="list" aria-label="Form progress">'
        '<li class="dz-form-stepper-item is-not-last" aria-current="step">'
        '<span class="dz-form-stepper-circle is-active"><span>1</span></span>'
        '<span class="dz-form-stepper-label is-active">Details</span>'
        '<span class="dz-form-stepper-connector" aria-hidden="true"></span></li>'
        '<li class="dz-form-stepper-item is-not-last">'
        '<span class="dz-form-stepper-circle"><span>2</span></span>'
        '<span class="dz-form-stepper-label">Schedule</span>'
        '<span class="dz-form-stepper-connector" aria-hidden="true"></span></li>'
        '<li class="dz-form-stepper-item">'
        '<span class="dz-form-stepper-circle"><span>3</span></span>'
        '<span class="dz-form-stepper-label">Review</span></li>'
        "</ol>"
        '<section class="dz-form-section">'
        '<h3 class="dz-form-section-title">Contact details</h3>'
        '<p class="dz-form-section-note">Shown on invoices and receipts.</p>'
        '<div class="dz-form-field">'
        '<label class="dz-form-label" for="hm-fc-name">Full name'
        '<span class="dz-form-required" aria-hidden="true">*</span></label>'
        '<input id="hm-fc-name" class="dz-form-input" type="text" '
        'aria-required="true"></div>'
        "</section>"
        "</div>",
        notes="Sections are real <code>&lt;section&gt;</code>s with an "
        "<code>h3</code> title + optional note; fields inside use the HM "
        "form primitives. The error summary is "
        "<code>role=&quot;alert&quot;</code> (the server re-renders it on "
        "a failed submit). The stepper here shows RENDERED states "
        "(<code>is-active</code>/<code>is-not-last</code>, "
        "<code>aria-current=&quot;step&quot;</code>) — the live navigation "
        "behaviour is the <code>wizard</code> Hyperpart "
        "(<code>dz-wizard.js</code>; the dzWizard Alpine island retired in "
        "Tier F4d).",
        tags=("forms",),
        composes=("field",),
    ),
    Hyperpart(
        "wizard",
        "Wizard",
        "Forms",
        "Multi-stage form navigation: the stepper drives stage reveal — "
        "back freely, forward one validated step at a time.",
        '<div data-dz-wizard data-dz-step="0" class="hm-measure-lg">'
        '<ol class="dz-form-stepper" role="list" aria-label="Form progress">'
        '<li class="dz-form-stepper-item is-not-last" '
        'data-dz-state="current" aria-current="step">'
        '<button type="button" class="dz-form-stepper-button" data-dz-step-to="0">'
        '<span class="dz-form-stepper-circle is-active"><span>1</span></span>'
        '<span class="dz-form-stepper-label is-active">Details</span>'
        '<span class="visually-hidden" data-dz-step-status>current</span></button>'
        '<span class="dz-form-stepper-connector" aria-hidden="true"></span></li>'
        '<li class="dz-form-stepper-item is-not-last" data-dz-state="pending">'
        '<button type="button" class="dz-form-stepper-button" data-dz-step-to="1">'
        '<span class="dz-form-stepper-circle"><span>2</span></span>'
        '<span class="dz-form-stepper-label">Schedule</span>'
        '<span class="visually-hidden" data-dz-step-status>pending</span></button>'
        '<span class="dz-form-stepper-connector" aria-hidden="true"></span></li>'
        '<li class="dz-form-stepper-item" data-dz-state="pending">'
        '<button type="button" class="dz-form-stepper-button" data-dz-step-to="2">'
        '<span class="dz-form-stepper-circle"><span>3</span></span>'
        '<span class="dz-form-stepper-label">Review</span>'
        '<span class="visually-hidden" data-dz-step-status>pending</span></button></li>'
        "</ol>"
        '<div class="dz-wizard-stage" data-dz-stage="0">'
        '<div class="dz-form-field">'
        '<label class="dz-form-label" for="hm-wiz-name">Project name'
        '<span class="dz-form-required" aria-hidden="true">*</span></label>'
        '<input id="hm-wiz-name" class="dz-form-input" type="text" required '
        'aria-required="true"></div></div>'
        '<div class="dz-wizard-stage" data-dz-stage="1" hidden>'
        '<div class="dz-form-field">'
        '<label class="dz-form-label" for="hm-wiz-date">Start date</label>'
        '<input id="hm-wiz-date" class="dz-form-input" type="date"></div></div>'
        '<div class="dz-wizard-stage" data-dz-stage="2" hidden>'
        "<p>Review your answers, then submit.</p></div>"
        "</div>",
        notes="State-in-DOM: the root's <code>data-dz-step</code> is the "
        "current stage; stages toggle via the native <code>hidden</code> "
        "attribute; stepper items carry "
        "<code>data-dz-state=&quot;complete|current|pending&quot;</code> "
        "(the checkmark is pure CSS off the state). "
        "<code>dz-wizard.js</code> allows going BACK freely and FORWARD "
        "one step at a time — only after every required input in the "
        "current stage passes <code>reportValidity()</code>. No-JS renders "
        "stage one with numbered steps (the form still posts whole).",
        tags=("forms",),
        controller="controllers/dz-wizard.js",
        composes=("form-chrome", "field"),
    ),
    Hyperpart(
        "money",
        "Money field",
        "Forms",
        "Major-unit decimal input over a hidden minor-unit carrier — the "
        "form posts integer minor units, never floats.",
        '<div class="dz-money hm-measure" data-dz-money '
        'data-dz-currency="GBP" data-dz-scale="2">'
        '<div class="dz-form-money-group">'
        '<span class="dz-form-money-prefix" aria-hidden="true">£</span>'
        '<input type="text" inputmode="decimal" id="hm-money-input" '
        'value="15.00" class="dz-form-input dz-form-input-trailing" '
        'placeholder="0.00" aria-label="Amount (GBP)">'
        "</div>"
        '<input type="hidden" name="amount_minor" value="1500">'
        '<input type="hidden" name="amount_currency" value="GBP">'
        "</div>",
        notes="State-in-DOM: the root's <code>data-dz-scale</code> is the "
        "conversion factor; <code>dz-money.js</code> keeps the hidden "
        "<code>*_minor</code> carrier in sync on input, normalizes the "
        "display to <code>toFixed(scale)</code> on blur (empty clears the "
        "carrier), and — in selector mode — reads a currency "
        "<code>&lt;select&gt;</code>'s <code>data-scale</code>/"
        "<code>data-symbol</code> options to retune scale and prefix. The "
        "edit-mode display value is SERVER-computed from the minor "
        "carrier, so there is no client init pass.",
        tags=("forms",),
        controller="controllers/dz-money.js",
        composes=("field",),
    ),
    Hyperpart(
        "pdf",
        "PDF viewer",
        "Data",
        "The hx-pdf viewing shell: server-authorized bytes, lazy PDF.js "
        "rendering, toolbar slots for paging/zoom, URL deep-links — "
        "progressive enhancement over a download link.",
        '<section class="dz-pdf" data-dz-pdf '
        'data-dz-pdf-src="sample.pdf" '
        'data-dz-pdf-lib="https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/legacy/build/pdf.min.mjs" '
        'data-dz-pdf-worker="https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/legacy/build/pdf.worker.min.mjs">'
        '<header class="dz-pdf-toolbar" data-dz-pdf-toolbar>'
        '<button type="button" class="dz-button" data-dz-size="sm" '
        'data-dz-variant="outline" data-dz-pdf-prev>Previous</button>'
        "<label>Page "
        '<input class="dz-pdf-page-input" data-dz-pdf-page value="1" '
        'inputmode="numeric" aria-label="Page number">'
        "</label>"
        '<span class="dz-pdf-page-count" data-dz-pdf-page-count></span>'
        '<button type="button" class="dz-button" data-dz-size="sm" '
        'data-dz-variant="outline" data-dz-pdf-next>Next</button>'
        '<span class="dz-pdf-toolbar-spacer"></span>'
        '<button type="button" class="dz-button" data-dz-size="sm" '
        'data-dz-variant="outline" data-dz-pdf-zoom-out aria-label="Zoom out">−</button>'
        '<button type="button" class="dz-button" data-dz-size="sm" '
        'data-dz-variant="outline" data-dz-pdf-zoom-in aria-label="Zoom in">+</button>'
        '<button type="button" class="dz-button" data-dz-size="sm" '
        'data-dz-variant="outline" data-dz-pdf-fit-width>Fit width</button>'
        '<a href="sample.pdf" class="dz-button" data-dz-size="sm" '
        'data-dz-variant="ghost" data-dz-pdf-download-link download>Download</a>'
        "</header>"
        '<div class="dz-pdf-status" data-dz-pdf-status aria-live="polite"></div>'
        '<div class="dz-pdf-stage" data-dz-pdf-viewer tabindex="0">'
        '<noscript><a href="sample.pdf" download>Download PDF</a></noscript>'
        "</div>"
        "</section>",
        notes="The application renders the shell and CONTROLS ACCESS; "
        "PDF.js renders the document. <code>dz-pdf.js</code> lazy-loads "
        "the library as an ES module from <code>data-dz-pdf-lib</code> "
        "only when the viewer scrolls into view — no PDF bytes or engine "
        "in the bundle. In Dazzle, <code>data-dz-pdf-src</code> points at "
        "the scope-gated range proxy "
        "(<code>/_dazzle/documents/{entity}/{id}/{field}/file</code> — "
        "document access IS entity access), and PDF.js range-requests "
        "pages on demand. <code>data-dz-pdf-state=&quot;url&quot;</code> "
        "opts a viewer into <code>?dzpdf-page/?dzpdf-zoom</code> "
        "deep-links (replaceState — Back stays page navigation). Without "
        "JS the noscript download link is the whole experience. In "
        "production, VENDOR the PDF.js module — dynamic import() cannot "
        "carry SRI; the gallery's CDN pin is demo-only.",
        tags=("data", "htmx"),
        controller="controllers/dz-pdf.js",
        composes=("button",),
        exchanges=(
            Exchange(
                method="GET",
                endpoint="/_dazzle/documents/{entity}/{id}/{field}/file",
                trigger="PDF.js fetching document bytes (initial + Range "
                "requests as the user pages)",
                response="the file field's bytes — 200 whole-body or "
                "206 partial with Content-Range; opaque 404 when the "
                "record is out of scope; 416 for unsatisfiable ranges",
                swap="none (bytes consumed by the rendering engine)",
            ),
        ),
    ),
    Hyperpart(
        "two-factor",
        "Two-factor panel",
        "Forms",
        "The 2FA enrolment/settings card: QR + manual secret, the "
        "big-digit code input, recovery-code grid, and factor status "
        "rows.",
        '<div class="dz-auth-card hm-measure">'
        '<h1 class="dz-auth-card-title">Set Up 2FA</h1>'
        '<p class="dz-auth-card-subtitle">Aurora Ops</p>'
        '<h2 class="dz-auth-section-title">Authenticator App</h2>'
        '<p class="dz-auth-section-body">Scan this QR code with your '
        "authenticator app.</p>"
        '<div class="dz-auth-qr-container">'
        '<button class="dz-button" data-dz-variant="outline">Generate QR '
        "Code</button></div>"
        '<p class="dz-auth-section-body">Or enter the secret manually: '
        '<code class="dz-auth-secret-inline">JBSW Y3DP EHPK 3PXP</code></p>'
        '<form class="dz-auth-form">'
        '<div class="dz-auth-field">'
        '<label for="hm-2fa-code" class="dz-auth-label">Enter code from app</label>'
        '<input type="text" id="hm-2fa-code" inputmode="numeric" '
        'pattern="[0-9]*" maxlength="6" placeholder="000000" '
        'class="dz-auth-input-code">'
        "</div>"
        '<button type="submit" class="dz-button dz-auth-submit" '
        'data-dz-variant="primary">Verify and Enable</button>'
        "</form>"
        '<hr class="dz-auth-hr">'
        '<div class="dz-auth-recovery-alert" role="alert">'
        '<h3 class="dz-auth-recovery-alert-title">Save Your Recovery Codes</h3>'
        '<p class="dz-auth-recovery-alert-body">Store these codes in a safe '
        "place. Each code can only be used once.</p></div>"
        '<div class="dz-auth-recovery-grid">'
        '<span class="dz-auth-recovery-pill">QK2M-8Y1D</span>'
        '<span class="dz-auth-recovery-pill">HW7C-04RA</span>'
        '<span class="dz-auth-recovery-pill">ZX3N-55PT</span>'
        '<span class="dz-auth-recovery-pill">MB9E-71LQ</span>'
        "</div>"
        '<div class="dz-auth-status-row">'
        '<div class="dz-auth-status-label">Authenticator app</div>'
        '<span class="dz-badge" data-dz-tone="success">Enabled</span></div>'
        '<div class="dz-auth-status-row is-last">'
        '<div class="dz-auth-status-label">Email codes</div>'
        '<span class="dz-badge">Off</span></div>'
        '<a href="#" class="dz-auth-back-link">Back to App</a>'
        "</div>",
        notes="In Dazzle the enrolment flow is driven by ID-anchored "
        "vanilla JS (<code>dz-2fa-setup.js</code>/<code>-settings.js</code> "
        "against JSON endpoints): the QR image lands CLASSLESS in "
        "<code>dz-auth-qr-container</code> (the container styles it), "
        "recovery pills and status rows are JS-created (shown here with status badges; the Dazzle settings JS renders dz-button action controls in that slot), and the "
        "error/success alerts toggle via the native <code>hidden</code> "
        "attribute on stable ids. The code input reserves letter-spacing for six "
        "digits. Wrap full pages in <code>dz-auth-page</code> for the "
        "centered layout.",
        tags=("forms",),
        composes=("button", "badge"),
    ),
    Hyperpart(
        "search-select",
        "Search select",
        "Forms",
        "The FK typeahead: a debounced combobox whose results panel opens "
        "on focus and closes on blur — state is one aria-expanded "
        "attribute; selection is an htmx exchange per row.",
        '<div class="dz-search-select hm-measure" data-dz-widget="search_select">'
        '<input type="hidden" name="company" id="hm-ss-field" value="">'
        '<input type="text" id="hm-ss-input" class="dz-search-select-input" '
        'placeholder="Search companies…" autocomplete="off" role="combobox" '
        'aria-expanded="false" aria-controls="hm-ss-results" '
        'aria-autocomplete="list" aria-haspopup="listbox" '
        'hx-get="/mock/typeahead" '
        'hx-trigger="keyup changed delay:300ms" '
        'hx-target="#hm-ss-results" hx-params="q">'
        '<div id="hm-ss-results" role="listbox" '
        'aria-label="Company suggestions" class="dz-search-select-results">'
        '<div class="dz-search-select-prompt" role="option" aria-disabled="true">'
        "Type at least 3 characters to search..."
        "</div></div></div>",
        notes="State-in-DOM: <code>dz-search-select.js</code> flips "
        "<code>aria-expanded</code> on focusin/focusout (200ms blur grace "
        "— result rows are htmx affordances, so the click must land before "
        "the panel hides) and CSS hides the panel off the attribute. Each "
        "result row carries its own <code>hx-get</code> to a select "
        "endpoint that swaps the panel with a confirmation and fills the "
        "hidden FK input server-side. The form posts the hidden input, "
        "never the visible text.",
        tags=("forms", "htmx"),
        controller="controllers/dz-search-select.js",
        exchanges=(
            Exchange(
                method="GET",
                endpoint="/app/fragments/search?source={source}&q=",
                trigger="keyup on the combobox, debounced (`delay:{n}ms`)",
                response="result rows — each a `dz-search-result-row` div "
                "carrying its own hx-get to the select endpoint — or the "
                "`dz-search-result-empty` prompt",
                swap="innerHTML",
            ),
            Exchange(
                method="GET",
                endpoint="/app/fragments/select?source={source}&id={id}",
                trigger="a click on a result row",
                response="the `dz-select-result-confirm` line replacing the "
                "panel contents (the hidden FK input is set alongside)",
                swap="innerHTML",
            ),
        ),
    ),
    Hyperpart(
        "combobox",
        "Combobox",
        "Forms",
        "Searchable enum single-select — a native <select> progressively "
        "enhanced into a type-to-filter combobox. JS off: a fully usable "
        "select. JS on: a searchable role=combobox overlay; the native "
        "select stays as the submitted value.",
        '<label class="dz-field hm-measure" for="hm-cb-field">'
        '<span class="dz-field__label">Priority</span>'
        '<select id="hm-cb-field" name="priority" '
        'data-dz-combobox class="dz-form-input">'
        '<option value="">Select a priority…</option>'
        '<option value="low">Low</option>'
        '<option value="medium" selected>Medium</option>'
        '<option value="high">High</option>'
        '<option value="urgent">Urgent</option>'
        "</select></label>",
        notes="Progressive enhancement: the server renders a real "
        "<code>&lt;select data-dz-combobox&gt;</code> with all its options "
        "(placeholder first) — usable and submittable with no JS, native "
        "<code>required</code> intact. On first interaction "
        "<code>dz-combobox.js</code> builds a sibling overlay: a "
        "<code>role=&quot;combobox&quot;</code> input + a "
        "<code>role=&quot;listbox&quot;</code> of the options, hiding the "
        "native select (kept in the DOM as the submitted value). State is "
        "in the DOM — <code>data-dz-open</code> on the root (CSS hides the "
        "listbox off it), <code>aria-expanded</code> mirrored on the input. "
        "Typing filters (substring, case-insensitive); Up/Down move "
        "<code>aria-activedescendant</code>; Enter/click selects (writes the "
        "native select + fires <code>change</code>); Esc closes; focus "
        "leaving the widget closes after a 200ms grace.",
        tags=("forms",),
        controller="controllers/dz-combobox.js",
    ),
    Hyperpart(
        "tags",
        "Tags",
        "Forms",
        "Multi-value chips + free create — a native text input carrying a "
        "comma-joined value, progressively enhanced into a chips UI. JS off: "
        "a usable comma-separated text field. JS on: type + Enter/comma "
        "creates a chip, × removes; the native input stays as the submitted "
        "value.",
        '<label class="dz-field hm-measure" for="hm-tags-field">'
        '<span class="dz-field__label">Labels</span>'
        '<input id="hm-tags-field" name="labels" type="text" '
        'data-dz-tags class="dz-form-input" value="urgent,backend" '
        'placeholder="Add a label…"></label>',
        notes="Progressive enhancement: the server renders a plain "
        "<code>&lt;input type=&quot;text&quot; data-dz-tags&gt;</code> whose "
        "value is a COMMA-JOINED tag string — usable and submittable with no "
        "JS (type <code>a, b, c</code>; the server splits on comma), native "
        "<code>required</code> intact. On first interaction "
        "<code>dz-tags.js</code> wraps it in a <code>.dz-tags</code> root — a "
        "<code>role=&quot;list&quot;</code> of removable chips + a borderless "
        "entry — and hides the native input (kept in the DOM as the submitted "
        "value). Every add/remove rewrites the native input to the "
        "comma-joined chip list and fires <code>change</code>, so the submit "
        "shape never changes. Type + Enter or comma creates a chip "
        "(trim/dedup/skip-empty); paste splits on comma/newline; × or "
        "Backspace-on-empty removes a chip; add/remove is announced via a "
        "visually-hidden <code>aria-live</code> region.",
        tags=("forms",),
        controller="controllers/dz-tags.js",
    ),
    Hyperpart(
        "date-range",
        "Date range",
        "Forms",
        "Two native date inputs driving one htmx exchange — the from/to "
        "filter bar for time-scoped regions.",
        '<div class="dz-date-range-picker date-range-bar">'
        '<label class="dz-date-range-label" for="hm-dr-from">From</label>'
        '<input type="date" id="hm-dr-from" name="date_from" value="2026-06-01" '
        'class="dz-date-range-input" hx-get="/mock/search" '
        'hx-target="#hm-dr-out" hx-swap="innerHTML" '
        'hx-include="closest .date-range-bar">'
        '<label class="dz-date-range-label" for="hm-dr-to">To</label>'
        '<input type="date" id="hm-dr-to" name="date_to" value="2026-06-30" '
        'class="dz-date-range-input" hx-get="/mock/search" '
        'hx-target="#hm-dr-out" hx-swap="innerHTML" '
        'hx-include="closest .date-range-bar">'
        '<div id="hm-dr-out" hidden></div>'
        "</div>",
        notes="Native <code>type=&quot;date&quot;</code> inputs — no picker "
        "JS. Each input fires the region's hx-get on change and "
        "<code>hx-include=&quot;closest .date-range-bar&quot;</code> sends "
        "BOTH bounds every time, so the server always sees the full range.",
        tags=("forms", "htmx"),
        exchanges=(
            Exchange(
                method="GET",
                endpoint="/app/{region}?date_from=&date_to=",
                trigger="either date input's change — hx-include sends both bounds",
                response="the re-rendered region body for the new range",
                swap="innerHTML",
            ),
        ),
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
        "accordion",
        "Accordion",
        "Navigation",
        "Native <details> group; single-open via the HTML name= attribute — "
        "opening one closes its siblings, zero JS.",
        '<div class="dz-accordion">'
        '<details class="dz-accordion__item" name="hm-acc" open>'
        '<summary class="dz-accordion__trigger">What is a Hyperpart?</summary>'
        '<div class="dz-accordion__panel">A server-rendered partial plus its exchange '
        "contract — the htmx-native unit of reuse.</div></details>"
        '<details class="dz-accordion__item" name="hm-acc">'
        '<summary class="dz-accordion__trigger">Do I need a client framework?</summary>'
        '<div class="dz-accordion__panel">No — state lives on the server and htmx swaps the markup.</div></details>'
        '<details class="dz-accordion__item" name="hm-acc">'
        '<summary class="dz-accordion__trigger">Can two panels be open at once?</summary>'
        '<div class="dz-accordion__panel">Not while they share a name=. Drop the attribute for an '
        "independent, multi-open group.</div></details></div>",
        notes="Exclusivity is the native <code>name</code> attribute on "
        "<code>&lt;details&gt;</code> — the browser closes the open sibling for you. No "
        "<code>aria-expanded</code> wiring: <code>&lt;details&gt;/&lt;summary&gt;</code> carry it.",
        tags=("interactive",),
    ),
    Hyperpart(
        "tabs",
        "Tabs",
        "Navigation",
        "A lazy tab strip — an honest link-strip (buttons + aria-current, no "
        "unkept role=tablist). Each panel hx-gets its content the first time it "
        "is shown.",
        '<div class="dz-tabs">'
        '<div class="dz-tabs__list">'
        '<button class="dz-tabs__tab" aria-current="true" data-dz-tab-target="hm-tab-overview">Overview</button>'
        '<button class="dz-tabs__tab" data-dz-tab-target="hm-tab-activity">Activity</button>'
        '<button class="dz-tabs__tab" data-dz-tab-target="hm-tab-settings">Settings</button>'
        "</div>"
        '<div id="hm-tab-overview" class="dz-tabs__panel">'
        '<p class="hm-demo-muted">Active on the Pro plan, renewing 1 August.</p></div>'
        '<div id="hm-tab-activity" class="dz-tabs__panel" hidden '
        'hx-get="/mock/tabs/activity" hx-trigger="intersect once" hx-swap="innerHTML">'
        '<div class="dz-tabs__loading">{svg:loader-circle}</div></div>'
        '<div id="hm-tab-settings" class="dz-tabs__panel" hidden '
        'hx-get="/mock/tabs/settings" hx-trigger="intersect once" hx-swap="innerHTML">'
        '<div class="dz-tabs__loading">{svg:loader-circle}</div></div>'
        "</div>",
        notes="The tabs are <code>&lt;button&gt;</code>s with <code>aria-current</code> — no "
        "<code>role=tablist</code> without the roving-tabindex/arrow-key contract to back it "
        "(honest, like the menu). <code>dz-tabs.js</code> reveals the chosen panel scoped to "
        "its <code>.dz-tabs</code> root; showing a hidden panel triggers its "
        "<code>intersect once</code> lazy load. The first panel is eager (content inline).",
        tags=("interactive", "htmx"),
        exchanges=(
            Exchange(
                method="GET",
                endpoint="/app/{region}/{tab}",
                trigger="a panel, the first time it is revealed (`intersect once`); an eager panel on `load`",
                response="the panel's content fragment (rows, a form, a chart — whatever the tab shows)",
                swap="innerHTML of the panel itself (no hx-target)",
                states=("loading", "populated", "error"),
            ),
        ),
        controller="controllers/dz-tabs.js",
        mock="/mock/tabs",
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
        '<div class="hm-stack hm-measure">'
        '<div class="dz-progress" role="progressbar" aria-label="Storage used" aria-valuenow="62" aria-valuemin="0" aria-valuemax="100"><div class="dz-progress__bar" style="--dz-progress-value:62%"></div></div>'
        '<div class="dz-progress" data-dz-tone="success" role="progressbar" aria-label="Upload progress" aria-valuenow="100" aria-valuemin="0" aria-valuemax="100"><div class="dz-progress__bar" style="--dz-progress-value:100%"></div></div></div>',
    ),
    Hyperpart(
        "skeleton",
        "Skeleton",
        "Feedback",
        "Loading placeholder with a lifecycle-driven sheen (TASTE-9) — drop it "
        "into a swap target while the request is in flight.",
        '<div class="dz-card dz-card-body hm-measure hm-stack" aria-hidden="true">'
        '<div class="hm-demo-row">'
        '<div class="dz-skeleton" data-dz-shape="circle"></div>'
        '<div class="hm-grow hm-stack">'
        '<div class="dz-skeleton" data-dz-shape="text"></div>'
        '<div class="dz-skeleton" data-dz-shape="text"></div>'
        "</div></div>"
        '<div class="dz-skeleton" data-dz-shape="block"></div></div>',
        notes="Purely decorative, so the placeholder region is <code>aria-hidden</code>; announce "
        "&ldquo;loading&rdquo; on the live region that owns the swap. Shapes: "
        "<code>data-dz-shape=&quot;text|circle|block&quot;</code>. The sheen honours "
        "<code>prefers-reduced-motion</code>.",
    ),
    Hyperpart(
        "empty-state",
        "Empty state",
        "Feedback",
        "Icon + one sentence + primary action — never a bare 'No X'.",
        '<div class="dz-card dz-card-body hm-measure"><div class="dz-empty-state">'
        '<span class="dz-empty-state__icon">{svg:inbox}</span>'
        '<h3 class="dz-empty-state__title">No invoices yet</h3>'
        '<p class="dz-empty-state__description">Create your first invoice to get started.</p>'
        '<div class="dz-empty-state__action"><a class="dz-button" data-dz-variant="primary" href="#">New Invoice</a></div></div></div>',
    ),
    # ── Composites (Hyperparts built FROM other Hyperparts) ──────────
    Hyperpart(
        "toolbar",
        "Toolbar",
        "Composites",
        "Inline composition — real button, toggle-group and menu markup nested "
        "in a role=toolbar bar. No client tree, no props: composition is HTML.",
        '<div class="dz-toolbar" role="toolbar" aria-label="Editor actions">'
        '<button class="dz-button" data-dz-variant="primary">{icon:circle-plus} New</button>'
        '<div class="dz-toggle-group" role="radiogroup" aria-label="View">'
        '<label><input type="radio" name="tb-view" checked><span>List</span></label>'
        '<label><input type="radio" name="tb-view"><span>Grid</span></label>'
        "</div>"
        '<details class="dz-menu"><summary class="dz-button" data-dz-variant="outline">More ▾</summary>'
        '<div class="dz-menu__panel">'
        '<button class="dz-menu__item">{icon:copy} Duplicate</button>'
        '<button class="dz-menu__item" data-dz-tone="destructive">{icon:trash-2} Delete</button>'
        "</div></details></div>",
        notes="The dependency chips aggregate what the children need (here: Sprite, "
        "from the menu/button icons). Copy the whole thing — it is just nested markup.",
        tags=("composite",),
        composes=("button", "toggle-group", "menu"),
    ),
    Hyperpart(
        "master-detail",
        "Master–detail",
        "Composites",
        "Exchange composition — a list item hx-gets its detail card into the "
        "detail pane. The canonical htmx composite; two can coexist on a page.",
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
        '<div class="dz-card-delta">Paid · 2 days ago</div></div></div></div>',
        notes="The detail pane loads a card fragment via hx-get; dz-master-detail.js "
        "sets aria-current on the chosen item, scoped to THIS root so two coexist.",
        tags=("composite", "htmx"),
        exchanges=(
            Exchange(
                method="GET",
                endpoint="/app/master-detail/{id}",
                trigger="a list item, on click",
                response='a detail card fragment — `<div class="dz-card dz-card-body">…`',
                swap="innerHTML of the sibling `.dz-master-detail__detail` pane",
                states=("loading", "populated", "error"),
            ),
        ),
        controller="controllers/dz-master-detail.js",
        mock="/mock/master-detail",
        composes=("card",),
    ),
    # ── Layout ───────────────────────────────────────────────────────
    # The Every-Layout vocabulary as CSS-only Hyperparts: intrinsic,
    # media-query-free responsiveness. Variants ride data-dz-* attributes;
    # the consumer-set knobs (--dz-sidebar-width, --dz-grid-min) are
    # PUBLIC_CSS_PROPS, so they follow the namespace prefix.
    Hyperpart(
        "stack",
        "Stack",
        "Layout",
        "Vertical rhythm: children flow top-to-bottom with one gap token. "
        "The workhorse — most page sections are a stack of stacks.",
        '<div class="dz-stack" data-dz-gap="md">'
        '<div class="hm-demo-box">One</div>'
        '<div class="hm-demo-box">Two</div>'
        '<div class="hm-demo-box">Three</div>'
        "</div>",
        notes="Flex column + <code>gap</code> — margins stay on the children's "
        "insides, so any fragment composes without margin-collapse surprises. "
        "<code>data-dz-gap</code> takes <code>xs|sm|md|lg|xl</code> (the spacing "
        "token scale); unset = <code>md</code>. Nest freely: a stack inside a "
        "stack is the normal way to vary rhythm between groups.",
        tags=("layout",),
    ),
    Hyperpart(
        "cluster",
        "Cluster",
        "Layout",
        "A wrapping horizontal group — buttons, chips, metadata rows. Items "
        "keep their size and wrap when the line runs out.",
        '<div class="dz-cluster" data-dz-gap="sm">'
        '<button class="dz-button" data-dz-variant="primary">Save</button>'
        '<button class="dz-button" data-dz-variant="outline">Cancel</button>'
        '<span class="dz-badge" data-dz-tone="neutral">Draft</span>'
        "</div>",
        notes="Flex row + <code>flex-wrap</code> + <code>gap</code>. "
        "<code>data-dz-gap</code> as on stack. <code>data-dz-align</code> "
        "(<code>center|start|end|baseline</code>, default center) sets "
        "cross-axis alignment; <code>data-dz-justify</code> "
        "(<code>start|end|between|center</code>, default start) distributes "
        "the line. Never fixes widths — that's what makes it safe for "
        "translation-length and zoom changes.",
        tags=("layout",),
    ),
    Hyperpart(
        "sidebar-layout",
        "Sidebar",
        "Layout",
        "Two panes: a fixed-ish side and a fluid content pane that wraps "
        "UNDER the side when it would get too narrow — responsive without a "
        "media query.",
        '<div class="dz-sidebar-layout" style="--dz-sidebar-width: 12rem">'
        '<div class="hm-demo-box">Side (12rem)</div>'
        '<div class="hm-demo-box">Content — wraps under the side when '
        "narrower than its minimum comfortable width.</div>"
        "</div>",
        notes="The Every-Layout sidebar: flex + wrap; the side gets "
        "<code>flex-basis: var(--dz-sidebar-width)</code> (a PUBLIC knob — "
        "set it inline or at :root), the content gets "
        "<code>flex-grow: 999</code> with "
        "<code>min-inline-size: var(--dz-sidebar-content-min, 50%)</code> — "
        "when the content can't hold that minimum on the line, it wraps to a "
        'full-width row. <code>data-dz-side="end"</code> puts the side '
        "after the content. No media query: the breakpoint is the CONTENT'S "
        "minimum, so the same markup works in a page, a card, or a drawer.",
        tags=("layout",),
    ),
    Hyperpart(
        "auto-grid",
        "Auto grid",
        "Layout",
        "A responsive card grid with no breakpoints: columns pack to fit, "
        "each at least the minimum width, all equal.",
        '<div class="dz-auto-grid" style="--dz-grid-min: 9rem">'
        '<div class="hm-demo-box">A</div><div class="hm-demo-box">B</div>'
        '<div class="hm-demo-box">C</div><div class="hm-demo-box">D</div>'
        '<div class="hm-demo-box">E</div>'
        "</div>",
        notes="<code>grid-template-columns: repeat(auto-fit, "
        "minmax(min(var(--dz-grid-min, 14rem), 100%), 1fr))</code> — the "
        "inner <code>min()</code> stops overflow when the container is "
        "narrower than the minimum (the classic auto-fit footgun). "
        "<code>--dz-grid-min</code> is a PUBLIC knob; gap rides "
        "<code>data-dz-gap</code> as on stack.",
        tags=("layout",),
    ),
    Hyperpart(
        "center",
        "Center",
        "Layout",
        "A measure-capped, centred column — reading width for prose and forms.",
        '<div class="dz-center" data-dz-measure="prose">'
        '<p class="hm-demo-muted">A comfortable reading measure tops out '
        "around 65 characters; this block centres itself and caps its width "
        "so lines stay scannable on any screen.</p>"
        "</div>",
        notes="<code>margin-inline: auto</code> + <code>max-inline-size</code>. "
        "<code>data-dz-measure</code>: <code>prose</code> (65ch), "
        "<code>wide</code> (90ch), <code>full</code> (no cap, still a "
        "centring context). This is the published form of the measure the "
        "gallery's own chrome uses.",
        tags=("layout",),
    ),
    Hyperpart(
        "app-shell",
        "App shell",
        "Composites",
        "The SaaS/admin application frame: persistent left navigation, an "
        "optional sticky top bar, a routed main workspace, and a "
        "responsive/collapsible sidebar whose state the server renders.",
        # The FULL motif (routed navigation, whole sidebar anatomy) lives on
        # the saas-shell Blueprint; the builder frames this demo (framed=True).
        '<div class="dz-app-shell" data-dz-sidebar="open">'
        '<aside class="dz-app-sidebar" id="dz-app-sidebar">'
        '<div class="dz-sidebar">'
        '<div class="dz-sidebar-brand"><span class="dz-sidebar-brand-text">Acme Ops</span></div>'
        '<nav class="dz-sidebar-nav" aria-label="Primary">'
        '<ul class="dz-sidebar-nav-list">'
        '<li><a class="dz-sidebar-nav-link" aria-current="page" href="#">'
        '<span class="dz-sidebar-nav-icon">{svg:layout-dashboard}</span>'
        '<span class="dz-sidebar-nav-label">Dashboard</span></a></li>'
        '<li><a class="dz-sidebar-nav-link" href="#">'
        '<span class="dz-sidebar-nav-icon">{svg:receipt}</span>'
        '<span class="dz-sidebar-nav-label">Invoices</span></a></li>'
        "</ul></nav></div></aside>"
        '<div class="dz-app-content">'
        '<header class="dz-app-header">'
        '<div class="dz-topbar">'
        '<div class="dz-topbar-leading">'
        '<button type="button" class="dz-sidebar-toggle" data-dz-sidebar-toggle '
        'aria-expanded="true" aria-controls="dz-app-sidebar" aria-label="Toggle navigation">'
        '<span class="dz-sidebar-toggle__icon" aria-hidden="true"></span></button>'
        "</div>"
        '<div class="dz-topbar-title"><span class="dz-topbar-title-text">Dashboard</span></div>'
        '<div class="dz-topbar-trailing">'
        '<button type="button" class="dz-icon-button" aria-label="Notifications">'
        "{svg:triangle-alert}</button></div>"
        "</div></header>"
        # a <div> here, NOT <main>: this demo embeds in the gallery page,
        # which already has its own <main> (one visible main per document).
        # In a real app the workspace slot IS <main id="main-content"> —
        # the saas-shell Blueprint (its own document) shows the true form.
        '<div class="dz-app-main">'
        '<p class="hm-demo-muted">The routed workspace. The hamburger collapses '
        "the sidebar; the state persists via a cookie so the server renders it "
        "correctly on the next request.</p>"
        "</div></div></div>",
        notes="The shell root carries <code>data-dz-sidebar=&quot;open|closed&quot;</code> "
        "— SERVER-rendered from the <code>dz_sidebar</code> cookie, so first "
        "paint is correct with no flash; <code>dz-app-shell.js</code> flips the "
        "attribute and re-writes the cookie when "
        "<code>[data-dz-sidebar-toggle]</code> is clicked (and mirrors "
        "<code>aria-expanded</code>). Desktop (≥64rem): the sidebar is "
        "persistent and the content pane pads around it; narrow: it slides "
        "off-canvas and overlays (this component owns that media query "
        "deliberately — viewport policy, not intrinsic wrapping — the layout "
        "primitives inside stay media-query-free). The demo above is a "
        "standalone page embedded via iframe (its own browsing context, so "
        "the fixed sidebar behaves exactly as shipped) — the snippet below "
        "is the pure, copyable "
        "shell markup, with one embedding concession: the workspace slot is "
        "a <code>&lt;div&gt;</code> here because this demo lives inside the "
        "gallery's own <code>&lt;main&gt;</code>; in your app it is "
        "<code>&lt;main id=&quot;main-content&quot;&gt;</code> (one visible "
        "main per document — the Blueprint shows the true form). The full "
        "motif — routed "
        "navigation swapping the main slot — is the "
        '<a href="blueprints/saas-shell.html">saas-shell Blueprint</a>.',
        tags=("composite", "shell"),
        controller="controllers/dz-app-shell.js",
        framed=True,
    ),
    Hyperpart(
        "status-list",
        "Status list",
        "Data",
        "System / check states as an icon + title + caption list — tone rides "
        "data-dz-state per row, never colour alone.",
        '<div class="dz-status-list-region hm-measure-lg">'
        '<ul class="dz-status-list" data-dz-entry-count="3">'
        '<li class="dz-status-list-entry" data-dz-state="success">'
        '<span class="dz-status-list-icon" aria-hidden="true">{svg:circle-check}</span>'
        '<div class="dz-status-list-text">'
        '<div class="dz-status-list-title">Payments API</div>'
        '<div class="dz-status-list-caption">Operational · 99.99% this month</div></div>'
        '<span class="dz-status-list-pill">success</span></li>'
        '<li class="dz-status-list-entry" data-dz-state="warning">'
        '<span class="dz-status-list-icon" aria-hidden="true">{svg:triangle-alert}</span>'
        '<div class="dz-status-list-text">'
        '<div class="dz-status-list-title">Webhooks</div>'
        '<div class="dz-status-list-caption">Elevated retries since 09:20</div></div>'
        '<span class="dz-status-list-pill">warning</span></li>'
        '<li class="dz-status-list-entry" data-dz-state="neutral">'
        '<span class="dz-status-list-icon-spacer" aria-hidden="true"></span>'
        '<div class="dz-status-list-text">'
        '<div class="dz-status-list-title">Nightly export</div>'
        '<div class="dz-status-list-caption">Scheduled 02:00</div></div></li>'
        "</ul></div>",
        notes="Per-row state is <code>data-dz-state</code> on the entry (the "
        "pill repeats it as text for WCAG 1.4.1); a neutral row has no pill "
        "and an icon SPACER keeps the text column aligned. The wrapper's "
        "<code>data-dz-entry-count</code> is the server's row count — "
        "handy for e2e assertions without counting DOM.",
        tags=("data",),
    ),
    Hyperpart(
        "action-grid",
        "Action grid",
        "Data",
        "Tone-tinted CTA cards with a count badge — the dashboard's "
        "'what needs doing' surface. Cards with a URL are anchors; the grid "
        "packs intrinsically.",
        '<div class="dz-action-grid-region">'
        '<div class="dz-action-grid">'
        '<a class="dz-action-card" data-dz-tone="warning" href="#">'
        '<div class="dz-action-card-row">'
        '<span class="dz-action-card-icon">{svg:triangle-alert}</span>'
        '<span class="dz-action-card-count" data-dz-tone-badge="warning">3</span></div>'
        '<span class="dz-action-card-label">Overdue invoices</span></a>'
        '<a class="dz-action-card" data-dz-tone="accent" href="#">'
        '<div class="dz-action-card-row">'
        '<span class="dz-action-card-icon">{svg:receipt}</span>'
        '<span class="dz-action-card-count" data-dz-tone-badge="accent">12</span></div>'
        '<span class="dz-action-card-label">Awaiting approval</span></a>'
        '<div class="dz-action-card" data-dz-tone="neutral">'
        '<div class="dz-action-card-row">'
        '<span class="dz-action-card-icon-spacer"></span></div>'
        '<span class="dz-action-card-label">Nothing else today</span></div>'
        "</div></div>",
        notes="Tone tints the card surface via <code>data-dz-tone</code> and "
        "the count badge via <code>data-dz-tone-badge</code>. A URL makes "
        "the card an <code>&lt;a&gt;</code> (whole card = the target); "
        "without one it renders a static <code>&lt;div&gt;</code>. An icon "
        "SPACER holds the row height when a card has no icon.",
        tags=("data",),
    ),
    Hyperpart(
        "queue",
        "Queue",
        "Data",
        "The worklist: a count, roll-up metrics, and attention-flagged rows — "
        "the triage surface for SLA-driven work.",
        '<div class="dz-queue-region hm-measure-lg">'
        '<div class="dz-queue-count-row">'
        '<span class="dz-queue-count">7</span><span>open items</span></div>'
        '<div class="dz-queue-metrics">'
        '<div class="dz-queue-metric">'
        '<div class="dz-queue-metric-value">2</div>'
        '<div class="dz-queue-metric-label">breaching today</div></div>'
        '<div class="dz-queue-metric">'
        '<div class="dz-queue-metric-value">4h</div>'
        '<div class="dz-queue-metric-label">median age</div></div></div>'
        '<ul class="dz-queue-rows">'
        '<li class="dz-queue-row" data-dz-attn="critical">'
        '<div class="dz-queue-row-main">'
        '<div class="dz-queue-row-headline">'
        '<span class="dz-queue-row-title">Refund request — Acme</span></div>'
        '<p class="dz-queue-row-attn">SLA breaches at 16:00 — assign now.</p>'
        '<span class="dz-queue-row-date">2h left</span></div></li>'
        '<li class="dz-queue-row">'
        '<div class="dz-queue-row-main">'
        '<div class="dz-queue-row-headline">'
        '<span class="dz-queue-row-title">KYC review — Globex</span></div>'
        '<span class="dz-queue-row-date">due tomorrow</span></div></li>'
        "</ul></div>",
        notes="Attention rows carry <code>data-dz-attn=&quot;&lt;level&gt;&quot;</code> "
        "plus a human message (<code>dz-queue-row-attn</code>) — the flag is "
        "never colour-only. Counts and metrics are SERVER-rendered rollups "
        "(the same query that produced the rows, so they can't disagree).",
        tags=("data",),
    ),
    Hyperpart(
        "kanban",
        "Kanban",
        "Data",
        "Status columns of cards — the flow view. Columns show a count; "
        "overflowing boards offer a server-rendered Load-all.",
        '<div class="dz-kanban-board">'
        '<div class="dz-kanban-column">'
        '<div class="dz-kanban-column-head">'
        '<span class="dz-badge" data-dz-tone="neutral">Open</span>'
        '<span class="dz-kanban-column-count">2</span></div>'
        '<div class="dz-kanban-stack">'
        '<div class="dz-kanban-card">'
        '<div class="dz-kanban-card-body">'
        '<h4 class="dz-kanban-card-title">Refund request — Acme</h4>'
        '<p class="dz-kanban-card-field">£1,250 · assigned to Ada</p>'
        '<p class="dz-kanban-card-attn" data-dz-attn="critical">SLA breaches at 16:00</p>'
        "</div></div>"
        '<div class="dz-kanban-card">'
        '<div class="dz-kanban-card-body">'
        '<h4 class="dz-kanban-card-title">KYC review — Globex</h4>'
        '<p class="dz-kanban-card-field">due tomorrow</p>'
        "</div></div></div></div>"
        '<div class="dz-kanban-column">'
        '<div class="dz-kanban-column-head">'
        '<span class="dz-badge" data-dz-tone="info">In progress</span>'
        '<span class="dz-kanban-column-count">1</span></div>'
        '<div class="dz-kanban-stack">'
        '<div class="dz-kanban-card">'
        '<div class="dz-kanban-card-body">'
        '<h4 class="dz-kanban-card-title">Chargeback — Initech</h4>'
        '<p class="dz-kanban-card-field">evidence uploaded</p>'
        "</div></div></div></div>"
        '<div class="dz-kanban-column">'
        '<div class="dz-kanban-column-head">'
        '<span class="dz-badge" data-dz-tone="success">'
        '<span class="dz-badge-icon">{svg:circle-check}</span>Done</span>'
        '<span class="dz-kanban-column-count">0</span></div>'
        '<div class="dz-kanban-stack">'
        '<p class="dz-kanban-empty">Nothing here yet.</p>'
        "</div></div></div>",
        notes="Cards are SERVER-rendered — a drag-and-drop extension is a "
        "future controller on these seams, not a client state graph. "
        "Attention text carries <code>data-dz-attn=&quot;&lt;level&gt;&quot;</code> "
        "(critical/warning/notice — the same attn contract the timeline's "
        "bullets and the queue's rows use). An overflowing board renders a "
        "<code>dz-kanban-load-all</code> button whose <code>hx-get</code> "
        "re-fetches the region at full page size.",
        tags=("data",),
    ),
    Hyperpart(
        "timeline",
        "Timeline",
        "Data",
        "Dated events on a vertical line — bullets carry the attention "
        "contract, dates keep a fixed column so titles align.",
        '<div class="dz-timeline-region hm-measure-lg">'
        '<ul class="dz-timeline-list">'
        '<li class="dz-timeline-item">'
        '<span class="dz-timeline-bullet-wrap">'
        '<svg class="dz-timeline-bullet dz-attn-bullet dz-attn-tone-critical" '
        'fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">'
        '<circle cx="10" cy="10" r="6"/></svg></span>'
        '<div class="dz-timeline-row">'
        '<div class="dz-timeline-date">Today</div>'
        '<div class="dz-timeline-content">'
        '<p class="dz-timeline-title">Payment failed — retry scheduled</p>'
        '<p class="dz-timeline-field">Card declined (insufficient funds)</p>'
        "</div></div></li>"
        '<li class="dz-timeline-item">'
        '<span class="dz-timeline-bullet-wrap">'
        '<svg class="dz-timeline-bullet dz-attn-bullet dz-attn-tone-default" '
        'fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">'
        '<circle cx="10" cy="10" r="6"/></svg></span>'
        '<div class="dz-timeline-row">'
        '<div class="dz-timeline-date">Mon</div>'
        '<div class="dz-timeline-content">'
        '<p class="dz-timeline-title">Invoice sent</p>'
        "</div></div></li>"
        "</ul></div>",
        notes="The bullet is an inline SVG on <code>currentColor</code>, "
        "toned by <code>dz-attn-tone-*</code> (critical/warning/notice/"
        "default) — the shared attention vocabulary. Overflowing timelines "
        "append a <code>dz-timeline-overflow</code> count line.",
        tags=("data",),
    ),
    Hyperpart(
        "activity-feed",
        "Activity feed",
        "Data",
        "Who-did-what rows on a dotted spine — actor, time, and a message bubble.",
        '<div class="hm-measure-lg">'
        '<ul class="dz-activity-feed">'
        '<li class="dz-activity-row">'
        '<span class="dz-activity-dot">'
        '<svg fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">'
        '<circle cx="10" cy="10" r="6"/></svg></span>'
        '<div class="dz-activity-row-inner">'
        '<div class="dz-activity-time">09:41</div>'
        '<div class="dz-activity-bubble">'
        '<span class="dz-activity-actor">Ada</span> approved the refund.'
        "</div></div></li>"
        '<li class="dz-activity-row">'
        '<span class="dz-activity-dot">'
        '<svg fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">'
        '<circle cx="10" cy="10" r="6"/></svg></span>'
        '<div class="dz-activity-row-inner">'
        '<div class="dz-activity-time">09:12</div>'
        '<div class="dz-activity-bubble">'
        '<span class="dz-activity-actor">System</span> flagged the account '
        "for review.</div></div></li>"
        "</ul></div>",
        notes="Rows are server-rendered newest-first; an empty feed renders "
        "<code>dz-activity-empty</code>. The dot column and bubble keep "
        "alignment without a grid — the row is the flex unit.",
        tags=("data",),
    ),
    Hyperpart(
        "related-tables",
        "Related records",
        "Data",
        "A detail view's companions: tabbed groups of related records — "
        "status cards, a compact table, or a file list — each tab counted.",
        '<div class="dz-related-group hm-measure-lg">'
        '<div class="dz-tabs">'
        '<div class="dz-tabs__list">'
        '<button type="button" class="dz-tabs__tab" aria-current="true" '
        'data-dz-tab-target="hm-rel-invoices">Invoices'
        '<span class="dz-related-tab-count">2</span></button>'
        '<button type="button" class="dz-tabs__tab" '
        'data-dz-tab-target="hm-rel-files">Files'
        '<span class="dz-related-tab-count">1</span></button>'
        "</div>"
        '<div id="hm-rel-invoices" class="dz-tabs__panel">'
        '<div class="dz-related-status-grid">'
        '<div class="dz-related-status-card">'
        '<div class="dz-related-status-card-row">'
        '<div class="dz-related-status-card-text">'
        '<span class="dz-related-status-card-primary">INV-001 · £1,250</span>'
        '<span class="dz-related-status-card-secondary">due 12 Jul</span></div>'
        '<span class="dz-related-status-card-badge">'
        '<span class="dz-badge" data-dz-tone="success">Paid</span></span>'
        "</div></div>"
        '<div class="dz-related-status-card">'
        '<div class="dz-related-status-card-row">'
        '<div class="dz-related-status-card-text">'
        '<span class="dz-related-status-card-primary">INV-002 · £980</span>'
        '<span class="dz-related-status-card-secondary">due 28 Jul</span></div>'
        '<span class="dz-related-status-card-badge">'
        '<span class="dz-badge" data-dz-tone="warning">'
        '<span class="dz-badge-icon">{svg:triangle-alert}</span>Overdue</span></span>'
        "</div></div></div></div>"
        '<div id="hm-rel-files" class="dz-tabs__panel" hidden>'
        '<div class="dz-related-status-grid">'
        '<div class="dz-related-status-card">'
        '<div class="dz-related-status-card-row">'
        '<div class="dz-related-status-card-text">'
        '<span class="dz-related-status-card-primary">contract.pdf</span>'
        '<span class="dz-related-status-card-secondary">uploaded 3 Jul</span>'
        "</div></div></div></div></div>"
        "</div></div>",
        notes="One <code>dz-related-group</code> per related entity. The tab "
        "strip IS the tabs Hyperpart (<code>dz-tabs__tab</code> + "
        "<code>data-dz-tab-target</code>, driven by dz-tabs.js) with a "
        "related-specific count chip; panels are native-<code>hidden</code> "
        "toggles. Three body shapes share the chrome: the status-card grid "
        "(shown), a compact <code>dz-related-table</code>, and a "
        "<code>dz-related-file-list</code>. In Dazzle these render from the "
        "detail view's related groups — the same shared cell core as list "
        "rows, so badges/dates match.",
        tags=("data",),
        composes=("tabs", "badge"),
    ),
    Hyperpart(
        "metrics",
        "Metric tiles",
        "Data",
        "The KPI strip: label + value tiles in a packing grid, optionally "
        "toned. The server stamps the tile count for e2e anchors.",
        '<div class="dz-metrics-grid" data-dz-tile-count="3">'
        '<div class="dz-metric-tile" data-dz-metric-key="outstanding">'
        '<div class="dz-metric-label">Outstanding</div>'
        '<div class="dz-metric-value">£12,450</div></div>'
        '<div class="dz-metric-tile" data-dz-metric-key="paid" data-dz-tone="positive">'
        '<div class="dz-metric-label">Paid this month</div>'
        '<div class="dz-metric-value">£48,900</div></div>'
        '<div class="dz-metric-tile" data-dz-metric-key="overdue" data-dz-tone="warning">'
        '<div class="dz-metric-label">Overdue</div>'
        '<div class="dz-metric-value">3</div></div>'
        "</div>",
        notes="Each tile carries <code>data-dz-metric-key</code> (a stable "
        "anchor for tests/telemetry) and an optional <code>data-dz-tone</code>. "
        "In Dazzle one scope-aware GROUP BY query fills the whole strip — "
        "the tiles can never disagree with each other.",
        tags=("data", "chart"),
    ),
    Hyperpart(
        "sparkline",
        "Sparkline",
        "Data",
        "A headline number with its recent shape — the smallest chart: a "
        "current value, its bucket label, and an area glyph.",
        '<div class="dz-sparkline-region">'
        '<div class="dz-sparkline-headline">'
        '<span class="dz-sparkline-value">184ms</span>'
        '<span class="dz-sparkline-bucket-label">this hour</span></div>'
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 32" '
        'class="dz-sparkline-svg" role="img" '
        'aria-label="Sparkline — 12 points, latest 184ms, peak 240ms">'
        '<polygon points="0,32 0,20 18,18 36,22 54,14 72,16 90,10 108,12 126,8 '
        '144,14 162,6 180,9 180,32" fill="var(--colour-brand)" '
        'fill-opacity="0.15" stroke="none"/>'
        '<polyline points="0,20 18,18 36,22 54,14 72,16 90,10 108,12 126,8 '
        '144,14 162,6 180,9" fill="none" stroke="var(--colour-brand)" '
        'stroke-width="1.25" stroke-linejoin="round" stroke-linecap="round"/>'
        "</svg></div>",
        notes="The SVG is server-rendered with a numeric summary in "
        "<code>aria-label</code> (points / latest / peak) — the glyph is "
        "decoration; the numbers are the content. An empty series renders "
        "<code>dz-sparkline-empty</code>; a single point renders the "
        "headline alone.",
        tags=("data", "chart"),
    ),
    Hyperpart(
        "funnel",
        "Funnel",
        "Data",
        "Stage-by-stage narrowing — each bar's width is the stage's share, "
        "with a total summary line.",
        '<div class="dz-funnel-chart-region hm-measure-lg">'
        '<div class="dz-funnel-stages">'
        '<div class="dz-funnel-stage-row">'
        '<div class="dz-funnel-stage" data-dz-funnel-step="0" style="width: 100%;">'
        '<span class="dz-funnel-stage-label">Visited</span>'
        '<span class="dz-funnel-stage-count"> (1,204)</span></div></div>'
        '<div class="dz-funnel-stage-row">'
        '<div class="dz-funnel-stage" data-dz-funnel-step="1" style="width: 62%;">'
        '<span class="dz-funnel-stage-label">Signed up</span>'
        '<span class="dz-funnel-stage-count"> (746)</span></div></div>'
        '<div class="dz-funnel-stage-row">'
        '<div class="dz-funnel-stage" data-dz-funnel-step="2" style="width: 28%;">'
        '<span class="dz-funnel-stage-label">Subscribed</span>'
        '<span class="dz-funnel-stage-count"> (338)</span></div></div>'
        "</div>"
        '<p class="dz-funnel-summary">1,204 total</p>'
        "</div>",
        notes="Widths are SERVER-computed percentages on inline style — the "
        "one place inline style is the contract (a per-row datum, like the "
        "progress knob). <code>data-dz-funnel-step</code> tones the stages "
        "in sequence.",
        tags=("data", "chart"),
    ),
    Hyperpart(
        "bar-chart",
        "Bar chart",
        "Data",
        "Label / track / value rows — the workhorse categorical chart, "
        "server-computed and scope-safe.",
        '<div class="dz-bar-chart-region hm-measure-lg">'
        '<div class="dz-bar-chart-bars">'
        '<div class="dz-bar-chart-row">'
        '<span class="dz-bar-chart-label">API</span>'
        '<div class="dz-bar-chart-track">'
        '<div class="dz-bar-chart-fill" style="width: 84%"></div></div>'
        '<span class="dz-bar-chart-value">126</span></div>'
        '<div class="dz-bar-chart-row">'
        '<span class="dz-bar-chart-label">Dashboard</span>'
        '<div class="dz-bar-chart-track">'
        '<div class="dz-bar-chart-fill" style="width: 56%"></div></div>'
        '<span class="dz-bar-chart-value">84</span></div>'
        '<div class="dz-bar-chart-row">'
        '<span class="dz-bar-chart-label">Billing</span>'
        '<div class="dz-bar-chart-track">'
        '<div class="dz-bar-chart-fill" style="width: 23%"></div></div>'
        '<span class="dz-bar-chart-value">35</span></div>'
        "</div></div>",
        notes="In Dazzle every bar chart compiles to ONE scope-aware "
        "<code>GROUP BY</code> — the bucket list and the counts come from "
        "the same query, so they cannot disagree (the #847-class bug this "
        "design retired). Fill widths are server-computed percentages of "
        "the max bucket.",
        tags=("data", "chart"),
    ),
    Hyperpart(
        "chart-legend",
        "Chart legend",
        "Data",
        "The shared tail of every multi-series chart: swatch + series-name "
        "chips and a sample/series summary line.",
        '<div class="hm-measure-lg">'
        '<ul class="dz-chart-legend">'
        '<li class="dz-chart-legend-item">'
        '<span class="dz-chart-legend-swatch" '
        'style="background:var(--colour-brand)"></span>'
        '<span class="dz-chart-legend-name">Revenue</span></li>'
        '<li class="dz-chart-legend-item">'
        '<span class="dz-chart-legend-swatch" '
        'style="background:var(--colour-success)"></span>'
        '<span class="dz-chart-legend-name">Costs</span></li>'
        "</ul>"
        '<p class="dz-chart-summary">12 buckets · 2 series · peak £48,900</p>'
        "</div>",
        notes="Every SVG chart (line / area / radar / box-plot) ends with "
        "this pair instead of restyling it per chart: a "
        "<code>&lt;ul&gt;</code> of swatch + mono series-name items, and a "
        "mono summary line of bucket/series counts and the peak. The swatch "
        "background is the series colour the chart body uses for its "
        "strokes — inline, per series, server-assigned.",
        tags=("data", "chart"),
    ),
    Hyperpart(
        "heatmap",
        "Heatmap",
        "Data",
        "A two-dimensional grid of toned cells — rows × buckets, thresholds "
        "driving good/warn/bad tones, never colour alone (the value is IN "
        "the cell).",
        '<div class="dz-heatmap-region hm-measure-lg">'
        '<div class="dz-heatmap-scroll">'
        '<table class="dz-heatmap-grid">'
        "<thead><tr><th></th><th>Mon</th><th>Tue</th><th>Wed</th></tr></thead>"
        "<tbody><tr>"
        '<td class="dz-heatmap-row-label">API</td>'
        '<td class="dz-heatmap-cell" data-dz-heatmap-tone="good"> 99.9 </td>'
        '<td class="dz-heatmap-cell" data-dz-heatmap-tone="good"> 99.7 </td>'
        '<td class="dz-heatmap-cell" data-dz-heatmap-tone="warn"> 97.2 </td>'
        "</tr><tr>"
        '<td class="dz-heatmap-row-label">Webhooks</td>'
        '<td class="dz-heatmap-cell" data-dz-heatmap-tone="warn"> 96.1 </td>'
        '<td class="dz-heatmap-cell" data-dz-heatmap-tone="bad"> 89.4 </td>'
        '<td class="dz-heatmap-cell" data-dz-heatmap-tone="good"> 99.2 </td>'
        "</tr></tbody></table></div></div>",
        notes="Cell tones ride <code>data-dz-heatmap-tone=&quot;good|warn|"
        "bad&quot;</code>, resolved server-side against the declared "
        "thresholds — and the numeric value always renders inside the cell, "
        "so tone is reinforcement, not the only signal. Overflowing grids "
        "append a <code>dz-heatmap-overflow</code> count line; the scroll "
        "wrapper keeps wide grids inside their card.",
        tags=("data", "chart"),
    ),
    Hyperpart(
        "bullet",
        "Bullet chart",
        "Data",
        "Actual vs target on qualitative bands — the KPI-with-context bar. "
        "All geometry is server-computed inline percentages.",
        '<div class="dz-bullet-region hm-measure-lg">'
        '<div class="dz-bullet-rows">'
        '<div class="dz-bullet-row">'
        '<span class="dz-bullet-label">Revenue</span>'
        '<div class="dz-bullet-track">'
        '<span class="dz-bullet-band" style="left: 0%; width: 60%; '
        'background: var(--colour-danger);" title="Poor: 0–60"></span>'
        '<span class="dz-bullet-band" style="left: 60%; width: 25%; '
        'background: hsl(40, 90%, 55%);" title="OK: 60–85"></span>'
        '<span class="dz-bullet-band" style="left: 85%; width: 15%; '
        'background: hsl(145, 55%, 45%);" title="Good: 85–100"></span>'
        '<span class="dz-bullet-actual" style="width: 72%;" '
        'title="Revenue actual: 72"></span>'
        '<span class="dz-bullet-target" style="left: 80%;" '
        'title="Revenue target: 80"></span>'
        "</div>"
        '<span class="dz-bullet-value">72 / 80</span>'
        "</div></div>"
        '<p class="dz-bullet-summary">1 rows · scale 0–100</p>'
        "</div>",
        notes="Bands, the actual bar, and the target tick are absolutely "
        "positioned by SERVER-computed inline percentages (per-row data, the "
        "same contract as the funnel widths); each carries a "
        "<code>title</code> with its numeric range. Band fills come from the "
        "server's reference-band colour map (<code>target</code> → "
        "<code>var(--colour-brand)</code>, <code>destructive</code> → "
        "<code>var(--colour-danger)</code>, plus fixed positive/warning/"
        "muted values) — saturated colours, because the band layer renders "
        "at 0.18 opacity. The value (and target, when set) renders as text "
        "beside the track; the mono summary line carries row count and "
        "scale.",
        tags=("data", "chart"),
    ),
    Hyperpart(
        "pivot",
        "Pivot table",
        "Data",
        "Two group-bys crossed into a matrix — row labels × column buckets, "
        "empty intersections rendered as explicit nulls.",
        '<div class="dz-pivot-region hm-measure-lg">'
        '<div class="dz-pivot-scroll">'
        '<table class="dz-pivot-grid">'
        "<thead><tr><th>System</th><th>Severity</th>"
        '<th class="is-measure">Count</th></tr></thead>'
        "<tbody>"
        "<tr><td>API</td>"
        '<td><span class="dz-badge dz-badge-sm" data-dz-tone="destructive" '
        'role="status" aria-label="Status: Critical">'
        '<span class="dz-badge-icon">{svg:circle-x}</span>Critical</span></td>'
        '<td class="is-measure">3</td></tr>'
        "<tr><td>Dashboard</td>"
        '<td><span class="dz-pivot-null">—</span></td>'
        '<td class="is-measure">9</td></tr>'
        "</tbody></table></div>"
        '<p class="dz-pivot-summary">2 rows</p>'
        "</div>",
        notes="One scope-aware two-dimensional <code>GROUP BY</code> fills "
        "the whole matrix: dimension columns lead (status values render as "
        "badges, FK values as their label text), then measure columns — "
        "<code>class=&quot;is-measure&quot;</code> on the measure th/td pair "
        "drives the mono right-aligned numeric treatment. Empty "
        "intersections render <code>dz-pivot-null</code> em-dashes rather "
        "than blanks (absence is data). The scroll wrapper keeps wide "
        "matrices inside their card.",
        tags=("data", "chart"),
    ),
    Hyperpart(
        "bar-track",
        "Bar track",
        "Data",
        "Value-against-capacity rows with real progressbar semantics — the "
        "resource-usage sibling of the bar chart.",
        '<div class="dz-bar-track-region hm-measure-lg">'
        '<div class="dz-bar-track-rows">'
        '<div class="dz-bar-track-row">'
        '<span class="dz-bar-track-label" title="Storage">Storage</span>'
        '<div class="dz-bar-track" role="progressbar" aria-valuemin="0" '
        'aria-valuemax="100" aria-valuenow="62" aria-label="Storage: 62%">'
        '<span class="dz-bar-track-fill" style="width: 62%;" '
        'title="Storage: 62%"></span></div>'
        '<span class="dz-bar-track-value">62%</span></div>'
        '<div class="dz-bar-track-row">'
        '<span class="dz-bar-track-label" title="Compute">Compute</span>'
        '<div class="dz-bar-track" role="progressbar" aria-valuemin="0" '
        'aria-valuemax="100" aria-valuenow="38" aria-label="Compute: 38%">'
        '<span class="dz-bar-track-fill" style="width: 38%;" '
        'title="Compute: 38%"></span></div>'
        '<span class="dz-bar-track-value">38%</span></div>'
        "</div></div>",
        notes="Each track is a real <code>role=&quot;progressbar&quot;</code> "
        "with numeric aria values — the fill width is presentation, the "
        "aria is the content. Labels and fills both carry <code>title</code> "
        "for hover detail.",
        tags=("data", "chart"),
    ),
    Hyperpart(
        "histogram",
        "Histogram",
        "Data",
        "Value-distribution buckets as a server-rendered SVG plus a mono summary line.",
        '<div class="dz-histogram-region hm-measure-lg">'
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 48" '
        'role="img" aria-label="Histogram — 6 buckets, 120 samples">'
        '<rect x="4" y="30" width="24" height="18" fill="var(--colour-brand)" fill-opacity="0.7"/>'
        '<rect x="32" y="18" width="24" height="30" fill="var(--colour-brand)" fill-opacity="0.7"/>'
        '<rect x="60" y="6" width="24" height="42" fill="var(--colour-brand)" fill-opacity="0.7"/>'
        '<rect x="88" y="14" width="24" height="34" fill="var(--colour-brand)" fill-opacity="0.7"/>'
        '<rect x="116" y="28" width="24" height="20" fill="var(--colour-brand)" fill-opacity="0.7"/>'
        '<rect x="144" y="38" width="24" height="10" fill="var(--colour-brand)" fill-opacity="0.7"/>'
        "</svg>"
        '<p class="dz-histogram-summary">6 buckets · 120 samples</p>'
        "</div>",
        notes="The SVG body is SERVER-computed (this demo is schematic — the "
        "real geometry comes from <code>dazzle.render.svg.histogram_svg</code>) "
        "with the numeric story in <code>aria-label</code> and the mono "
        "summary line.",
        tags=("data", "chart"),
    ),
    Hyperpart(
        "box-plot",
        "Box plot",
        "Data",
        "Distribution five-number summaries per bucket — a server-rendered "
        "SVG with the counts in the summary line.",
        '<div class="dz-box-plot-region hm-measure-lg">'
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 48" '
        'role="img" aria-label="Box plot — 3 buckets">'
        '<line x1="20" y1="8" x2="20" y2="40" stroke="var(--colour-text-muted)"/>'
        '<rect x="8" y="16" width="24" height="16" fill="var(--colour-brand)" '
        'fill-opacity="0.25" stroke="var(--colour-brand)"/>'
        '<line x1="8" y1="24" x2="32" y2="24" stroke="var(--colour-brand)" stroke-width="2"/>'
        '<line x1="90" y1="4" x2="90" y2="44" stroke="var(--colour-text-muted)"/>'
        '<rect x="78" y="12" width="24" height="22" fill="var(--colour-brand)" '
        'fill-opacity="0.25" stroke="var(--colour-brand)"/>'
        '<line x1="78" y1="20" x2="102" y2="20" stroke="var(--colour-brand)" stroke-width="2"/>'
        '<line x1="160" y1="10" x2="160" y2="38" stroke="var(--colour-text-muted)"/>'
        '<rect x="148" y="18" width="24" height="14" fill="var(--colour-brand)" '
        'fill-opacity="0.25" stroke="var(--colour-brand)"/>'
        '<line x1="148" y1="26" x2="172" y2="26" stroke="var(--colour-brand)" stroke-width="2"/>'
        "</svg>"
        '<p class="dz-box-plot-summary">3 buckets · whiskers at min/max</p>'
        "</div>",
        notes="Schematic demo — real whisker/quartile geometry is "
        "server-computed. The summary line carries the bucket count.",
        tags=("data", "chart"),
    ),
    Hyperpart(
        "progress-region",
        "Progress stages",
        "Data",
        "A native progress bar with stage chips — where the work is, stage "
        "by stage, with completion tones.",
        '<div class="dz-progress-region hm-measure-lg">'
        '<div class="dz-progress-header">'
        '<progress data-dz-progress value="33" max="100"></progress>'
        "<span>33%</span>"
        "</div>"
        '<div class="dz-progress-stages">'
        '<span class="dz-progress-chip" data-dz-stage-tone="complete">Draft (4)</span>'
        '<span class="dz-progress-chip" data-dz-stage-tone="active">Review (2)</span>'
        '<span class="dz-progress-chip" data-dz-stage-tone="empty">Published (0)</span>'
        "</div>"
        '<p class="dz-progress-summary">1 of 3 complete</p>'
        "</div>",
        notes="The bar is a NATIVE <code>&lt;progress&gt;</code> (styled via "
        "<code>data-dz-progress</code>) with its percent readout as a plain "
        "<code>&lt;span&gt;</code> beside it in the header; chips are plain "
        "text (<code>Name (count)</code>) toned by "
        "<code>data-dz-stage-tone=&quot;complete|active|empty&quot;</code>; "
        "the summary paragraph follows the stages.",
        tags=("data",),
    ),
    Hyperpart(
        "profile-card",
        "Profile card",
        "Data",
        "The identity panel: avatar or initials beside name and meta, an "
        "optional 3-up stats grid, and a bulleted facts list.",
        '<div class="dz-profile-card-region hm-measure">'
        '<div class="dz-profile-card">'
        '<div class="dz-profile-identity">'
        '<span class="dz-profile-initials" aria-hidden="true">MR</span>'
        '<div class="dz-profile-text">'
        '<h3 class="dz-profile-primary">Maya Reyes</h3>'
        '<p class="dz-profile-secondary">Operations lead · North grid</p>'
        "</div></div>"
        '<dl class="dz-profile-stats">'
        '<div class="dz-profile-stat">'
        '<dt class="dz-profile-stat-label">Open work orders</dt>'
        '<dd class="dz-profile-stat-value">7</dd></div>'
        '<div class="dz-profile-stat">'
        '<dt class="dz-profile-stat-label">Sites</dt>'
        '<dd class="dz-profile-stat-value">3</dd></div>'
        '<div class="dz-profile-stat">'
        '<dt class="dz-profile-stat-label">On call</dt>'
        '<dd class="dz-profile-stat-value">—</dd></div>'
        "</dl>"
        '<ul class="dz-profile-facts">'
        '<li class="dz-profile-fact">'
        '<span class="dz-profile-fact-bullet" aria-hidden="true">·</span>'
        '<span class="dz-profile-fact-text">Certified for HV switching</span></li>'
        '<li class="dz-profile-fact">'
        '<span class="dz-profile-fact-bullet" aria-hidden="true">·</span>'
        '<span class="dz-profile-fact-text">Joined March 2024</span></li>'
        "</ul></div></div>",
        notes="The avatar slot prefers an <code>&lt;img "
        "class=&quot;dz-profile-avatar&quot;&gt;</code> and falls back to "
        "an initials chip; empty stat values render an em-dash (absence is "
        "data). Stats are a real <code>&lt;dl&gt;</code>; the facts bullet "
        "is decorative markup, hidden from assistive tech.",
        tags=("data",),
    ),
    Hyperpart(
        "grid-list",
        "Cell grid",
        "Data",
        "A responsive grid of plain record cells — title plus label: value "
        "lines, 1 → 2 → 3 columns as the container widens.",
        '<div class="dz-grid-region">'
        '<div class="dz-grid-list">'
        '<div class="dz-grid-cell ">'
        '<h4 class="dz-grid-cell-title">Aurora Substation</h4>'
        '<p class="dz-grid-cell-field">'
        '<span class="dz-grid-cell-field-label">Region:</span> North</p>'
        '<p class="dz-grid-cell-field">'
        '<span class="dz-grid-cell-field-label">Load:</span> 82%</p>'
        "</div>"
        '<div class="dz-grid-cell ">'
        '<h4 class="dz-grid-cell-title">Beacon Substation</h4>'
        '<p class="dz-grid-cell-field">'
        '<span class="dz-grid-cell-field-label">Region:</span> East</p>'
        '<p class="dz-grid-cell-field">'
        '<span class="dz-grid-cell-field-label">Load:</span> 47%</p>'
        "</div>"
        '<div class="dz-grid-cell ">'
        '<h4 class="dz-grid-cell-title">Cinder Substation</h4>'
        '<p class="dz-grid-cell-field">'
        '<span class="dz-grid-cell-field-label">Region:</span> West</p>'
        '<p class="dz-grid-cell-field">'
        '<span class="dz-grid-cell-field-label">Load:</span> 91%</p>'
        "</div>"
        "</div></div>",
        notes="Cells are deliberately chrome-free — the surrounding card "
        "owns borders and title. The column count is a viewport response "
        "(1 column, then 2 at 40rem, 3 at 64rem). The "
        "<code>is-clickable</code> hover/cursor affordance is styled but "
        "currently a LEGACY reserve — the substrate grid emitter does not "
        "yet wire cell drill URLs (follow-up on the Dazzle side).",
        tags=("data",),
    ),
    Hyperpart(
        "list-region",
        "List region",
        "Data",
        "The in-card data table: an actions row with CSV export, a "
        "horizontally scrollable table, and an overflow count.",
        '<div class="dz-list-region">'
        '<div class="dz-list-actions">'
        '<div class="dz-list-action-group">'
        '<button type="button" class="dz-list-csv-button" '
        'title="Export CSV" aria-label="Export CSV">{svg:download}</button>'
        "</div></div>"
        '<div class="dz-list-scroll">'
        '<table class="dz-list-table">'
        "<thead><tr>"
        '<th><a href="#" class="dz-list-sort-link">Name<span>▲</span></a></th>'
        "<th>Owner</th><th>Status</th>"
        "</tr></thead>"
        "<tbody>"
        '<tr class="dz-list-row is-clickable">'
        "<td>Quarterly audit</td><td>M. Reyes</td><td>Active</td></tr>"
        '<tr class="dz-list-row ">'
        "<td>Vendor renewal</td><td>A. Osei</td><td>Draft</td></tr>"
        "</tbody></table></div>"
        '<p class="dz-list-overflow">Showing 2 of 14</p>'
        "</div>",
        notes="The CSV button is ALWAYS rendered in the actions row. The "
        "snippet omits its wiring: the real emitter adds "
        "<code>data-dz-csv-endpoint</code>/<code>data-dz-csv-filename</code> "
        "and an <code>onclick</code> that calls "
        "<code>window.dz.downloadCsv(endpoint, filename)</code> against the "
        "server export route. Sortable headers are "
        "<code>dz-list-sort-link</code> anchors carrying an hx-get with "
        "<code>?sort=&lt;col&gt;&amp;dir=&lt;asc|desc&gt;</code> — the "
        "server re-renders the region; the active column shows a text "
        "caret. Rows wired to a drill URL carry <code>is-clickable</code>; "
        "the overflow line reports what the page cut. For the full "
        "hypermedia table primitive (selection, filters, pagination) use "
        "the <code>grid</code> Hyperpart — this one is the lighter in-card "
        "region.",
        tags=("data",),
    ),
    Hyperpart(
        "task-inbox",
        "Task inbox",
        "Data",
        "The personal worklist: filter chips over urgency-flagged items, "
        "each a drill link with title and meta.",
        '<div class="hm-measure-lg">'
        '<div class="dz-task-inbox-chips">'
        '<div class="dz-task-inbox-chip" data-dz-chip-id="all">'
        '<span class="dz-task-inbox-chip-count">6</span>'
        '<span class="dz-task-inbox-chip-label">All</span></div>'
        '<div class="dz-task-inbox-chip" data-dz-chip-id="overdue">'
        '<span class="dz-task-inbox-chip-count">2</span>'
        '<span class="dz-task-inbox-chip-label">Overdue</span></div>'
        "</div>"
        '<ul class="dz-task-inbox-items">'
        '<li class="dz-task-inbox-item" data-dz-urgency="overdue" data-dz-item-id="t1">'
        '<a class="dz-task-inbox-item-link" href="#">'
        '<span class="dz-task-inbox-item-icon" aria-hidden="true">{svg:inbox}</span>'
        '<div class="dz-task-inbox-item-body">'
        '<div class="dz-task-inbox-item-title">Approve refund — Acme</div>'
        '<div class="dz-task-inbox-item-meta">due in 2h · assigned to you</div>'
        "</div></a></li>"
        '<li class="dz-task-inbox-item" data-dz-urgency="due" data-dz-item-id="t2">'
        '<a class="dz-task-inbox-item-link" href="#">'
        '<span class="dz-task-inbox-item-icon" aria-hidden="true">{svg:inbox}</span>'
        '<div class="dz-task-inbox-item-body">'
        '<div class="dz-task-inbox-item-title">Review KYC — Globex</div>'
        '<div class="dz-task-inbox-item-meta">due tomorrow</div>'
        "</div></a></li>"
        "</ul></div>",
        notes="Items carry <code>data-dz-urgency=&quot;overdue|due|soon|"
        "later&quot;</code> (the server clamps anything else to "
        "<code>later</code>) + a stable <code>data-dz-item-id</code>; the "
        "whole row is one link, leading with its icon. Chips render count "
        "THEN label (<code>data-dz-chip-id</code> anchors a filter exchange "
        "in Dazzle).",
        tags=("data",),
    ),
    Hyperpart(
        "tree",
        "Tree",
        "Data",
        "Hierarchy on native <details>/<summary> — indented children, "
        "rotating chevron, child-count chips. No JS at all.",
        '<div class="hm-measure">'
        '<details class="dz-tree-node" open>'
        '<summary class="dz-tree-summary">'
        '<svg class="dz-tree-chevron" fill="none" viewBox="0 0 24 24" '
        'stroke="currentColor" stroke-width="2" aria-hidden="true">'
        '<path stroke-linecap="round" stroke-linejoin="round" '
        'd="M9 5l7 7-7 7"/></svg>'
        '<span class="dz-tree-label">Engineering</span>'
        '<span class="dz-tree-count">2</span>'
        "</summary>"
        '<div class="dz-tree-children">'
        '<details class="dz-tree-node">'
        '<summary class="dz-tree-summary">'
        '<svg class="dz-tree-chevron" fill="none" viewBox="0 0 24 24" '
        'stroke="currentColor" stroke-width="2" aria-hidden="true">'
        '<path stroke-linecap="round" stroke-linejoin="round" '
        'd="M9 5l7 7-7 7"/></svg>'
        '<span class="dz-tree-label">Platform</span>'
        '<span class="dz-tree-count">1</span>'
        "</summary>"
        '<div class="dz-tree-children">'
        '<details class="dz-tree-node">'
        '<summary class="dz-tree-summary">'
        '<svg class="dz-tree-chevron" fill="none" viewBox="0 0 24 24" '
        'stroke="currentColor" stroke-width="2" aria-hidden="true">'
        '<path stroke-linecap="round" stroke-linejoin="round" '
        'd="M9 5l7 7-7 7"/></svg>'
        '<span class="dz-tree-label">Build tooling</span>'
        "</summary></details>"
        "</div></details>"
        '<details class="dz-tree-node">'
        '<summary class="dz-tree-summary">'
        '<svg class="dz-tree-chevron" fill="none" viewBox="0 0 24 24" '
        'stroke="currentColor" stroke-width="2" aria-hidden="true">'
        '<path stroke-linecap="round" stroke-linejoin="round" '
        'd="M9 5l7 7-7 7"/></svg>'
        '<span class="dz-tree-label">Design systems</span>'
        "</summary></details>"
        "</div></details>"
        "</div>",
        notes="Pure hypermedia: state is the native <code>open</code> "
        "attribute, the chevron rotation keys off "
        "<code>.dz-tree-node[open]</code>, and each level indents via its "
        "<code>dz-tree-children</code> wrapper. The server emits depth-0 "
        "nodes <code>open</code> by default; the count chip renders only "
        "for nodes with children.",
        tags=("data",),
    ),
    Hyperpart(
        "diagram",
        "Diagram",
        "Data",
        "A horizontal-scroll wrapper for server-emitted Mermaid source — "
        "the library replaces the <pre> with rendered SVG.",
        '<div class="dz-diagram-scroll">'
        '<pre class="mermaid dz-diagram-source">'
        "erDiagram\n"
        "  CUSTOMER ||--o{ ORDER : places\n"
        "  ORDER ||--|{ LINE_ITEM : contains"
        "</pre>"
        "</div>",
        notes="The gallery shows the raw source (Mermaid is not loaded "
        "here); in Dazzle the emitter appends the Mermaid loader script "
        "and the library swaps the <code>&lt;pre&gt;</code> for SVG at "
        "runtime — the source styling only matters for the initial paint "
        "flash. The wrapper owns overflow; <code>dz-diagram-empty</code> "
        "is the no-data paragraph.",
        tags=("data",),
    ),
    # ── Primitives ───────────────────────────────────────────────────
    Hyperpart(
        "separator",
        "Separator",
        "Primitives",
        "A hairline divider on the border token — horizontal (`<hr>`) or "
        "vertical (`role=separator`).",
        '<div class="hm-stack hm-measure">'
        '<p class="hm-demo-muted">Account details</p>'
        '<hr class="dz-separator">'
        '<p class="hm-demo-muted">Billing and invoices</p>'
        '<div class="hm-demo-row">'
        '<span class="hm-demo-muted">Draft</span>'
        '<div class="dz-separator--vertical" role="separator" aria-orientation="vertical"></div>'
        '<span class="hm-demo-muted">Published</span>'
        '<div class="dz-separator--vertical" role="separator" aria-orientation="vertical"></div>'
        '<span class="hm-demo-muted">Archived</span>'
        "</div></div>",
        notes="The horizontal rule is a native <code>&lt;hr&gt;</code> (implicitly "
        "<code>role=separator</code>); the vertical divider is a zero-width element with an "
        "explicit <code>role=separator</code> + <code>aria-orientation=&quot;vertical&quot;</code>.",
    ),
    Hyperpart(
        "icon",
        "Icon",
        "Primitives",
        "Inline SVG from a vendored Lucide registry — currentColor, decorative "
        "by default. Shown here as the sprite <use> form (one sheet per page).",
        '<div class="dz-icon-demo">'
        '<svg class="dz-icon dz-icon--size-xs" aria-hidden="true"><use href="#i-circle-check"/></svg>'
        '<svg class="dz-icon dz-icon--size-sm" aria-hidden="true"><use href="#i-circle-check"/></svg>'
        '<svg class="dz-icon dz-icon--size-md" aria-hidden="true"><use href="#i-circle-check"/></svg>'
        '<svg class="dz-icon dz-icon--size-lg" aria-hidden="true"><use href="#i-circle-check"/></svg>'
        '<svg class="dz-icon dz-icon--size-xl" aria-hidden="true"><use href="#i-circle-check"/></svg>'
        "</div>",
        notes="Two delivery forms, one registry. <strong>Sprite</strong> "
        '(<code>&lt;svg class="icon"&gt;&lt;use href="#name"/&gt;&lt;/svg&gt;</code>) '
        "is short and legible but needs the icon sheet inlined once per page — "
        "use it when an icon repeats. <strong>Inline</strong> (the full "
        "<code>&lt;svg&gt;</code> with path data) is self-contained — use it when "
        "you want no sheet dependency. Both inherit text colour via "
        "<code>currentColor</code> and are <code>aria-hidden</code> by default; "
        "pass a label for a meaningful, non-decorative icon. Sizes: "
        "<code>icon--size-xs</code> … <code>icon--size-xl</code>.",
        tags=("icon", "svg", "sprite", "a11y"),
    ),
]
