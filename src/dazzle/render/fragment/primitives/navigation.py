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
