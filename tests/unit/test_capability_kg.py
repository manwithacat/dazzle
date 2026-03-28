"""Tests for capability discovery KG seeding."""

import tomllib
from pathlib import Path

_TOML_PATH = Path(__file__).resolve().parents[2] / "src/dazzle/mcp/semantics_kb/capabilities.toml"


class TestCapabilitiesToml:
    def test_toml_file_is_valid(self):
        toml_path = (
            Path(__file__).resolve().parents[2] / "src/dazzle/mcp/semantics_kb/capabilities.toml"
        )
        assert toml_path.exists()
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
        assert data["meta"]["category"] == "UX Capabilities"

    def test_every_entry_has_required_fields(self):
        toml_path = (
            Path(__file__).resolve().parents[2] / "src/dazzle/mcp/semantics_kb/capabilities.toml"
        )
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
        concepts = data.get("concepts", {})
        assert len(concepts) > 0
        for name, entry in concepts.items():
            assert "definition" in entry, f"{name} missing definition"
            assert "syntax" in entry, f"{name} missing syntax"
            assert "applies_to" in entry, f"{name} missing applies_to"

    def test_toml_registered_in_toml_files_list(self):
        from dazzle.mcp.semantics_kb import TOML_FILES

        assert "capabilities.toml" in TOML_FILES

    def test_widget_rules_cross_check(self):
        toml_path = (
            Path(__file__).resolve().parents[2] / "src/dazzle/mcp/semantics_kb/capabilities.toml"
        )
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
        concept_ids = set(data.get("concepts", {}).keys())
        expected = {
            "widget_rich_text",
            "widget_combobox",
            "widget_picker",
            "widget_tags",
            "widget_color",
            "widget_slider",
        }
        for key in expected:
            assert key in concept_ids, f"Missing: {key}"


class TestRegressionCrossCheck:
    def test_every_capability_key_has_toml_entry(self):
        """Cross-check: every capability key produced by rules has a TOML entry."""
        with open(_TOML_PATH, "rb") as f:
            data = tomllib.load(f)
        concept_ids = set(data.get("concepts", {}).keys())
        expected_keys = {
            "widget_rich_text",
            "widget_combobox",
            "widget_picker",
            "widget_tags",
            "widget_color",
            "widget_slider",
            "layout_kanban",
            "layout_timeline",
            "layout_related_groups",
            "layout_multi_section",
            "component_command_palette",
            "component_toggle_group",
            "completeness_unreachable",
            "completeness_missing_edit",
            "completeness_missing_list",
            "completeness_missing_create",
        }
        for key in expected_keys:
            assert key in concept_ids, f"Missing TOML entry for: {key}"

    def test_every_non_completeness_entry_has_demonstrated_in(self):
        """Every non-completeness TOML entry should list at least one example app."""
        with open(_TOML_PATH, "rb") as f:
            data = tomllib.load(f)
        for name, entry in data.get("concepts", {}).items():
            if name.startswith("completeness_"):
                continue
            demos = entry.get("demonstrated_in", [])
            assert len(demos) >= 1, f"{name} has no demonstrated_in entries"
