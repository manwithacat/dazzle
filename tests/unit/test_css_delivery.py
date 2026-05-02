"""Tests for CSS delivery architecture — cascade layers and local-first delivery."""

import subprocess
import sys
import tempfile
from pathlib import Path

STATIC_DIR = (
    Path(__file__).resolve().parent.parent.parent / "src" / "dazzle_ui" / "runtime" / "static"
)
STATIC_CSS = STATIC_DIR / "css"

# Legacy ordering retained for the dazzle-framework.css entry-point
# tests below — that file is the pre-v0.62 cascade and is kept for
# tests that pin its existence.
LEGACY_LAYERED = ("dazzle-layer.css", "design-system.css", "site-sections.css")
LEGACY_UNLAYERED = ("dz.css", "dz-tones.css")
LEGACY_ALL = LEGACY_LAYERED + LEGACY_UNLAYERED

# Canonical order — must match static/css/dazzle.css and css_loader.py.
# Each entry is (layer_name, path_relative_to_static).
LAYERED_ORDER: tuple[tuple[str, str], ...] = (
    ("reset", "css/reset.css"),
    ("vendor", "vendor/tom-select.css"),
    ("vendor", "vendor/flatpickr.css"),
    ("vendor", "vendor/quill.snow.css"),
    # vendor/pickr.css removed in #976 — colour widget uses native input.
    ("tokens", "css/tokens.css"),
    ("tokens", "css/design-system.css"),
    ("base", "css/base.css"),
    ("utilities", "css/utilities.css"),
    ("components", "css/components/badge.css"),
    ("components", "css/components/button.css"),
    ("components", "css/components/dashboard.css"),
    ("components", "css/components/detail.css"),
    ("components", "css/components/form.css"),
    ("components", "css/components/fragments.css"),
    ("components", "css/components/htmx-states.css"),
    ("components", "css/components/pdf-viewer.css"),
    ("components", "css/components/regions.css"),
    ("components", "css/components/table.css"),
    ("components", "css/dazzle-layer.css"),
    ("components", "css/site-sections.css"),
)
UNLAYERED_FILES: tuple[str, ...] = (
    "css/dz.css",
    "css/dz-widgets.css",
    "css/dz-tones.css",
)
ALL_CSS_PATHS = tuple(p for _, p in LAYERED_ORDER) + UNLAYERED_FILES


class TestFrameworkCssEntryPoint:
    """Pre-v0.62 dazzle-framework.css entry — kept around but no longer
    served by base.html (see TestDazzleCssEntry below). These tests pin
    its file shape so we notice if it is accidentally repurposed."""

    def test_file_exists(self) -> None:
        assert (STATIC_CSS / "dazzle-framework.css").exists()

    def test_imports_in_canonical_order(self) -> None:
        content = (STATIC_CSS / "dazzle-framework.css").read_text()
        positions = []
        for filename in LEGACY_ALL:
            pos = content.find(filename)
            assert pos != -1, f"{filename} not found in dazzle-framework.css"
            positions.append(pos)
        assert positions == sorted(positions), (
            f"Import order does not match canonical: {LEGACY_ALL}"
        )

    def test_layered_imports_use_layer_framework(self) -> None:
        content = (STATIC_CSS / "dazzle-framework.css").read_text()
        for filename in LEGACY_LAYERED:
            assert f'@import "{filename}" layer(framework)' in content

    def test_unlayered_imports_have_no_layer(self) -> None:
        content = (STATIC_CSS / "dazzle-framework.css").read_text()
        for filename in LEGACY_UNLAYERED:
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
    """The runtime CSS bundle (served at /styles/dazzle.css) must
    mirror the canonical static/css/dazzle.css cascade — including
    every component family. Pre-#920, the loader only emitted the
    three legacy files, so .dz-button et al. arrived with zero rules
    on any page using the bundle (notably the marketing site)."""

    def test_canonical_order(self) -> None:
        from dazzle_ui.runtime.css_loader import CSS_SOURCE_FILES, CSS_UNLAYERED_FILES

        assert CSS_SOURCE_FILES == LAYERED_ORDER
        assert CSS_UNLAYERED_FILES == UNLAYERED_FILES

    def test_output_contains_layer_declaration(self) -> None:
        from dazzle_ui.runtime.css_loader import get_bundled_css

        css = get_bundled_css()
        # v0.62: layer order matches static/css/dazzle.css
        assert "@layer reset, vendor, tokens, base, utilities, components, overrides;" in css

    def test_output_wraps_each_layered_file_in_its_layer(self) -> None:
        from dazzle_ui.runtime.css_loader import get_bundled_css

        css = get_bundled_css()
        # Each (layer, path) entry produces one `@layer <name> {` block.
        for layer, _path in LAYERED_ORDER:
            assert f"@layer {layer} {{" in css, f"missing @layer {layer} block"

    def test_output_includes_every_component_family(self) -> None:
        """#920 regression guard: every components/*.css family must
        be concatenated, not just the three legacy files."""
        from dazzle_ui.runtime.css_loader import get_bundled_css

        css = get_bundled_css()
        for family in (
            "components/badge.css",
            "components/button.css",
            "components/dashboard.css",
            "components/detail.css",
            "components/form.css",
            "components/fragments.css",
            "components/htmx-states.css",
            "components/pdf-viewer.css",
            "components/regions.css",
            "components/table.css",
        ):
            assert family in css, f"{family} missing from bundle"

    def test_button_css_contains_dz_button_rule(self) -> None:
        """End-to-end: the bundle the marketing site receives MUST
        contain a `.dz-button` rule. Pre-#920 it shipped zero."""
        from dazzle_ui.runtime.css_loader import get_bundled_css

        css = get_bundled_css()
        assert ".dz-button" in css

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
        for f in ALL_CSS_PATHS:
            assert f in source_map["sources"]


class TestDazzleCssEntry:
    """v0.62 (post-merge bug fix): base.html must load `dazzle.css` —
    NOT the legacy `dazzle-framework.css` — and dazzle.css must @import
    every component family + every legacy framework file the templates
    still rely on. Found broken in production by aegismark on the v0.62
    merge: base.html had been left pointing at dazzle-framework.css
    which only imported the legacy stack and skipped every
    components/*.css file (incl. the load-bearing fragments.css)."""

    @classmethod
    def _base_html(cls) -> str:
        repo_root = Path(__file__).resolve().parent.parent.parent
        return (repo_root / "src/dazzle_ui/templates/base.html").read_text()

    @classmethod
    def _dazzle_css(cls) -> str:
        return (STATIC_CSS / "dazzle.css").read_text()

    def test_base_html_loads_dazzle_css(self) -> None:
        contents = self._base_html()
        assert "'css/dazzle.css'" in contents

    def test_base_html_does_not_load_legacy_entry(self) -> None:
        """Guard against accidental revert to the legacy entry point."""
        contents = self._base_html()
        assert "'css/dazzle-framework.css'" not in contents

    def test_dazzle_css_imports_every_component_family(self) -> None:
        """The 9 component families MUST be @imported — they own every
        .dz-* class the v0.62 refactor moved templates to consume."""
        css = self._dazzle_css()
        for family in (
            "components/badge.css",
            "components/button.css",
            "components/dashboard.css",
            "components/detail.css",
            "components/form.css",
            "components/fragments.css",
            "components/htmx-states.css",
            "components/pdf-viewer.css",
            "components/regions.css",
            "components/table.css",
        ):
            assert f'@import url("{family}")' in css, f"{family} missing"

    def test_dazzle_css_imports_legacy_framework_files(self) -> None:
        """The legacy framework files still own rules templates rely on
        (dz-app structural shell, design-system tokens, dz-tones tinting,
        dz.css transitions, etc.). They MUST be @imported by dazzle.css
        so the cascade still resolves their rules."""
        css = self._dazzle_css()
        for legacy in (
            "dazzle-layer.css",
            "design-system.css",
            "site-sections.css",
            "dz.css",
            "dz-widgets.css",
            "dz-tones.css",
        ):
            assert f'@import url("{legacy}")' in css, f"{legacy} missing"


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
        css = (repo_root / "src/dazzle_ui/runtime/static/dist" / "dazzle.min.css").read_text()
        # v0.62: layer order matches static/css/dazzle.css (#920).
        assert "@layer reset, vendor, tokens, base, utilities, components, overrides;" in css

    def test_dist_css_wraps_files_in_each_layer(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent.parent
        css = (repo_root / "src/dazzle_ui/runtime/static/dist" / "dazzle.min.css").read_text()
        # Every layer used by the canonical cascade should produce at
        # least one wrapping `@layer <name> {` block in the bundle.
        for layer in ("reset", "vendor", "tokens", "base", "utilities", "components"):
            assert f"@layer {layer} {{" in css, f"missing @layer {layer} block"

    def test_dist_css_contains_dz_button_rule(self) -> None:
        """#920 regression guard: the bundled CDN distribution MUST
        contain a `.dz-button` rule. Pre-#920 it shipped zero."""
        repo_root = Path(__file__).resolve().parent.parent.parent
        css = (repo_root / "src/dazzle_ui/runtime/static/dist" / "dazzle.min.css").read_text()
        assert ".dz-button" in css
