"""Tests for project-local site-section override loader (#1110 Part A)."""

from pathlib import Path

from dazzle.http.runtime.renderers.site_section_builder import render_typed_section
from dazzle.http.runtime.renderers.site_section_override_loader import (
    SectionOverrideRegistry,
    discover_section_overrides,
    write_section_overrides_readme,
)


def test_empty_registry_is_falsy() -> None:
    reg = SectionOverrideRegistry()
    assert not reg
    assert reg.list_overrides() == []


def test_register_and_get_roundtrips() -> None:
    reg = SectionOverrideRegistry()

    def builder(section: dict) -> str:
        return "<x/>"

    reg.register("custom", builder)
    assert reg.get("custom") is builder
    assert reg.get("unknown") is None
    assert reg.list_overrides() == ["custom"]
    assert bool(reg) is True


def test_register_replaces_previous_builder() -> None:
    reg = SectionOverrideRegistry()

    def first(section: dict) -> str:
        return "first"

    def second(section: dict) -> str:
        return "second"

    reg.register("custom", first)
    reg.register("custom", second)
    assert reg.get("custom") is second


def test_discover_missing_directory_returns_empty_registry(tmp_path: Path) -> None:
    """No site_sections/ dir → empty registry, no errors."""
    reg = discover_section_overrides(tmp_path)
    assert isinstance(reg, SectionOverrideRegistry)
    assert not reg


def test_discover_picks_up_build_section_function(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "site_sections"
    plugin_dir.mkdir()
    (plugin_dir / "custom.py").write_text(
        "def build_pricing_section(section):\n"
        "    return '<section class=\"custom-pricing\">x</section>'\n"
    )
    reg = discover_section_overrides(tmp_path)
    assert "pricing" in reg.list_overrides()
    builder = reg.get("pricing")
    assert builder is not None
    assert "custom-pricing" in builder({"type": "pricing"})


def test_discover_skips_underscore_prefixed_files(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "site_sections"
    plugin_dir.mkdir()
    (plugin_dir / "_helpers.py").write_text("def build_pricing_section(section):\n    return ''\n")
    reg = discover_section_overrides(tmp_path)
    assert reg.list_overrides() == []


def test_discover_skips_functions_with_wrong_arity(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "site_sections"
    plugin_dir.mkdir()
    (plugin_dir / "broken.py").write_text(
        "def build_pricing_section(section, extra):\n    return ''\n"
    )
    reg = discover_section_overrides(tmp_path)
    assert reg.list_overrides() == []


def test_discover_isolates_broken_file_from_others(tmp_path: Path) -> None:
    """One broken plugin must not poison the rest of the registry."""
    plugin_dir = tmp_path / "site_sections"
    plugin_dir.mkdir()
    (plugin_dir / "broken.py").write_text("raise RuntimeError('boom')\n")
    (plugin_dir / "ok.py").write_text("def build_pricing_section(section):\n    return 'ok'\n")
    reg = discover_section_overrides(tmp_path)
    assert reg.get("pricing") is not None


def test_render_typed_section_uses_override_when_registered(tmp_path: Path) -> None:
    """An override beats the framework default for the same type."""
    reg = SectionOverrideRegistry()
    reg.register("pricing", lambda s: "<section class='custom'/>")
    html = render_typed_section({"type": "pricing"}, overrides=reg)
    assert html == "<section class='custom'/>"


def test_render_typed_section_falls_back_to_default(tmp_path: Path) -> None:
    """When the registry doesn't know the type, the framework default wins."""
    reg = SectionOverrideRegistry()
    html = render_typed_section({"type": "pricing"}, overrides=reg)
    # Framework default emits dz-section-pricing.
    assert "dz-section-pricing" in html


def test_render_typed_section_allows_override_for_new_type(tmp_path: Path) -> None:
    """Overrides can register entirely new section types, not just override defaults."""
    reg = SectionOverrideRegistry()
    reg.register("project_specific", lambda s: "<section class='ps'/>")
    html = render_typed_section({"type": "project_specific"}, overrides=reg)
    assert html == "<section class='ps'/>"


def test_write_readme_creates_when_absent(tmp_path: Path) -> None:
    path = write_section_overrides_readme(tmp_path)
    assert path is not None
    assert path == tmp_path / "site_sections" / "README.md"
    assert "Project-local site section builders" in path.read_text()


def test_write_readme_is_idempotent(tmp_path: Path) -> None:
    """A custom README in site_sections/ survives the scaffold call."""
    plugin_dir = tmp_path / "site_sections"
    plugin_dir.mkdir()
    readme = plugin_dir / "README.md"
    readme.write_text("CUSTOM")
    result = write_section_overrides_readme(tmp_path)
    assert result is None  # not created — already existed
    assert readme.read_text() == "CUSTOM"
