"""Layout primitives — Stack (vertical), Row (horizontal), Split (two-panel),
Grid (n-column), AspectRatio (media frame).

These are the structural building blocks that hold other primitives. They do
not have semantic meaning beyond layout — for semantic containers, see
`primitives/containers.py`.

NOTE: the `children` field type uses `tuple[object, ...]` for now; once Task 16
declares the `Fragment` union alias, this gets retyped to `tuple[Fragment, ...]`.
The type alias forward-reference would create a circular import, so we
intentionally use `object` as a structural placeholder until Task 16 wires it.
"""

from dataclasses import dataclass
from typing import Literal

_GAPS = ("none", "sm", "md", "lg")
_ALIGNS = ("start", "center", "end", "stretch")
_RATIOS = ("1:2", "1:1", "2:1", "1:3", "3:1")
_ASPECT_RATIOS = ("1/1", "4/3", "16/9", "21/9")


@dataclass(frozen=True, slots=True)
class Stack:
    """Vertical stack of children."""

    children: tuple[object, ...]
    gap: Literal["none", "sm", "md", "lg"] = "md"

    def __post_init__(self) -> None:
        if not self.children:
            raise ValueError("Stack requires at least one child")
        if self.gap not in _GAPS:
            raise ValueError(f"invalid gap {self.gap!r}")


@dataclass(frozen=True, slots=True)
class Row:
    """Horizontal row of children."""

    children: tuple[object, ...]
    gap: Literal["none", "sm", "md", "lg"] = "md"
    align: Literal["start", "center", "end", "stretch"] = "start"

    def __post_init__(self) -> None:
        if not self.children:
            raise ValueError("Row requires at least one child")
        if self.gap not in _GAPS:
            raise ValueError(f"invalid gap {self.gap!r}")
        if self.align not in _ALIGNS:
            raise ValueError(f"invalid align {self.align!r}")


@dataclass(frozen=True, slots=True)
class Split:
    """Two-panel split (typically inbox-like list/detail layouts)."""

    start: object
    end: object
    ratio: Literal["1:2", "1:1", "2:1", "1:3", "3:1"] = "1:2"

    def __post_init__(self) -> None:
        if self.ratio not in _RATIOS:
            raise ValueError(f"invalid ratio {self.ratio!r}")


@dataclass(frozen=True, slots=True)
class Grid:
    """N-column grid. Columns must be in [1, 12]."""

    children: tuple[object, ...]
    columns: int = 3

    def __post_init__(self) -> None:
        if not self.children:
            raise ValueError("Grid requires at least one child")
        if not (1 <= self.columns <= 12):
            raise ValueError(f"columns must be in [1, 12]; got {self.columns}")


@dataclass(frozen=True, slots=True)
class AspectRatio:
    """HM media frame — dual-lock ``.dz-aspect-ratio`` (HMC-036 / HMC-132).

    Locks width/height for a single child (typically an image). Ratio presets
    match gallery ``data-dz-ratio`` tokens. Field/media compose also mounts this
    spine for ``logo_url`` / ``preview_url`` / ``photo_url`` thumbs.
    """

    child: object
    ratio: Literal["1/1", "4/3", "16/9", "21/9"] = "16/9"
    width: str | None = None
    aria_label: str | None = None

    def __post_init__(self) -> None:
        if self.ratio not in _ASPECT_RATIOS:
            raise ValueError(
                f"invalid aspect ratio {self.ratio!r}; expected one of {_ASPECT_RATIOS}"
            )
        if self.width is not None and not str(self.width).strip():
            raise ValueError("AspectRatio width must be non-empty when provided")
