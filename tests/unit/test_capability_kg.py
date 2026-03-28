"""Tests for capability discovery KG seeding."""

import tomllib
from pathlib import Path


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
