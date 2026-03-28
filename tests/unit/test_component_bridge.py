"""Tests for the dz-component-bridge.js script."""

import pathlib

BRIDGE_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle_ui"
    / "runtime"
    / "static"
    / "js"
    / "dz-component-bridge.js"
)


def test_bridge_script_exists():
    assert BRIDGE_PATH.exists(), f"Bridge script not found at {BRIDGE_PATH}"


def test_bridge_script_has_required_patterns():
    content = BRIDGE_PATH.read_text()
    assert "htmx:beforeSwap" in content
    assert "htmx:afterSettle" in content
    assert "data-dz-widget" in content
    assert "registerWidget" in content


def test_bridge_script_is_iife():
    """Bridge must be wrapped in an IIFE to avoid polluting global scope."""
    content = BRIDGE_PATH.read_text()
    # Strip leading block comment (if any) before checking for the IIFE wrapper
    import re

    stripped = re.sub(r"^/\*.*?\*/\s*", "", content, flags=re.DOTALL).strip()
    assert stripped.startswith("(function")
