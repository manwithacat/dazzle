"""Cyfuture-pilot regression: an unmigrated `for persona X:` used to be
silently skipped by the scenario parser, then `persona X:` re-dispatched
as a top-level PersonaSpec, surfacing as a misleading "Duplicate persona"
linker error with the same module name on both sides.

After Plan 15 follow-up, the parser raises an actionable error pointing
at PR #998's grammar migration."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from dazzle.core.errors import DazzleError
from dazzle.core.parser import parse_modules


def _write_dsl(text: str) -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".dsl", delete=False)
    f.write(text)
    f.close()
    return Path(f.name)


def test_for_persona_in_scenario_body_raises_actionable_error() -> None:
    """The scenario body is a place the cyfuture pilot found the silent
    skip. An unmigrated `for persona X:` triggers a parse error with a
    sed hint, not a downstream "Duplicate persona" linker error."""
    dsl = """module synthetic
app sample "Demo"

persona agent "Agent":
  description: "test"

scenario test_scenario "Test":
  description: "Tests the parser hint"
  for persona agent:
    given:
      - some setup
"""
    path = _write_dsl(dsl)
    with pytest.raises(DazzleError, match="`for` is not valid"):
        parse_modules([path])


def test_actionable_error_mentions_pr_998_and_migration_command() -> None:
    """The error should say what was renamed and how to migrate."""
    dsl = """module synthetic
app sample "Demo"

scenario s "S":
  for persona alice:
    given:
      - x
"""
    path = _write_dsl(dsl)
    with pytest.raises(DazzleError) as excinfo:
        parse_modules([path])
    msg = str(excinfo.value)
    assert "#998" in msg or "as" in msg.lower()
    assert "sed" in msg or "rename" in msg.lower() or "migrate" in msg.lower()
