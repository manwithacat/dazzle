"""Frozen-dataclass token types parameterising visual treatment.

Each token sub-type maps to a primitive that needs theming. The root `Tokens`
type composes them. Apps select a token sheet via the DSL `theme:` clause
(implemented in Plan 2) or override per-app in `app/ui/tokens.py`.
"""

from dataclasses import dataclass, field
from typing import Literal

_RADII = ("none", "sm", "md", "lg")
_BORDERS = ("none", "subtle", "emphatic")
_PADDINGS = ("compact", "normal", "comfortable")  # CardTokens.padding
_DENSITY_SCALE = ("compact", "normal", "comfortable")  # TableTokens.density
_SPACING_SCALE = ("compact", "normal", "comfortable")  # Spacing.base
_SHADOWS = ("none", "low", "elevated")
_BUTTON_VARIANTS = ("primary", "secondary", "danger", "ghost")
_SIZES = ("sm", "md", "lg")
_PALETTE_ROLES = ("default", "primary", "muted", "subtle", "emphatic")


@dataclass(frozen=True, slots=True)
class CardTokens:
    radius: Literal["none", "sm", "md", "lg"] = "md"
    border: Literal["none", "subtle", "emphatic"] = "subtle"
    padding: Literal["compact", "normal", "comfortable"] = "normal"
    shadow: Literal["none", "low", "elevated"] = "none"

    def __post_init__(self) -> None:
        if self.radius not in _RADII:
            raise ValueError(f"invalid radius {self.radius!r}")
        if self.border not in _BORDERS:
            raise ValueError(f"invalid border {self.border!r}")
        if self.padding not in _PADDINGS:
            raise ValueError(f"invalid padding {self.padding!r}")
        if self.shadow not in _SHADOWS:
            raise ValueError(f"invalid shadow {self.shadow!r}")


@dataclass(frozen=True, slots=True)
class ButtonTokens:
    variant: Literal["primary", "secondary", "danger", "ghost"] = "secondary"
    size: Literal["sm", "md", "lg"] = "md"

    def __post_init__(self) -> None:
        if self.variant not in _BUTTON_VARIANTS:
            raise ValueError(f"invalid variant {self.variant!r}")
        if self.size not in _SIZES:
            raise ValueError(f"invalid size {self.size!r}")


@dataclass(frozen=True, slots=True)
class TableTokens:
    density: Literal["compact", "normal", "comfortable"] = "normal"
    striped: bool = False

    def __post_init__(self) -> None:
        if self.density not in _DENSITY_SCALE:
            raise ValueError(f"invalid density {self.density!r}")


@dataclass(frozen=True, slots=True)
class Palette:
    """Semantic colour roles. Concrete hex values live in CSS custom properties;
    this type only names the role. Adding a colour here without a CSS custom
    property means undefined visual output."""

    accent: str = "default"
    surface: str = "default"
    danger: str = "default"

    def __post_init__(self) -> None:
        for attr_name in ("accent", "surface", "danger"):
            value = getattr(self, attr_name)
            if value not in _PALETTE_ROLES:
                raise ValueError(f"invalid palette {attr_name} {value!r}")


@dataclass(frozen=True, slots=True)
class Spacing:
    """Spacing scale. Values are token names mapped to rem in CSS custom props."""

    base: Literal["compact", "normal", "comfortable"] = "normal"

    def __post_init__(self) -> None:
        if self.base not in _SPACING_SCALE:
            raise ValueError(f"invalid spacing base {self.base!r}")


@dataclass(frozen=True, slots=True)
class Tokens:
    card: CardTokens = field(default_factory=CardTokens)
    button: ButtonTokens = field(default_factory=ButtonTokens)
    table: TableTokens = field(default_factory=TableTokens)
    palette: Palette = field(default_factory=Palette)
    spacing: Spacing = field(default_factory=Spacing)
