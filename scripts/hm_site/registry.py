"""HaTchi-MaXchi component registry — the copy-paste catalogue.

Single source for the static site AND (post-extraction) the agent-facing
component reference. Each entry is one component: a title, a one-line
blurb, the canonical HTML (rendered live in the gallery AND shown as the
copy-paste snippet — they are the same string, so the docs can never drift
from the demo), and optional notes on the htmx4 wiring.

Icon/SVG placeholders (``{icon:name}``) are expanded by the builder from
the vendored Lucide registry so snippets stay readable.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Component:
    id: str
    title: str
    group: str
    blurb: str
    html: str  # rendered live AND shown as the snippet
    notes: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)


# Groups order the gallery nav.
GROUPS = ["Actions", "Feedback", "Navigation", "Overlays", "Forms", "Data"]

COMPONENTS: list[Component] = [
    # ── Actions ──────────────────────────────────────────────────────
    Component(
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
    Component(
        "badge",
        "Badge",
        "Feedback",
        "Colour + icon + text — status never relies on colour alone (WCAG 1.4.1).",
        '<div class="hm-demo-row">'
        '<span class="dz-badge" data-dz-tone="success" role="status"><span class="dz-badge-icon">{icon:circle-check}</span>Approved</span>'
        '<span class="dz-badge" data-dz-tone="warning" role="status"><span class="dz-badge-icon">{icon:triangle-alert}</span>Pending</span>'
        '<span class="dz-badge" data-dz-tone="destructive" role="status"><span class="dz-badge-icon">{icon:circle-x}</span>Rejected</span>'
        '<span class="dz-badge" data-dz-tone="neutral" role="status">Draft</span>'
        "</div>",
        tags=("identity",),
    ),
    Component(
        "alert",
        "Alert",
        "Feedback",
        "Tone-wash surfaces — an identity layer shadcn has no vocabulary for.",
        '<div class="dz-alert" data-dz-tone="warning" role="alert" style="max-width:34rem">'
        '<span class="dz-alert__icon">{icon:triangle-alert}</span>'
        '<div class="dz-alert__body"><div class="dz-alert__title">Payment method expiring</div>'
        '<div class="dz-alert__description">Your card ending 4242 expires next month.</div></div></div>',
        tags=("identity",),
    ),
    Component(
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
    Component(
        "command",
        "Command palette",
        "Overlays",
        "The hx-get palette — the htmx4 flagship. Press ⌘K.",
        '<button class="dz-button dz-button-outline" data-hm-open-command>Open palette <kbd class="dz-kbd">⌘K</kbd></button>'
        '<dialog class="dz-command" aria-label="Command palette">'
        '<input class="dz-command__input" type="search" placeholder="Search workspaces and records…" '
        'hx-get="/mock/command" hx-trigger="input changed delay:150ms, focus once" '
        'hx-target="next .dz-command__results">'
        '<div class="dz-command__results" role="listbox"></div></dialog>',
        notes="In Dazzle the input's hx-get hits <code>/app/command</code>, which returns "
        "persona-scoped results. Here a mock htmx returns a canned list so the demo works "
        "with no server.",
        tags=("interactive", "htmx"),
    ),
    Component(
        "confirm",
        "Confirm dialog",
        "Overlays",
        "Designed replacement for window.confirm — every hx-confirm upgrades automatically.",
        '<button class="dz-button dz-button-destructive" hx-delete="/mock/noop" '
        'hx-confirm="Delete this invoice? This cannot be undone.">Delete invoice</button>',
        notes="dz-confirm.js intercepts <code>htmx:confirm</code>. No per-button wiring — "
        "any element with <code>hx-confirm</code> gets the designed dialog.",
        tags=("interactive", "htmx"),
    ),
    Component(
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
    Component(
        "popover",
        "Popover",
        "Overlays",
        "Free-content panel, details-based; body can lazy-load via htmx.",
        '<details class="dz-popover"><summary class="dz-button dz-button-outline">Details</summary>'
        '<div class="dz-popover__panel"><div style="font-weight:var(--weight-semibold);font-size:var(--text-sm);margin-bottom:.25rem">Dimensions</div>'
        '<p style="margin:0;font-size:var(--text-sm);color:var(--colour-text-muted)">Filters, previews, quick forms.</p></div></details>',
        tags=("interactive",),
    ),
    Component(
        "tooltip",
        "Tooltip",
        "Overlays",
        "CSS-only attribute tooltip — zero JS.",
        '<button class="dz-button dz-button-outline" data-dz-tooltip="Saved 2 minutes ago">Hover me</button>',
    ),
    # ── Forms ────────────────────────────────────────────────────────
    Component(
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
    Component(
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
    Component(
        "breadcrumb",
        "Breadcrumb",
        "Navigation",
        "CSS-generated chevrons; clean list markup.",
        '<nav class="dz-breadcrumb" aria-label="Breadcrumb"><ol>'
        '<li><a href="#">Home</a></li><li><a href="#">Invoices</a></li>'
        '<li aria-current="page">INV-0042</li></ol></nav>',
    ),
    Component(
        "avatar",
        "Avatar",
        "Data",
        "Initials or image; stacked groups.",
        '<div class="hm-demo-row">'
        '<span class="dz-avatar-group"><span class="dz-avatar">JD</span><span class="dz-avatar">AK</span><span class="dz-avatar">+3</span></span>'
        '<span class="dz-avatar" data-dz-size="lg">HM</span></div>',
    ),
    Component(
        "progress",
        "Progress",
        "Feedback",
        "Toned determinate bar.",
        '<div style="max-width:20rem;display:flex;flex-direction:column;gap:.75rem">'
        '<div class="dz-progress" role="progressbar" aria-valuenow="62" aria-valuemin="0" aria-valuemax="100"><div class="dz-progress__bar" style="width:62%"></div></div>'
        '<div class="dz-progress" data-dz-tone="success" role="progressbar" aria-valuenow="100" aria-valuemin="0" aria-valuemax="100"><div class="dz-progress__bar" style="width:100%"></div></div></div>',
    ),
    Component(
        "empty-state",
        "Empty state",
        "Feedback",
        "Icon + one sentence + primary action — never a bare 'No X'.",
        '<div class="dz-card" style="padding:1.5rem;max-width:22rem"><div class="dz-empty-state">'
        '<span class="dz-empty-state__icon">{icon:inbox}</span>'
        '<h3 class="dz-empty-state__title">No invoices yet</h3>'
        '<p class="dz-empty-state__description">Create your first invoice to get started.</p>'
        '<div class="dz-empty-state__action"><a class="dz-button dz-button-primary" href="#">New Invoice</a></div></div></div>',
    ),
]
