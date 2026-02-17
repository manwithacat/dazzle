"""Tests for the project-level override registry (v0.29.0).

Covers:
- scan_project_overrides() declaration header parsing
- extract_block_hashes() content hashing
- build_registry() full pipeline
- save_registry() / load_registry() persistence
- check_overrides() compatibility checking
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def framework_templates_dir() -> Path:
    """Return the framework templates directory."""
    return Path(__file__).parent.parent.parent / "src" / "dazzle_ui" / "templates"


@pytest.fixture()
def project_dir(tmp_path: Path) -> Path:
    """Create a project templates dir with a declared override."""
    templates = tmp_path / "templates"
    templates.mkdir()
    layout_dir = templates / "layouts"
    layout_dir.mkdir()
    (layout_dir / "app_shell.html").write_text(
        "{# dazzle:override layouts/app_shell.html #}\n"
        "{# dazzle:blocks sidebar_brand, sidebar_nav #}\n"
        '{% extends "dz://layouts/app_shell.html" %}\n'
        "{% block sidebar_brand %}\n"
        "<h1>Custom Brand</h1>\n"
        "{% endblock %}\n"
        "{% block sidebar_nav %}\n"
        "<nav>Custom Nav</nav>\n"
        "{% endblock %}\n"
    )
    return tmp_path


class TestScanProjectOverrides:
    """scan_project_overrides() parses declaration headers."""

    def test_finds_override_declaration(self, project_dir: Path) -> None:
        from dazzle_ui.runtime.override_registry import scan_project_overrides

        result = scan_project_overrides(project_dir / "templates")
        assert len(result) == 1
        assert result[0]["target"] == "layouts/app_shell.html"
        assert result[0]["blocks"] == ["sidebar_brand", "sidebar_nav"]
        assert result[0]["source"] == "layouts/app_shell.html"

    def test_ignores_templates_without_declaration(self, tmp_path: Path) -> None:
        from dazzle_ui.runtime.override_registry import scan_project_overrides

        templates = tmp_path / "templates"
        templates.mkdir()
        (templates / "custom.html").write_text("<div>No declaration</div>")

        result = scan_project_overrides(templates)
        assert result == []

    def test_nonexistent_dir_returns_empty(self) -> None:
        from dazzle_ui.runtime.override_registry import scan_project_overrides

        result = scan_project_overrides(Path("/nonexistent"))
        assert result == []

    def test_override_without_blocks_header(self, tmp_path: Path) -> None:
        from dazzle_ui.runtime.override_registry import scan_project_overrides

        templates = tmp_path / "templates"
        templates.mkdir()
        (templates / "page.html").write_text(
            "{# dazzle:override components/form.html #}\n"
            '{% extends "dz://components/form.html" %}\n'
        )
        result = scan_project_overrides(templates)
        assert len(result) == 1
        assert result[0]["blocks"] == []

    def test_multiple_overrides(self, tmp_path: Path) -> None:
        from dazzle_ui.runtime.override_registry import scan_project_overrides

        templates = tmp_path / "templates"
        templates.mkdir()
        (templates / "a.html").write_text("{# dazzle:override layouts/app_shell.html #}\n")
        (templates / "b.html").write_text("{# dazzle:override components/form.html #}\n")

        result = scan_project_overrides(templates)
        assert len(result) == 2
        targets = {r["target"] for r in result}
        assert "layouts/app_shell.html" in targets
        assert "components/form.html" in targets


class TestExtractBlockHashes:
    """extract_block_hashes() computes content hashes."""

    def test_hashes_existing_blocks(self, framework_templates_dir: Path) -> None:
        from dazzle_ui.runtime.override_registry import extract_block_hashes

        hashes = extract_block_hashes(
            framework_templates_dir,
            "layouts/app_shell.html",
            ["sidebar_brand", "sidebar_nav"],
        )
        assert "sidebar_brand" in hashes
        assert "sidebar_nav" in hashes
        assert len(hashes["sidebar_brand"]) == 8  # SHA-256 first 8 chars

    def test_missing_block_not_in_result(self, framework_templates_dir: Path) -> None:
        from dazzle_ui.runtime.override_registry import extract_block_hashes

        hashes = extract_block_hashes(
            framework_templates_dir,
            "layouts/app_shell.html",
            ["nonexistent_block"],
        )
        assert "nonexistent_block" not in hashes

    def test_missing_template_returns_empty(self, framework_templates_dir: Path) -> None:
        from dazzle_ui.runtime.override_registry import extract_block_hashes

        hashes = extract_block_hashes(
            framework_templates_dir,
            "nonexistent.html",
            ["sidebar_brand"],
        )
        assert hashes == {}

    def test_same_content_same_hash(self, tmp_path: Path) -> None:
        from dazzle_ui.runtime.override_registry import extract_block_hashes

        content = "{% block test_block %}Hello World{% endblock %}"
        (tmp_path / "tpl.html").write_text(content)

        hash1 = extract_block_hashes(tmp_path, "tpl.html", ["test_block"])
        hash2 = extract_block_hashes(tmp_path, "tpl.html", ["test_block"])
        assert hash1 == hash2

    def test_different_content_different_hash(self, tmp_path: Path) -> None:
        from dazzle_ui.runtime.override_registry import extract_block_hashes

        (tmp_path / "tpl.html").write_text("{% block test_block %}Hello{% endblock %}")
        hash1 = extract_block_hashes(tmp_path, "tpl.html", ["test_block"])

        (tmp_path / "tpl.html").write_text("{% block test_block %}World{% endblock %}")
        hash2 = extract_block_hashes(tmp_path, "tpl.html", ["test_block"])

        assert hash1["test_block"] != hash2["test_block"]


class TestBuildRegistry:
    """build_registry() combines scanning and hashing."""

    def test_builds_complete_registry(
        self, project_dir: Path, framework_templates_dir: Path
    ) -> None:
        from dazzle_ui.runtime.override_registry import build_registry

        registry = build_registry(
            project_dir / "templates",
            framework_templates_dir,
            framework_version="0.29.0",
        )
        assert "template_overrides" in registry
        entries = registry["template_overrides"]
        assert len(entries) == 1
        assert entries[0]["target"] == "layouts/app_shell.html"
        assert entries[0]["framework_version"] == "0.29.0"
        assert "sidebar_brand" in entries[0]["block_hashes"]

    def test_empty_project_dir(self, tmp_path: Path, framework_templates_dir: Path) -> None:
        from dazzle_ui.runtime.override_registry import build_registry

        templates = tmp_path / "templates"
        templates.mkdir()
        registry = build_registry(templates, framework_templates_dir)
        assert registry["template_overrides"] == []


class TestPersistence:
    """save_registry() and load_registry() round-trip."""

    def test_round_trip(self, tmp_path: Path) -> None:
        from dazzle_ui.runtime.override_registry import load_registry, save_registry

        registry = {
            "template_overrides": [
                {
                    "source": "layouts/app_shell.html",
                    "target": "layouts/app_shell.html",
                    "blocks": ["sidebar_brand"],
                    "framework_version": "0.29.0",
                    "block_hashes": {"sidebar_brand": "a1b2c3d4"},
                }
            ]
        }
        path = tmp_path / ".dazzle" / "overrides.json"
        save_registry(registry, path)
        loaded = load_registry(path)
        assert loaded == registry

    def test_load_missing_file(self, tmp_path: Path) -> None:
        from dazzle_ui.runtime.override_registry import load_registry

        result = load_registry(tmp_path / "nonexistent.json")
        assert result == {"template_overrides": []}

    def test_load_corrupt_file(self, tmp_path: Path) -> None:
        from dazzle_ui.runtime.override_registry import load_registry

        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not json {{{")
        result = load_registry(bad_file)
        assert result == {"template_overrides": []}

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        from dazzle_ui.runtime.override_registry import save_registry

        path = tmp_path / "deep" / "nested" / "overrides.json"
        save_registry({"template_overrides": []}, path)
        assert path.is_file()


class TestCheckOverrides:
    """check_overrides() compares stored vs current block hashes."""

    def test_unchanged_blocks_report_ok(
        self, project_dir: Path, framework_templates_dir: Path, tmp_path: Path
    ) -> None:
        from dazzle_ui.runtime.override_registry import (
            build_registry,
            check_overrides,
            save_registry,
        )

        # Build registry with current hashes
        registry = build_registry(project_dir / "templates", framework_templates_dir, "0.29.0")
        registry_path = tmp_path / "overrides.json"
        save_registry(registry, registry_path)

        # Check against same framework — all should be ok
        results = check_overrides(project_dir / "templates", framework_templates_dir, registry_path)
        assert len(results) == 2  # sidebar_brand, sidebar_nav
        assert all(r["status"] == "ok" for r in results)

    def test_changed_block_reports_changed(self, tmp_path: Path) -> None:
        from dazzle_ui.runtime.override_registry import check_overrides, save_registry

        # Create a framework template
        fw_dir = tmp_path / "framework"
        fw_dir.mkdir()
        (fw_dir / "test.html").write_text("{% block header %}Original{% endblock %}")

        # Save registry with old hash
        registry = {
            "template_overrides": [
                {
                    "source": "test.html",
                    "target": "test.html",
                    "blocks": ["header"],
                    "framework_version": "0.28.0",
                    "block_hashes": {"header": "old_hash"},
                }
            ]
        }
        registry_path = tmp_path / "overrides.json"
        save_registry(registry, registry_path)

        # Framework block has changed
        results = check_overrides(tmp_path / "project", fw_dir, registry_path)
        assert len(results) == 1
        assert results[0]["status"] == "changed"
        assert results[0]["old_hash"] == "old_hash"
        assert results[0]["new_hash"] != "old_hash"

    def test_no_registry_returns_empty(self, tmp_path: Path) -> None:
        from dazzle_ui.runtime.override_registry import check_overrides

        results = check_overrides(tmp_path, tmp_path, tmp_path / "missing.json")
        assert results == []
