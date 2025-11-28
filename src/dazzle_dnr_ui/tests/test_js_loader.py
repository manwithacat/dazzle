"""
Tests for the JavaScript loader module.

Tests module loading, bundling, and caching functionality.
"""

import pytest

from dazzle_dnr_ui.runtime.js_loader import (
    load_js_module,
    load_js_modules,
    generate_iife_bundle,
    generate_esm_bundle,
    get_runtime_js,
    get_realtime_js,
    clear_cache,
)


# =============================================================================
# Module Loading Tests
# =============================================================================


class TestModuleLoading:
    """Tests for loading individual JS modules."""

    def test_load_signals_module(self):
        """Test loading the signals module."""
        source = load_js_module("signals.js")
        assert "createSignal" in source
        assert "createEffect" in source
        assert "batch" in source

    def test_load_state_module(self):
        """Test loading the state module."""
        source = load_js_module("state.js")
        assert "getState" in source
        assert "setState" in source
        assert "stateStores" in source

    def test_load_components_module(self):
        """Test loading the components module."""
        source = load_js_module("components.js")
        assert "registerComponent" in source
        assert "Page" in source
        assert "Card" in source
        assert "Button" in source

    def test_load_realtime_module(self):
        """Test loading the realtime module."""
        source = load_js_module("realtime.js")
        assert "RealtimeClient" in source
        assert "OptimisticManager" in source
        assert "PresenceManager" in source

    def test_load_nonexistent_module(self):
        """Test that loading nonexistent module raises error."""
        with pytest.raises(FileNotFoundError):
            load_js_module("nonexistent.js")

    def test_load_multiple_modules(self):
        """Test loading multiple modules at once."""
        modules = load_js_modules(["signals.js", "state.js"])
        assert len(modules) == 2
        assert "signals.js" in modules
        assert "state.js" in modules

    def test_load_all_modules(self):
        """Test loading all modules."""
        modules = load_js_modules(None)
        assert len(modules) >= 10  # We have at least 10 core modules


# =============================================================================
# Bundle Generation Tests
# =============================================================================


class TestBundleGeneration:
    """Tests for bundle generation."""

    def test_iife_bundle_basic(self):
        """Test basic IIFE bundle generation."""
        bundle = generate_iife_bundle(include_realtime=False)

        # Should be wrapped in IIFE
        assert "(function(global)" in bundle
        assert "window : global);" in bundle

        # Should export DNR global
        assert "global.DNR" in bundle

    def test_iife_bundle_contains_core_functions(self):
        """Test that IIFE bundle contains core functions."""
        bundle = generate_iife_bundle()

        assert "createSignal" in bundle
        assert "createEffect" in bundle
        assert "createElement" in bundle
        assert "registerComponent" in bundle

    def test_iife_bundle_with_realtime(self):
        """Test IIFE bundle includes realtime when requested."""
        bundle = generate_iife_bundle(include_realtime=True)

        assert "RealtimeClient" in bundle
        assert "OptimisticManager" in bundle

    def test_esm_bundle_basic(self):
        """Test basic ESM bundle generation."""
        bundle = generate_esm_bundle(include_realtime=False)

        # ESM should have export statements
        assert "export" in bundle

    def test_esm_bundle_with_realtime(self):
        """Test ESM bundle includes realtime when requested."""
        bundle = generate_esm_bundle(include_realtime=True)

        assert "RealtimeClient" in bundle


# =============================================================================
# Convenience Function Tests
# =============================================================================


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_get_runtime_js_iife(self):
        """Test getting runtime JS in IIFE format."""
        js = get_runtime_js(use_esm=False)
        assert "(function(global)" in js

    def test_get_runtime_js_esm(self):
        """Test getting runtime JS in ESM format."""
        js = get_runtime_js(use_esm=True)
        assert "export" in js

    def test_get_realtime_js(self):
        """Test getting realtime JS."""
        js = get_realtime_js()
        assert "RealtimeClient" in js


# =============================================================================
# Cache Tests
# =============================================================================


class TestCaching:
    """Tests for caching functionality."""

    def test_cache_works(self):
        """Test that caching returns same result."""
        first = load_js_module("signals.js")
        second = load_js_module("signals.js")
        # Should be same object due to caching
        assert first is second

    def test_clear_cache(self):
        """Test clearing the cache."""
        first = load_js_module("signals.js")
        clear_cache()
        second = load_js_module("signals.js")
        # After cache clear, should be different objects with same content
        assert first == second
