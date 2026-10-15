"""Tests for the rhythm MCP handlers.

`list` / `get` / `coverage` are the operations the `rhythm` tool registers, so
they are exercised through its dispatcher (`handle_rhythm`); `gaps` is
exercised through `gaps_rhythm_handler` (the pipeline calls it). Every test
patches only the AppSpec loader.
"""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from dazzle.core.ir.rhythm import PhaseKind, PhaseSpec, RhythmSpec, SceneSpec
from dazzle.core.ir.stories import StorySpec, StoryStatus, StoryTrigger

_LOADER = "dazzle.mcp.server.handlers.rhythm.load_project_appspec"
_TOOL_OPS = {"list", "get", "coverage"}

# ---------------------------------------------------------------------------
# Spec builders
# ---------------------------------------------------------------------------


def _named(name: str, **attrs: Any) -> MagicMock:
    obj = MagicMock()
    obj.name = name
    for key, value in attrs.items():
        setattr(obj, key, value)
    return obj


def _persona(pid: str) -> MagicMock:
    p = MagicMock()
    p.id = pid
    return p


def _surface(
    name: str,
    *,
    entity_ref: str | None = None,
    access: MagicMock | None = None,
    mode: str = "list",
) -> MagicMock:
    return _named(name, entity_ref=entity_ref, access=access, mode=mode)


def _acl(allow: list[str] | None = None, deny: list[str] | None = None) -> MagicMock:
    access = MagicMock()
    access.require_auth = True
    access.allow_personas = allow or []
    access.deny_personas = deny or []
    return access


def _entity(name: str, field_count: int = 2) -> MagicMock:
    return _named(name, fields=[MagicMock() for _ in range(field_count)])


def _rhythm(
    *scenes: SceneSpec,
    name: str = "r1",
    persona: str = "user",
    kind: PhaseKind | None = None,
) -> RhythmSpec:
    """Single-phase rhythm `p1` — the shape most tests need."""
    return RhythmSpec(
        name=name,
        title=name.upper(),
        persona=persona,
        phases=[PhaseSpec(name="p1", kind=kind, scenes=list(scenes))],
    )


def _app(
    rhythms: list[RhythmSpec] | None = None,
    *,
    personas: list[str] | None = None,
    surfaces: list[MagicMock] | None = None,
    workspaces: list[str] | None = None,
    entities: list[MagicMock] | None = None,
    stories: list[StorySpec] | None = None,
) -> MagicMock:
    spec = MagicMock()
    spec.rhythms = rhythms or []
    spec.personas = [_persona(p) for p in (["user"] if personas is None else personas)]
    spec.surfaces = surfaces or []
    spec.workspaces = [_named(w) for w in workspaces or []]
    spec.domain.entities = entities or []
    spec.stories = stories or []
    return spec


def _story(
    story_id: str, actor: str = "user", status: StoryStatus = StoryStatus.ACCEPTED
) -> StorySpec:
    return StorySpec(
        story_id=story_id,
        title=f"Story {story_id}",
        persona=actor,
        trigger=StoryTrigger.USER_CLICK,
        entities=["Task"],
        status=status,
        created_at="2026-01-01T00:00:00",
    )


def _onboarding_app() -> MagicMock:
    """`onboarding` for `new_user`: a list scene and an entity-bound submit scene."""
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
    return _app(
        [rhythm],
        personas=["new_user"],
        surfaces=[
            _surface("course_list"),
            _surface("course_detail", entity_ref="Enrollment", mode="detail"),
        ],
        entities=[_entity("Enrollment")],
    )


def _kinds_app() -> MagicMock:
    """`onboarding` with one active and one ambient phase."""
    rhythm = RhythmSpec(
        name="onboarding",
        title="New User Onboarding",
        persona="new_user",
        cadence="quarterly",
        phases=[
            PhaseSpec(
                name="discovery",
                kind=PhaseKind.ACTIVE,
                scenes=[SceneSpec(name="browse", title="Browse Courses", surface="course_list")],
            ),
            PhaseSpec(
                name="background",
                kind=PhaseKind.AMBIENT,
                scenes=[SceneSpec(name="notify", title="Notify", surface="notifications")],
            ),
        ],
    )
    return _app([rhythm], personas=["new_user"])


def _fiscal_app() -> MagicMock:
    """`fiscal` with per-phase cadence hints (periodic + ambient)."""
    rhythm = RhythmSpec(
        name="fiscal",
        title="Fiscal Year",
        persona="director",
        phases=[
            PhaseSpec(
                name="q1",
                kind=PhaseKind.PERIODIC,
                cadence="January-March",
                scenes=[SceneSpec(name="review", surface="budget_list")],
            ),
            PhaseSpec(
                name="ongoing",
                kind=PhaseKind.AMBIENT,
                cadence="ad-hoc, between deadlines",
                scenes=[SceneSpec(name="check", surface="dashboard")],
            ),
        ],
    )
    return _app([rhythm], personas=["director"])


def _run(op: str, app: MagicMock, args: dict[str, Any] | None = None, project: Path | None = None):
    """Run one rhythm operation against `app`; return the decoded JSON."""
    from dazzle.mcp.server.handlers import rhythm as handlers

    project = project or Path("/fake")
    with patch(_LOADER, return_value=app):
        if op in _TOOL_OPS:
            from dazzle.mcp.server.handlers_consolidated import handle_rhythm

            raw = handle_rhythm(
                {"operation": op, "_resolved_project_path": project, **(args or {})}
            )
        else:
            raw = handlers.gaps_rhythm_handler(project, args or {})
    return json.loads(raw)


# ---------------------------------------------------------------------------
# list / get
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("app_builder", "expected"),
    [
        pytest.param(
            _onboarding_app,
            {"phase_count": 1, "ambient_phases": 0, "scene_count": 2},
            id="single-phase-no-ambient",
        ),
        pytest.param(
            _kinds_app,
            {"phase_count": 2, "ambient_phases": 1, "scene_count": 2},
            id="counts-ambient-phases",
        ),
    ],
)
def test_list_rhythms(app_builder, expected: dict):
    data = _run("list", app_builder())
    assert data == {
        "rhythms": [
            {
                "name": "onboarding",
                "title": "New User Onboarding",
                "persona": "new_user",
                "cadence": "quarterly",
                **expected,
            }
        ]
    }


def test_get_rhythm_returns_phases_and_scenes():
    data = _run("get", _onboarding_app(), {"name": "onboarding"})
    assert (data["name"], data["persona"], data["cadence"]) == (
        "onboarding",
        "new_user",
        "quarterly",
    )
    [phase] = data["phases"]
    assert phase["name"] == "discovery"
    assert phase["scenes"] == [
        {
            "name": "browse",
            "title": "Browse Courses",
            "surface": "course_list",
            "actions": [],
            "entity": None,
            "expects": None,
            "story": None,
        },
        {
            "name": "enroll",
            "title": "Enroll",
            "surface": "course_detail",
            "actions": ["submit"],
            "entity": "Enrollment",
            "expects": None,
            "story": None,
        },
    ]


# One serialization contract: `get` includes per-phase metadata field X
# (kind / kind-null-when-unset / cadence) — #1530.
@pytest.mark.parametrize(
    ("app_builder", "rhythm_name", "field", "expected_by_phase"),
    [
        pytest.param(_kinds_app, "onboarding", "kind", ["active", "ambient"], id="kind"),
        pytest.param(_onboarding_app, "onboarding", "kind", [None], id="kind-null-when-unset"),
        pytest.param(
            _fiscal_app,
            "fiscal",
            "cadence",
            ["January-March", "ad-hoc, between deadlines"],
            id="cadence",
        ),
    ],
)
def test_get_rhythm_includes_phase_field(app_builder, rhythm_name, field, expected_by_phase):
    data = _run("get", app_builder(), {"name": rhythm_name})
    assert [phase[field] for phase in data["phases"]] == expected_by_phase


def test_unknown_rhythm_is_error():
    """`get` answers an unknown name with an error document, not an empty result."""
    assert _run("get", _onboarding_app(), {"name": "nonexistent"}) == {
        "error": "Rhythm 'nonexistent' not found"
    }


# ---------------------------------------------------------------------------
# coverage
# ---------------------------------------------------------------------------


def _ambient_split_app() -> MagicMock:
    """`power_user` has an ambient phase; `new_user` does not."""
    with_ambient = RhythmSpec(
        name="daily_check",
        title="Daily Check",
        persona="power_user",
        phases=[
            PhaseSpec(
                name="work",
                kind=PhaseKind.ACTIVE,
                scenes=[SceneSpec(name="do_work", surface="dashboard")],
            ),
            PhaseSpec(
                name="monitoring",
                kind=PhaseKind.AMBIENT,
                scenes=[SceneSpec(name="alerts", surface="alerts_panel")],
            ),
        ],
    )
    without_ambient = _rhythm(
        SceneSpec(name="register", surface="signup"),
        name="onboarding",
        persona="new_user",
        kind=PhaseKind.ACTIVE,
    )
    return _app(
        [with_ambient, without_ambient],
        personas=["power_user", "new_user"],
        surfaces=[_surface("dashboard"), _surface("alerts_panel"), _surface("signup")],
    )


def _cov(accessible_surfaces, accessible_workspaces, exercised, pct, unexercised):
    return {
        "accessible_surfaces": accessible_surfaces,
        "accessible_workspaces": accessible_workspaces,
        "exercised": exercised,
        "coverage_pct": pct,
        "unexercised": unexercised,
    }


# One coverage contract: persona-level and surface/workspace-level coverage
# over all rhythms. Per-persona coverage is scoped to what the persona can
# reach: open surfaces (no ACL) count, `allow_personas` / `deny_personas`
# exclude, workspaces always count and are tracked apart from surfaces.
@pytest.mark.parametrize(
    ("app", "expected"),
    [
        pytest.param(
            _onboarding_app(),
            {
                "personas_with_rhythms": ["new_user"],
                "personas_without_rhythms": [],
                "surfaces_exercised": ["course_detail", "course_list"],
                "surfaces_unexercised": [],
                "persona_coverage": {"new_user": _cov(2, 0, 2, 100, [])},
            },
            id="open-surfaces-all-accessible",
        ),
        pytest.param(
            _ambient_split_app(),
            {
                "personas_with_ambient": ["power_user"],
                "personas_without_ambient": ["new_user"],
            },
            id="ambient-persona-split",
        ),
        # director reaches budget_review, approval_queue (allow-listed) and
        # public_page (no ACL), not agent_capacity: 2 of 3 exercised.
        pytest.param(
            _app(
                [
                    _rhythm(
                        SceneSpec(name="review", surface="budget_review"),
                        SceneSpec(name="approve", surface="approval_queue"),
                        persona="director",
                    )
                ],
                personas=["director"],
                surfaces=[
                    _surface("budget_review", access=_acl(allow=["director", "finance"])),
                    _surface("approval_queue", access=_acl(allow=["director"])),
                    _surface("agent_capacity", access=_acl(allow=["agent_manager"])),
                    _surface("public_page"),
                ],
            ),
            {"persona_coverage": {"director": _cov(3, 0, 2, 67, ["public_page"])}},
            id="allow-list-scopes-persona",
        ),
        pytest.param(
            _app(
                [_rhythm(SceneSpec(name="s1", surface="public_docs"), persona="intern")],
                personas=["intern"],
                surfaces=[
                    _surface("public_docs"),
                    _surface("admin_panel", access=_acl(deny=["intern"])),
                ],
            ),
            {"persona_coverage": {"intern": _cov(1, 0, 1, 100, [])}},
            id="deny-list-excludes-persona",
        ),
        pytest.param(
            _app(
                [
                    _rhythm(
                        SceneSpec(name="arrive", surface="director_dash"),
                        SceneSpec(name="review", surface="budget_list"),
                        persona="director",
                    )
                ],
                personas=["director"],
                surfaces=[_surface("budget_list")],
                workspaces=["director_dash"],
            ),
            {
                "total_workspaces": 1,
                "workspaces_exercised": ["director_dash"],
                "workspaces_unexercised": [],
                "surfaces_exercised": ["budget_list"],
                "persona_coverage": {"director": _cov(1, 1, 2, 100, [])},
            },
            id="workspace-targets-tracked-apart",
        ),
    ],
)
def test_coverage(app, expected: dict):
    data = _run("coverage", app)
    assert {key: data[key] for key in expected} == expected


# ---------------------------------------------------------------------------
# gaps
# ---------------------------------------------------------------------------


# One classification contract: each spec shape produces exactly one gap of
# the expected kind + severity + description mention (#1530).
@pytest.mark.parametrize(
    ("rhythms", "stories", "persona_ids", "kind", "severity", "desc_contains"),
    [
        pytest.param(
            [_rhythm(SceneSpec(name="s1", surface="sf1", story="ST-999"))],
            [],
            ["user"],
            "capability",
            "blocking",
            "ST-999",
            id="missing-story-blocking",
        ),
        pytest.param(
            [_rhythm(SceneSpec(name="s1", surface="sf1", story="ST-001"))],
            [_story("ST-001", status=StoryStatus.DRAFT)],
            ["user"],
            "capability",
            "blocking",
            "DRAFT",
            id="draft-story-blocking",
        ),
        pytest.param(
            [_rhythm(SceneSpec(name="s1", surface="sf1"))],
            [],
            ["user"],
            "unmapped",
            "advisory",
            "s1",
            id="unmapped-scene-advisory",
        ),
        pytest.param(
            [_rhythm(SceneSpec(name="s1", surface="sf1", story="ST-002"))],
            [_story("ST-001"), _story("ST-002")],
            ["user"],
            "orphan",
            "advisory",
            "ST-001",
            id="orphan-story-advisory",
        ),
        pytest.param(
            [_rhythm(SceneSpec(name="s1", surface="sf1", story="ST-001"), kind=PhaseKind.ACTIVE)],
            [_story("ST-001")],
            ["user"],
            "ambient",
            "advisory",
            "user",
            id="no-ambient-phase-advisory",
        ),
        pytest.param(
            [],
            [_story("ST-001", actor="lonely_persona")],
            ["lonely_persona"],
            "unscored",
            "advisory",
            "lonely_persona",
            id="unscored-persona-advisory",
        ),
    ],
)
def test_gaps_classification(
    tmp_path, rhythms, stories, persona_ids, kind, severity, desc_contains
):
    app = _app(rhythms, stories=stories, personas=persona_ids)
    result = _run("gaps", app, project=tmp_path)
    [gap] = [g for g in result["gaps"] if g["kind"] == kind]
    assert gap["severity"] == severity
    assert desc_contains in gap["description"]


def test_gaps_report_orders_summarises_and_persists(tmp_path):
    """Blocking gaps lead `roadmap_order`, the summary counts every gap by
    kind, severity and persona, and the report is written to `gaps-*.json`.
    The rhythm's phase has no kind, so the persona also gets an ambient gap."""
    rhythm = _rhythm(
        SceneSpec(name="unmapped_scene", surface="sf1"),  # advisory: unmapped
        SceneSpec(name="bad_ref", surface="sf2", story="ST-NOPE"),  # blocking: capability
    )
    app = _app([rhythm], stories=[_story("ST-ORPHAN")])  # advisory: orphan
    result = _run("gaps", app, project=tmp_path)

    assert [g["severity"] for g in result["roadmap_order"]] == [
        "blocking",
        "advisory",
        "advisory",
        "advisory",
    ]
    assert result["summary"] == {
        "total": 4,
        "by_kind": {"unmapped": 1, "capability": 1, "orphan": 1, "ambient": 1},
        "by_severity": {"advisory": 3, "blocking": 1},
        "by_persona": {"user": 4},
    }
    [report] = (tmp_path / ".dazzle" / "evaluations").glob("gaps-*.json")
    assert json.loads(report.read_text()) == result


def test_gaps_layers_evaluated_failures(tmp_path):
    """A failed dimension in a stored `eval-*.json` becomes a blocking gap."""
    app = _app(
        [_rhythm(SceneSpec(name="s1", surface="sf1", story="ST-001"))],
        stories=[_story("ST-001")],
    )
    eval_dir = tmp_path / ".dazzle" / "evaluations"
    eval_dir.mkdir(parents=True)
    (eval_dir / "eval-20260101-000000.json").write_text(
        json.dumps(
            {
                "rhythm": "r1",
                "timestamp": "20260101-000000",
                "evaluations": [
                    {
                        "scene_name": "s1",
                        "phase_name": "p1",
                        "dimensions": [
                            {"dimension": "action", "score": "fail", "evidence": "broken"}
                        ],
                        "gap_type": "capability",
                        "story_ref": "ST-001",
                    }
                ],
            }
        )
    )
    result = _run("gaps", app, project=tmp_path)
    [gap] = [g for g in result["gaps"] if "failed action" in g["description"]]
    assert gap["severity"] == "blocking"


# ---------------------------------------------------------------------------
# story ⇄ rhythm composition query (#1559 slice 2)
# ---------------------------------------------------------------------------


def _composition_spec():
    """Spec with two stories and one rhythm: ST-1 composed (active phase),
    ST-2 declared but composed into no journey, plus one story-less scene."""
    stories = [
        StorySpec(
            story_id="ST-1",
            title="Submit report",
            persona="agent",
            trigger=StoryTrigger.FORM_SUBMITTED,
            status=StoryStatus.ACCEPTED,
        ),
        StorySpec(
            story_id="ST-2",
            title="Archive report",
            persona="agent",
            trigger=StoryTrigger.STATUS_CHANGED,
            status=StoryStatus.ACCEPTED,
        ),
    ]
    rhythm = RhythmSpec(
        name="agent_daily",
        persona="agent",
        phases=[
            PhaseSpec(
                name="work",
                kind=PhaseKind.ACTIVE,
                scenes=[
                    SceneSpec(name="submit", surface="report_create", story="ST-1"),
                    SceneSpec(name="idle_glance", surface="dashboard"),  # no story
                ],
            )
        ],
    )
    spec = MagicMock()
    spec.stories = stories
    spec.rhythms = [rhythm]
    return spec


def test_story_composition_full_map():
    from dazzle.mcp.server.handlers.stories import story_composition_handler

    with patch(
        "dazzle.mcp.server.handlers.stories.load_project_appspec",
        return_value=_composition_spec(),
    ):
        result = json.loads(story_composition_handler(Path("/fake"), {}))

    assert result["summary"] == {
        "total_stories": 2,
        "composed": 1,
        "uncomposed": 1,
        "linked_scenes": 1,
        "unlinked_scenes": 1,
    }
    # ST-2 is declared but composed into no journey — the drift-trap signal.
    assert result["stories_uncomposed"] == ["ST-2"]
    # The story-less scene is surfaced for the reverse direction.
    assert result["scenes_unlinked"] == [
        {"rhythm": "agent_daily", "phase": "work", "scene": "idle_glance"}
    ]
    edge = result["edges"][0]
    assert edge["story_id"] == "ST-1"
    assert edge["phase_kind"] == "active"
    assert edge["story_exists"] is True


def test_story_composition_focus_active_phase():
    """Answers 'which active phase composes story X'."""
    from dazzle.mcp.server.handlers.stories import story_composition_handler

    with patch(
        "dazzle.mcp.server.handlers.stories.load_project_appspec",
        return_value=_composition_spec(),
    ):
        result = json.loads(
            story_composition_handler(Path("/fake"), {"story_ids": ["ST-1", "ST-404"]})
        )

    st1 = result["stories"]["ST-1"]
    assert st1["exists"] is True
    assert len(st1["active_phases"]) == 1
    assert st1["active_phases"][0]["scene"] == "submit"
    # Unknown story is reported as non-existent, not silently dropped.
    assert result["stories"]["ST-404"] == {
        "exists": False,
        "composed_by": [],
        "active_phases": [],
    }
