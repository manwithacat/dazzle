"""Tests for #947 cycle 1 — dz-debug introspection helper.

Pins the source-level shape of `window.dzDebug`:
- Method surface (dataIdentity, componentRoots, lastSettleAt,
  lastSettleTarget, reset)
- Subscribes to `htmx:afterSettle` so tests can poll for "did
  the morph fire yet"
- Uses `Alpine.$data` to resolve the proxy via a selector
- Uses a `WeakMap` so the proxy registry doesn't leak references
- Bundled into the framework JS dist so projects loading
  `dist/dazzle.min.js` get it for free

The dynamic browser-driven gates land in cycles 2-3 of #947;
this file covers the cycle-1 source contract.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DZ_DEBUG_PATH = REPO_ROOT / "src/dazzle_ui/runtime/static/js/dz-debug.js"
BASE_TEMPLATE_PATH = REPO_ROOT / "src/dazzle_ui/templates/base.html"
BUILD_DIST_PATH = REPO_ROOT / "scripts/build_dist.py"


class TestSourceShape:
    def _load(self) -> str:
        return DZ_DEBUG_PATH.read_text()

    def test_file_exists(self) -> None:
        assert DZ_DEBUG_PATH.exists(), "dz-debug.js must ship under static/js/"

    def test_namespace_is_window_dzDebug(self) -> None:
        """The introspection surface is exposed at `window.dzDebug`
        so tests can reach it via `page.evaluate(...)` and humans
        can reach it via the browser console."""
        source = self._load()
        assert "window.dzDebug" in source

    def test_exposes_dataIdentity(self) -> None:
        """The load-bearing API: returns a stable string identity
        for an Alpine `$data` proxy at a selector. Two calls return
        the same string iff the same proxy is active."""
        source = self._load()
        assert "dataIdentity:" in source or "dataIdentity," in source

    def test_exposes_componentRoots(self) -> None:
        """Lists `[x-data]` roots — useful for spotting zombie
        roots after morph."""
        source = self._load()
        assert "componentRoots:" in source or "componentRoots," in source

    def test_exposes_lastSettleAt(self) -> None:
        """Returns the timestamp of the most recent
        `htmx:afterSettle`. Tests poll on this rather than
        `setTimeout`-and-pray."""
        source = self._load()
        assert "lastSettleAt:" in source or "lastSettleAt," in source

    def test_exposes_lastSettleTarget(self) -> None:
        source = self._load()
        assert "lastSettleTarget:" in source or "lastSettleTarget," in source

    def test_exposes_reset(self) -> None:
        """Test convenience method to drop the proxy registry between
        cases so proxy-id counters don't leak across tests."""
        source = self._load()
        assert "reset:" in source or "reset," in source


class TestRegistryHooks:
    def _load(self) -> str:
        return DZ_DEBUG_PATH.read_text()

    def test_subscribes_to_htmx_aftersettle(self) -> None:
        """The settle timestamp is updated via an event listener,
        not by polling. Listener attaches to `document.body` so it
        catches every settle regardless of which subtree morphed."""
        source = self._load()
        assert 'addEventListener("htmx:afterSettle"' in source

    def test_uses_alpine_data_for_proxy_resolution(self) -> None:
        """Same lookup path #936/#945 use — `Alpine.$data(el)`
        returns the live proxy. Capturing it via closure would go
        stale exactly the way #945 documented."""
        source = self._load()
        assert "Alpine.$data" in source

    def test_uses_weakmap_for_proxy_registry(self) -> None:
        """A `WeakMap` keyed on the proxy lets the GC reclaim the
        entry when the proxy is destroyed. Strong references would
        keep dead proxies alive, defeating the staleness-detection
        purpose."""
        source = self._load()
        assert "WeakMap" in source

    def test_methods_no_op_without_alpine(self) -> None:
        """During boot (Alpine not yet loaded) calls return `null`
        rather than throwing. The proxy lookup explicitly guards
        on `Alpine.$data` availability."""
        source = self._load()
        assert "Alpine.$data" in source
        # Guard pattern present — typeof check or truthy check
        assert 'typeof window.Alpine.$data !== "function"' in source or "!window.Alpine" in source


class TestBundleIntegration:
    def test_loaded_from_base_template(self) -> None:
        """`base.html` references `dz-debug.js` so projects using
        the framework's base layout get the introspection surface
        for free."""
        base = BASE_TEMPLATE_PATH.read_text()
        assert "dz-debug.js" in base

    def test_listed_in_build_dist_js_sources(self) -> None:
        """`scripts/build_dist.py` includes dz-debug.js in
        `JS_SOURCES` so projects loading `dist/dazzle.min.js` (with
        their own custom base template) get the introspection
        surface bundled."""
        source = BUILD_DIST_PATH.read_text()
        assert '"js" / "dz-debug.js"' in source

    def test_in_framework_set_for_comment_stripping(self) -> None:
        """`FRAMEWORK_JS` controls which files get comment-stripping
        in the dist bundle. `dz-debug.js` carries a multi-line
        docstring + section banners that should be stripped."""
        source = BUILD_DIST_PATH.read_text()
        assert '"dz-debug.js"' in source
