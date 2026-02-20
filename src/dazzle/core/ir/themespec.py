"""
ThemeSpec YAML IR types for declarative theme configuration.

Defines the structure of themespec.yaml which sits between sitespec.yaml
and the CSS generation pipeline. A ThemeSpecYAML produces a ThemeSpec
(from dazzle_ui.specs.theme) that the existing CSS pipeline consumes.

Eight sections: palette, typography, spacing, shape, attention_map,
layout, imagery, meta.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# =============================================================================
# Enums
# =============================================================================


class ColorMode(StrEnum):
    """Color mode for the theme."""

    LIGHT = "light"
    DARK = "dark"
    AUTO = "auto"


class DensityEnum(StrEnum):
    """Spacing density presets."""

    COMPACT = "compact"
    COMFORTABLE = "comfortable"
    SPACIOUS = "spacious"


class ShapePreset(StrEnum):
    """Border radius presets."""

    SHARP = "sharp"
    SUBTLE = "subtle"
    ROUNDED = "rounded"
    PILL = "pill"


class ShadowPreset(StrEnum):
    """Shadow depth presets."""

    NONE = "none"
    SUBTLE = "subtle"
    MEDIUM = "medium"
    DRAMATIC = "dramatic"


class TypographyRatioPreset(StrEnum):
    """Modular scale ratio presets with associated float values."""

    MINOR_SECOND = "minor_second"
    MAJOR_SECOND = "major_second"
    MINOR_THIRD = "minor_third"
    MAJOR_THIRD = "major_third"
    PERFECT_FOURTH = "perfect_fourth"
    AUGMENTED_FOURTH = "augmented_fourth"
    PERFECT_FIFTH = "perfect_fifth"
    GOLDEN_RATIO = "golden_ratio"


# Mapping from preset to numeric ratio
TYPOGRAPHY_RATIO_VALUES: dict[str, float] = {
    TypographyRatioPreset.MINOR_SECOND: 1.067,
    TypographyRatioPreset.MAJOR_SECOND: 1.125,
    TypographyRatioPreset.MINOR_THIRD: 1.200,
    TypographyRatioPreset.MAJOR_THIRD: 1.250,
    TypographyRatioPreset.PERFECT_FOURTH: 1.333,
    TypographyRatioPreset.AUGMENTED_FOURTH: 1.414,
    TypographyRatioPreset.PERFECT_FIFTH: 1.500,
    TypographyRatioPreset.GOLDEN_RATIO: 1.618,
}


# =============================================================================
# Section 1: Palette
# =============================================================================


class SemanticColorOverrides(BaseModel):
    """Optional overrides for semantic color hues."""

    model_config = ConfigDict(frozen=True)

    success_hue: float | None = Field(default=None, description="Hue for success (default 145)")
    warning_hue: float | None = Field(default=None, description="Hue for warning (default 85)")
    danger_hue: float | None = Field(default=None, description="Hue for danger (default 25)")
    info_hue: float | None = Field(default=None, description="Hue for info (default 240)")


class PaletteSpec(BaseModel):
    """Palette specification driven by brand hue and chroma."""

    model_config = ConfigDict(frozen=True)

    brand_hue: float = Field(
        default=260.0,
        ge=0.0,
        le=360.0,
        description="Primary brand hue on the OKLCH wheel (0-360)",
    )
    brand_chroma: float = Field(
        default=0.15,
        ge=0.0,
        le=0.4,
        description="Primary brand chroma (0-0.4, higher = more vivid)",
    )
    mode: ColorMode = Field(default=ColorMode.LIGHT, description="Light, dark, or auto mode")
    accent_hue_offset: float = Field(
        default=30.0, description="Hue offset for accent/secondary color"
    )
    neutral_chroma: float = Field(
        default=0.02,
        ge=0.0,
        le=0.1,
        description="Chroma for neutral tones",
    )
    semantic_overrides: SemanticColorOverrides = Field(
        default_factory=SemanticColorOverrides,
        description="Override default semantic color hues",
    )


# =============================================================================
# Section 2: Typography
# =============================================================================


class FontStackSpec(BaseModel):
    """Font stack configuration."""

    model_config = ConfigDict(frozen=True)

    heading: str = Field(
        default="Inter, system-ui, sans-serif",
        description="Font stack for headings",
    )
    body: str = Field(
        default="Inter, system-ui, sans-serif",
        description="Font stack for body text",
    )
    mono: str = Field(
        default="'JetBrains Mono', 'Fira Code', monospace",
        description="Font stack for code/monospace",
    )


class TypographySpec(BaseModel):
    """Typography specification using a modular scale."""

    model_config = ConfigDict(frozen=True)

    base_size_px: int = Field(
        default=16,
        ge=12,
        le=24,
        description="Base font size in pixels",
    )
    ratio: TypographyRatioPreset = Field(
        default=TypographyRatioPreset.MAJOR_THIRD,
        description="Modular scale ratio preset",
    )
    line_height_body: float = Field(default=1.6, description="Line height for body text")
    line_height_heading: float = Field(default=1.2, description="Line height for headings")
    font_stacks: FontStackSpec = Field(
        default_factory=FontStackSpec,
        description="Font family stacks",
    )


# =============================================================================
# Section 3: Spacing
# =============================================================================


class SpacingSpec(BaseModel):
    """Spacing specification based on a base unit and density."""

    model_config = ConfigDict(frozen=True)

    base_unit_px: int = Field(
        default=4,
        ge=2,
        le=8,
        description="Base spacing unit in pixels",
    )
    density: DensityEnum = Field(
        default=DensityEnum.COMFORTABLE,
        description="Density preset affecting spacing multiplier",
    )


# =============================================================================
# Section 4: Shape
# =============================================================================


class ShapeSpec(BaseModel):
    """Shape specification for borders, radii, and shadows."""

    model_config = ConfigDict(frozen=True)

    radius_preset: ShapePreset = Field(
        default=ShapePreset.SUBTLE,
        description="Border radius preset",
    )
    shadow_preset: ShadowPreset = Field(
        default=ShadowPreset.MEDIUM,
        description="Shadow depth preset",
    )
    border_width_px: int = Field(
        default=1,
        ge=0,
        le=4,
        description="Default border width in pixels",
    )


# =============================================================================
# Section 5: Attention Map
# =============================================================================


class VisualTreatment(BaseModel):
    """Visual treatment to apply when an attention rule matches."""

    model_config = ConfigDict(frozen=True)

    bg_token: str | None = Field(default=None, description="Background color token name")
    border_token: str | None = Field(default=None, description="Border color token name")
    text_token: str | None = Field(default=None, description="Text color token name")
    icon: str | None = Field(default=None, description="Icon identifier")
    animation: str | None = Field(default=None, description="CSS animation class name")


class AttentionRule(BaseModel):
    """Maps attention signal conditions to visual treatments."""

    model_config = ConfigDict(frozen=True)

    match_signal_level: str | None = Field(
        default=None, description="SignalLevel to match (critical, warning, notice, info)"
    )
    match_signal_kind: str | None = Field(default=None, description="AttentionSignalKind to match")
    match_entity_category: str | None = Field(default=None, description="Entity category to match")
    treatment: VisualTreatment = Field(description="Visual treatment to apply")


class AttentionMapSpec(BaseModel):
    """Attention map mapping signals to visual treatments."""

    model_config = ConfigDict(frozen=True)

    rules: list[AttentionRule] = Field(
        default_factory=list,
        description="Attention rules in priority order (first match wins)",
    )


# =============================================================================
# Section 6: Layout Composition
# =============================================================================


class SurfaceCompositionRule(BaseModel):
    """Layout composition rules for surfaces."""

    model_config = ConfigDict(frozen=True)

    max_columns: int = Field(default=3, ge=1, le=6, description="Maximum columns for grid layouts")
    sidebar_width_px: int = Field(default=260, description="Sidebar width in pixels")
    content_max_width_px: int = Field(default=1200, description="Maximum content width in pixels")


class LayoutCompositionSpec(BaseModel):
    """Layout composition specification."""

    model_config = ConfigDict(frozen=True)

    surfaces: SurfaceCompositionRule = Field(
        default_factory=SurfaceCompositionRule,
        description="Surface composition rules",
    )


# =============================================================================
# Section 7: Imagery
# =============================================================================


class ImageryVocabulary(BaseModel):
    """Vocabulary for imagery generation prompts."""

    model_config = ConfigDict(frozen=True)

    style_keywords: list[str] = Field(
        default_factory=lambda: ["clean", "professional", "modern"],
        description="Visual style keywords for image generation",
    )
    mood_keywords: list[str] = Field(
        default_factory=lambda: ["confident", "approachable"],
        description="Mood/tone keywords for image generation",
    )
    exclusions: list[str] = Field(
        default_factory=lambda: ["text", "watermark", "logo"],
        description="Negative prompt keywords",
    )
    color_reference: str = Field(
        default="brand palette",
        description="Color reference for generated imagery",
    )


class ImagerySpec(BaseModel):
    """Imagery specification for generated assets."""

    model_config = ConfigDict(frozen=True)

    vocabulary: ImageryVocabulary = Field(
        default_factory=ImageryVocabulary,
        description="Vocabulary for diffusion prompt assembly",
    )
    default_aspect_ratio: str = Field(default="16:9", description="Default aspect ratio")
    default_resolution: str = Field(default="1024x576", description="Default resolution")


# =============================================================================
# Section 8: Meta
# =============================================================================

# Default fields that agents can edit
DEFAULT_AGENT_EDITABLE_FIELDS: tuple[str, ...] = (
    "palette.brand_hue",
    "palette.brand_chroma",
    "palette.mode",
    "typography.ratio",
    "typography.base_size_px",
    "spacing.density",
    "shape.radius_preset",
    "shape.shadow_preset",
    "imagery.vocabulary.style_keywords",
    "imagery.vocabulary.mood_keywords",
)


class ThemeMetaSpec(BaseModel):
    """Metadata about the theme specification."""

    model_config = ConfigDict(frozen=True)

    version: int = Field(default=1, description="ThemeSpec schema version")
    generated_by: str | None = Field(default=None, description="Tool/agent that generated this")
    generated_at: str | None = Field(default=None, description="ISO timestamp of generation")
    agent_editable_fields: list[str] = Field(
        default_factory=lambda: list(DEFAULT_AGENT_EDITABLE_FIELDS),
        description="Dotted field paths that agents may safely edit",
    )


# =============================================================================
# Root Model
# =============================================================================


class ThemeSpecYAML(BaseModel):
    """Root ThemeSpec YAML configuration.

    Named ThemeSpecYAML to avoid collision with ThemeSpec in dazzle_ui.specs.theme.
    This model represents the user-facing themespec.yaml file that drives
    deterministic theme generation.
    """

    model_config = ConfigDict(frozen=True)

    palette: PaletteSpec = Field(
        default_factory=PaletteSpec,
        description="Color palette configuration",
    )
    typography: TypographySpec = Field(
        default_factory=TypographySpec,
        description="Typography configuration",
    )
    spacing: SpacingSpec = Field(
        default_factory=SpacingSpec,
        description="Spacing configuration",
    )
    shape: ShapeSpec = Field(
        default_factory=ShapeSpec,
        description="Shape and border configuration",
    )
    attention_map: AttentionMapSpec = Field(
        default_factory=AttentionMapSpec,
        description="Attention signal to visual treatment mapping",
    )
    layout: LayoutCompositionSpec = Field(
        default_factory=LayoutCompositionSpec,
        description="Layout composition rules",
    )
    imagery: ImagerySpec = Field(
        default_factory=ImagerySpec,
        description="Imagery generation configuration",
    )
    meta: ThemeMetaSpec = Field(
        default_factory=ThemeMetaSpec,
        description="Metadata about the theme specification",
    )

    def get_field_value(self, dotted_path: str) -> Any:
        """Get a value by dotted path (e.g. 'palette.brand_hue')."""
        parts = dotted_path.split(".")
        obj: Any = self
        for part in parts:
            if isinstance(obj, BaseModel):
                obj = getattr(obj, part, None)
            elif isinstance(obj, dict):
                obj = obj.get(part)
            else:
                return None
        return obj

    def is_agent_editable(self, field_path: str) -> bool:
        """Check if a field path is in the agent-editable list."""
        return field_path in self.meta.agent_editable_fields
