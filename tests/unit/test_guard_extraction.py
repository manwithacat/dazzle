"""Tests for guard extraction from stories (Issue #81a).

Uses direct module import to avoid triggering mcp.server import from dazzle.mcp.__init__.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

# ============================================================================
# Direct module import to avoid mcp.server dependency
# ============================================================================

_event_first_tools_module = None


def _import_module():
    """Import event_first_tools module directly."""
    global _event_first_tools_module

    if _event_first_tools_module is not None:
        return

    # Mock the MCP server packages to prevent import errors
    _mocked = ["mcp", "mcp.server", "mcp.server.fastmcp"]
    _orig = {k: sys.modules.get(k) for k in _mocked}
    for k in _mocked:
        sys.modules[k] = MagicMock(pytest_plugins=[])

    # Get path to event_first_tools.py
    src_path = Path(__file__).parent.parent.parent / "src"
    module_path = src_path / "dazzle" / "mcp" / "event_first_tools.py"

    # Import module
    spec = importlib.util.spec_from_file_location(
        "event_first_tools_module",
        module_path,
    )
    _event_first_tools_module = importlib.util.module_from_spec(spec)
    sys.modules["event_first_tools_module"] = _event_first_tools_module
    spec.loader.exec_module(_event_first_tools_module)

    # Restore sys.modules to prevent pollution of other tests
    for k, v in _orig.items():
        if v is None:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v


# Import the module
_import_module()


def _build_guard_expression(guard_type, constraint_text, entity):
    return _event_first_tools_module._build_guard_expression(guard_type, constraint_text, entity)


def _match_transitions_to_constraint(constraint_text, state_machine):
    return _event_first_tools_module._match_transitions_to_constraint(
        constraint_text, state_machine
    )


def extract_guards(appspec):
    return _event_first_tools_module.extract_guards(appspec)


def _make_entity(name: str, fields: list[str], transitions: list[tuple[str, str]]):
    """Create a mock entity with state machine."""
    entity = MagicMock()
    entity.name = name
    entity.fields = []
    for f in fields:
        field = MagicMock()
        field.name = f
        entity.fields.append(field)

    sm = MagicMock()
    sm.transitions = []
    for from_s, to_s in transitions:
        t = MagicMock()
        t.from_state = from_s
        t.to_state = to_s
        sm.transitions.append(t)
    sm.states = list({s for pair in transitions for s in pair})
    entity.state_machine = sm
    return entity


def _make_story(story_id, title="Test", scope=None, constraints=None):
    """Create a mock story."""
    story = MagicMock()
    story.story_id = story_id
    story.title = title
    story.scope = scope or []
    story.constraints = constraints or []
    return story


class TestMatchTransitions:
    def test_matches_by_state_name(self):
        sm = MagicMock()
        t1 = MagicMock(from_state="draft", to_state="prepared")
        t2 = MagicMock(from_state="prepared", to_state="reviewed")
        sm.transitions = [t1, t2]

        matches = _match_transitions_to_constraint("prepared by preparer", sm)
        assert ("draft", "prepared") in matches
        assert ("prepared", "reviewed") in matches

    def test_no_match(self):
        sm = MagicMock()
        t1 = MagicMock(from_state="draft", to_state="submitted")
        sm.transitions = [t1]

        matches = _match_transitions_to_constraint("reviewer must differ", sm)
        assert matches == []


class TestBuildGuardExpression:
    def test_requires_different_field_with_fields(self):
        entity = _make_entity("VATReturn", ["preparer", "reviewer"], [])
        expr = _build_guard_expression(
            "requires_different_field",
            "Reviewer must differ from preparer",
            entity,
        )
        assert "requires_different_field(preparer, reviewer)" == expr

    def test_requires_role(self):
        entity = _make_entity("Task", [], [])
        expr = _build_guard_expression(
            "requires_role",
            "Only reviewer can approve",
            entity,
        )
        assert "requires_role(reviewer)" == expr

    def test_requires_field(self):
        entity = _make_entity("VATReturn", ["vrn"], [])
        expr = _build_guard_expression(
            "requires_field",
            "Must have VRN set before filing",
            entity,
        )
        assert "requires_field(vrn)" == expr

    def test_requires_field_value(self):
        entity = _make_entity("Task", [], [])
        expr = _build_guard_expression(
            "requires_field_value",
            "status must be approved",
            entity,
        )
        assert "requires(status=approved)" == expr


class TestExtractGuards:
    def test_extracts_from_constraint(self):
        entity = _make_entity(
            "VATReturn",
            ["preparer", "reviewer"],
            [("draft", "prepared"), ("prepared", "reviewed")],
        )

        story = _make_story(
            "ST-001",
            scope=["VATReturn"],
            constraints=["Reviewer must differ from preparer"],
        )

        appspec = MagicMock()
        appspec.domain.entities = [entity]
        appspec.stories = [story]
        appspec.metadata = {}

        proposals = extract_guards(appspec)
        assert len(proposals) >= 1
        assert proposals[0]["entity"] == "VATReturn"
        assert proposals[0]["guard_type"] == "requires_different_field"
        assert proposals[0]["source_story"] == "ST-001"

    def test_no_constraints_returns_empty(self):
        entity = _make_entity("Task", [], [("open", "closed")])
        story = _make_story("ST-001", scope=["Task"], constraints=[])

        appspec = MagicMock()
        appspec.domain.entities = [entity]
        appspec.stories = [story]
        appspec.metadata = {}

        assert extract_guards(appspec) == []

    def test_no_state_machine_skipped(self):
        entity = MagicMock()
        entity.name = "Task"
        entity.state_machine = None

        story = _make_story("ST-001", scope=["Task"], constraints=["Only admin can delete"])

        appspec = MagicMock()
        appspec.domain.entities = [entity]
        appspec.stories = [story]
        appspec.metadata = {}

        assert extract_guards(appspec) == []

    def test_deduplication(self):
        entity = _make_entity("VATReturn", ["preparer", "reviewer"], [("draft", "prepared")])

        # Two stories with same constraint for same entity
        story1 = _make_story(
            "ST-001",
            scope=["VATReturn"],
            constraints=["Reviewer must differ from preparer"],
        )
        story2 = _make_story(
            "ST-002",
            scope=["VATReturn"],
            constraints=["Reviewer must differ from preparer"],
        )

        appspec = MagicMock()
        appspec.domain.entities = [entity]
        appspec.stories = [story1, story2]
        appspec.metadata = {}

        proposals = extract_guards(appspec)
        # Should be deduplicated (same entity, transition, expression)
        expressions = [p["guard_expression"] for p in proposals]
        assert len(set(expressions)) == len(expressions)
