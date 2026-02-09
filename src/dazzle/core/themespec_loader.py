"""
ThemeSpec persistence layer for DAZZLE design system.

Handles reading and writing ThemeSpec configurations to themespec.yaml
in the project root. ThemeSpec drives deterministic theme generation
from a small set of declarative parameters.

Default location: {project_root}/themespec.yaml
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .ir.themespec import (
    AttentionMapSpec,
    AttentionRule,
    FontStackSpec,
    ImagerySpec,
    ImageryVocabulary,
    LayoutCompositionSpec,
    PaletteSpec,
    SemanticColorOverrides,
    ShapeSpec,
    SpacingSpec,
    SurfaceCompositionRule,
    ThemeMetaSpec,
    ThemeSpecYAML,
    TypographySpec,
    VisualTreatment,
)

logger = logging.getLogger(__name__)

THEMESPEC_FILE = "themespec.yaml"


class ThemeSpecError(Exception):
    """Error loading or validating ThemeSpec."""

    pass


# =============================================================================
# Path helpers
# =============================================================================


def get_themespec_path(project_root: Path) -> Path:
    """Get the themespec.yaml file path."""
    return project_root / THEMESPEC_FILE


def themespec_exists(project_root: Path) -> bool:
    """Check if a themespec.yaml exists in the project."""
    return get_themespec_path(project_root).exists()


# =============================================================================
# Loading
# =============================================================================


def _parse_themespec_data(data: dict[str, Any]) -> ThemeSpecYAML:
    """Parse ThemeSpecYAML from raw YAML data with type coercion.

    Handles enum string values, nested models, and defaults.
    """
    try:
        # Parse palette
        palette_data = data.get("palette", {})
        semantic_data = (
            palette_data.pop("semantic_overrides", {}) if isinstance(palette_data, dict) else {}
        )
        palette_data = dict(palette_data) if palette_data else {}
        if semantic_data:
            palette_data["semantic_overrides"] = SemanticColorOverrides(**semantic_data)
        palette = PaletteSpec(**palette_data) if palette_data else PaletteSpec()

        # Parse typography
        typo_data = data.get("typography", {})
        typo_data = dict(typo_data) if typo_data else {}
        font_data = typo_data.pop("font_stacks", {}) if "font_stacks" in typo_data else {}
        if font_data:
            typo_data["font_stacks"] = FontStackSpec(**font_data)
        typography = TypographySpec(**typo_data) if typo_data else TypographySpec()

        # Parse spacing
        spacing_data = data.get("spacing", {})
        spacing = SpacingSpec(**spacing_data) if spacing_data else SpacingSpec()

        # Parse shape
        shape_data = data.get("shape", {})
        shape = ShapeSpec(**shape_data) if shape_data else ShapeSpec()

        # Parse attention_map
        attn_data = data.get("attention_map", {})
        rules = []
        if attn_data and "rules" in attn_data:
            for rule_data in attn_data["rules"]:
                treatment_data = rule_data.get("treatment", {})
                treatment = VisualTreatment(**treatment_data)
                rule_fields = {k: v for k, v in rule_data.items() if k != "treatment"}
                rules.append(AttentionRule(**rule_fields, treatment=treatment))
        attention_map = AttentionMapSpec(rules=rules)

        # Parse layout
        layout_data = data.get("layout", {})
        surfaces_data = layout_data.get("surfaces", {}) if layout_data else {}
        surfaces = (
            SurfaceCompositionRule(**surfaces_data) if surfaces_data else SurfaceCompositionRule()
        )
        layout_comp = LayoutCompositionSpec(surfaces=surfaces)

        # Parse imagery
        imagery_data = data.get("imagery", {})
        imagery_data = dict(imagery_data) if imagery_data else {}
        vocab_data = imagery_data.pop("vocabulary", {}) if "vocabulary" in imagery_data else {}
        if vocab_data:
            imagery_data["vocabulary"] = ImageryVocabulary(**vocab_data)
        imagery = ImagerySpec(**imagery_data) if imagery_data else ImagerySpec()

        # Parse meta
        meta_data = data.get("meta", {})
        meta = ThemeMetaSpec(**meta_data) if meta_data else ThemeMetaSpec()

        return ThemeSpecYAML(
            palette=palette,
            typography=typography,
            spacing=spacing,
            shape=shape,
            attention_map=attention_map,
            layout=layout_comp,
            imagery=imagery,
            meta=meta,
        )
    except (KeyError, ValueError, TypeError) as e:
        raise ThemeSpecError(f"Failed to parse ThemeSpec: {e}") from e


def load_themespec(project_root: Path, *, use_defaults: bool = True) -> ThemeSpecYAML:
    """Load ThemeSpec from themespec.yaml.

    Args:
        project_root: Root directory of the DAZZLE project.
        use_defaults: If True, return default ThemeSpec when file doesn't exist.

    Returns:
        ThemeSpecYAML instance.

    Raises:
        ThemeSpecError: If file doesn't exist (when use_defaults=False) or invalid.
    """
    themespec_path = get_themespec_path(project_root)

    if not themespec_path.exists():
        if use_defaults:
            logger.debug("No themespec.yaml found, using defaults")
            return create_default_themespec()
        raise ThemeSpecError(f"ThemeSpec not found: {themespec_path}")

    try:
        content = themespec_path.read_text(encoding="utf-8")
        data = yaml.safe_load(content)

        if not data:
            if use_defaults:
                logger.warning(f"Empty themespec.yaml at {themespec_path}, using defaults")
                return create_default_themespec()
            raise ThemeSpecError(f"Empty or invalid YAML in {themespec_path}")

        return _parse_themespec_data(data)

    except yaml.YAMLError as e:
        raise ThemeSpecError(f"Invalid YAML in {themespec_path}: {e}") from e
    except ValidationError as e:
        raise ThemeSpecError(f"Invalid ThemeSpec schema in {themespec_path}: {e}") from e


def save_themespec(project_root: Path, themespec: ThemeSpecYAML) -> Path:
    """Save ThemeSpec to themespec.yaml.

    Args:
        project_root: Root directory of the DAZZLE project.
        themespec: ThemeSpecYAML to save.

    Returns:
        Path to the saved themespec.yaml file.
    """
    themespec_path = get_themespec_path(project_root)

    data = themespec.model_dump(mode="json")

    themespec_path.write_text(
        yaml.dump(
            data,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    logger.info(f"Saved ThemeSpec to {themespec_path}")
    return themespec_path


# =============================================================================
# Validation
# =============================================================================


class ThemeSpecValidationResult:
    """Result of ThemeSpec validation."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def add_error(self, message: str) -> None:
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def __repr__(self) -> str:
        return (
            f"ThemeSpecValidationResult(errors={len(self.errors)}, warnings={len(self.warnings)})"
        )


# Valid dotted paths for agent_editable_fields validation
_VALID_FIELD_PATHS: set[str] = {
    "palette.brand_hue",
    "palette.brand_chroma",
    "palette.mode",
    "palette.accent_hue_offset",
    "palette.neutral_chroma",
    "typography.ratio",
    "typography.base_size_px",
    "typography.line_height_body",
    "typography.line_height_heading",
    "typography.font_stacks.heading",
    "typography.font_stacks.body",
    "typography.font_stacks.mono",
    "spacing.density",
    "spacing.base_unit_px",
    "shape.radius_preset",
    "shape.shadow_preset",
    "shape.border_width_px",
    "imagery.vocabulary.style_keywords",
    "imagery.vocabulary.mood_keywords",
    "imagery.vocabulary.exclusions",
    "imagery.vocabulary.color_reference",
    "imagery.default_aspect_ratio",
    "imagery.default_resolution",
    "layout.surfaces.max_columns",
    "layout.surfaces.sidebar_width_px",
    "layout.surfaces.content_max_width_px",
}

# Valid attention signal levels and kinds for validation
_VALID_SIGNAL_LEVELS = {"critical", "warning", "notice", "info"}
_VALID_SIGNAL_KINDS = {
    "deadline",
    "overdue",
    "threshold",
    "status_change",
    "anomaly",
    "approval",
    "mention",
    "assignment",
}


def validate_themespec(
    themespec: ThemeSpecYAML,
    project_root: Path | None = None,
) -> ThemeSpecValidationResult:
    """Validate a ThemeSpec for semantic correctness.

    Args:
        themespec: ThemeSpecYAML to validate.
        project_root: Project root (unused, for API consistency).

    Returns:
        ThemeSpecValidationResult with errors and warnings.
    """
    result = ThemeSpecValidationResult()

    # Palette validation
    if themespec.palette.brand_hue < 0 or themespec.palette.brand_hue > 360:
        result.add_error(f"palette.brand_hue must be 0-360, got {themespec.palette.brand_hue}")
    if themespec.palette.brand_chroma < 0 or themespec.palette.brand_chroma > 0.4:
        result.add_error(
            f"palette.brand_chroma must be 0-0.4, got {themespec.palette.brand_chroma}"
        )

    # Typography validation
    if themespec.typography.base_size_px < 12 or themespec.typography.base_size_px > 24:
        result.add_error(
            f"typography.base_size_px must be 12-24, got {themespec.typography.base_size_px}"
        )

    # Attention rule validation
    for i, rule in enumerate(themespec.attention_map.rules):
        if rule.match_signal_level and rule.match_signal_level not in _VALID_SIGNAL_LEVELS:
            result.add_warning(
                f"attention_map.rules[{i}].match_signal_level "
                f"'{rule.match_signal_level}' is not a known SignalLevel"
            )
        if rule.match_signal_kind and rule.match_signal_kind not in _VALID_SIGNAL_KINDS:
            result.add_warning(
                f"attention_map.rules[{i}].match_signal_kind "
                f"'{rule.match_signal_kind}' is not a known AttentionSignalKind"
            )

    # Meta: validate agent_editable_fields
    for field_path in themespec.meta.agent_editable_fields:
        if field_path not in _VALID_FIELD_PATHS:
            result.add_warning(
                f"meta.agent_editable_fields: '{field_path}' is not a recognized field path"
            )

    # Warnings for defaults
    if themespec.palette.brand_chroma == 0.0:
        result.add_warning("palette.brand_chroma is 0 — colors will be completely desaturated")

    return result


def validate_agent_edit(themespec: ThemeSpecYAML, field_path: str) -> bool:
    """Check if a field path is allowed for agent editing.

    Args:
        themespec: ThemeSpecYAML to check against.
        field_path: Dotted field path to check.

    Returns:
        True if the field is agent-editable.
    """
    return field_path in themespec.meta.agent_editable_fields


# =============================================================================
# Scaffolding
# =============================================================================


def create_default_themespec(
    brand_hue: float = 260.0,
    brand_chroma: float = 0.15,
) -> ThemeSpecYAML:
    """Create a default ThemeSpecYAML with sensible defaults.

    Args:
        brand_hue: Primary brand hue.
        brand_chroma: Primary brand chroma.

    Returns:
        ThemeSpecYAML with defaults.
    """
    return ThemeSpecYAML(
        palette=PaletteSpec(brand_hue=brand_hue, brand_chroma=brand_chroma),
        typography=TypographySpec(),
        spacing=SpacingSpec(),
        shape=ShapeSpec(),
        attention_map=AttentionMapSpec(),
        layout=LayoutCompositionSpec(),
        imagery=ImagerySpec(),
        meta=ThemeMetaSpec(),
    )


def scaffold_themespec(
    project_root: Path,
    *,
    brand_hue: float = 260.0,
    brand_chroma: float = 0.15,
    product_name: str = "My App",
    overwrite: bool = False,
) -> Path | None:
    """Create a default themespec.yaml file.

    Args:
        project_root: Root directory of the DAZZLE project.
        brand_hue: Primary brand hue.
        brand_chroma: Primary brand chroma.
        product_name: Product name (used in meta).
        overwrite: If True, overwrite existing file.

    Returns:
        Path to created file, or None if skipped.
    """
    themespec_path = get_themespec_path(project_root)

    if themespec_path.exists() and not overwrite:
        logger.debug(f"Skipping existing themespec: {themespec_path}")
        return None

    from datetime import UTC, datetime

    themespec = ThemeSpecYAML(
        palette=PaletteSpec(brand_hue=brand_hue, brand_chroma=brand_chroma),
        typography=TypographySpec(),
        spacing=SpacingSpec(),
        shape=ShapeSpec(),
        attention_map=AttentionMapSpec(),
        layout=LayoutCompositionSpec(),
        imagery=ImagerySpec(),
        meta=ThemeMetaSpec(
            generated_by="dazzle scaffold",
            generated_at=datetime.now(UTC).isoformat(),
        ),
    )

    return save_themespec(project_root, themespec)
