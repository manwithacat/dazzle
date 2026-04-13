"""Parser tests for the `fitness:` block inside entity declarations.

Part of Agent-Led Fitness v1 Task 2.
"""

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl


def _entity(dsl: str, name: str):
    _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
    for entity in fragment.entities:
        if entity.name == name:
            return entity
    raise AssertionError(f"entity {name} not found in parsed fragment")


def test_entity_with_fitness_repr_fields_parses() -> None:
    source = """
module fitness_demo

app fitness_demo "Demo"

entity Ticket "Ticket":
  id: uuid pk
  title: str(200) required
  status: enum[new, closed] required
  assignee_id: ref User

  fitness:
    repr_fields: [title, status, assignee_id]

entity User "User":
  id: uuid pk
  email: str(200) required
"""
    ticket = _entity(source, "Ticket")
    assert ticket.fitness is not None
    assert ticket.fitness.repr_fields == ["title", "status", "assignee_id"]


def test_entity_without_fitness_block_parses() -> None:
    source = """
module fitness_demo

app fitness_demo "Demo"

entity Note "Note":
  id: uuid pk
  body: text
"""
    note = _entity(source, "Note")
    assert note.fitness is None


def test_fitness_repr_fields_must_reference_declared_fields() -> None:
    source = """
module fitness_demo

app fitness_demo "Demo"

entity Ticket "Ticket":
  id: uuid pk
  title: str(200) required

  fitness:
    repr_fields: [title, nonexistent]
"""
    with pytest.raises(Exception, match="nonexistent"):
        parse_dsl(source, Path("test.dsl"))
