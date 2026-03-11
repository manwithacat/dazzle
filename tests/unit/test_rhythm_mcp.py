"""Tests for rhythm MCP handler."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dazzle.core.ir.rhythm import PhaseKind, PhaseSpec, RhythmSpec, SceneSpec


@pytest.fixture
def mock_appspec():
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


@pytest.fixture
def mock_appspec_with_kinds():
    rhythm = RhythmSpec(
        name="onboarding",
        title="New User Onboarding",
        persona="new_user",
        cadence="quarterly",
        phases=[
            PhaseSpec(
                name="discovery",
                kind=PhaseKind.ACTIVE,
                scenes=[
                    SceneSpec(name="browse", title="Browse Courses", surface="course_list"),
                ],
            ),
            PhaseSpec(
                name="background",
                kind=PhaseKind.AMBIENT,
                scenes=[
                    SceneSpec(name="notify", title="Notify", surface="notifications"),
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

    spec.surfaces = []
    spec.domain.entities = []
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


def test_list_rhythms_includes_ambient_phases(mock_appspec_with_kinds):
    """list operation includes ambient phase count."""
    from dazzle.mcp.server.handlers.rhythm import list_rhythms_handler

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=mock_appspec_with_kinds,
    ):
        result = list_rhythms_handler(Path("/fake"), {})
        data = json.loads(result)
        assert data["rhythms"][0]["ambient_phases"] == 1


def test_get_rhythm_includes_phase_kind(mock_appspec_with_kinds):
    """get operation includes kind on phases."""
    from dazzle.mcp.server.handlers.rhythm import get_rhythm_handler

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=mock_appspec_with_kinds,
    ):
        result = get_rhythm_handler(Path("/fake"), {"name": "onboarding"})
        data = json.loads(result)
        assert data["phases"][0]["kind"] == "active"
        assert data["phases"][1]["kind"] == "ambient"


def test_get_rhythm_phase_kind_null_when_unset(mock_appspec):
    """get operation returns null kind when phase has no kind set."""
    from dazzle.mcp.server.handlers.rhythm import get_rhythm_handler

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=mock_appspec,
    ):
        result = get_rhythm_handler(Path("/fake"), {"name": "onboarding"})
        data = json.loads(result)
        assert data["phases"][0]["kind"] is None


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


def test_evaluate_submit_scores_persists(tmp_path, mock_appspec):
    """submit_scores action writes evaluation to .dazzle/evaluations/."""
    from dazzle.mcp.server.handlers.rhythm import evaluate_rhythm_handler

    scores = [
        {
            "scene_name": "browse",
            "phase_name": "discovery",
            "dimensions": [
                {"dimension": "arrival", "score": "pass", "evidence": "ok"},
                {"dimension": "orientation", "score": "pass", "evidence": "ok"},
                {"dimension": "action", "score": "pass", "evidence": "ok"},
                {"dimension": "completion", "score": "pass", "evidence": "ok"},
                {"dimension": "confidence", "score": "pass", "evidence": "ok"},
            ],
            "gap_type": "none",
            "story_ref": None,
        }
    ]
    project = tmp_path / "project"
    project.mkdir()
    (project / ".dazzle").mkdir()

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=mock_appspec,
    ):
        result = evaluate_rhythm_handler(
            project,
            {"name": "onboarding", "action": "submit_scores", "scores": scores},
        )
    data = json.loads(result)
    assert "stored" in data
    assert data["count"] == 1

    eval_dir = project / ".dazzle" / "evaluations"
    assert eval_dir.exists()
    eval_files = list(eval_dir.glob("eval-*.json"))
    assert len(eval_files) == 1

    stored = json.loads(eval_files[0].read_text())
    assert stored["rhythm"] == "onboarding"
    assert len(stored["evaluations"]) == 1
    assert stored["evaluations"][0]["scene_name"] == "browse"


def test_evaluate_submit_scores_validates_rhythm(tmp_path, mock_appspec):
    """submit_scores returns error when rhythm not found."""
    from dazzle.mcp.server.handlers.rhythm import evaluate_rhythm_handler

    project = tmp_path / "project"
    project.mkdir()
    (project / ".dazzle").mkdir()

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=mock_appspec,
    ):
        result = evaluate_rhythm_handler(
            project,
            {"name": "nonexistent", "action": "submit_scores", "scores": []},
        )
    data = json.loads(result)
    assert "error" in data


def test_evaluate_returns_stored_scores(tmp_path, mock_appspec):
    """evaluate action returns stored scores alongside structural checks."""
    from dazzle.mcp.server.handlers.rhythm import evaluate_rhythm_handler

    scores = [
        {
            "scene_name": "browse",
            "phase_name": "discovery",
            "dimensions": [
                {"dimension": "arrival", "score": "pass", "evidence": "ok"},
                {"dimension": "orientation", "score": "pass", "evidence": "ok"},
                {"dimension": "action", "score": "pass", "evidence": "ok"},
                {"dimension": "completion", "score": "pass", "evidence": "ok"},
                {"dimension": "confidence", "score": "pass", "evidence": "ok"},
            ],
            "gap_type": "none",
            "story_ref": None,
        }
    ]
    project = tmp_path / "project"
    project.mkdir()
    (project / ".dazzle").mkdir()

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=mock_appspec,
    ):
        # Submit scores first
        evaluate_rhythm_handler(
            project,
            {"name": "onboarding", "action": "submit_scores", "scores": scores},
        )

        # Now run structural evaluate — should include scene_scores
        result = evaluate_rhythm_handler(
            project,
            {"name": "onboarding"},
        )
    data = json.loads(result)
    assert "checks" in data
    assert "scene_scores" in data
    assert data["scene_scores"] is not None
    assert len(data["scene_scores"]) == 1
    assert data["scene_scores"][0]["scene_name"] == "browse"


@pytest.fixture
def mock_appspec_coverage_ambient():
    """Two personas: one with an ambient phase, one without."""

    rhythm_with_ambient = RhythmSpec(
        name="daily_check",
        title="Daily Check",
        persona="power_user",
        cadence="daily",
        phases=[
            PhaseSpec(
                name="work",
                kind=PhaseKind.ACTIVE,
                scenes=[
                    SceneSpec(name="do_work", title="Do Work", surface="dashboard"),
                ],
            ),
            PhaseSpec(
                name="monitoring",
                kind=PhaseKind.AMBIENT,
                scenes=[
                    SceneSpec(name="alerts", title="Alerts", surface="alerts_panel"),
                ],
            ),
        ],
    )
    rhythm_without_ambient = RhythmSpec(
        name="onboarding",
        title="Onboarding",
        persona="new_user",
        cadence="once",
        phases=[
            PhaseSpec(
                name="setup",
                kind=PhaseKind.ACTIVE,
                scenes=[
                    SceneSpec(name="register", title="Register", surface="signup"),
                ],
            ),
        ],
    )

    spec = MagicMock()
    spec.rhythms = [rhythm_with_ambient, rhythm_without_ambient]

    p1 = MagicMock()
    p1.id = "power_user"
    p2 = MagicMock()
    p2.id = "new_user"
    spec.personas = [p1, p2]

    s1 = MagicMock()
    s1.name = "dashboard"
    s2 = MagicMock()
    s2.name = "alerts_panel"
    s3 = MagicMock()
    s3.name = "signup"
    spec.surfaces = [s1, s2, s3]
    spec.domain.entities = []
    return spec


def test_coverage_includes_ambient_analysis(mock_appspec_coverage_ambient):
    """Coverage output includes ambient persona analysis."""
    from dazzle.mcp.server.handlers.rhythm import coverage_rhythms_handler

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=mock_appspec_coverage_ambient,
    ):
        result = coverage_rhythms_handler(Path("/fake"), {})
        data = json.loads(result)
        assert "personas_with_ambient" in data
        assert "personas_without_ambient" in data
        assert data["personas_with_ambient"] == ["power_user"]
        assert data["personas_without_ambient"] == ["new_user"]


def test_evaluate_no_stored_scores(mock_appspec):
    """evaluate action returns null scene_scores when none stored."""
    from dazzle.mcp.server.handlers.rhythm import evaluate_rhythm_handler

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=mock_appspec,
    ):
        result = evaluate_rhythm_handler(Path("/fake"), {"name": "onboarding"})
    data = json.loads(result)
    assert "scene_scores" in data
    assert data["scene_scores"] is None
