"""Navigation primitives — NavItem, NavGroup, Sidebar.

The typed shape an app uses to declare its primary navigation. Sidebar
slots into `AppShell.sidebar`; the rendered HTML matches the legacy
`templates/layouts/app_shell.html` sidebar markup so existing component
CSS and Alpine state attributes (`data-dz-sidebar`, `aria-current`)
continue to apply.
"""

from dataclasses import dataclass

from dazzle.render.fragment.htmx import URL


@dataclass(frozen=True, slots=True)
class BreadcrumbItem:
    """One crumb in a Breadcrumb trail.

    ``href=None`` marks the current page (renders as ``aria-current="page"``
    without a link). Linked crumbs take a path or absolute URL string.
    """

    label: str
    href: str | None = None

    def __post_init__(self) -> None:
        if not self.label or not str(self.label).strip():
            raise ValueError("BreadcrumbItem requires a non-empty label")


@dataclass(frozen=True, slots=True)
class Breadcrumb:
    """HM Breadcrumb hyperpart — dual-lock ``nav.dz-breadcrumb`` trail.

    Gallery spine: ``<nav class="dz-breadcrumb" aria-label="Breadcrumb"><ol>…``.
    Separators are CSS-generated (chevrons). Authored as shell trail from
    ``current_route`` / page title (see ``build_shell_breadcrumb``) or composed
    explicitly as a fragment.

    Dual-lock root: ``.dz-breadcrumb`` (contracts/breadcrumb.py).
    """

    items: tuple[BreadcrumbItem, ...]
    aria_label: str = "Breadcrumb"

    def __post_init__(self) -> None:
        if not self.items:
            raise ValueError("Breadcrumb requires at least one BreadcrumbItem")
        if not self.aria_label or not str(self.aria_label).strip():
            raise ValueError("Breadcrumb aria_label must be non-empty")


@dataclass(frozen=True, slots=True)
class MenubarAction:
    """One command inside a Menubar menu panel (link or button-shaped).

    Prefer ``href`` for navigation; omit for a no-op / host-owned action label.
    """

    label: str
    href: str | None = None

    def __post_init__(self) -> None:
        if not self.label or not str(self.label).strip():
            raise ValueError("MenubarAction requires a non-empty label")


@dataclass(frozen=True, slots=True)
class MenubarMenu:
    """One File / Edit / View-style top-level menubar entry (details/summary)."""

    label: str
    actions: tuple[MenubarAction, ...]

    def __post_init__(self) -> None:
        if not self.label or not str(self.label).strip():
            raise ValueError("MenubarMenu requires a non-empty label")
        if not self.actions:
            raise ValueError("MenubarMenu requires at least one MenubarAction")


@dataclass(frozen=True, slots=True)
class Menubar:
    """HM Menubar hyperpart — dual-lock ``div.dz-menubar`` app command strip.

    Gallery spine: exclusive-open ``details`` items under ``[data-dz-menubar]``.
    App chrome (File / Edit / View), not product site IA (that is navigation-menu)
    and not a single overflow menu (that is menu).

    Dual-lock root: ``[data-dz-menubar]`` (contracts/menubar.py).
    Authoring: ``menubar: true`` on the app block → shell trail from nav groups
    (see ``build_shell_menubar``).
    """

    menus: tuple[MenubarMenu, ...]
    aria_label: str = "App"

    def __post_init__(self) -> None:
        if not self.menus:
            raise ValueError("Menubar requires at least one MenubarMenu")
        if not self.aria_label or not str(self.aria_label).strip():
            raise ValueError("Menubar aria_label must be non-empty")


@dataclass(frozen=True, slots=True)
class NavigationMenuLink:
    """Top-level or panel link inside a NavigationMenu.

    ``href=None`` emits a non-navigating span (rare host-owned placeholder).
    ``current=True`` sets ``aria-current="page"`` on the anchor.
    ``description`` becomes a ``<small>`` under the label in mega panels.
    """

    label: str
    href: str | None = None
    current: bool = False
    description: str = ""

    def __post_init__(self) -> None:
        if not self.label or not str(self.label).strip():
            raise ValueError("NavigationMenuLink requires a non-empty label")


@dataclass(frozen=True, slots=True)
class NavigationMenuGroup:
    """One titled column inside a mega / branch panel."""

    links: tuple[NavigationMenuLink, ...]
    title: str = ""

    def __post_init__(self) -> None:
        if not self.links:
            raise ValueError("NavigationMenuGroup requires at least one NavigationMenuLink")


@dataclass(frozen=True, slots=True)
class NavigationMenuBranch:
    """Top-level details trigger with optional multi-column mega panel."""

    label: str
    groups: tuple[NavigationMenuGroup, ...]
    mega: bool = False

    def __post_init__(self) -> None:
        if not self.label or not str(self.label).strip():
            raise ValueError("NavigationMenuBranch requires a non-empty label")
        if not self.groups:
            raise ValueError("NavigationMenuBranch requires at least one NavigationMenuGroup")


@dataclass(frozen=True, slots=True)
class NavigationMenu:
    """HM NavigationMenu hyperpart — dual-lock product/site top nav.

    Gallery spine: ``nav.dz-navigation-menu[data-dz-navigation-menu]`` with
    link items and optional ``details`` mega branches. Product go-to IA
    (sitespec top nav), not app File/Edit/View menubar and not the app-shell
    sidebar.

    Dual-lock root: ``[data-dz-navigation-menu]`` (contracts/navigation_menu.py).
    Authoring: sitespec ``layout.nav`` → ``build_site_navigation_menu``.
    """

    items: tuple[NavigationMenuLink | NavigationMenuBranch, ...]
    aria_label: str = "Product"

    def __post_init__(self) -> None:
        if not self.items:
            raise ValueError("NavigationMenu requires at least one item")
        if not self.aria_label or not str(self.aria_label).strip():
            raise ValueError("NavigationMenu aria_label must be non-empty")


@dataclass(frozen=True, slots=True)
class NavItem:
    """Single navigation entry — typically a link to a workspace,
    surface, or external resource.

    `active` drives `aria-current="page"` on the rendered anchor (a
    convention the legacy template's CSS already keys off, see
    `templates/layouts/app_shell.html` line 12-13). `icon` is an
    optional icon name; when set, the renderer composes an `Icon`
    primitive inline before the label.
    """

    label: str
    href: URL
    active: bool = False
    icon: str = ""

    def __post_init__(self) -> None:
        if not self.label:
            raise ValueError("NavItem requires a non-empty label")


@dataclass(frozen=True, slots=True)
class NavGroup:
    """Collapsible group of nav items.

    Renders as a native `<details>` element so the open/closed state
    works without JavaScript. `collapsed=True` defaults the group to
    closed on first paint; persistent state is up to the consumer
    (e.g. wire an Alpine `x-init` via a wrapper, or accept the
    HTML-native default).
    """

    label: str
    items: tuple[NavItem, ...]
    icon: str = ""
    collapsed: bool = False

    def __post_init__(self) -> None:
        if not self.label:
            raise ValueError("NavGroup requires a non-empty label")
        if not self.items:
            raise ValueError("NavGroup requires at least one NavItem")


@dataclass(frozen=True, slots=True)
class SkipLink:
    """A11y skip-link — visually hidden until focused, then jumps the
    keyboard caret directly to the main content area.

    Place at the top of the page body so keyboard and screen-reader
    users can bypass repetitive navigation. AppShell auto-emits one
    pointing at its own `<main id="main-content">` element; callers
    using Page without AppShell should compose this primitive
    explicitly into their body.

    The default `target="#main-content"` matches the contract AppShell
    fulfils (its `<main>` element carries that id). If your layout
    uses a different anchor, set `target` accordingly.

    `text` is the visible label that shows when the link is focused.
    Override for i18n.
    """

    target: str = "#main-content"
    text: str = "Skip to main content"

    def __post_init__(self) -> None:
        if not self.target:
            raise ValueError("SkipLink requires a non-empty target")
        if not self.text:
            raise ValueError("SkipLink requires non-empty text")


@dataclass(frozen=True, slots=True)
class Topbar:
    """Application top bar — title (text) + free leading / trailing slots.

    Sits in `AppShell.header`. The legacy `app_shell.html` template
    composes a fixed structure (mobile drawer button + sidebar toggle +
    app name + user info + theme/dark toggles); this primitive
    intentionally stays generic — a typed `title` for the most common
    case, plus two free Fragment slots for everything else.

    `leading` typically holds a sidebar-toggle Button or breadcrumb
    Stack; `trailing` typically holds user identity Text + dark-mode
    Button + theme Combobox. Typed UserMenu / ThemeToggle primitives
    land in follow-ups when the patterns stabilise; for now compose
    from existing primitives (Button, Text, Stack).

    CSS class names match the legacy `dz-topbar` / `dz-topbar-leading`
    / `dz-topbar-title` / `dz-topbar-trailing` structure so existing
    component CSS applies without changes.
    """

    title: str = ""
    leading: object | None = None
    trailing: object | None = None
    show_sidebar_toggle: bool = False
    """#1294 — when True, the renderer emits a built-in hamburger toggle
    (`[data-dz-sidebar-toggle]`) at the start of the leading area. The JS
    controller flips `data-dz-sidebar` on the `.dz-app-shell` root and
    persists the choice to the `dz_sidebar` cookie, so the sidebar nav is
    reachable (collapse on desktop, open/dismiss on narrow viewports).
    `build_app_chrome_page` sets this True; standalone Topbars default off.

    #1602 — on desktop with the sidebar open, CSS hides this topbar
    (chrome) toggle in favour of the rail toggle emitted on
    ``Sidebar.show_sidebar_toggle``; topbar toggle remains for mobile
    and for reopening when the sidebar is closed."""


@dataclass(frozen=True, slots=True)
class Sidebar:
    """Application sidebar — flat items + optional groups + optional header.

    `header` is a free Fragment slot for app branding (logo, app name,
    user identity). `items` is the flat list at the top of the
    sidebar (typically Home, Settings, etc). `groups` are the
    collapsible workspace-grouped sections.

    All three are independent — a minimal sidebar is just `Sidebar()`
    (renders an empty nav, useful as a placeholder); a typical sidebar
    has all three populated.
    """

    items: tuple[NavItem, ...] = ()
    groups: tuple[NavGroup, ...] = ()
    header: object | None = None
    show_sidebar_toggle: bool = False
    """#1602 — when True, emit a rail-side collapse control in the
    sidebar header (desktop-open placement). Paired with
    ``Topbar.show_sidebar_toggle``; CSS shows only one at a time."""
