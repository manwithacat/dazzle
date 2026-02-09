"""Tests for the ThemeSpec declarative theme system.

Covers: IR models, OKLCH, generators, loader, DTCG, imagery, bridge, MCP handlers.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

# =============================================================================
# Phase 1: IR Models
# =============================================================================


class TestThemeSpecIR:
    """Test ThemeSpecYAML IR models."""

    def test_default_construction(self):
        from dazzle.core.ir.themespec import ThemeSpecYAML

        ts = ThemeSpecYAML()
        assert ts.palette.brand_hue == 260.0
        assert ts.palette.brand_chroma == 0.15
        assert ts.palette.mode == "light"
        assert ts.typography.base_size_px == 16
        assert ts.typography.ratio == "major_third"
        assert ts.spacing.density == "comfortable"
        assert ts.shape.radius_preset == "subtle"
        assert ts.shape.shadow_preset == "medium"
        assert ts.imagery.default_aspect_ratio == "16:9"
        assert ts.meta.version == 1

    def test_frozen_models(self):
        from dazzle.core.ir.themespec import ThemeSpecYAML

        ts = ThemeSpecYAML()
        with pytest.raises(ValidationError):
            ts.palette = None  # type: ignore[assignment]

    def test_custom_palette(self):
        from dazzle.core.ir.themespec import ColorMode, PaletteSpec, ThemeSpecYAML

        palette = PaletteSpec(brand_hue=180.0, brand_chroma=0.2, mode=ColorMode.DARK)
        ts = ThemeSpecYAML(palette=palette)
        assert ts.palette.brand_hue == 180.0
        assert ts.palette.mode == "dark"

    def test_typography_ratio_values(self):
        from dazzle.core.ir.themespec import TYPOGRAPHY_RATIO_VALUES

        assert TYPOGRAPHY_RATIO_VALUES["major_third"] == 1.250
        assert TYPOGRAPHY_RATIO_VALUES["golden_ratio"] == 1.618
        assert len(TYPOGRAPHY_RATIO_VALUES) == 8

    def test_attention_rule(self):
        from dazzle.core.ir.themespec import AttentionRule, VisualTreatment

        treatment = VisualTreatment(bg_token="danger-bg", icon="alert")
        rule = AttentionRule(match_signal_level="critical", treatment=treatment)
        assert rule.match_signal_level == "critical"
        assert rule.treatment.bg_token == "danger-bg"

    def test_get_field_value(self):
        from dazzle.core.ir.themespec import ThemeSpecYAML

        ts = ThemeSpecYAML()
        assert ts.get_field_value("palette.brand_hue") == 260.0
        assert ts.get_field_value("typography.ratio") == "major_third"
        assert ts.get_field_value("nonexistent.path") is None

    def test_is_agent_editable(self):
        from dazzle.core.ir.themespec import ThemeSpecYAML

        ts = ThemeSpecYAML()
        assert ts.is_agent_editable("palette.brand_hue") is True
        assert ts.is_agent_editable("meta.version") is False

    def test_palette_validation_bounds(self):
        from pydantic import ValidationError

        from dazzle.core.ir.themespec import PaletteSpec

        with pytest.raises(ValidationError):
            PaletteSpec(brand_hue=400.0)
        with pytest.raises(ValidationError):
            PaletteSpec(brand_chroma=0.5)

    def test_serialization_roundtrip(self):
        from dazzle.core.ir.themespec import ThemeSpecYAML

        ts = ThemeSpecYAML()
        data = ts.model_dump(mode="json")
        ts2 = ThemeSpecYAML(**data)
        assert ts2.palette.brand_hue == ts.palette.brand_hue
        assert ts2.typography.ratio == ts.typography.ratio

    def test_ir_exports(self):
        """ThemeSpec types are accessible from the IR package."""
        from dazzle.core.ir import ColorMode, PaletteSpec, ThemeSpecYAML

        assert ThemeSpecYAML is not None
        assert PaletteSpec is not None
        assert ColorMode is not None


# =============================================================================
# Phase 2: OKLCH
# =============================================================================


class TestOKLCH:
    """Test OKLCH palette generation."""

    def test_oklch_to_css_basic(self):
        from dazzle.core.oklch import oklch_to_css

        result = oklch_to_css(0.5, 0.15, 260.0)
        assert result.startswith("oklch(")
        assert "260.0" in result
        assert "/" not in result  # no alpha

    def test_oklch_to_css_alpha(self):
        from dazzle.core.oklch import oklch_to_css

        result = oklch_to_css(0.5, 0.15, 260.0, alpha=0.5)
        assert "/ 0.50" in result

    def test_generate_palette_light(self):
        from dazzle.core.oklch import generate_palette

        palette = generate_palette(260.0, 0.15, "light")
        # Check key tokens exist
        assert "primary-500" in palette
        assert "secondary-500" in palette
        assert "accent-500" in palette
        assert "neutral-500" in palette
        assert "success" in palette
        assert "warning" in palette
        assert "danger" in palette
        assert "info" in palette
        assert "bg-primary" in palette
        assert "text-primary" in palette
        assert "border-default" in palette

    def test_generate_palette_dark(self):
        from dazzle.core.oklch import generate_palette

        light = generate_palette(260.0, 0.15, "light")
        dark = generate_palette(260.0, 0.15, "dark")
        # Dark bg should be darker than light bg
        assert light["bg-primary"] != dark["bg-primary"]

    def test_generate_palette_scale_completeness(self):
        from dazzle.core.oklch import generate_palette

        palette = generate_palette(260.0, 0.15)
        for prefix in ["primary", "secondary", "accent", "neutral"]:
            for step in ["50", "100", "200", "300", "400", "500", "600", "700", "800", "950"]:
                assert f"{prefix}-{step}" in palette, f"Missing {prefix}-{step}"

    def test_semantic_overrides(self):
        from dazzle.core.oklch import generate_palette

        palette = generate_palette(260.0, 0.15, semantic_overrides={"success_hue": 200.0})
        assert "success" in palette
        # The hue should be reflected in the output
        assert "200.0" in palette["success"]


# =============================================================================
# Phase 3: Generators
# =============================================================================


class TestGenerators:
    """Test theme token generators."""

    def test_type_scale(self):
        from dazzle.core.theme_generators import generate_type_scale

        scale = generate_type_scale(16, "major_third")
        assert "text-base" in scale
        assert "text-xs" in scale
        assert "text-6xl" in scale
        assert scale["text-base"] == "1.0000rem"
        # text-lg should be larger than text-base
        base_val = float(scale["text-base"].replace("rem", ""))
        lg_val = float(scale["text-lg"].replace("rem", ""))
        assert lg_val > base_val

    def test_type_scale_line_heights(self):
        from dazzle.core.theme_generators import generate_type_scale

        scale = generate_type_scale(16, "major_third", 1.6, 1.2)
        assert scale["text-base-lh"] == "1.6"
        assert scale["text-xl-lh"] == "1.2"  # heading

    def test_spacing_scale(self):
        from dazzle.core.theme_generators import generate_spacing_scale

        spacing = generate_spacing_scale(4, "comfortable")
        assert "space-0" in spacing
        assert spacing["space-0"] == "0"
        assert "space-4" in spacing
        # space-4 = 4 * 4 * 1.0 = 16px = 1rem
        assert spacing["space-4"] == "1.0000rem"

    def test_spacing_density(self):
        from dazzle.core.theme_generators import generate_spacing_scale

        compact = generate_spacing_scale(4, "compact")
        spacious = generate_spacing_scale(4, "spacious")
        # spacious space-4 should be larger
        compact_val = float(compact["space-4"].replace("rem", ""))
        spacious_val = float(spacious["space-4"].replace("rem", ""))
        assert spacious_val > compact_val

    def test_shape_tokens(self):
        from dazzle.core.theme_generators import generate_shape_tokens

        tokens = generate_shape_tokens("subtle", "medium", 1)
        assert "radius-sm" in tokens
        assert "radius-md" in tokens
        assert "shadow-sm" in tokens
        assert "shadow-xl" in tokens
        assert tokens["border-width"] == "1px"

    def test_shape_sharp(self):
        from dazzle.core.theme_generators import generate_shape_tokens

        tokens = generate_shape_tokens("sharp", "none", 0)
        assert tokens["radius-sm"] == "0"
        assert tokens["shadow-sm"] == "none"
        assert tokens["border-width"] == "0px"


# =============================================================================
# Phase 4: Loader
# =============================================================================


class TestThemeSpecLoader:
    """Test ThemeSpec YAML loader."""

    def test_create_default(self):
        from dazzle.core.themespec_loader import create_default_themespec

        ts = create_default_themespec()
        assert ts.palette.brand_hue == 260.0

    def test_create_custom(self):
        from dazzle.core.themespec_loader import create_default_themespec

        ts = create_default_themespec(brand_hue=180.0, brand_chroma=0.2)
        assert ts.palette.brand_hue == 180.0
        assert ts.palette.brand_chroma == 0.2

    def test_save_and_load(self, tmp_path: Path):
        from dazzle.core.themespec_loader import (
            create_default_themespec,
            load_themespec,
            save_themespec,
        )

        ts = create_default_themespec(brand_hue=120.0)
        save_themespec(tmp_path, ts)

        loaded = load_themespec(tmp_path)
        assert loaded.palette.brand_hue == 120.0
        assert loaded.palette.brand_chroma == 0.15
        assert loaded.typography.ratio == "major_third"

    def test_load_missing_uses_defaults(self, tmp_path: Path):
        from dazzle.core.themespec_loader import load_themespec

        ts = load_themespec(tmp_path, use_defaults=True)
        assert ts.palette.brand_hue == 260.0

    def test_load_missing_raises(self, tmp_path: Path):
        from dazzle.core.themespec_loader import ThemeSpecError, load_themespec

        with pytest.raises(ThemeSpecError):
            load_themespec(tmp_path, use_defaults=False)

    def test_themespec_exists(self, tmp_path: Path):
        from dazzle.core.themespec_loader import (
            create_default_themespec,
            save_themespec,
            themespec_exists,
        )

        assert themespec_exists(tmp_path) is False
        save_themespec(tmp_path, create_default_themespec())
        assert themespec_exists(tmp_path) is True

    def test_scaffold(self, tmp_path: Path):
        from dazzle.core.themespec_loader import load_themespec, scaffold_themespec

        path = scaffold_themespec(tmp_path, brand_hue=90.0, brand_chroma=0.1)
        assert path is not None
        assert path.exists()

        ts = load_themespec(tmp_path)
        assert ts.palette.brand_hue == 90.0

    def test_scaffold_no_overwrite(self, tmp_path: Path):
        from dazzle.core.themespec_loader import scaffold_themespec

        scaffold_themespec(tmp_path)
        result = scaffold_themespec(tmp_path)  # second call
        assert result is None

    def test_validate_valid(self):
        from dazzle.core.themespec_loader import create_default_themespec, validate_themespec

        ts = create_default_themespec()
        result = validate_themespec(ts)
        assert result.is_valid

    def test_validate_agent_edit(self):
        from dazzle.core.themespec_loader import create_default_themespec, validate_agent_edit

        ts = create_default_themespec()
        assert validate_agent_edit(ts, "palette.brand_hue") is True
        assert validate_agent_edit(ts, "meta.version") is False

    def test_parse_with_attention_rules(self, tmp_path: Path):
        """Attention rules survive YAML roundtrip."""
        import yaml

        data = {
            "palette": {"brand_hue": 200.0},
            "attention_map": {
                "rules": [
                    {
                        "match_signal_level": "critical",
                        "treatment": {"bg_token": "danger-bg", "icon": "alert"},
                    }
                ]
            },
        }
        path = tmp_path / "themespec.yaml"
        path.write_text(yaml.dump(data))

        from dazzle.core.themespec_loader import load_themespec

        ts = load_themespec(tmp_path)
        assert len(ts.attention_map.rules) == 1
        assert ts.attention_map.rules[0].match_signal_level == "critical"
        assert ts.attention_map.rules[0].treatment.bg_token == "danger-bg"


# =============================================================================
# Phase 5: DTCG + Imagery
# =============================================================================


class TestDTCGExport:
    """Test DTCG tokens.json export."""

    def test_generate_tokens(self):
        from dazzle.core.dtcg_export import generate_dtcg_tokens
        from dazzle.core.ir.themespec import ThemeSpecYAML

        ts = ThemeSpecYAML()
        tokens = generate_dtcg_tokens(ts)
        assert "color" in tokens
        assert "fontSize" in tokens
        assert "fontFamily" in tokens
        assert "dimension" in tokens
        assert "shadow" in tokens

    def test_color_tokens_nested(self):
        from dazzle.core.dtcg_export import generate_dtcg_tokens
        from dazzle.core.ir.themespec import ThemeSpecYAML

        ts = ThemeSpecYAML()
        tokens = generate_dtcg_tokens(ts)
        # primary should be a nested group
        assert "primary" in tokens["color"]
        assert "500" in tokens["color"]["primary"]
        assert tokens["color"]["primary"]["500"]["$type"] == "color"

    def test_export_file(self, tmp_path: Path):
        from dazzle.core.dtcg_export import export_dtcg_file
        from dazzle.core.ir.themespec import ThemeSpecYAML

        ts = ThemeSpecYAML()
        output = tmp_path / "tokens.json"
        result = export_dtcg_file(ts, output)
        assert result.exists()
        data = json.loads(result.read_text())
        assert "color" in data

    def test_font_family_tokens(self):
        from dazzle.core.dtcg_export import generate_dtcg_tokens
        from dazzle.core.ir.themespec import ThemeSpecYAML

        ts = ThemeSpecYAML()
        tokens = generate_dtcg_tokens(ts)
        assert tokens["fontFamily"]["body"]["$type"] == "fontFamily"
        assert "Inter" in tokens["fontFamily"]["body"]["$value"]


class TestImageryPrompts:
    """Test imagery prompt generation."""

    def test_default_prompts(self):
        from dazzle.core.imagery_prompts import generate_imagery_prompts
        from dazzle.core.ir.themespec import ThemeSpecYAML

        ts = ThemeSpecYAML()
        prompts = generate_imagery_prompts(ts)
        assert len(prompts) > 0
        # Should have hero section
        hero_prompts = [p for p in prompts if p.section == "hero"]
        assert len(hero_prompts) == 1
        assert "clean" in hero_prompts[0].prompt
        assert "professional" in hero_prompts[0].prompt

    def test_negative_prompt(self):
        from dazzle.core.imagery_prompts import generate_imagery_prompts
        from dazzle.core.ir.themespec import ThemeSpecYAML

        ts = ThemeSpecYAML()
        prompts = generate_imagery_prompts(ts)
        assert "watermark" in prompts[0].negative_prompt

    def test_custom_vocabulary(self):
        from dazzle.core.imagery_prompts import generate_imagery_prompts
        from dazzle.core.ir.themespec import ImagerySpec, ImageryVocabulary, ThemeSpecYAML

        vocab = ImageryVocabulary(
            style_keywords=["minimal", "flat"],
            mood_keywords=["calm"],
            exclusions=["noise"],
        )
        imagery = ImagerySpec(vocabulary=vocab)
        ts = ThemeSpecYAML(imagery=imagery)
        prompts = generate_imagery_prompts(ts)
        assert "minimal" in prompts[0].prompt
        assert "calm" in prompts[0].prompt
        assert prompts[0].negative_prompt == "noise"

    def test_aspect_ratio(self):
        from dazzle.core.imagery_prompts import generate_imagery_prompts
        from dazzle.core.ir.themespec import ImagerySpec, ThemeSpecYAML

        imagery = ImagerySpec(default_aspect_ratio="4:3", default_resolution="800x600")
        ts = ThemeSpecYAML(imagery=imagery)
        prompts = generate_imagery_prompts(ts)
        assert prompts[0].aspect_ratio == "4:3"
        assert prompts[0].resolution == "800x600"


# =============================================================================
# Phase 6: Bridge
# =============================================================================


class TestBridge:
    """Test ThemeSpecYAML -> ThemeSpec bridge."""

    def test_resolve_from_themespec(self):
        from dazzle.core.ir.themespec import ThemeSpecYAML
        from dazzle_ui.themes.resolver import resolve_theme_from_themespec

        ts = ThemeSpecYAML()
        theme = resolve_theme_from_themespec(ts)
        assert theme.name == "themespec-generated"
        assert len(theme.tokens.colors) > 0
        assert len(theme.tokens.spacing) > 0
        assert len(theme.tokens.radii) > 0
        assert len(theme.tokens.typography) > 0
        assert len(theme.tokens.shadows) > 0

    def test_dark_mode_variant(self):
        from dazzle.core.ir.themespec import ColorMode, PaletteSpec, ThemeSpecYAML
        from dazzle_ui.themes.resolver import resolve_theme_from_themespec

        ts = ThemeSpecYAML(palette=PaletteSpec(mode=ColorMode.AUTO))
        theme = resolve_theme_from_themespec(ts)
        assert len(theme.variants) == 1
        assert theme.variants[0].name == "dark"

    def test_light_mode_no_variant(self):
        from dazzle.core.ir.themespec import ColorMode, PaletteSpec, ThemeSpecYAML
        from dazzle_ui.themes.resolver import resolve_theme_from_themespec

        ts = ThemeSpecYAML(palette=PaletteSpec(mode=ColorMode.LIGHT))
        theme = resolve_theme_from_themespec(ts)
        assert len(theme.variants) == 0

    def test_existing_resolve_still_works(self):
        """Regression: existing resolve_theme() is unaffected."""
        from dazzle_ui.themes.resolver import resolve_theme

        theme = resolve_theme("saas-default")
        assert theme.name == "saas-default"

    def test_bridge_export(self):
        """resolve_theme_from_themespec is accessible from themes package."""
        from dazzle_ui.themes import resolve_theme_from_themespec

        assert callable(resolve_theme_from_themespec)


# =============================================================================
# Phase 7: MCP Handlers
# =============================================================================


class TestMCPHandlers:
    """Test MCP handler functions for themespec."""

    def test_get_theme_handler(self, tmp_path: Path):
        from dazzle.mcp.server.handlers.sitespec import get_theme_handler

        result = json.loads(get_theme_handler(tmp_path, {}))
        assert result["exists"] is False  # no file, defaults returned
        assert result["palette"]["brand_hue"] == 260.0

    def test_scaffold_theme_handler(self, tmp_path: Path):
        from dazzle.mcp.server.handlers.sitespec import scaffold_theme_handler

        result = json.loads(scaffold_theme_handler(tmp_path, {"brand_hue": 120}))
        assert result["success"] is True
        assert result["brand_hue"] == 120

        # Verify file was created
        assert (tmp_path / "themespec.yaml").exists()

    def test_scaffold_no_overwrite(self, tmp_path: Path):
        from dazzle.mcp.server.handlers.sitespec import scaffold_theme_handler

        scaffold_theme_handler(tmp_path, {})
        result = json.loads(scaffold_theme_handler(tmp_path, {}))
        assert result["success"] is False

    def test_validate_theme_handler(self, tmp_path: Path):
        from dazzle.mcp.server.handlers.sitespec import validate_theme_handler

        result = json.loads(validate_theme_handler(tmp_path, {}))
        assert result["is_valid"] is True

    def test_generate_tokens_handler(self, tmp_path: Path):
        from dazzle.mcp.server.handlers.sitespec import generate_tokens_handler

        result = json.loads(generate_tokens_handler(tmp_path, {}))
        assert result["success"] is True
        assert result["format"] == "W3C DTCG"
        assert (tmp_path / "tokens.json").exists()

    def test_generate_imagery_prompts_handler(self, tmp_path: Path):
        from dazzle.mcp.server.handlers.sitespec import generate_imagery_prompts_handler

        result = json.loads(generate_imagery_prompts_handler(tmp_path, {}))
        assert result["prompt_count"] > 0
        assert "prompt" in result["prompts"][0]

    def test_handler_routing(self, tmp_path: Path):
        """Test that handlers_consolidated routes theme operations."""
        from dazzle.mcp.server.handlers_consolidated import handle_sitespec

        # Use _resolved_project_path to bypass dazzle.toml requirement
        result = json.loads(
            handle_sitespec(
                {
                    "operation": "get_theme",
                    "_resolved_project_path": tmp_path,
                }
            )
        )
        assert "palette" in result

    def test_handler_routing_unknown(self, tmp_path: Path):
        from dazzle.mcp.server.handlers_consolidated import handle_sitespec

        result = json.loads(
            handle_sitespec(
                {
                    "operation": "nonexistent",
                    "_resolved_project_path": tmp_path,
                }
            )
        )
        assert "error" in result
