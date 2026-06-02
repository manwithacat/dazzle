"""Tests for persona parser supporting `uses nav <name>` (#1324)."""

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError


def test_persona_parse_uses_nav():
    """Test that persona block parses `uses nav <name>` into nav_ref."""
    dsl = """
module m
app a "A"

nav teaching:
  group "Marking":
    Assignment

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


def test_nav_group_item_keyword_is_a_clear_parse_error():
    """#1328: a nav group lists bare names — `item X` is rejected with a clear
    error (was previously a silently-dropped phantom `item` entry)."""
    dsl = """
module m
app a "A"

nav teaching:
  group "Marking":
    item Assignment
"""
    with pytest.raises(ParseError, match=r"no `item` keyword"):
        parse_dsl(dsl, Path("test.dsl"))


def test_nav_group_extra_token_on_item_line_is_an_error():
    """One entity/workspace name per line; a stray trailing token errors."""
    dsl = """
module m
app a "A"

nav teaching:
  group "Marking":
    Assignment Extra
"""
    with pytest.raises(ParseError, match=r"one entity or workspace name per line"):
        parse_dsl(dsl, Path("test.dsl"))
