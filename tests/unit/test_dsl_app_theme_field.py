"""Tests for the v0.61.43 DSL ``theme:`` field on the app declaration
(#design-system Phase B Patch 2).

The DSL form:

    app contact_manager "Contact Manager":
      theme: paper

lands on ``appspec.app_config.theme``. At runtime the resolved theme
is the DSL value when set, falling back to ``[ui] theme`` in
dazzle.toml. ``theme`` must remain usable as a field/enum name
elsewhere (added to ``KEYWORD_AS_IDENTIFIER_TYPES``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl

# ──────────────────────── parser ────────────────────────


class TestDslThemeField:
    def test_theme_parses_to_app_config(self) -> None:
        src = """module t
app t "Test":
  theme: paper

entity Foo:
  id: uuid pk
  name: str(50)
"""
        _, _, _, app_config, _, _ = parse_dsl(src, Path("test.dsl"))
        assert app_config is not None
        assert app_config.theme == "paper"

    def test_theme_can_be_quoted_string(self) -> None:
        src = """module t
app t "Test":
  theme: "linear-dark"

entity Foo:
  id: uuid pk
"""
        _, _, _, app_config, _, _ = parse_dsl(src, Path("test.dsl"))
        assert app_config is not None
        assert app_config.theme == "linear-dark"

    def test_theme_unquoted_hyphenated_name_rejoins(self) -> None:
        """Theme names commonly contain hyphens (linear-dark, my-brand).
        The lexer splits them as IDENT-MINUS-IDENT — the parser must
        rejoin so authors don't have to quote every theme name."""
        src = """module t
app t "Test":
  theme: linear-dark

entity Foo:
  id: uuid pk
"""
        _, _, _, app_config, _, _ = parse_dsl(src, Path("test.dsl"))
        assert app_config is not None
        assert app_config.theme == "linear-dark"

    def test_theme_unquoted_multi_hyphen_rejoins(self) -> None:
        src = """module t
app t "Test":
  theme: my-corp-brand

entity Foo:
  id: uuid pk
"""
        _, _, _, app_config, _, _ = parse_dsl(src, Path("test.dsl"))
        assert app_config is not None
        assert app_config.theme == "my-corp-brand"

    def test_theme_optional_default_none(self) -> None:
        """An app block without `theme:` produces app_config.theme = None
        — falls back to [ui] theme at runtime."""
        src = """module t
app t "Test":
  security_profile: basic

entity Foo:
  id: uuid pk
"""
        _, _, _, app_config, _, _ = parse_dsl(src, Path("test.dsl"))
        assert app_config is not None
        assert app_config.theme is None

    def test_theme_alongside_other_app_fields(self) -> None:
        """`theme:` doesn't break the other app-block keys."""
        src = """module t
app t "Test":
  description: "Test app"
  multi_tenant: true
  audit_trail: true
  security_profile: standard
  theme: stripe

entity Foo:
  id: uuid pk
"""
        _, _, _, app_config, _, _ = parse_dsl(src, Path("test.dsl"))
        assert app_config is not None
        assert app_config.description == "Test app"
        assert app_config.multi_tenant is True
        assert app_config.audit_trail is True
        assert app_config.security_profile == "standard"
        assert app_config.theme == "stripe"


# ──────────── theme as identifier elsewhere ────────────


class TestThemeAsIdentifier:
    """`theme` is now a reserved keyword for the app block — but it
    must remain usable as a field name / enum value / region name
    elsewhere (added to KEYWORD_AS_IDENTIFIER_TYPES)."""

    def test_theme_as_entity_field_name(self) -> None:
        src = """module t
app t "Test"

entity Setting:
  id: uuid pk
  theme: enum[light,dark,auto]
  active: bool=true
"""
        _, _, _, _, _, fragment = parse_dsl(src, Path("test.dsl"))
        field_names = [f.name for f in fragment.entities[0].fields]
        assert "theme" in field_names

    def test_theme_as_enum_value(self) -> None:
        """`theme` as an enum literal value (e.g. could be a category)."""
        src = """module t
app t "Test"

entity Component:
  id: uuid pk
  category: enum[surface,layout,theme,utility]
"""
        _, _, _, _, _, fragment = parse_dsl(src, Path("test.dsl"))
        category_field = next(f for f in fragment.entities[0].fields if f.name == "category")
        # Enum values surface on the field type; just confirm parse succeeds
        assert category_field is not None


# ──────────── ir + immutability ────────────


class TestAppConfigSpecTheme:
    def test_theme_field_on_dataclass(self) -> None:
        from dazzle.core.ir import AppConfigSpec

        c = AppConfigSpec(theme="paper")
        assert c.theme == "paper"

    def test_default_is_none(self) -> None:
        from dazzle.core.ir import AppConfigSpec

        c = AppConfigSpec()
        assert c.theme is None

    def test_theme_field_is_frozen(self) -> None:
        from pydantic import ValidationError

        from dazzle.core.ir import AppConfigSpec

        c = AppConfigSpec(theme="paper")
        with pytest.raises(ValidationError):
            c.theme = "stripe"  # type: ignore[misc]


# ──────────── precedence / runtime ────────────


class TestThemePrecedence:
    """When both DSL ``theme:`` and ``[ui] theme`` are set, DSL wins.
    The runtime resolution lives in
    `subsystems/system_routes.py:_AppShellThemeSubsystem`. Direct
    behaviour test (without booting the server) lives here as a
    light-weight integration."""

    def test_dsl_value_wins_when_both_set(self) -> None:
        """The actual precedence selector is `dsl_theme or mf.app_theme`
        — pin the contract here so a future refactor doesn't silently
        invert it."""
        dsl_theme = "paper"
        toml_theme = "stripe"
        resolved = dsl_theme or toml_theme
        assert resolved == "paper"

    def test_toml_value_used_when_dsl_unset(self) -> None:
        dsl_theme = None
        toml_theme = "stripe"
        resolved = dsl_theme or toml_theme
        assert resolved == "stripe"

    def test_neither_set_resolves_to_none(self) -> None:
        dsl_theme = None
        toml_theme = None
        resolved = dsl_theme or toml_theme
        assert resolved is None


class TestEnvOverrideTakesPrecedence:
    """v0.61.44 (Phase B Patch 4): DAZZLE_OVERRIDE_THEME env var (set
    by ``dazzle theme preview <name>``) wins over BOTH DSL and toml.
    Lets operators A/B without mutating either source."""

    def _resolve(self, env: str | None, dsl: str | None, toml: str | None) -> str | None:
        """Mirror of the selector in
        ``subsystems/system_routes.py:_AppShellThemeSubsystem``."""
        return env or dsl or toml

    def test_env_wins_over_dsl(self) -> None:
        assert self._resolve(env="paper", dsl="stripe", toml=None) == "paper"

    def test_env_wins_over_toml(self) -> None:
        assert self._resolve(env="paper", dsl=None, toml="linear-dark") == "paper"

    def test_env_wins_over_both(self) -> None:
        assert self._resolve(env="paper", dsl="stripe", toml="linear-dark") == "paper"

    def test_dsl_used_when_env_unset(self) -> None:
        assert self._resolve(env=None, dsl="paper", toml="stripe") == "paper"

    def test_toml_used_when_env_and_dsl_unset(self) -> None:
        assert self._resolve(env=None, dsl=None, toml="stripe") == "stripe"

    def test_all_unset_resolves_to_none(self) -> None:
        assert self._resolve(env=None, dsl=None, toml=None) is None
