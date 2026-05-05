"""Interactive primitives — Button, Link, Interactive (wrapper), InlineEdit.

Buttons and Links carry typed htmx attributes. The Interactive wrapper
attaches htmx behaviour to any non-naturally-interactive child (clickable
card, hover-loaded row).

htmx invariants enforced at construction:
- A primitive cannot have both hx_get and hx_post.
- A primitive with any htmx-fetching attribute MUST have hx_target.

These replace the htmx-undefined-guards / preload-silence scanner tests.
"""

from dataclasses import dataclass
from typing import Literal

from dazzle.render.fragment.errors import HtmxBindingError
from dazzle.render.fragment.htmx import URL, HxTrigger, TargetSelector
from dazzle.render.fragment.tokens import ButtonTokens

_BUTTON_VARIANTS = ("primary", "secondary", "danger", "ghost")
_VISIBILITIES = ("visible", "hidden", "disabled")
_HX_SWAPS = ("innerHTML", "outerHTML", "beforebegin", "afterend", "delete", "none")


def _validate_htmx_pair(
    *,
    hx_get: URL | None,
    hx_post: URL | None,
    hx_target: TargetSelector | None,
    primitive_name: str,
) -> None:
    if hx_get is not None and hx_post is not None:
        raise HtmxBindingError(f"{primitive_name} cannot have both hx_get and hx_post")
    if (hx_get is not None or hx_post is not None) and hx_target is None:
        raise HtmxBindingError(f"{primitive_name} with hx_get/hx_post needs hx_target")


@dataclass(frozen=True, slots=True)
class Button:
    """A clickable button with typed htmx attributes.

    Invariants enforced at construction:
    - Cannot have both hx_get and hx_post.
    - If hx_get or hx_post is set, hx_target MUST be set.
    - variant must be one of primary/secondary/danger/ghost.
    - visibility must be one of visible/hidden/disabled.
    """

    label: str
    variant: Literal["primary", "secondary", "danger", "ghost"] = "secondary"
    visibility: Literal["visible", "hidden", "disabled"] = "visible"

    hx_get: URL | None = None
    hx_post: URL | None = None
    hx_target: TargetSelector | None = None
    hx_swap: (
        Literal["innerHTML", "outerHTML", "beforebegin", "afterend", "delete", "none"] | None
    ) = None
    hx_trigger: HxTrigger | None = None
    hx_indicator: TargetSelector | None = None
    hx_confirm: str | None = None

    tokens: ButtonTokens | None = None

    def __post_init__(self) -> None:
        if self.variant not in _BUTTON_VARIANTS:
            raise ValueError(f"invalid variant {self.variant!r}")
        if self.visibility not in _VISIBILITIES:
            raise ValueError(f"invalid visibility {self.visibility!r}")
        if self.hx_swap is not None and self.hx_swap not in _HX_SWAPS:
            raise ValueError(f"invalid hx_swap {self.hx_swap!r}")
        _validate_htmx_pair(
            hx_get=self.hx_get,
            hx_post=self.hx_post,
            hx_target=self.hx_target,
            primitive_name="Button",
        )


@dataclass(frozen=True, slots=True)
class Link:
    """A hyperlink to a URL. Pure navigation — no htmx attributes.

    For htmx-driven navigation, use Button with hx_get, or wrap content in
    Interactive."""

    label: str
    href: URL


@dataclass(frozen=True, slots=True)
class Interactive:
    """Wraps any Fragment with htmx behaviour. Used sparingly — naturally-
    interactive primitives (Button, Link, InlineEdit) carry their own htmx
    fields. Interactive exists for clickable cards, hover-loaded rows, etc."""

    child: object
    hx_get: URL | None = None
    hx_post: URL | None = None
    hx_target: TargetSelector | None = None
    hx_swap: (
        Literal["innerHTML", "outerHTML", "beforebegin", "afterend", "delete", "none"] | None
    ) = None
    hx_trigger: HxTrigger | None = None

    def __post_init__(self) -> None:
        if self.hx_swap is not None and self.hx_swap not in _HX_SWAPS:
            raise ValueError(f"invalid hx_swap {self.hx_swap!r}")
        _validate_htmx_pair(
            hx_get=self.hx_get,
            hx_post=self.hx_post,
            hx_target=self.hx_target,
            primitive_name="Interactive",
        )


@dataclass(frozen=True, slots=True)
class InlineEdit:
    """Click-to-edit field. Compiles to an htmx-driven swap.

    The `field_name` references an entity field in the surrounding IR; the
    renderer wires up hx_post to the field-update endpoint.
    """

    field_name: str
    value: str
    placeholder: str = ""
