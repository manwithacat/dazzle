"""Content primitives — Text, Heading, Icon, Badge, EmptyState, Skeleton, Bubble, HoverCard.

These are the leaf-level visual primitives. They do not contain children
(except EmptyState, which contains an optional action). Most apps' visible
text routes through Text or Heading; status indicators route through Badge.
Bubble is the chat speech shell (HM dual-lock ``.dz-bubble``).
HoverCard is the rich preview affordance (HM dual-lock ``.dz-hover-card``)."""

from dataclasses import dataclass
from typing import Literal

_TONES = ("default", "muted", "danger", "success", "warning")
_BADGE_VARIANTS = ("default", "info", "success", "warning", "danger")
_ICON_SIZES = ("sm", "md", "lg")
_BUBBLE_FROM = ("in", "out")
_BUBBLE_TONES = ("", "danger")


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


@dataclass(frozen=True, slots=True)
class Bubble:
    """HM Bubble hyperpart — dual-lock ``.dz-bubble`` chat content shell.

    Gallery spine: rounded inbound/outbound speech shell. Orientation via
    ``data-dz-from="in|out"``; optional ``data-dz-tone="danger"``. Compose
    under ``display: conversation`` (stack of bubbles from Comment rows or
    static entries) or nest inside a future Message row.

    Dual-lock root: ``.dz-bubble`` (contracts/bubble.py).
    """

    text: str
    from_: Literal["in", "out"] = "in"
    tone: Literal["", "danger"] = ""

    def __post_init__(self) -> None:
        if not self.text or not str(self.text).strip():
            raise ValueError("Bubble requires non-empty text")
        if self.from_ not in _BUBBLE_FROM:
            raise ValueError(f"invalid Bubble from_ {self.from_!r}; expected in|out")
        if self.tone not in _BUBBLE_TONES:
            raise ValueError(f"invalid Bubble tone {self.tone!r}")


@dataclass(frozen=True, slots=True)
class HoverCard:
    """HM HoverCard hyperpart — dual-lock ``.dz-hover-card`` rich preview.

    Gallery spine: trigger + floating panel opens on ``:hover`` /
    ``:focus-within`` (fine pointers + keyboard) and on click/tap via
    ``controllers/dz-hover-card.js`` (``data-dz-open``). No region verb —
    compose guest under person chips or nest explicitly as a Fragment.

    Dual-lock root: ``.dz-hover-card`` (contracts/hover_card.py).
    """

    trigger: str
    title: str
    description: str = ""
    open: bool = False

    def __post_init__(self) -> None:
        if not self.trigger or not str(self.trigger).strip():
            raise ValueError("HoverCard requires non-empty trigger")
        if not self.title or not str(self.title).strip():
            raise ValueError("HoverCard requires non-empty title")


_MARKER_TONES = ("", "success", "warning", "danger")
_MARKER_SIZES = ("", "lg")


@dataclass(frozen=True, slots=True)
class Marker:
    """HM Marker hyperpart — dual-lock ``.dz-marker`` map pin chrome.

    Gallery spine: pin silhouette + optional label. Host owns map
    projection / placement (``x_pct`` / ``y_pct`` on a MapBoard canvas).
    Authored via ``display: map`` (region board of pins) or composed
    explicitly as a Fragment.

    Dual-lock root: ``.dz-marker`` (contracts/marker.py).
    """

    label: str
    tone: Literal["", "success", "warning", "danger"] = ""
    size: Literal["", "lg"] = ""
    x_pct: float = 50.0
    y_pct: float = 50.0
    title: str = ""

    def __post_init__(self) -> None:
        if not self.label or not str(self.label).strip():
            raise ValueError("Marker requires non-empty label")
        if self.tone not in _MARKER_TONES:
            raise ValueError(f"invalid Marker tone {self.tone!r}")
        if self.size not in _MARKER_SIZES:
            raise ValueError(f"invalid Marker size {self.size!r}")
        if not (0.0 <= float(self.x_pct) <= 100.0):
            raise ValueError("Marker x_pct must be in [0, 100]")
        if not (0.0 <= float(self.y_pct) <= 100.0):
            raise ValueError("Marker y_pct must be in [0, 100]")


@dataclass(frozen=True, slots=True)
class MapBoard:
    """Host map plan canvas of Marker pins (``display: map``).

    Vendor-free static board — no tile SDK. Markers are dual-lock HM
    chrome; the canvas (``.dz-map``) is framework host CSS placement.
    """

    markers: tuple[Marker, ...]
    label: str = "Map"
    empty_message: str = "No locations."

    def __post_init__(self) -> None:
        if not self.label or not str(self.label).strip():
            raise ValueError("MapBoard requires non-empty label")
