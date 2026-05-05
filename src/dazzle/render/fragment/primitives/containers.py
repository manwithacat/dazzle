"""Container primitives — Card, Region, Toolbar.

The `__post_init__` invariants in this module are what makes the
contract_checker scanner obsolete. Each invariant here corresponds to a
named scanner function being retired in Phase 9.

Surface, Drawer, Modal, Tabs come later (Task 13) — they extend the
container vocabulary but do not introduce new card-safety invariants.
"""

from dataclasses import dataclass, field
from typing import Literal

from dazzle.render.fragment.errors import CardSafetyError
from dazzle.render.fragment.tokens import CardTokens

_REGION_KINDS = ("list", "detail", "form", "dashboard", "kanban", "calendar", "report")


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

    kind: Literal["list", "detail", "form", "dashboard", "kanban", "calendar", "report"]
    body: object

    def __post_init__(self) -> None:
        if self.kind not in _REGION_KINDS:
            raise ValueError(f"invalid region kind {self.kind!r}; must be one of {_REGION_KINDS}")


@dataclass(frozen=True, slots=True)
class Toolbar:
    """Action bar attached to a surface or region.

    `actions` carries the buttons in display order. Once Button is available
    (Task 12), the post-init enforces "first action cannot be visibility=hidden"
    — the type-level replacement for the find_hidden_primary_actions scanner.
    """

    label: str
    actions: tuple[object, ...] = field(default_factory=tuple)
