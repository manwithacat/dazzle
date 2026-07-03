"""Content primitives — Text, Heading, Icon, Badge, EmptyState, Skeleton.

These are the leaf-level visual primitives. They do not contain children
(except EmptyState, which contains an optional action). Most apps' visible
text routes through Text or Heading; status indicators route through Badge."""

from dataclasses import dataclass
from typing import Literal

_TONES = ("default", "muted", "danger", "success", "warning")
_BADGE_VARIANTS = ("default", "info", "success", "warning", "danger")
_ICON_SIZES = ("sm", "md", "lg")


@dataclass(frozen=True, slots=True)
class Text:
    body: str
    tone: Literal["default", "muted", "danger", "success", "warning"] = "default"

    def __post_init__(self) -> None:
        if self.tone not in _TONES:
            raise ValueError(f"invalid tone {self.tone!r}")


@dataclass(frozen=True, slots=True)
class Heading:
    body: str
    level: int = 1

    def __post_init__(self) -> None:
        if not (1 <= self.level <= 6):
            raise ValueError(f"level must be in [1, 6]; got {self.level}")


@dataclass(frozen=True, slots=True)
class Icon:
    name: str
    size: Literal["sm", "md", "lg"] = "md"

    def __post_init__(self) -> None:
        if self.size not in _ICON_SIZES:
            raise ValueError(f"invalid size {self.size!r}")


@dataclass(frozen=True, slots=True)
class Badge:
    label: str
    variant: Literal["default", "info", "success", "warning", "danger"] = "default"

    def __post_init__(self) -> None:
        if self.variant not in _BADGE_VARIANTS:
            raise ValueError(f"invalid variant {self.variant!r}")


@dataclass(frozen=True, slots=True)
class EmptyState:
    title: str
    description: str
    action: object | None = None  # Button | Link, retyped post-Task 16
    icon: str = "inbox"  # vendored-registry name (TASTE-8); "" = no icon


@dataclass(frozen=True, slots=True)
class Skeleton:
    """Loading-state placeholder with N animated lines."""

    lines: int = 3

    def __post_init__(self) -> None:
        if self.lines < 1:
            raise ValueError(f"lines must be >= 1; got {self.lines}")
