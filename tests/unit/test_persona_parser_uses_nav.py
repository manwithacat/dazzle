"""Tests for persona parser supporting `uses nav <name>` (#1324)."""

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl


def test_persona_parse_uses_nav():
    """Test that persona block parses `uses nav <name>` into nav_ref."""
    dsl = """
module m
app a "A"

nav teaching:
  group "Marking":
    item Assignment

persona teacher "Teacher":
  uses nav teaching
"""
    _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
    assert len(fragment.personas) == 1
    persona = fragment.personas[0]
    assert persona.id == "teacher"
    assert persona.label == "Teacher"
    assert persona.nav_ref == "teaching"


def test_persona_nav_ref_defaults_none():
    """Test that persona without `uses nav` has nav_ref=None."""
    dsl = """
module m
app a "A"

persona teacher "Teacher":
  description: "A teacher"
"""
    _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
    assert len(fragment.personas) == 1
    persona = fragment.personas[0]
    assert persona.nav_ref is None
