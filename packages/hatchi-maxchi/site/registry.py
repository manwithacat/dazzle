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
    mock: str | None = None  # the gallery mock endpoint (interactive Hyperparts)


# Groups order the gallery nav.
GROUPS = [
    "Actions",
    "Feedback",
    "Navigation",
    "Overlays",
    "Forms",
    "Data",
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
        "A server-rendered data table: sortable headers, a filter bar, and row "
        "selection with a bulk-action bar — all HTML over the wire, on a real "
        "<table>. The tbody hydrates its rows over the wire (hx-get on load); "
        "search, sortable headers, filters, row selection (per page, or ALL matching "
        "rows with exclusions), bulk actions, and pagination are live (dz-grid.js, "
        "delegated + state-in-DOM) and compose into one server query. State is "
        "URL-synced (data-dz-grid-url): deep-linkable, Back walks grid states.",
        '<div class="hm-stack hm-measure-lg">'
        # data-dz-grid-url: opt-in URL-synced state — the grid's query mirrors
        # into the address bar (deep-linkable, Back walks grid states).
        '<div class="dz-table" data-dz-grid data-dz-grid-url data-dz-bulk-count="0" '
        'data-dz-grid-page="1">'
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
        "<thead><tr>"
        '<th class="dz-table-th-select">'
        '<input type="checkbox" data-dz-grid-select-all aria-label="Select all rows"></th>'
        '<th class="dz-table-th" aria-sort="none">'
        '<button type="button" class="dz-table-sort-button" data-dz-grid-sort="first">First name'
        '<span class="dz-table-sort-icon" aria-hidden="true">{svg:chevron-up}</span></button></th>'
        '<th class="dz-table-th" aria-sort="none">'
        '<button type="button" class="dz-table-sort-button" data-dz-grid-sort="last">Last name'
        '<span class="dz-table-sort-icon" aria-hidden="true">{svg:chevron-up}</span></button></th>'
        '<th class="dz-table-th" aria-sort="none">'
        '<button type="button" class="dz-table-sort-button" data-dz-grid-sort="plan">Plan'
        '<span class="dz-table-sort-icon" aria-hidden="true">{svg:chevron-up}</span></button></th>'
        '<th class="dz-table-th" aria-sort="none">'
        '<button type="button" class="dz-table-sort-button" data-dz-grid-sort="signed">Signed up'
        '<span class="dz-table-sort-icon" aria-hidden="true">{svg:chevron-up}</span></button></th>'
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
        ),
        controller="controllers/dz-grid.js",
        mock="/mock/grid",
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
        "</div></form></dialog>",
        notes="Opened by the shared <code>dz-dialog.js</code> "
        "(<code>[data-dz-dialog-open]</code>); close is native (method=dialog submit, Esc, "
        "backdrop). Anchor the edge with <code>data-dz-side=&quot;right|left&quot;</code>; the "
        "panel slides in via the native <code>@starting-style</code> transition, honouring "
        "<code>prefers-reduced-motion</code>.",
        tags=("interactive",),
        composes=("dialog", "button"),
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
