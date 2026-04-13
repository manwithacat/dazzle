"""Parser tests for lifecycle: blocks inside entity declarations (plan task 3)."""

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl

LIFECYCLE_DSL = """
module test_app

app test_app "Test"

entity Ticket "Support Ticket":
  id: uuid pk
  assignee_id: ref User
  resolution_notes: text
  status: enum[new, assigned, in_progress, resolved, closed] required

  lifecycle:
    status_field: status
    states:
      - new         (order: 0)
      - assigned    (order: 1)
      - in_progress (order: 2)
      - resolved    (order: 3)
      - closed      (order: 4)
    transitions:
      - from: new
        to: assigned
        evidence: assignee_id != null
        role: support_agent
      - from: in_progress
        to: resolved
        evidence: resolution_notes != null
        roles: [support_agent, manager]

entity User "User":
  id: uuid pk
  email: str(200)
"""

NO_LIFECYCLE_DSL = """
module test_app

app test_app "Test"

entity Note "Note":
  id: uuid pk
  body: text
"""


def _first_entity(dsl: str, name: str):
    _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
    for entity in fragment.entities:
        if entity.name == name:
            return entity
    raise AssertionError(f"entity {name} not found in parsed fragment")


def test_parse_lifecycle_block_happy_path() -> None:
    ticket = _first_entity(LIFECYCLE_DSL, "Ticket")

    assert ticket.lifecycle is not None
    lc = ticket.lifecycle
    assert lc.status_field == "status"

    # States
    assert len(lc.states) == 5
    assert lc.states[0].name == "new"
    assert lc.states[0].order == 0
    assert lc.states[1].name == "assigned"
    assert lc.states[1].order == 1
    assert lc.states[4].name == "closed"
    assert lc.states[4].order == 4

    # Transitions
    assert len(lc.transitions) == 2

    t0 = lc.transitions[0]
    assert t0.from_state == "new"
    assert t0.to_state == "assigned"
    assert t0.evidence == "assignee_id != null"
    assert t0.roles == ["support_agent"]

    t1 = lc.transitions[1]
    assert t1.from_state == "in_progress"
    assert t1.to_state == "resolved"
    assert t1.evidence == "resolution_notes != null"
    # `roles: [support_agent, manager]` — list form
    assert t1.roles == ["support_agent", "manager"]


def test_entity_without_lifecycle_has_none() -> None:
    note = _first_entity(NO_LIFECYCLE_DSL, "Note")
    assert note.lifecycle is None
