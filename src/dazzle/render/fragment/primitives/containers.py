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
class Region:
    """A semantic region inside a surface — list, detail, form, dashboard, etc.

    Region has NO `title` field by design. The dashboard slot (in Surface,
    Task 13) owns region titles. Replaces the `find_duplicate_titles_in_cards`
    scanner.
    """

    kind: Literal["list", "detail", "form", "dashboard", "kanban", "calendar", "report", "related"]
    body: object

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
