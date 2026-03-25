"""Tests for CSS delivery architecture — cascade layers and local-first delivery."""

from __future__ import annotations

import tempfile
from pathlib import Path

STATIC_CSS = (
    Path(__file__).resolve().parent.parent.parent
    / "src"
    / "dazzle_ui"
    / "runtime"
    / "static"
    / "css"
)

# Canonical order — must match dazzle-framework.css, css_loader.py, build_dist.py
CANONICAL_ORDER = ["dazzle-layer.css", "design-system.css", "dz.css", "site-sections.css"]


class TestFrameworkCssEntryPoint:
    def test_file_exists(self) -> None:
        assert (STATIC_CSS / "dazzle-framework.css").exists()

    def test_imports_in_canonical_order(self) -> None:
        content = (STATIC_CSS / "dazzle-framework.css").read_text()
        positions = []
        for filename in CANONICAL_ORDER:
            pos = content.find(filename)
            assert pos != -1, f"{filename} not found in dazzle-framework.css"
            positions.append(pos)
        assert positions == sorted(positions), (
            f"Import order does not match canonical: {CANONICAL_ORDER}"
        )

    def test_all_imports_use_layer_framework(self) -> None:
        content = (STATIC_CSS / "dazzle-framework.css").read_text()
        for filename in CANONICAL_ORDER:
            assert f'@import "{filename}" layer(framework)' in content

    def test_no_feedback_widget_import(self) -> None:
        content = (STATIC_CSS / "dazzle-framework.css").read_text()
        assert "feedback-widget" not in content


class TestCdnDefault:
    def test_manifest_cdn_default_is_false(self) -> None:
        from dazzle.core.manifest import ProjectManifest

        m = ProjectManifest(name="t", version="0", project_root=".", module_paths=[])
        assert m.cdn is False

    def test_manifest_loader_cdn_default_is_false(self) -> None:
        from dazzle.core.manifest import load_manifest

        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write('[project]\nname = "test"\nversion = "0.1"\nmodules = ["app.dsl"]\n')
            f.flush()
            m = load_manifest(Path(f.name))
        assert m.cdn is False

    def test_manifest_explicit_cdn_true_preserved(self) -> None:
        from dazzle.core.manifest import load_manifest

        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(
                '[project]\nname = "test"\nversion = "0.1"\nmodules = ["app.dsl"]\n\n[ui]\ncdn = true\n'
            )
            f.flush()
            m = load_manifest(Path(f.name))
        assert m.cdn is True


class TestCssLoader:
    def test_canonical_order(self) -> None:
        from dazzle_ui.runtime.css_loader import CSS_SOURCE_FILES

        assert CSS_SOURCE_FILES == CANONICAL_ORDER

    def test_output_contains_layer_declaration(self) -> None:
        from dazzle_ui.runtime.css_loader import get_bundled_css

        css = get_bundled_css()
        assert "@layer base, framework, app, overrides;" in css

    def test_output_wraps_files_in_layer_framework(self) -> None:
        from dazzle_ui.runtime.css_loader import get_bundled_css

        css = get_bundled_css()
        assert css.count("@layer framework {") == len(CANONICAL_ORDER)

    def test_output_contains_source_map(self) -> None:
        from dazzle_ui.runtime.css_loader import get_bundled_css

        css = get_bundled_css()
        assert "sourceMappingURL=data:application/json;base64," in css

    def test_source_map_lists_all_sources(self) -> None:
        import base64
        import json

        from dazzle_ui.runtime.css_loader import get_bundled_css

        css = get_bundled_css()
        marker = "sourceMappingURL=data:application/json;base64,"
        start = css.index(marker) + len(marker)
        end = css.index(" */", start)
        b64 = css[start:end]
        source_map = json.loads(base64.b64decode(b64))
        assert source_map["version"] == 3
        for f in CANONICAL_ORDER:
            assert f in source_map["sources"]
