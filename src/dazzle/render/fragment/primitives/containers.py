"""Container primitives — Card, Region, Toolbar, Surface, Tabs, Drawer, Modal.

The `__post_init__` invariants in this module are what makes the
contract_checker scanner obsolete. Each invariant here corresponds to a
named scanner function being retired in Phase 9.

Surface, Tabs, Drawer, Modal extend the container vocabulary. Surface
carries one card-safety invariant of its own — its header cannot be a
Card (the surface IS the chrome).
"""

from dataclasses import dataclass, field
from typing import Literal

from dazzle.render.fragment.errors import CardSafetyError
from dazzle.render.fragment.tokens import CardTokens

_REGION_KINDS = ("list", "detail", "form", "dashboard", "kanban", "calendar", "report", "related")


@dataclass(frozen=True, slots=True)
class Card:
    """Visual chrome — a bordered/padded surface wrapping content.

    Invariant: a Card cannot directly contain another Card (in body, header,
    or footer). Replaces the `find_nested_chromes` scanner.
    """

    body: object
    header: object | None = None
    footer: object | None = None
    tokens: CardTokens | None = None

    def __post_init__(self) -> None:
        for slot_name, slot_val in (
            ("body", self.body),
            ("header", self.header),
            ("footer", self.footer),
        ):
            if isinstance(slot_val, Card):
                raise CardSafetyError(
                    f"Card cannot directly contain another Card (in slot {slot_name!r}); "
                    f"if you need a nested card layout, compose via a layout primitive (Stack/Row) "
                    f"or unwrap the inner Card."
                )


@dataclass(frozen=True, slots=True)
class DzTableMount:
    """The HM grid-root mount for a stateful list Region (ADR-0049 D3,
    Alpine mount retired in convergence C2.4).

    When a `Region(kind="list")` carries a `DzTableMount`, the renderer adds
    `id`, `data-dz-grid`, `data-dz-grid-url`, `data-dz-grid-edit-url`
    and `data-dz-bulk-count="0"` to the region root — the delegated HM grid
    controller and its extensions (dz-grid.js / -cols / -resize / -edit)
    resolve every behaviour against those attributes. The extra config
    fields (sort/inline/bulk/entity) are retained on the primitive for the
    builders that thread them into the Table/toolbar primitives.
    `inline_editable` is a tuple to keep the frozen dataclass hashable.
    """

    table_id: str
    endpoint: str
    sort_field: str = ""
    sort_dir: str = "asc"
    inline_editable: tuple[str, ...] = ()
    bulk_actions: bool = False
    entity_name: str = ""


@dataclass(frozen=True, slots=True)
class Region:
    """A semantic region inside a surface — list, detail, form, dashboard, etc.

    Region has NO `title` field by design. The dashboard slot (in Surface,
    Task 13) owns region titles. Replaces the `find_duplicate_titles_in_cards`
    scanner.
    """

    kind: Literal["list", "detail", "form", "dashboard", "kanban", "calendar", "report", "related"]
    body: object
    data_table: str = ""
    """Entity name to emit as `data-dazzle-table="<entity>"` on the
    region root. List regions need this attribute so the contract
    checker (and htmx `closest [data-dazzle-table]` selectors in
    search/filter fragments) can locate the entity container."""
    mount: DzTableMount | None = None
    """ADR-0049 D3 → C2.4: optional grid mount for stateful list regions.
    When set, the region root carries the HM grid-root attributes
    (`data-dz-grid` etc.). None = a plain (uncontrolled) region."""
    data_entity: str = ""
    """ADR-0049 Phase 2: entity name for a detail region — emitted as
    `data-dazzle-entity`/`data-dz-entity` (the selector tier2 e2e gestures +
    dz-analytics.js scope a detail surface by). Empty = omitted."""
    data_entity_id: str = ""
    """The record id for a detail region — emitted as `data-dz-entity-id`."""

    def __post_init__(self) -> None:
        if self.kind not in _REGION_KINDS:
            raise ValueError(f"invalid region kind {self.kind!r}; must be one of {_REGION_KINDS}")


@dataclass(frozen=True, slots=True)
class Toolbar:
    """Action bar attached to a surface or region.

    Invariant: the FIRST action cannot have visibility="hidden". Replaces the
    find_hidden_primary_actions scanner. The first action is the primary
    action of the toolbar; hiding it makes the toolbar unfindable.
    """

    label: str
    actions: tuple[object, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.actions:
            first = self.actions[0]
            visibility = getattr(first, "visibility", "visible")
            if visibility == "hidden":
                raise CardSafetyError(
                    "Toolbar primary action cannot be hidden; first action determines "
                    "toolbar discoverability. If the action is conditionally available, "
                    "use visibility='disabled' instead."
                )


@dataclass(frozen=True, slots=True)
class Surface:
    """Top-level rendered surface — list, detail, form, dashboard, etc.

    Surface has THREE slots and only three: header, body, footer. There is
    intentionally no `title` slot; the header carries titling. This is the
    structural invariant that prevents duplicate-title violations at the
    surface level (regions are constrained the same way in `Region`).

    A Card cannot occupy the header slot — that would re-introduce nested
    chrome. Body and footer are unconstrained for chrome since their content
    is typically the "inside" of the surface where Cards are appropriate.
    """

    body: object
    header: object | None = None
    footer: object | None = None

    def __post_init__(self) -> None:
        if isinstance(self.header, Card):
            raise CardSafetyError(
                "Surface header cannot be a Card; the surface IS the chrome. "
                "Use plain Text/Heading/Toolbar in the header slot."
            )


@dataclass(frozen=True, slots=True)
class Tabs:
    """Tabbed container. Each tab is `(key, Fragment)` — keys must be unique."""

    tabs: tuple[tuple[str, object], ...]

    def __post_init__(self) -> None:
        if not self.tabs:
            raise ValueError("Tabs requires at least one tab")
        seen: set[str] = set()
        for key, _panel in self.tabs:
            if key in seen:
                raise ValueError(f"duplicate tab key {key!r}")
            seen.add(key)


@dataclass(frozen=True, slots=True)
class Drawer:
    """Slide-over panel. Anchored to a screen edge."""

    body: object
    side: Literal["left", "right", "top", "bottom"] = "right"

    def __post_init__(self) -> None:
        if self.side not in ("left", "right", "top", "bottom"):
            raise ValueError(f"invalid side {self.side!r}")


@dataclass(frozen=True, slots=True)
class Modal:
    """Centered overlay dialog."""

    body: object
    size: Literal["sm", "md", "lg", "xl"] = "md"

    def __post_init__(self) -> None:
        if self.size not in ("sm", "md", "lg", "xl"):
            raise ValueError(f"invalid size {self.size!r}")


@dataclass(frozen=True, slots=True)
class ErrorPage:
    """Standalone error page — 404, 500, 403, generic.

    Used inside `Page.body` for routes that don't compose an AppShell
    (auth pages, framework error responses). Renders a centred
    `<section>` with a status code, message, and optional home link.

    `code` is rendered as a large display heading. `message` is the
    user-facing description. `home_href` produces a "Go home" link
    when set; pass `None` to omit (e.g. error pages embedded inside
    an existing app shell).
    """

    code: int
    message: str
    home_href: object | None = None  # URL | None (avoid import cycle)
    home_label: str = "Go home"

    def __post_init__(self) -> None:
        if not self.message:
            raise ValueError("ErrorPage requires a non-empty message")


@dataclass(frozen=True, slots=True)
class AppShell:
    """Multi-slot application layout — sidebar / header / body / footer.

    The structural skeleton an app uses inside `Page.body` to organise
    its primary navigation, top bar, main content, and footer. Mirrors
    the `dz-app-shell` / `dz-app-content` structure the legacy
    `app_shell.html` template produces, but with typed slots instead of
    Jinja `block` overrides.

    `body` is required; `sidebar`, `header`, `footer` are optional. A
    minimal use is `AppShell(body=Surface(...))` — just a content
    column with no chrome around it. A full use composes navigation
    primitives (Sidebar, Topbar — landing in a follow-up) into the
    optional slots.

    Renderer behaviour: emits the same CSS class structure as the
    legacy template, so existing component CSS continues to apply.
    Alpine state (sidebar persistence, dark-mode toggle) is intentionally
    NOT bundled into the primitive — that's the responsibility of the
    caller, who passes the appropriate header content (e.g. a Topbar
    primitive that wires its own toggle), or a RawHTML escape hatch
    for legacy Alpine markup during the migration window.
    """

    body: object
    sidebar: object | None = None
    header: object | None = None
    footer: object | None = None
    skip_link_text: str = "Skip to main content"
    """A11y skip-link label. The renderer always emits a skip-link
    targeting the AppShell's own `<main id="main-content">` element
    so keyboard users have a stable bypass; set to empty string to
    disable (rare — almost always wrong)."""

    # Phase 4 app-shell migration (v0.67.44): contract data-* attrs that
    # downstream tooling reads off the `<main>` element. The legacy
    # `layouts/app_shell.html` emitted these from per-render context;
    # the typed substrate carries them in the primitive so the same
    # E2E locators / agent observers / accessibility scanners keep
    # working unchanged.
    view_name: str = ""
    """Contract attr `data-dazzle-view` — surface ID (e.g.
    `"task_list"`). Set per render from `PageContext.view_name`."""
    surface_name: str = ""
    """Contract attr `data-dz-surface` — workspace surface name when
    present. Optional; empty omits the attribute."""
    workspace_name: str = ""
    """Contract attr `data-dz-workspace` — workspace identifier when
    present. Optional; empty omits the attribute."""
    page_purpose: str = ""
    """Surface-level purpose subtitle (UX-048). Rendered as a muted
    intro `<p class="dz-page-purpose">` above the body inside `<main>`
    when non-empty. Empty omits the element entirely."""
    sidebar_state: str = "open"
    """#1294 — open/closed state emitted as `data-dz-sidebar` on the
    `.dz-app-shell` root. The CSS keys off it to slide the sidebar
    on-screen (`open`) or off-screen (`closed`) and offset the content
    area. Defaults to `"open"` so the nav is reachable on first paint;
    callers thread the persisted value from `theme.get_sidebar_state()`
    (the `dz_sidebar` cookie). Only `"open"`/`"closed"` are emitted."""
    command_endpoint: str = ""
    """HaTchi-MaXchi command palette (tranche 2B adoption). When set (e.g.
    `"/app/command"`), the shell emits an empty `dz-command` dialog wired to
    this hx-get endpoint; `dz-command.js` opens it on ⌘K and the input
    fetches persona-scoped results on focus. Empty omits the palette."""


@dataclass(frozen=True, slots=True)
class Page:
    """Full HTML document — `<html>` + `<head>` + `<body>`.

    Top-level chrome primitive. Most surfaces compose their inner
    content inside a Surface or Region; the Page primitive is what
    wraps that content into a deliverable HTML document.

    Slots:
        body — the main content (typically a Surface, Stack of Surfaces,
            or workspace layout). Required.
        title — `<title>` text (also drives the page tab title).
        lang — `<html lang="...">` value. Defaults to "en".
        theme — optional theme identifier; rendered as `data-theme`
            attribute on `<html>` for CSS theme cascading.
        css_links — tuple of stylesheet URLs to include in `<head>`.
            Order is preserved (cascade-relevant).
        js_scripts — tuple of script URLs to include (deferred) in
            `<head>`. Order is preserved.
        favicon — favicon URL (rendered as `<link rel="icon">`).
        meta — tuple of (name, content) pairs for `<meta>` tags.
            charset and viewport are always emitted; this tuple is
            additional/custom metadata.
        cascade_layer_order — CSS `@layer` declaration. Drives the
            cascade priority (e.g. "reset, vendor, tokens, base,
            utilities, components, framework, app, overrides"). Must
            be a superset of every layer name the bundled
            `dazzle.min.css` declares — see the default below.

    Body-level slots (rendered after the main body):
        toast_container — emit the `dz-toast-stack` markup if True.
        modal_slot — emit the `dz-modal-slot` placeholder if True.
        page_announcer — emit the a11y `dz-page-announcer` div if True.

    Example:
        Page(
            title="Tasks — My App",
            theme="linear-dark",
            css_links=("/static/dist/dazzle.min.css",),
            js_scripts=("/static/dist/dazzle.min.js",),
            body=Surface(header=Heading("Tasks", level=1), body=...),
        )
    """

    title: str
    body: object
    lang: str = "en"
    theme: str | None = None
    css_links: tuple[str, ...] = ()
    js_scripts: tuple[str, ...] = ()
    favicon: str = "/static/assets/dazzle-favicon.svg"
    meta: tuple[tuple[str, str], ...] = ()
    # Phase 4 (v0.67.42): Open Graph + similar `<meta property="...">`
    # tags. The HTML spec distinguishes `name=` (standard metadata) from
    # `property=` (RDFa-extended metadata used by OG, og:title etc.) —
    # the `meta` field emits the former, `og_meta` the latter. Twitter
    # card tags use `name="twitter:*"` so they still go in `meta`.
    og_meta: tuple[tuple[str, str], ...] = ()
    # Post-#1042 theme-support restoration: external origins emitted
    # as `<link rel="preconnect" href="...">` in `<head>`. Themes that
    # ship custom fonts (Inter, Geist, JetBrains Mono…) declare the
    # font CDN host here so the browser opens the TCP+TLS handshake
    # before the stylesheet itself loads.
    font_preconnect: tuple[str, ...] = ()
    # #1279: must include every layer the bundled `dazzle.min.css` declares,
    # in the canonical order. The cascade rule for `@layer` locks a name's
    # position the first time it's seen — so this inline `<style>@layer ...>`
    # tag (emitted before any `<link>`) determines the global order. Missing
    # names ship as appended layers AFTER the last name here, which inverts
    # the intended priority: a 4-name list like `base, framework, app, overrides`
    # would cause `dazzle.min.css`'s own `components` and `utilities` layers
    # to land *after* `overrides` and win the cascade. The list below mirrors
    # `src/dazzle/page/runtime/static/css/dazzle.css:22` plus the project-level
    # `framework` and `app` slots, placed between `components` and `overrides`
    # so project component CSS can target framework primitives without losing
    # to the framework bundle's own component rules.
    cascade_layer_order: str = (
        "reset, vendor, tokens, base, utilities, components, framework, app, overrides"
    )
    toast_container: bool = True
    modal_slot: bool = True
    page_announcer: bool = True

    def __post_init__(self) -> None:
        if not self.title:
            raise ValueError("Page requires a non-empty title")
        if not self.lang:
            raise ValueError("Page requires a non-empty lang")
