"""Tests for CSS delivery architecture — cascade layers and local-first delivery."""

import subprocess
import sys
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
# Layered files go into @layer framework; unlayered files are appended after.
LAYERED_ORDER = ("dazzle-layer.css", "design-system.css", "site-sections.css")
UNLAYERED_FILES = ("dz.css", "dz-tones.css")
ALL_CSS_FILES = LAYERED_ORDER + UNLAYERED_FILES


class TestFrameworkCssEntryPoint:
    def test_file_exists(self) -> None:
        assert (STATIC_CSS / "dazzle-framework.css").exists()

    def test_imports_in_canonical_order(self) -> None:
        content = (STATIC_CSS / "dazzle-framework.css").read_text()
        positions = []
        for filename in ALL_CSS_FILES:
            pos = content.find(filename)
            assert pos != -1, f"{filename} not found in dazzle-framework.css"
            positions.append(pos)
        assert positions == sorted(positions), (
            f"Import order does not match canonical: {ALL_CSS_FILES}"
        )

    def test_layered_imports_use_layer_framework(self) -> None:
        content = (STATIC_CSS / "dazzle-framework.css").read_text()
        for filename in LAYERED_ORDER:
            assert f'@import "{filename}" layer(framework)' in content

    def test_unlayered_imports_have_no_layer(self) -> None:
        content = (STATIC_CSS / "dazzle-framework.css").read_text()
        for filename in UNLAYERED_FILES:
            assert f'@import "{filename}"' in content
            assert f'@import "{filename}" layer(' not in content

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
        from dazzle_ui.runtime.css_loader import CSS_SOURCE_FILES, CSS_UNLAYERED_FILES

        assert CSS_SOURCE_FILES == LAYERED_ORDER
        assert CSS_UNLAYERED_FILES == UNLAYERED_FILES

    def test_output_contains_layer_declaration(self) -> None:
        from dazzle_ui.runtime.css_loader import get_bundled_css

        css = get_bundled_css()
        assert "@layer base, framework, app, overrides;" in css

    def test_output_wraps_layered_files_in_layer_framework(self) -> None:
        from dazzle_ui.runtime.css_loader import get_bundled_css

        css = get_bundled_css()
        assert css.count("@layer framework {") == len(LAYERED_ORDER)

    def test_unlayered_files_not_in_layer(self) -> None:
        from dazzle_ui.runtime.css_loader import get_bundled_css

        css = get_bundled_css()
        assert "unlayered" in css
        for filename in UNLAYERED_FILES:
            assert filename in css

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
        for f in ALL_CSS_FILES:
            assert f in source_map["sources"]


class TestBuildDist:
    @classmethod
    def setup_class(cls) -> None:
        """Build dist once for all tests in this class."""
        repo_root = Path(__file__).resolve().parent.parent.parent
        result = subprocess.run(
            [sys.executable, "scripts/build_dist.py"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"build_dist.py failed: {result.stderr}"

    def test_dist_css_contains_layer_declaration(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent.parent
        css = (repo_root / "dist" / "dazzle.min.css").read_text()
        assert "@layer base, framework, app, overrides;" in css

    def test_dist_css_wraps_files_in_layer(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent.parent
        css = (repo_root / "dist" / "dazzle.min.css").read_text()
        assert css.count("@layer framework {") >= 4
