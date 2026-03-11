"""Tests for rhythm MCP handler."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dazzle.core.ir.rhythm import PhaseKind, PhaseSpec, RhythmSpec, SceneSpec
from dazzle.core.ir.stories import StorySpec, StoryStatus, StoryTrigger


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
    surf_list.access = None

    surf_detail = MagicMock()
    surf_detail.name = "course_detail"
    surf_detail.mode = "detail"
    surf_detail.entity_ref = "Enrollment"
    surf_detail.access = None

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
    s1.access = None
    s2 = MagicMock()
    s2.name = "alerts_panel"
    s2.access = None
    s3 = MagicMock()
    s3.name = "signup"
    s3.access = None
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


def test_coverage_persona_scoped(mock_appspec):
    """Coverage includes per-persona scoped metrics."""
    from dazzle.mcp.server.handlers.rhythm import coverage_rhythms_handler

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=mock_appspec,
    ):
        result = coverage_rhythms_handler(Path("/fake"), {})
        data = json.loads(result)
        assert "persona_coverage" in data
        pc = data["persona_coverage"]
        assert "new_user" in pc
        # Both surfaces have access=None (no auth required) → both accessible
        assert pc["new_user"]["accessible_surfaces"] == 2
        assert pc["new_user"]["exercised_surfaces"] == 2
        assert pc["new_user"]["coverage_pct"] == 100


def test_coverage_persona_scoped_with_acl():
    """Persona-scoped coverage respects allow_personas ACL."""
    from dazzle.mcp.server.handlers.rhythm import coverage_rhythms_handler

    rhythm = RhythmSpec(
        name="director_arc",
        title="Director Arc",
        persona="director",
        phases=[
            PhaseSpec(
                name="fiscal",
                scenes=[
                    SceneSpec(name="review", surface="budget_review"),
                    SceneSpec(name="approve", surface="approval_queue"),
                ],
            ),
        ],
    )

    spec = MagicMock()
    spec.rhythms = [rhythm]

    persona = MagicMock()
    persona.id = "director"
    spec.personas = [persona]

    # 4 surfaces: 2 accessible to director, 2 restricted to other roles
    s1 = MagicMock()
    s1.name = "budget_review"
    s1.access = MagicMock()
    s1.access.require_auth = True
    s1.access.allow_personas = ["director", "finance"]
    s1.access.deny_personas = []

    s2 = MagicMock()
    s2.name = "approval_queue"
    s2.access = MagicMock()
    s2.access.require_auth = True
    s2.access.allow_personas = ["director"]
    s2.access.deny_personas = []

    s3 = MagicMock()
    s3.name = "agent_capacity"
    s3.access = MagicMock()
    s3.access.require_auth = True
    s3.access.allow_personas = ["agent_manager"]
    s3.access.deny_personas = []

    s4 = MagicMock()
    s4.name = "public_page"
    s4.access = None  # No auth required

    spec.surfaces = [s1, s2, s3, s4]
    spec.domain.entities = []

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=spec,
    ):
        result = coverage_rhythms_handler(Path("/fake"), {})
        data = json.loads(result)

    pc = data["persona_coverage"]["director"]
    # director can access: budget_review, approval_queue, public_page (3 of 4)
    assert pc["accessible_surfaces"] == 3
    # rhythm exercises: budget_review, approval_queue (2 of 3 accessible)
    assert pc["exercised_surfaces"] == 2
    assert pc["coverage_pct"] == 67  # 2/3 rounded
    assert pc["unexercised"] == ["public_page"]


def test_coverage_persona_deny_list():
    """Persona denied by deny_personas is excluded from surface access."""
    from dazzle.mcp.server.handlers.rhythm import coverage_rhythms_handler

    rhythm = RhythmSpec(
        name="r1",
        title="R1",
        persona="intern",
        phases=[
            PhaseSpec(
                name="p1",
                scenes=[SceneSpec(name="s1", surface="public_docs")],
            ),
        ],
    )

    spec = MagicMock()
    spec.rhythms = [rhythm]

    persona = MagicMock()
    persona.id = "intern"
    spec.personas = [persona]

    s1 = MagicMock()
    s1.name = "public_docs"
    s1.access = None

    s2 = MagicMock()
    s2.name = "admin_panel"
    s2.access = MagicMock()
    s2.access.require_auth = True
    s2.access.allow_personas = []  # all authenticated
    s2.access.deny_personas = ["intern"]

    spec.surfaces = [s1, s2]
    spec.domain.entities = []

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=spec,
    ):
        result = coverage_rhythms_handler(Path("/fake"), {})
        data = json.loads(result)

    pc = data["persona_coverage"]["intern"]
    assert pc["accessible_surfaces"] == 1  # only public_docs
    assert pc["exercised_surfaces"] == 1
    assert pc["coverage_pct"] == 100


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


# ---------------------------------------------------------------------------
# Gaps analysis tests
# ---------------------------------------------------------------------------


def _make_story(
    story_id: str,
    actor: str = "user",
    status: StoryStatus = StoryStatus.ACCEPTED,
) -> StorySpec:
    return StorySpec(
        story_id=story_id,
        title=f"Story {story_id}",
        actor=actor,
        trigger=StoryTrigger.USER_CLICK,
        scope=["Task"],
        status=status,
        created_at="2026-01-01T00:00:00",
    )


def _make_gaps_appspec(
    *,
    rhythms: list[RhythmSpec] | None = None,
    stories: list[StorySpec] | None = None,
    persona_ids: list[str] | None = None,
) -> MagicMock:
    spec = MagicMock()
    spec.rhythms = rhythms or []
    spec.stories = stories or []
    personas = []
    for pid in persona_ids or []:
        p = MagicMock()
        p.id = pid
        personas.append(p)
    spec.personas = personas
    spec.surfaces = []
    spec.domain.entities = []
    return spec


def test_gaps_missing_story(tmp_path):
    """Scene referencing non-existent story produces blocking capability gap."""
    from dazzle.mcp.server.handlers.rhythm import gaps_rhythm_handler

    rhythm = RhythmSpec(
        name="r1",
        title="R1",
        persona="user",
        phases=[
            PhaseSpec(
                name="p1",
                scenes=[SceneSpec(name="s1", surface="sf1", story="ST-999")],
            ),
        ],
    )
    app = _make_gaps_appspec(rhythms=[rhythm], stories=[], persona_ids=["user"])
    project = tmp_path / "proj"
    project.mkdir()

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=app,
    ):
        result = json.loads(gaps_rhythm_handler(project, {}))

    cap_gaps = [g for g in result["gaps"] if g["kind"] == "capability"]
    assert len(cap_gaps) >= 1
    assert cap_gaps[0]["severity"] == "blocking"
    assert "ST-999" in cap_gaps[0]["description"]


def test_gaps_draft_story(tmp_path):
    """Scene referencing DRAFT story produces blocking capability gap."""
    from dazzle.mcp.server.handlers.rhythm import gaps_rhythm_handler

    story = _make_story("ST-001", actor="user", status=StoryStatus.DRAFT)
    rhythm = RhythmSpec(
        name="r1",
        title="R1",
        persona="user",
        phases=[
            PhaseSpec(
                name="p1",
                scenes=[SceneSpec(name="s1", surface="sf1", story="ST-001")],
            ),
        ],
    )
    app = _make_gaps_appspec(rhythms=[rhythm], stories=[story], persona_ids=["user"])
    project = tmp_path / "proj"
    project.mkdir()

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=app,
    ):
        result = json.loads(gaps_rhythm_handler(project, {}))

    cap_gaps = [g for g in result["gaps"] if g["kind"] == "capability"]
    assert len(cap_gaps) >= 1
    assert cap_gaps[0]["severity"] == "blocking"
    assert "DRAFT" in cap_gaps[0]["description"]


def test_gaps_unmapped_scene(tmp_path):
    """Scene without story ref produces advisory unmapped gap."""
    from dazzle.mcp.server.handlers.rhythm import gaps_rhythm_handler

    rhythm = RhythmSpec(
        name="r1",
        title="R1",
        persona="user",
        phases=[
            PhaseSpec(
                name="p1",
                scenes=[SceneSpec(name="s1", surface="sf1")],
            ),
        ],
    )
    app = _make_gaps_appspec(rhythms=[rhythm], stories=[], persona_ids=["user"])
    project = tmp_path / "proj"
    project.mkdir()

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=app,
    ):
        result = json.loads(gaps_rhythm_handler(project, {}))

    unmapped = [g for g in result["gaps"] if g["kind"] == "unmapped"]
    assert len(unmapped) == 1
    assert unmapped[0]["severity"] == "advisory"


def test_gaps_orphan_story(tmp_path):
    """Story not referenced by any scene produces advisory orphan gap."""
    from dazzle.mcp.server.handlers.rhythm import gaps_rhythm_handler

    story = _make_story("ST-001", actor="user")
    other_story = _make_story("ST-002", actor="user")
    rhythm = RhythmSpec(
        name="r1",
        title="R1",
        persona="user",
        phases=[
            PhaseSpec(
                name="p1",
                scenes=[SceneSpec(name="s1", surface="sf1", story="ST-002")],
            ),
        ],
    )
    app = _make_gaps_appspec(rhythms=[rhythm], stories=[story, other_story], persona_ids=["user"])
    project = tmp_path / "proj"
    project.mkdir()

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=app,
    ):
        result = json.loads(gaps_rhythm_handler(project, {}))

    orphans = [g for g in result["gaps"] if g["kind"] == "orphan"]
    assert len(orphans) == 1
    assert orphans[0]["severity"] == "advisory"
    assert "ST-001" in orphans[0]["description"]


def test_gaps_no_ambient(tmp_path):
    """Persona with rhythm but no ambient phase produces advisory ambient gap."""
    from dazzle.mcp.server.handlers.rhythm import gaps_rhythm_handler

    story = _make_story("ST-001", actor="user")
    rhythm = RhythmSpec(
        name="r1",
        title="R1",
        persona="user",
        phases=[
            PhaseSpec(
                name="p1",
                kind=PhaseKind.ACTIVE,
                scenes=[SceneSpec(name="s1", surface="sf1", story="ST-001")],
            ),
        ],
    )
    app = _make_gaps_appspec(rhythms=[rhythm], stories=[story], persona_ids=["user"])
    project = tmp_path / "proj"
    project.mkdir()

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=app,
    ):
        result = json.loads(gaps_rhythm_handler(project, {}))

    ambient = [g for g in result["gaps"] if g["kind"] == "ambient"]
    assert len(ambient) == 1
    assert ambient[0]["severity"] == "advisory"
    assert "user" in ambient[0]["description"]


def test_gaps_unscored_persona(tmp_path):
    """Persona with stories but no rhythm produces advisory unscored gap."""
    from dazzle.mcp.server.handlers.rhythm import gaps_rhythm_handler

    story = _make_story("ST-001", actor="lonely_persona")
    app = _make_gaps_appspec(rhythms=[], stories=[story], persona_ids=["lonely_persona"])
    project = tmp_path / "proj"
    project.mkdir()

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=app,
    ):
        result = json.loads(gaps_rhythm_handler(project, {}))

    unscored = [g for g in result["gaps"] if g["kind"] == "unscored"]
    assert len(unscored) == 1
    assert unscored[0]["severity"] == "advisory"
    assert "lonely_persona" in unscored[0]["description"]


def test_gaps_roadmap_blocking_first(tmp_path):
    """Blocking gaps appear before advisory in roadmap_order."""
    from dazzle.mcp.server.handlers.rhythm import gaps_rhythm_handler

    rhythm = RhythmSpec(
        name="r1",
        title="R1",
        persona="user",
        phases=[
            PhaseSpec(
                name="p1",
                scenes=[
                    SceneSpec(name="unmapped_scene", surface="sf1"),  # advisory
                    SceneSpec(name="bad_ref", surface="sf2", story="ST-NOPE"),  # blocking
                ],
            ),
        ],
    )
    app = _make_gaps_appspec(rhythms=[rhythm], stories=[], persona_ids=["user"])
    project = tmp_path / "proj"
    project.mkdir()

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=app,
    ):
        result = json.loads(gaps_rhythm_handler(project, {}))

    roadmap = result["roadmap_order"]
    assert len(roadmap) >= 2
    blocking_indices = [i for i, g in enumerate(roadmap) if g["severity"] == "blocking"]
    advisory_indices = [i for i, g in enumerate(roadmap) if g["severity"] == "advisory"]
    assert blocking_indices
    assert advisory_indices
    assert max(blocking_indices) < min(advisory_indices)


def test_gaps_summary_counts(tmp_path):
    """Summary totals are correct."""
    from dazzle.mcp.server.handlers.rhythm import gaps_rhythm_handler

    orphan_story = _make_story("ST-ORPHAN", actor="user")
    rhythm = RhythmSpec(
        name="r1",
        title="R1",
        persona="user",
        phases=[
            PhaseSpec(
                name="p1",
                scenes=[
                    SceneSpec(name="s1", surface="sf1"),  # unmapped
                    SceneSpec(name="s2", surface="sf2", story="ST-NOPE"),  # capability
                ],
            ),
        ],
    )
    app = _make_gaps_appspec(rhythms=[rhythm], stories=[orphan_story], persona_ids=["user"])
    project = tmp_path / "proj"
    project.mkdir()

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=app,
    ):
        result = json.loads(gaps_rhythm_handler(project, {}))

    summary = result["summary"]
    assert summary["total"] == len(result["gaps"])
    assert sum(summary["by_kind"].values()) == summary["total"]
    assert sum(summary["by_severity"].values()) == summary["total"]


def test_gaps_persists_report(tmp_path):
    """Report written to .dazzle/evaluations/gaps-*.json."""
    from dazzle.mcp.server.handlers.rhythm import gaps_rhythm_handler

    rhythm = RhythmSpec(
        name="r1",
        title="R1",
        persona="user",
        phases=[
            PhaseSpec(
                name="p1",
                scenes=[SceneSpec(name="s1", surface="sf1")],
            ),
        ],
    )
    app = _make_gaps_appspec(rhythms=[rhythm], stories=[], persona_ids=["user"])
    project = tmp_path / "proj"
    project.mkdir()

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=app,
    ):
        gaps_rhythm_handler(project, {})

    eval_dir = project / ".dazzle" / "evaluations"
    assert eval_dir.exists()
    gap_files = list(eval_dir.glob("gaps-*.json"))
    assert len(gap_files) == 1
    stored = json.loads(gap_files[0].read_text())
    assert "gaps" in stored
    assert "summary" in stored
    assert "roadmap_order" in stored


def test_gaps_layers_evaluated_failures(tmp_path):
    """Evaluation failures from stored eval files are layered in."""
    from dazzle.mcp.server.handlers.rhythm import gaps_rhythm_handler

    story = _make_story("ST-001", actor="user")
    rhythm = RhythmSpec(
        name="r1",
        title="R1",
        persona="user",
        phases=[
            PhaseSpec(
                name="p1",
                scenes=[SceneSpec(name="s1", surface="sf1", story="ST-001")],
            ),
        ],
    )
    app = _make_gaps_appspec(rhythms=[rhythm], stories=[story], persona_ids=["user"])
    project = tmp_path / "proj"
    project.mkdir()

    # Write an eval file with a failure
    eval_dir = project / ".dazzle" / "evaluations"
    eval_dir.mkdir(parents=True)
    eval_data = {
        "rhythm": "r1",
        "timestamp": "20260101-000000",
        "evaluations": [
            {
                "scene_name": "s1",
                "phase_name": "p1",
                "dimensions": [
                    {"dimension": "action", "score": "fail", "evidence": "broken"},
                ],
                "gap_type": "capability",
                "story_ref": "ST-001",
            },
        ],
    }
    (eval_dir / "eval-20260101-000000.json").write_text(json.dumps(eval_data))

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=app,
    ):
        result = json.loads(gaps_rhythm_handler(project, {}))

    eval_gaps = [g for g in result["gaps"] if "failed action" in g.get("description", "")]
    assert len(eval_gaps) == 1
    assert eval_gaps[0]["severity"] == "blocking"


# ---------------------------------------------------------------------------
# Lifecycle handler tests
# ---------------------------------------------------------------------------


def _make_lifecycle_appspec(
    *,
    entities: list[MagicMock] | None = None,
    stories: list[StorySpec] | None = None,
    rhythms: list[RhythmSpec] | None = None,
    persona_ids: list[str] | None = None,
) -> MagicMock:
    """Build a mock appspec for lifecycle tests."""
    spec = MagicMock()
    spec.domain.entities = entities or []
    spec.stories = stories or []
    spec.rhythms = rhythms or []
    personas = []
    for pid in persona_ids or []:
        p = MagicMock()
        p.id = pid
        personas.append(p)
    spec.personas = personas
    spec.surfaces = []
    return spec


def _make_entity(name: str, field_count: int = 2) -> MagicMock:
    """Build a mock entity with fields."""
    entity = MagicMock()
    entity.name = name
    entity.fields = [MagicMock() for _ in range(field_count)]
    return entity


def test_lifecycle_empty_project(tmp_path):
    """Empty project -> new_domain, all steps not_started."""
    from dazzle.mcp.server.handlers.rhythm import lifecycle_rhythm_handler

    app = _make_lifecycle_appspec()
    project = tmp_path / "proj"
    project.mkdir()

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=app,
    ):
        result = json.loads(lifecycle_rhythm_handler(project, {}))

    assert result["maturity"] == "new_domain"
    assert len(result["steps"]) == 8
    assert result["steps"][0]["name"] == "model_domain"
    assert result["steps"][0]["status"] == "not_started"
    assert result["current_focus"] == "model_domain"


def test_lifecycle_with_entities(tmp_path):
    """Project with entities -> step 1 complete."""
    from dazzle.mcp.server.handlers.rhythm import lifecycle_rhythm_handler

    app = _make_lifecycle_appspec(entities=[_make_entity("Task")])
    project = tmp_path / "proj"
    project.mkdir()

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=app,
    ):
        result = json.loads(lifecycle_rhythm_handler(project, {}))

    assert result["steps"][0]["status"] == "complete"
    assert result["steps"][0]["name"] == "model_domain"
    # Still new_domain since only step 1 complete
    assert result["maturity"] == "new_domain"
    assert result["current_focus"] == "write_stories"


def test_lifecycle_maturity_building(tmp_path):
    """Steps 1-3 complete -> building."""
    from dazzle.mcp.server.handlers.rhythm import lifecycle_rhythm_handler

    story = _make_story("ST-001", actor="user", status=StoryStatus.ACCEPTED)
    rhythm = RhythmSpec(
        name="r1",
        title="R1",
        persona="user",
        phases=[
            PhaseSpec(
                name="p1",
                scenes=[SceneSpec(name="s1", surface="sf1", story="ST-001")],
            ),
        ],
    )
    app = _make_lifecycle_appspec(
        entities=[_make_entity("Task")],
        stories=[story],
        rhythms=[rhythm],
        persona_ids=["user"],
    )
    project = tmp_path / "proj"
    project.mkdir()

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=app,
    ):
        result = json.loads(lifecycle_rhythm_handler(project, {}))

    assert result["steps"][0]["status"] == "complete"  # model_domain
    assert result["steps"][1]["status"] == "complete"  # write_stories
    assert result["steps"][2]["status"] == "complete"  # write_rhythms
    assert result["maturity"] == "building"


def test_lifecycle_write_rhythms_partial_persona_coverage(tmp_path):
    """Rhythms exist but don't cover all personas -> partial."""
    from dazzle.mcp.server.handlers.rhythm import lifecycle_rhythm_handler

    story = _make_story("ST-001", actor="user", status=StoryStatus.ACCEPTED)
    rhythm = RhythmSpec(
        name="r1",
        title="R1",
        persona="user",
        phases=[
            PhaseSpec(
                name="p1",
                scenes=[SceneSpec(name="s1", surface="sf1", story="ST-001")],
            ),
        ],
    )
    app = _make_lifecycle_appspec(
        entities=[_make_entity("Task")],
        stories=[story],
        rhythms=[rhythm],
        persona_ids=["user", "admin"],  # admin has no rhythm
    )
    project = tmp_path / "proj"
    project.mkdir()

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=app,
    ):
        result = json.loads(lifecycle_rhythm_handler(project, {}))

    assert result["steps"][2]["status"] == "partial"
    assert result["steps"][2]["name"] == "write_rhythms"


def test_lifecycle_map_scenes_partial(tmp_path):
    """Some scenes missing story refs -> step 4 partial."""
    from dazzle.mcp.server.handlers.rhythm import lifecycle_rhythm_handler

    story = _make_story("ST-001", actor="user", status=StoryStatus.ACCEPTED)
    rhythm = RhythmSpec(
        name="r1",
        title="R1",
        persona="user",
        phases=[
            PhaseSpec(
                name="p1",
                scenes=[
                    SceneSpec(name="s1", surface="sf1", story="ST-001"),
                    SceneSpec(name="s2", surface="sf2"),  # no story ref
                ],
            ),
        ],
    )
    app = _make_lifecycle_appspec(
        entities=[_make_entity("Task")],
        stories=[story],
        rhythms=[rhythm],
        persona_ids=["user"],
    )
    project = tmp_path / "proj"
    project.mkdir()

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=app,
    ):
        result = json.loads(lifecycle_rhythm_handler(project, {}))

    assert result["steps"][3]["status"] == "partial"
    assert result["steps"][3]["name"] == "map_scenes_to_stories"


def test_lifecycle_current_focus_is_first_incomplete(tmp_path):
    """current_focus points to first non-complete step."""
    from dazzle.mcp.server.handlers.rhythm import lifecycle_rhythm_handler

    # Only entities -> steps 2-8 incomplete, focus should be write_stories
    app = _make_lifecycle_appspec(entities=[_make_entity("Task")])
    project = tmp_path / "proj"
    project.mkdir()

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=app,
    ):
        result = json.loads(lifecycle_rhythm_handler(project, {}))

    assert result["current_focus"] == "write_stories"


def test_lifecycle_build_from_stories(tmp_path):
    """Step 5 complete when test_designs dir has JSON files."""
    from dazzle.mcp.server.handlers.rhythm import lifecycle_rhythm_handler

    story = _make_story("ST-001", actor="user", status=StoryStatus.ACCEPTED)
    rhythm = RhythmSpec(
        name="r1",
        title="R1",
        persona="user",
        phases=[
            PhaseSpec(
                name="p1",
                scenes=[SceneSpec(name="s1", surface="sf1", story="ST-001")],
            ),
        ],
    )
    app = _make_lifecycle_appspec(
        entities=[_make_entity("Task")],
        stories=[story],
        rhythms=[rhythm],
        persona_ids=["user"],
    )
    project = tmp_path / "proj"
    project.mkdir()

    # Create test_designs directory with a JSON file
    td_dir = project / ".dazzle" / "test_designs"
    td_dir.mkdir(parents=True)
    (td_dir / "design1.json").write_text("{}")

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=app,
    ):
        result = json.loads(lifecycle_rhythm_handler(project, {}))

    assert result["steps"][4]["status"] == "complete"
    assert result["steps"][4]["name"] == "build_from_stories"


def test_lifecycle_evaluating_maturity(tmp_path):
    """Steps 1-5 complete -> evaluating."""
    from dazzle.mcp.server.handlers.rhythm import lifecycle_rhythm_handler

    story = _make_story("ST-001", actor="user", status=StoryStatus.ACCEPTED)
    rhythm = RhythmSpec(
        name="r1",
        title="R1",
        persona="user",
        phases=[
            PhaseSpec(
                name="p1",
                scenes=[SceneSpec(name="s1", surface="sf1", story="ST-001")],
            ),
        ],
    )
    app = _make_lifecycle_appspec(
        entities=[_make_entity("Task")],
        stories=[story],
        rhythms=[rhythm],
        persona_ids=["user"],
    )
    project = tmp_path / "proj"
    project.mkdir()

    # Step 5: test_designs
    td_dir = project / ".dazzle" / "test_designs"
    td_dir.mkdir(parents=True)
    (td_dir / "design1.json").write_text("{}")

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=app,
    ):
        result = json.loads(lifecycle_rhythm_handler(project, {}))

    assert result["maturity"] == "evaluating"


def test_lifecycle_mature(tmp_path):
    """Steps 1-7 complete -> mature."""
    from dazzle.mcp.server.handlers.rhythm import lifecycle_rhythm_handler

    story = _make_story("ST-001", actor="user", status=StoryStatus.ACCEPTED)
    rhythm = RhythmSpec(
        name="r1",
        title="R1",
        persona="user",
        phases=[
            PhaseSpec(
                name="p1",
                scenes=[SceneSpec(name="s1", surface="sf1", story="ST-001")],
            ),
        ],
    )
    app = _make_lifecycle_appspec(
        entities=[_make_entity("Task")],
        stories=[story],
        rhythms=[rhythm],
        persona_ids=["user"],
    )
    project = tmp_path / "proj"
    project.mkdir()

    # Step 5: test_designs
    td_dir = project / ".dazzle" / "test_designs"
    td_dir.mkdir(parents=True)
    (td_dir / "design1.json").write_text("{}")

    # Step 6: evaluations/eval-*.json
    eval_dir = project / ".dazzle" / "evaluations"
    eval_dir.mkdir(parents=True)
    (eval_dir / "eval-20260101-000000.json").write_text("{}")

    # Step 7: evaluations/gaps-*.json
    (eval_dir / "gaps-20260101-000000.json").write_text("{}")

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=app,
    ):
        result = json.loads(lifecycle_rhythm_handler(project, {}))

    assert result["maturity"] == "mature"
    # Step 8 should be partial (since other steps are complete)
    assert result["steps"][7]["status"] == "partial"
    assert result["steps"][7]["name"] == "iterate"


def test_lifecycle_iterate_not_started_when_nothing_complete(tmp_path):
    """Step 8 (iterate) is not_started when no other step is complete."""
    from dazzle.mcp.server.handlers.rhythm import lifecycle_rhythm_handler

    app = _make_lifecycle_appspec()
    project = tmp_path / "proj"
    project.mkdir()

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=app,
    ):
        result = json.loads(lifecycle_rhythm_handler(project, {}))

    assert result["steps"][7]["status"] == "not_started"
    assert result["steps"][7]["name"] == "iterate"


def test_lifecycle_steps_have_suggestions(tmp_path):
    """Incomplete steps include actionable suggestions."""
    from dazzle.mcp.server.handlers.rhythm import lifecycle_rhythm_handler

    app = _make_lifecycle_appspec()
    project = tmp_path / "proj"
    project.mkdir()

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=app,
    ):
        result = json.loads(lifecycle_rhythm_handler(project, {}))

    # not_started steps should have suggestions
    for step in result["steps"]:
        if step["status"] == "not_started":
            assert len(step["suggestions"]) > 0, f"Step {step['name']} has no suggestions"


def test_propose_rhythm_includes_ambient_phase(mock_appspec):
    """Proposed rhythm includes an ambient phase."""
    from dazzle.mcp.server.handlers.rhythm import propose_rhythm_handler

    with patch(
        "dazzle.mcp.server.handlers.rhythm.load_project_appspec",
        return_value=mock_appspec,
    ):
        result = propose_rhythm_handler(Path("/fake"), {"persona": "new_user"})
    data = json.loads(result)
    dsl = data["proposed_dsl"]
    assert "kind: ambient" in dsl
    assert "phase ambient:" in dsl
