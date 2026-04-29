"""Tests for #938 — `[ui] dark_mode_toggle` config flag.

Covers:
- Manifest parses the flag (default True; explicit false disables)
- ``configure_dark_mode_toggle()`` gates ``get_theme_variant()`` so a
  stale ``dz_theme=dark`` cookie cannot trap newly opted-out projects
- ``is_dark_mode_toggle_enabled()`` is exposed to Jinja so layouts can
  conditionally render the toggle
- The fix that made same-toggle actually toggle: tokens.css binds
  ``data-theme="dark"`` to ``color-scheme: dark`` so ``light-dark()``
  flips when the in-app Alpine controller toggles the attribute
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from dazzle.core.manifest import load_manifest
from dazzle_ui.runtime.theme import (
    configure_dark_mode_toggle,
    get_theme_variant,
    is_dark_mode_toggle_enabled,
    theme_variant_ctxvar,
)


@pytest.fixture(autouse=True)
def _restore_dark_mode_default() -> None:
    """Each test starts with the toggle enabled (the production
    default). Explicit tests that disable it restore on teardown."""
    configure_dark_mode_toggle(True)
    yield
    configure_dark_mode_toggle(True)


# ---------------------------------------------------------------------------
# Manifest parse
# ---------------------------------------------------------------------------


def _write_manifest(tmp_path: Path, body: str) -> Path:
    manifest = tmp_path / "dazzle.toml"
    manifest.write_text(textwrap.dedent(body))
    return manifest


class TestManifestParse:
    def test_default_is_true(self, tmp_path: Path) -> None:
        path = _write_manifest(
            tmp_path,
            """
            [project]
            name = "t"
            version = "0.0.0"
            """,
        )
        mf = load_manifest(path)
        assert mf.dark_mode_toggle is True

    def test_explicit_false_disables(self, tmp_path: Path) -> None:
        path = _write_manifest(
            tmp_path,
            """
            [project]
            name = "t"
            version = "0.0.0"

            [ui]
            dark_mode_toggle = false
            """,
        )
        mf = load_manifest(path)
        assert mf.dark_mode_toggle is False

    def test_explicit_true_enables(self, tmp_path: Path) -> None:
        path = _write_manifest(
            tmp_path,
            """
            [project]
            name = "t"
            version = "0.0.0"

            [ui]
            dark_mode_toggle = true
            """,
        )
        mf = load_manifest(path)
        assert mf.dark_mode_toggle is True


# ---------------------------------------------------------------------------
# Theme module short-circuit
# ---------------------------------------------------------------------------


class TestThemeShortCircuit:
    def test_default_returns_ctxvar_value(self) -> None:
        token = theme_variant_ctxvar.set("dark")
        try:
            assert get_theme_variant() == "dark"
        finally:
            theme_variant_ctxvar.reset(token)

    def test_disabled_forces_light_even_with_dark_cookie(self) -> None:
        """A stale ``dz_theme=dark`` cookie sets the ctxvar to ``dark``,
        but with the toggle disabled the project's brand is light-only
        — return ``light`` regardless so the user isn't trapped."""
        configure_dark_mode_toggle(False)
        token = theme_variant_ctxvar.set("dark")
        try:
            assert get_theme_variant() == "light"
        finally:
            theme_variant_ctxvar.reset(token)

    def test_enabled_returns_ctxvar_value(self) -> None:
        configure_dark_mode_toggle(True)
        token = theme_variant_ctxvar.set("dark")
        try:
            assert get_theme_variant() == "dark"
        finally:
            theme_variant_ctxvar.reset(token)

    def test_is_dark_mode_toggle_enabled_reflects_config(self) -> None:
        configure_dark_mode_toggle(True)
        assert is_dark_mode_toggle_enabled() is True
        configure_dark_mode_toggle(False)
        assert is_dark_mode_toggle_enabled() is False


# ---------------------------------------------------------------------------
# Jinja global registration
# ---------------------------------------------------------------------------


class TestJinjaGlobal:
    def test_dark_mode_toggle_enabled_is_a_jinja_global(self) -> None:
        from dazzle_ui.runtime.template_renderer import get_jinja_env

        env = get_jinja_env()
        assert "dark_mode_toggle_enabled" in env.globals

    def test_global_is_callable_and_returns_bool(self) -> None:
        from dazzle_ui.runtime.template_renderer import get_jinja_env

        env = get_jinja_env()
        fn = env.globals["dark_mode_toggle_enabled"]
        assert callable(fn)
        configure_dark_mode_toggle(False)
        assert fn() is False
        configure_dark_mode_toggle(True)
        assert fn() is True

    def test_template_can_gate_on_global(self) -> None:
        """Smoke-test that a Jinja template using
        ``{% if dark_mode_toggle_enabled() %}`` actually toggles
        rendered output as the config flips."""
        from dazzle_ui.runtime.template_renderer import get_jinja_env

        env = get_jinja_env()
        template = env.from_string(
            "{% if dark_mode_toggle_enabled() %}<button>toggle</button>{% endif %}"
        )

        configure_dark_mode_toggle(True)
        assert template.render() == "<button>toggle</button>"
        configure_dark_mode_toggle(False)
        assert template.render() == ""


# ---------------------------------------------------------------------------
# tokens.css color-scheme binding
# ---------------------------------------------------------------------------


class TestColorSchemeBinding:
    """Pin the CSS rule that makes the toggle actually do something
    in the in-app shell. Without this rule, ``light-dark()`` keeps
    resolving to the OS preference even when the Alpine controller
    sets ``data-theme="dark"``, leaving framework chrome on the light
    palette while only design-system.css HSL tokens flip."""

    def test_data_theme_dark_binds_color_scheme(self) -> None:
        css = (
            Path(__file__).resolve().parents[2] / "src/dazzle_ui/runtime/static/css/tokens.css"
        ).read_text()
        # Whitespace-flexible match to keep the test forgiving of
        # future formatting churn.
        assert '[data-theme="dark"]' in css
        # Confirm the binding lines up with `color-scheme: dark` and
        # vice versa for light. Cheap substring proximity check.
        dark_idx = css.index('[data-theme="dark"]')
        # Look up to ~80 chars ahead for the property.
        assert "color-scheme: dark" in css[dark_idx : dark_idx + 80]

        light_idx = css.index('[data-theme="light"]')
        assert "color-scheme: light" in css[light_idx : light_idx + 80]
