"""Default nav-icon inference (HaTchi-MaXchi Phase 3, TASTE-6).

Every sidebar item gets an icon: authored ``icon:`` values win; otherwise
the label is matched against this keyword map so fleet apps get a sensible
icon vocabulary with zero DSL changes. Every name this module returns MUST
exist in the vendored registry (unit-asserted by ``test_nav_icons.py``) —
inference must never fall through to the client-hydration path.
"""

from dazzle.render.fragment.icon_registry import ICONS

__all__ = ["infer_nav_icon"]

_FALLBACK = "list"

# Checked in order — first keyword contained in the lowercased label wins.
# More specific terms come before general ones (e.g. "dashboard" before
# "board" would matter if both existed; keep it that way when extending).
_KEYWORD_ICONS: tuple[tuple[str, str], ...] = (
    ("dashboard", "layout-dashboard"),
    ("overview", "layout-dashboard"),
    ("home", "home"),
    ("task", "list-checks"),
    ("todo", "list-checks"),
    ("ticket", "ticket"),
    ("issue", "circle-alert"),
    ("incident", "triangle-alert"),
    ("alert", "bell"),
    ("notification", "bell"),
    ("user", "users"),
    ("people", "users"),
    ("member", "users"),
    ("team", "users"),
    ("staff", "users"),
    ("employee", "users"),
    ("pupil", "users"),
    ("student", "users"),
    ("contact", "users"),
    ("customer", "users"),
    ("client", "users"),
    ("tenant", "building-2"),
    ("compan", "building-2"),  # company/companies
    ("org", "building-2"),
    ("setting", "settings"),
    ("config", "settings"),
    ("admin", "settings"),
    ("health", "gauge"),
    ("status", "gauge"),
    ("monitor", "monitor"),
    ("deploy", "rocket"),
    ("release", "rocket"),
    ("report", "chart-bar"),
    ("analytic", "chart-bar"),
    ("insight", "chart-bar"),
    ("metric", "chart-line"),
    ("stat", "chart-line"),
    ("billing", "receipt"),
    ("invoice", "receipt"),
    ("payment", "credit-card"),
    ("expense", "banknote"),
    ("ledger", "landmark"),
    ("account", "wallet"),
    ("asset", "image"),
    ("file", "file-text"),
    ("document", "file-text"),
    ("upload", "upload"),
    ("template", "copy"),
    ("project", "kanban"),
    ("board", "kanban"),
    ("pipeline", "kanban"),
    ("work", "briefcase"),
    ("job", "briefcase"),
    ("feedback", "message-square"),
    ("review", "message-square"),
    ("comment", "message-circle"),
    ("mail", "mail"),
    ("inbox", "inbox"),
    ("message", "inbox"),
    ("calendar", "calendar"),
    ("schedule", "calendar"),
    ("event", "calendar"),
    ("order", "package"),
    ("product", "package"),
    ("inventory", "package"),
    ("shipment", "truck"),
    ("delivery", "truck"),
    ("approval", "badge-check"),
    ("sign", "pencil"),
    ("audit", "history"),
    ("log", "history"),
    ("histor", "history"),
    ("security", "shield"),
    ("permission", "shield"),
    ("role", "shield"),
    ("key", "key-round"),
    ("api", "code"),
    ("brand", "tag"),
    ("tag", "tag"),
    ("label", "tag"),
    ("campaign", "target"),
    ("class", "book-open"),
    ("course", "book-open"),
    ("lesson", "book-open"),
    ("search", "search"),
    ("archive", "archive"),
    ("trash", "trash-2"),
    ("star", "star"),
    ("favourite", "star"),
    ("favorite", "star"),
    ("manuscript", "book-open"),
    ("assessment", "clipboard-list"),
    ("survey", "clipboard-list"),
    ("form", "clipboard-list"),
)


def infer_nav_icon(label: str) -> str:
    """Best-effort registry icon for a nav *label*; never empty."""
    lowered = label.lower()
    for keyword, icon in _KEYWORD_ICONS:
        if keyword in lowered:
            return icon
    return _FALLBACK


# Import-time guard: inference must stay registry-closed. Cheap (runs once)
# and turns a typo'd icon name into an import error rather than a silent
# client-hydration fallback in production nav.
_unknown = {icon for _, icon in _KEYWORD_ICONS if icon not in ICONS}
if _unknown or _FALLBACK not in ICONS:  # pragma: no cover - guarded by tests
    raise RuntimeError(f"nav_icons references icons missing from the registry: {_unknown}")
