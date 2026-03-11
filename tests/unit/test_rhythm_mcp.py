"""Tests for rhythm MCP handler."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_appspec():
    from dazzle.core.ir.rhythm import PhaseSpec, RhythmSpec, SceneSpec

    rhythm = RhythmSpec(
        name="onboarding",
        title="New User Onboarding",
        persona="new_user",
        cadence="quarterly",
        phases=[
            PhaseSpec(
                name="discovery",
                scenes=[
                    SceneSpec(name="browse", title="Browse Courses", surface="course_list"),
                    SceneSpec(
                        name="enroll",
                        title="Enroll",
                        surface="course_detail",
                        actions=["submit"],
                        entity="Enrollment",
                    ),
                ],
            ),
        ],
    )
    spec = MagicMock()
    spec.rhythms = [rhythm]

    persona = MagicMock()
    persona.id = "new_user"
    persona.name = "New User"
    spec.personas = [persona]

    surf_list = MagicMock()
    surf_list.name = "course_list"
    surf_list.mode = "list"
    surf_list.entity_ref = None

    surf_detail = MagicMock()
    surf_detail.name = "course_detail"
    surf_detail.mode = "detail"
    surf_detail.entity_ref = "Enrollment"

    spec.surfaces = [surf_list, surf_detail]

    entity = MagicMock()
    entity.name = "Enrollment"
    spec.domain.entities = [entity]
    return spec


def test_list_rhythms(mock_appspec):
    from dazzle.mcp.server.handlers.rhythm import list_rhythms_handler

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=mock_appspec,
    ):
        result = list_rhythms_handler(Path("/fake"), {})
        data = json.loads(result)
        assert len(data["rhythms"]) == 1
        assert data["rhythms"][0]["name"] == "onboarding"
        assert data["rhythms"][0]["persona"] == "new_user"


def test_get_rhythm(mock_appspec):
    from dazzle.mcp.server.handlers.rhythm import get_rhythm_handler

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=mock_appspec,
    ):
        result = get_rhythm_handler(Path("/fake"), {"name": "onboarding"})
        data = json.loads(result)
        assert data["name"] == "onboarding"
        assert data["persona"] == "new_user"
        assert len(data["phases"]) == 1
        assert len(data["phases"][0]["scenes"]) == 2


def test_get_rhythm_not_found(mock_appspec):
    from dazzle.mcp.server.handlers.rhythm import get_rhythm_handler

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=mock_appspec,
    ):
        result = get_rhythm_handler(Path("/fake"), {"name": "nonexistent"})
        data = json.loads(result)
        assert "error" in data


def test_evaluate_rhythm(mock_appspec):
    from dazzle.mcp.server.handlers.rhythm import evaluate_rhythm_handler

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=mock_appspec,
    ):
        result = evaluate_rhythm_handler(Path("/fake"), {"name": "onboarding"})
        data = json.loads(result)
        assert "rhythm" in data
        assert "checks" in data


def test_coverage_rhythms(mock_appspec):
    from dazzle.mcp.server.handlers.rhythm import coverage_rhythms_handler

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=mock_appspec,
    ):
        result = coverage_rhythms_handler(Path("/fake"), {})
        data = json.loads(result)
        assert "personas_with_rhythms" in data
        assert "personas_without_rhythms" in data
        assert "surfaces_exercised" in data
        assert "surfaces_unexercised" in data
