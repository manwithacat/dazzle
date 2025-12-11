"""Tests for state machine parsing (v0.7.0)."""

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import (
    TimeUnit,
    TransitionTrigger,
)


class TestStateMachineParsing:
    """Tests for parsing entity state machines."""

    def test_basic_transitions(self) -> None:
        """Test parsing basic state transitions."""
        dsl = """
module test.core
app test_app "Test App"

entity Ticket "Ticket":
  id: uuid pk
  title: str(200) required
  status: enum[open, assigned, resolved, closed]
  assignee: str(100)

  transitions:
    open -> assigned: requires assignee
    assigned -> resolved
    resolved -> closed
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        entity = fragment.entities[0]
        assert entity.name == "Ticket"
        assert entity.has_state_machine
        assert entity.state_machine is not None

        sm = entity.state_machine
        assert sm.status_field == "status"
        assert sm.states == ["open", "assigned", "resolved", "closed"]
        assert len(sm.transitions) == 3

        # First transition: open -> assigned with guard
        t1 = sm.transitions[0]
        assert t1.from_state == "open"
        assert t1.to_state == "assigned"
        assert len(t1.guards) == 1
        assert t1.guards[0].requires_field == "assignee"
        assert t1.trigger == TransitionTrigger.MANUAL

        # Second transition: assigned -> resolved (no guard)
        t2 = sm.transitions[1]
        assert t2.from_state == "assigned"
        assert t2.to_state == "resolved"
        assert len(t2.guards) == 0

    def test_role_guard(self) -> None:
        """Test parsing role-based transition guards."""
        dsl = """
module test.core
app test_app "Test App"

entity Task "Task":
  id: uuid pk
  status: enum[draft, published, archived]

  transitions:
    * -> draft: role(admin)
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        entity = fragment.entities[0]
        sm = entity.state_machine
        assert sm is not None
        assert len(sm.transitions) == 1

        t = sm.transitions[0]
        assert t.from_state == "*"  # Wildcard
        assert t.to_state == "draft"
        assert t.is_wildcard
        assert len(t.guards) == 1
        assert t.guards[0].requires_role == "admin"

    def test_auto_transition(self) -> None:
        """Test parsing automatic transitions with delays."""
        dsl = """
module test.core
app test_app "Test App"

entity Task "Task":
  id: uuid pk
  status: enum[pending, processing, complete]

  transitions:
    processing -> complete: auto after 24 hours
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        entity = fragment.entities[0]
        sm = entity.state_machine
        assert sm is not None

        t = sm.transitions[0]
        assert t.from_state == "processing"
        assert t.to_state == "complete"
        assert t.is_auto
        assert t.trigger == TransitionTrigger.AUTO
        assert t.auto_spec is not None
        assert t.auto_spec.delay_value == 24
        assert t.auto_spec.delay_unit == TimeUnit.HOURS
        assert t.auto_spec.delay_seconds == 24 * 3600

    @pytest.mark.skip(reason="OR manual syntax not yet implemented")
    def test_auto_with_manual_override(self) -> None:
        """Test parsing auto transitions that also allow manual trigger.

        TODO: Implement the 'OR manual' syntax to allow both auto and manual triggers.
        """
        dsl = """
module test.core
app test_app "Test App"

entity Task "Task":
  id: uuid pk
  status: enum[review, approved]

  transitions:
    review -> approved: auto after 7 days OR manual
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        entity = fragment.entities[0]
        sm = entity.state_machine
        assert sm is not None

        t = sm.transitions[0]
        assert t.is_auto
        assert t.auto_spec is not None
        assert t.auto_spec.delay_value == 7
        assert t.auto_spec.delay_unit == TimeUnit.DAYS
        assert t.auto_spec.allow_manual is True

    def test_different_time_units(self) -> None:
        """Test parsing different time units for auto transitions."""
        dsl = """
module test.core
app test_app "Test App"

entity Task "Task":
  id: uuid pk
  status: enum[a, b, c, d]

  transitions:
    a -> b: auto after 5 minutes
    b -> c: auto after 2 hours
    c -> d: auto after 30 days
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        entity = fragment.entities[0]
        sm = entity.state_machine
        assert sm is not None
        assert len(sm.transitions) == 3

        # 5 minutes
        assert sm.transitions[0].auto_spec.delay_value == 5
        assert sm.transitions[0].auto_spec.delay_unit == TimeUnit.MINUTES
        assert sm.transitions[0].auto_spec.delay_seconds == 5 * 60

        # 2 hours
        assert sm.transitions[1].auto_spec.delay_value == 2
        assert sm.transitions[1].auto_spec.delay_unit == TimeUnit.HOURS
        assert sm.transitions[1].auto_spec.delay_seconds == 2 * 3600

        # 30 days
        assert sm.transitions[2].auto_spec.delay_value == 30
        assert sm.transitions[2].auto_spec.delay_unit == TimeUnit.DAYS
        assert sm.transitions[2].auto_spec.delay_seconds == 30 * 86400

    def test_state_machine_helper_methods(self) -> None:
        """Test StateMachineSpec helper methods."""
        dsl = """
module test.core
app test_app "Test App"

entity Ticket "Ticket":
  id: uuid pk
  status: enum[new, open, closed]

  transitions:
    new -> open
    open -> closed
    * -> new: role(admin)
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        entity = fragment.entities[0]
        sm = entity.state_machine
        assert sm is not None

        # Test get_transitions_from
        # "new" can transition via new->open AND via wildcard *->new
        from_new = sm.get_transitions_from("new")
        assert len(from_new) == 2  # new->open and *->new (wildcard matches all)
        target_states = {t.to_state for t in from_new}
        assert target_states == {"open", "new"}

        # Wildcard matches all states
        from_open = sm.get_transitions_from("open")
        assert len(from_open) == 2  # open->closed and *->new
        target_states = {t.to_state for t in from_open}
        assert target_states == {"closed", "new"}

        # Test get_allowed_targets
        targets = sm.get_allowed_targets("new")
        assert targets == {"open", "new"}  # direct + wildcard

        # Test is_transition_allowed
        assert sm.is_transition_allowed("new", "open") is True
        assert sm.is_transition_allowed("new", "closed") is False
        assert sm.is_transition_allowed("open", "new") is True  # via wildcard

        # Test get_transition
        t = sm.get_transition("new", "open")
        assert t is not None
        assert t.from_state == "new"

        t_none = sm.get_transition("new", "closed")
        assert t_none is None

    def test_entity_without_transitions(self) -> None:
        """Test that entities without transitions have no state machine."""
        dsl = """
module test.core
app test_app "Test App"

entity Task "Task":
  id: uuid pk
  status: enum[todo, done]
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        entity = fragment.entities[0]
        assert entity.has_state_machine is False
        assert entity.state_machine is None

    def test_role_field_name_not_conflicting(self) -> None:
        """Test that 'role' can still be used as a field name."""
        dsl = """
module test.core
app test_app "Test App"

entity User "User":
  id: uuid pk
  role: enum[admin, user, guest]
  name: str(100)
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        entity = fragment.entities[0]
        assert entity.name == "User"

        role_field = entity.get_field("role")
        assert role_field is not None
        assert role_field.type.enum_values == ["admin", "user", "guest"]
