"""Tests for the opt-in asset bundling system.

Covers:
- `should_bundle_assets()` resolver: every (mode, env, cli_override) cell
- `ProjectManifest.assets` parsing from `dazzle.toml`
- `base.html` branches correctly on `_bundle_assets`
- The bundled mode's script list matches what `build_dist.py` produces
  (so adding a new individual script without updating the bundle
  source list is caught at test time)
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_TEMPLATE_PATH = REPO_ROOT / "src/dazzle_ui/templates/base.html"
BUILD_DIST_PATH = REPO_ROOT / "scripts/build_dist.py"


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


class TestShouldBundleAssets:
    """Truth table for the resolver: 3 modes × 3 envs × 3 cli overrides."""

    def setup_method(self) -> None:
        # Snapshot DAZZLE_ENV so per-test assertions don't leak to siblings
        self._snapshot_env = os.environ.pop("DAZZLE_ENV", None)

    def teardown_method(self) -> None:
        if self._snapshot_env is not None:
            os.environ["DAZZLE_ENV"] = self._snapshot_env

    def test_default_mode_default_env_returns_false(self) -> None:
        from dazzle_ui.runtime.asset_bundle import should_bundle_assets

        # No mode passed, no env set, no override → individual scripts.
        assert should_bundle_assets() is False

    def test_auto_in_production_env_returns_true(self) -> None:
        from dazzle_ui.runtime.asset_bundle import should_bundle_assets

        assert should_bundle_assets("auto", env="production") is True

    def test_auto_in_staging_env_returns_true(self) -> None:
        from dazzle_ui.runtime.asset_bundle import should_bundle_assets

        # Staging is treated as production-equivalent for the bundle
        # decision (real users hit this; want fast loads).
        assert should_bundle_assets("auto", env="staging") is True

    def test_auto_in_dev_env_returns_false(self) -> None:
        from dazzle_ui.runtime.asset_bundle import should_bundle_assets

        assert should_bundle_assets("auto", env="development") is False

    def test_auto_with_no_env_returns_false(self) -> None:
        from dazzle_ui.runtime.asset_bundle import should_bundle_assets

        assert should_bundle_assets("auto", env="") is False

    def test_always_returns_true_regardless_of_env(self) -> None:
        from dazzle_ui.runtime.asset_bundle import should_bundle_assets

        assert should_bundle_assets("always", env="development") is True
        assert should_bundle_assets("always", env="") is True
        assert should_bundle_assets("always", env="production") is True

    def test_never_returns_false_regardless_of_env(self) -> None:
        from dazzle_ui.runtime.asset_bundle import should_bundle_assets

        assert should_bundle_assets("never", env="production") is False
        assert should_bundle_assets("never", env="staging") is False
        assert should_bundle_assets("never", env="") is False

    def test_cli_bundle_override_wins_over_never(self) -> None:
        from dazzle_ui.runtime.asset_bundle import should_bundle_assets

        # Project says "never bundle" — but `dazzle serve --bundle`
        # forces a one-off perf test.
        assert should_bundle_assets("never", env="production", cli_override="bundle") is True

    def test_cli_no_bundle_override_wins_over_always(self) -> None:
        from dazzle_ui.runtime.asset_bundle import should_bundle_assets

        # Project says "always bundle" — but `dazzle serve --no-bundle`
        # for ad-hoc live-reload debugging in production.
        assert should_bundle_assets("always", env="production", cli_override="no-bundle") is False

    def test_resolver_reads_dazzle_env_when_env_arg_omitted(self) -> None:
        from dazzle_ui.runtime.asset_bundle import should_bundle_assets

        os.environ["DAZZLE_ENV"] = "production"
        assert should_bundle_assets("auto") is True
        os.environ["DAZZLE_ENV"] = "development"
        assert should_bundle_assets("auto") is False


# ---------------------------------------------------------------------------
# Manifest parsing
# ---------------------------------------------------------------------------


class TestManifestAssetsParsing:
    def _write(self, body: str) -> Path:
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False, encoding="utf-8")
        tmp.write(body)
        tmp.flush()
        return Path(tmp.name)

    def test_default_assets_is_auto(self) -> None:
        from dazzle.core.manifest import load_manifest

        path = self._write('[project]\nname = "t"\nversion = "0.1"\nmodules = ["app.dsl"]\n')
        m = load_manifest(path)
        assert m.assets == "auto"

    def test_explicit_assets_always_preserved(self) -> None:
        from dazzle.core.manifest import load_manifest

        path = self._write(
            '[project]\nname = "t"\nversion = "0.1"\nmodules = ["app.dsl"]\n'
            '\n[ui]\nassets = "always"\n'
        )
        m = load_manifest(path)
        assert m.assets == "always"

    def test_explicit_assets_never_preserved(self) -> None:
        from dazzle.core.manifest import load_manifest

        path = self._write(
            '[project]\nname = "t"\nversion = "0.1"\nmodules = ["app.dsl"]\n'
            '\n[ui]\nassets = "never"\n'
        )
        m = load_manifest(path)
        assert m.assets == "never"

    def test_invalid_assets_value_raises(self) -> None:
        from dazzle.core.manifest import load_manifest

        path = self._write(
            '[project]\nname = "t"\nversion = "0.1"\nmodules = ["app.dsl"]\n'
            '\n[ui]\nassets = "yolo"\n'
        )
        with pytest.raises(ValueError, match="auto"):
            load_manifest(path)


# ---------------------------------------------------------------------------
# base.html template branching
# ---------------------------------------------------------------------------


class TestBaseHtmlBranches:
    def test_template_branches_on_bundle_assets(self) -> None:
        text = BASE_TEMPLATE_PATH.read_text()
        assert "{% if _bundle_assets %}" in text

    def test_bundle_branch_loads_dist_min_js(self) -> None:
        text = BASE_TEMPLATE_PATH.read_text()
        # The bundled branch must reference dist/dazzle.min.js
        bundle_idx = text.index("{% if _bundle_assets %}")
        else_idx = text.index("{% else %}", bundle_idx)
        bundle_block = text[bundle_idx:else_idx]
        assert "dist/dazzle.min.js" in bundle_block

    def test_bundle_branch_loads_dist_min_css(self) -> None:
        text = BASE_TEMPLATE_PATH.read_text()
        bundle_idx = text.index("{% if _bundle_assets %}")
        else_idx = text.index("{% else %}", bundle_idx)
        bundle_block = text[bundle_idx:else_idx]
        assert "dist/dazzle.min.css" in bundle_block

    def _bundle_branches(self) -> tuple[str, str]:
        """Return (bundle_block, individual_block) — anchors on the
        `_bundle_assets` branch, not any earlier `{% else %}` in
        base.html."""
        text = BASE_TEMPLATE_PATH.read_text()
        bundle_idx = text.index("{% if _bundle_assets %}")
        else_idx = text.index("{% else %}", bundle_idx)
        endif_idx = text.index("{% endif %}", else_idx)
        return text[bundle_idx:else_idx], text[else_idx:endif_idx]

    def test_individual_branch_loads_htmx_extensions(self) -> None:
        """The else-branch loads each script individually."""
        _bundle, ind_block = self._bundle_branches()
        # All 11 htmx scripts are in the individual branch
        assert "vendor/htmx.min.js" in ind_block
        assert "vendor/htmx-ext-sse.js" in ind_block
        assert "vendor/idiomorph-ext.min.js" in ind_block

    def test_individual_branch_loads_alpine(self) -> None:
        _bundle, ind_block = self._bundle_branches()
        assert "vendor/alpine.min.js" in ind_block
        assert "js/dz-alpine.js" in ind_block
        assert "js/dashboard-builder.js" in ind_block


# ---------------------------------------------------------------------------
# Drift guard: bundle <-> individual list parity
# ---------------------------------------------------------------------------


class TestBundleListParity:
    """When a developer adds a script to the individual branch in
    `base.html`, they must also add it to `JS_SOURCES` in
    `scripts/build_dist.py` so the bundled mode picks it up. This test
    catches accidental drift."""

    def _individual_scripts(self) -> set[str]:
        text = BASE_TEMPLATE_PATH.read_text()
        # Anchor on the bundle-specific branch, not any earlier else
        bundle_idx = text.index("{% if _bundle_assets %}")
        else_idx = text.index("{% else %}", bundle_idx)
        endif_idx = text.index("{% endif %}", else_idx)
        ind_block = text[else_idx:endif_idx]
        # Pull all `vendor/*.js` and `js/*.js` paths
        paths = re.findall(r"['\"]([^'\"]+\.js)['\"]\s*\|\s*static_url", ind_block)
        return {p.split("/")[-1] for p in paths}

    def _bundle_sources(self) -> set[str]:
        text = BUILD_DIST_PATH.read_text()
        # Pull every `STATIC / "<seg>" / "<file.js>"` path (and
        # site-static variants) declared in JS_SOURCES.
        # Heuristic: filenames that end in `.js"`.
        names = set(re.findall(r'"([^"]+\.js)"', text))
        # Filter out test references and the FRAMEWORK_JS bare-name set
        return {n for n in names if "/" not in n and n.endswith(".js")}

    def test_every_individual_script_is_in_the_bundle(self) -> None:
        ind = self._individual_scripts()
        bundle = self._bundle_sources()
        missing = ind - bundle
        assert not missing, (
            "Scripts in base.html's individual branch but NOT in "
            f"build_dist.py's JS_SOURCES: {sorted(missing)}\n\n"
            "Add them to scripts/build_dist.py JS_SOURCES so the "
            "bundled mode picks them up. Otherwise users on "
            "[ui] assets = 'always' will get a broken page."
        )
