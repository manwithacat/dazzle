"""Tests for the ThemeSpec declarative theme system.

Covers: IR models, OKLCH, generators, loader, DTCG, imagery, bridge, MCP handlers.
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

# =============================================================================
# Phase 1: IR Models
# =============================================================================


class TestThemeSpecIR:
    """Test ThemeSpecYAML IR models."""

    def test_ir_models_combined(self):
        """Combined: defaults, frozen, custom, typography ratios, attention rule,
        field value lookup, agent-editable check, validation bounds, roundtrip,
        and IR package exports."""
        from dazzle.core.ir import ColorMode as IRColorMode
        from dazzle.core.ir import PaletteSpec as IRPaletteSpec
        from dazzle.core.ir import ThemeSpecYAML as IRThemeSpecYAML
        from dazzle.core.ir.themespec import (
            TYPOGRAPHY_RATIO_VALUES,
            AttentionRule,
            ColorMode,
            PaletteSpec,
            ThemeSpecYAML,
            VisualTreatment,
        )

        # Defaults
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

        # Frozen
        with pytest.raises(ValidationError):
            ts.palette = None  # type: ignore[assignment]

        # Custom palette
        palette = PaletteSpec(brand_hue=180.0, brand_chroma=0.2, mode=ColorMode.DARK)
        ts2 = ThemeSpecYAML(palette=palette)
        assert ts2.palette.brand_hue == 180.0
        assert ts2.palette.mode == "dark"

        # Typography ratio values
        assert TYPOGRAPHY_RATIO_VALUES["major_third"] == 1.250
        assert TYPOGRAPHY_RATIO_VALUES["golden_ratio"] == 1.618
        assert len(TYPOGRAPHY_RATIO_VALUES) == 8

        # Attention rule
        treatment = VisualTreatment(bg_token="danger-bg", icon="alert")
        rule = AttentionRule(match_signal_level="critical", treatment=treatment)
        assert rule.match_signal_level == "critical"
        assert rule.treatment.bg_token == "danger-bg"

        # Field value lookup
        assert ts.get_field_value("palette.brand_hue") == 260.0
        assert ts.get_field_value("typography.ratio") == "major_third"
        assert ts.get_field_value("nonexistent.path") is None

        # Agent editable
        assert ts.is_agent_editable("palette.brand_hue") is True
        assert ts.is_agent_editable("meta.version") is False

        # Validation bounds
        with pytest.raises(ValidationError):
            PaletteSpec(brand_hue=400.0)
        with pytest.raises(ValidationError):
            PaletteSpec(brand_chroma=0.5)

        # Serialization roundtrip
        data = ts.model_dump(mode="json")
        ts3 = ThemeSpecYAML(**data)
        assert ts3.palette.brand_hue == ts.palette.brand_hue
        assert ts3.typography.ratio == ts.typography.ratio

        # IR exports
        assert IRThemeSpecYAML is not None
        assert IRPaletteSpec is not None
        assert IRColorMode is not None


# =============================================================================
# Phase 2: OKLCH
# =============================================================================


class TestOKLCH:
    """Test OKLCH palette generation."""

    def test_oklch_combined(self):
        """Combined: oklch_to_css basic + alpha, generate_palette light/dark/
        scale completeness, and semantic overrides."""
        from dazzle.core.oklch import generate_palette, oklch_to_css

        # oklch_to_css basic
        result = oklch_to_css(0.5, 0.15, 260.0)
        assert result.startswith("oklch(")
        assert "260.0" in result
        assert "/" not in result

        # oklch_to_css alpha
        result_alpha = oklch_to_css(0.5, 0.15, 260.0, alpha=0.5)
        assert "/ 0.50" in result_alpha

        # generate_palette light: key tokens
        palette = generate_palette(260.0, 0.15, "light")
        for k in (
            "primary-500",
            "secondary-500",
            "accent-500",
            "neutral-500",
            "success",
            "warning",
            "danger",
            "info",
            "bg-primary",
            "text-primary",
            "border-default",
        ):
            assert k in palette

        # light vs dark differ
        dark = generate_palette(260.0, 0.15, "dark")
        assert palette["bg-primary"] != dark["bg-primary"]

        # scale completeness
        for prefix in ["primary", "secondary", "accent", "neutral"]:
            for step in ["50", "100", "200", "300", "400", "500", "600", "700", "800", "950"]:
                assert f"{prefix}-{step}" in palette, f"Missing {prefix}-{step}"

        # semantic overrides
        overridden = generate_palette(260.0, 0.15, semantic_overrides={"success_hue": 200.0})
        assert "success" in overridden
        assert "200.0" in overridden["success"]


# =============================================================================
# Phase 3: Generators
# =============================================================================


class TestGenerators:
    """Test theme token generators."""

    def test_generators_combined(self):
        """Combined: type scale + line heights, spacing scale + density, shape
        tokens (subtle/medium and sharp/none)."""
        from dazzle.core.theme_generators import (
            generate_shape_tokens,
            generate_spacing_scale,
            generate_type_scale,
        )

        # Type scale
        scale = generate_type_scale(16, "major_third")
        assert "text-base" in scale
        assert "text-xs" in scale
        assert "text-6xl" in scale
        assert scale["text-base"] == "1.0000rem"
        base_val = float(scale["text-base"].replace("rem", ""))
        lg_val = float(scale["text-lg"].replace("rem", ""))
        assert lg_val > base_val

        # Type scale line heights
        scale_lh = generate_type_scale(16, "major_third", 1.6, 1.2)
        assert scale_lh["text-base-lh"] == "1.6"
        assert scale_lh["text-xl-lh"] == "1.2"

        # Spacing scale
        spacing = generate_spacing_scale(4, "comfortable")
        assert "space-0" in spacing
        assert spacing["space-0"] == "0"
        assert "space-4" in spacing
        assert spacing["space-4"] == "1.0000rem"

        # Spacing density
        compact = generate_spacing_scale(4, "compact")
        spacious = generate_spacing_scale(4, "spacious")
        compact_val = float(compact["space-4"].replace("rem", ""))
        spacious_val = float(spacious["space-4"].replace("rem", ""))
        assert spacious_val > compact_val

        # Shape tokens (subtle/medium)
        tokens = generate_shape_tokens("subtle", "medium", 1)
        assert "radius-sm" in tokens
        assert "radius-md" in tokens
        assert "shadow-sm" in tokens
        assert "shadow-xl" in tokens
        assert tokens["border-width"] == "1px"

        # Shape tokens (sharp/none)
        sharp = generate_shape_tokens("sharp", "none", 0)
        assert sharp["radius-sm"] == "0"
        assert sharp["shadow-sm"] == "none"
        assert sharp["border-width"] == "0px"


# =============================================================================
# Phase 4: Loader
# =============================================================================


class TestThemeSpecLoader:
    """Test ThemeSpec YAML loader."""

    def test_loader_combined(self, tmp_path: Path):
        """Combined: create default + custom, save+load, load missing
        (defaults & raises), themespec_exists, scaffold + no-overwrite,
        validate + agent edit check, attention rules YAML roundtrip."""
        import yaml

        from dazzle.core.themespec_loader import (
            ThemeSpecError,
            create_default_themespec,
            load_themespec,
            save_themespec,
            scaffold_themespec,
            themespec_exists,
            validate_agent_edit,
            validate_themespec,
        )

        # create_default
        ts_def = create_default_themespec()
        assert ts_def.palette.brand_hue == 260.0

        # create custom
        ts_custom = create_default_themespec(brand_hue=180.0, brand_chroma=0.2)
        assert ts_custom.palette.brand_hue == 180.0
        assert ts_custom.palette.brand_chroma == 0.2

        # validate valid + agent edit
        assert validate_themespec(ts_def).is_valid
        assert validate_agent_edit(ts_def, "palette.brand_hue") is True
        assert validate_agent_edit(ts_def, "meta.version") is False

        # save+load roundtrip (subdir A)
        sub_a = tmp_path / "a"
        sub_a.mkdir()
        ts_save = create_default_themespec(brand_hue=120.0)
        save_themespec(sub_a, ts_save)
        loaded = load_themespec(sub_a)
        assert loaded.palette.brand_hue == 120.0
        assert loaded.palette.brand_chroma == 0.15
        assert loaded.typography.ratio == "major_third"

        # load missing: defaults
        sub_b = tmp_path / "b"
        sub_b.mkdir()
        ts_missing = load_themespec(sub_b, use_defaults=True)
        assert ts_missing.palette.brand_hue == 260.0

        # load missing: raises
        sub_c = tmp_path / "c"
        sub_c.mkdir()
        with pytest.raises(ThemeSpecError):
            load_themespec(sub_c, use_defaults=False)

        # themespec_exists
        sub_d = tmp_path / "d"
        sub_d.mkdir()
        assert themespec_exists(sub_d) is False
        save_themespec(sub_d, create_default_themespec())
        assert themespec_exists(sub_d) is True

        # scaffold creates and respects no-overwrite
        sub_e = tmp_path / "e"
        sub_e.mkdir()
        path = scaffold_themespec(sub_e, brand_hue=90.0, brand_chroma=0.1)
        assert path is not None
        assert path.exists()
        ts_scaffold = load_themespec(sub_e)
        assert ts_scaffold.palette.brand_hue == 90.0
        assert scaffold_themespec(sub_e) is None  # no overwrite

        # parse_with_attention_rules: YAML roundtrip
        sub_f = tmp_path / "f"
        sub_f.mkdir()
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
        (sub_f / "themespec.yaml").write_text(yaml.dump(data))
        ts_attn = load_themespec(sub_f)
        assert len(ts_attn.attention_map.rules) == 1
        assert ts_attn.attention_map.rules[0].match_signal_level == "critical"
        assert ts_attn.attention_map.rules[0].treatment.bg_token == "danger-bg"


# =============================================================================
# Phase 5: DTCG + Imagery
# =============================================================================


class TestDTCGExport:
    """Test DTCG tokens.json export."""

    def test_dtcg_combined(self, tmp_path: Path):
        """Combined: generate_tokens shape, nested color groups, export_file,
        font family tokens."""
        from dazzle.core.dtcg_export import export_dtcg_file, generate_dtcg_tokens
        from dazzle.core.ir.themespec import ThemeSpecYAML

        ts = ThemeSpecYAML()
        tokens = generate_dtcg_tokens(ts)

        # Top-level keys
        assert "color" in tokens
        assert "fontSize" in tokens
        assert "fontFamily" in tokens
        assert "dimension" in tokens
        assert "shadow" in tokens

        # Nested color groups
        assert "primary" in tokens["color"]
        assert "500" in tokens["color"]["primary"]
        assert tokens["color"]["primary"]["500"]["$type"] == "color"

        # Font family tokens
        assert tokens["fontFamily"]["body"]["$type"] == "fontFamily"
        assert "Inter" in tokens["fontFamily"]["body"]["$value"]

        # Export file
        output = tmp_path / "tokens.json"
        result = export_dtcg_file(ts, output)
        assert result.exists()
        data = json.loads(result.read_text())
        assert "color" in data


class TestImageryPrompts:
    """Test imagery prompt generation."""

    def test_imagery_combined(self):
        """Combined: defaults (hero section), negative prompt, custom
        vocabulary, aspect ratio + resolution."""
        from dazzle.core.imagery_prompts import generate_imagery_prompts
        from dazzle.core.ir.themespec import (
            ImagerySpec,
            ImageryVocabulary,
            ThemeSpecYAML,
        )

        # Defaults
        ts = ThemeSpecYAML()
        prompts = generate_imagery_prompts(ts)
        assert len(prompts) > 0
        hero_prompts = [p for p in prompts if p.section == "hero"]
        assert len(hero_prompts) == 1
        assert "clean" in hero_prompts[0].prompt
        assert "professional" in hero_prompts[0].prompt

        # Negative prompt
        assert "watermark" in prompts[0].negative_prompt

        # Custom vocabulary
        vocab = ImageryVocabulary(
            style_keywords=["minimal", "flat"],
            mood_keywords=["calm"],
            exclusions=["noise"],
        )
        ts_custom = ThemeSpecYAML(imagery=ImagerySpec(vocabulary=vocab))
        custom_prompts = generate_imagery_prompts(ts_custom)
        assert "minimal" in custom_prompts[0].prompt
        assert "calm" in custom_prompts[0].prompt
        assert custom_prompts[0].negative_prompt == "noise"

        # Aspect ratio + resolution
        ts_ar = ThemeSpecYAML(
            imagery=ImagerySpec(default_aspect_ratio="4:3", default_resolution="800x600")
        )
        ar_prompts = generate_imagery_prompts(ts_ar)
        assert ar_prompts[0].aspect_ratio == "4:3"
        assert ar_prompts[0].resolution == "800x600"


# =============================================================================
# Phase 6: Bridge
# =============================================================================


class TestBridge:
    """Test ThemeSpecYAML -> ThemeSpec bridge."""

    def test_bridge_combined(self):
        """Combined: resolve from themespec, dark-mode variant (auto),
        light-mode no variant, existing resolve regression, package export."""
        from dazzle.core.ir.themespec import ColorMode, PaletteSpec, ThemeSpecYAML
        from dazzle.page.themes import (
            resolve_theme_from_themespec as pkg_export,
        )
        from dazzle.page.themes.resolver import (
            resolve_theme,
            resolve_theme_from_themespec,
        )

        # Default resolve
        theme = resolve_theme_from_themespec(ThemeSpecYAML())
        assert theme.name == "themespec-generated"
        assert len(theme.tokens.colors) > 0
        assert len(theme.tokens.spacing) > 0
        assert len(theme.tokens.radii) > 0
        assert len(theme.tokens.typography) > 0
        assert len(theme.tokens.shadows) > 0

        # Auto -> dark variant
        ts_auto = ThemeSpecYAML(palette=PaletteSpec(mode=ColorMode.AUTO))
        theme_auto = resolve_theme_from_themespec(ts_auto)
        assert len(theme_auto.variants) == 1
        assert theme_auto.variants[0].name == "dark"

        # Light -> no variant
        ts_light = ThemeSpecYAML(palette=PaletteSpec(mode=ColorMode.LIGHT))
        theme_light = resolve_theme_from_themespec(ts_light)
        assert len(theme_light.variants) == 0

        # Existing resolve still works
        existing = resolve_theme("saas-default")
        assert existing.name == "saas-default"

        # Package export
        assert callable(pkg_export)


# =============================================================================
# Phase 7: MCP Handlers
# =============================================================================


class TestMCPHandlers:
    """Test MCP handler functions for themespec."""

    def test_handlers_combined(self, tmp_path: Path):
        """Combined: get_theme, scaffold + no-overwrite, validate,
        generate_tokens, generate_imagery_prompts, handler_routing
        (known + unknown op)."""
        from dazzle.mcp.server.handlers.sitespec import (
            generate_imagery_prompts_handler,
            generate_tokens_handler,
            get_theme_handler,
            scaffold_theme_handler,
            validate_theme_handler,
        )
        from dazzle.mcp.server.handlers_consolidated import handle_sitespec

        # get_theme: defaults
        sub_get = tmp_path / "get"
        sub_get.mkdir()
        result = json.loads(get_theme_handler(sub_get, {}))
        assert result["exists"] is False
        assert result["palette"]["brand_hue"] == 260.0

        # scaffold creates file
        sub_scaffold = tmp_path / "scaffold"
        sub_scaffold.mkdir()
        result = json.loads(scaffold_theme_handler(sub_scaffold, {"brand_hue": 120}))
        assert result["success"] is True
        assert result["brand_hue"] == 120
        assert (sub_scaffold / "themespec.yaml").exists()

        # scaffold no-overwrite
        result2 = json.loads(scaffold_theme_handler(sub_scaffold, {}))
        assert result2["success"] is False

        # validate
        sub_v = tmp_path / "validate"
        sub_v.mkdir()
        v_result = json.loads(validate_theme_handler(sub_v, {}))
        assert v_result["is_valid"] is True

        # generate_tokens
        sub_t = tmp_path / "tokens"
        sub_t.mkdir()
        t_result = json.loads(generate_tokens_handler(sub_t, {}))
        assert t_result["success"] is True
        assert t_result["format"] == "W3C DTCG"
        assert (sub_t / "tokens.json").exists()

        # generate_imagery_prompts
        sub_i = tmp_path / "imagery"
        sub_i.mkdir()
        i_result = json.loads(generate_imagery_prompts_handler(sub_i, {}))
        assert i_result["prompt_count"] > 0
        assert "prompt" in i_result["prompts"][0]

        # handler routing (known op)
        sub_r = tmp_path / "route"
        sub_r.mkdir()
        r_result = json.loads(
            handle_sitespec({"operation": "get_theme", "_resolved_project_path": sub_r})
        )
        assert "palette" in r_result

        # handler routing (unknown op)
        u_result = json.loads(
            handle_sitespec({"operation": "nonexistent", "_resolved_project_path": sub_r})
        )
        assert "error" in u_result
