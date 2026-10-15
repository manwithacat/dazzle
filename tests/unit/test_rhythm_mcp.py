"""Tests for the rhythm MCP handlers.

`list` / `get` / `coverage` are the operations the `rhythm` tool registers, so
they are exercised through its dispatcher (`handle_rhythm`). `evaluate`,
`gaps`, `lifecycle`, `fidelity` and `propose` are not on the tool; `gaps` is
exercised through `gaps_rhythm_handler` (the pipeline calls it) and the rest
through the `rhythm_*_impl` functions `dazzle rhythm` calls. Every test patches
only the AppSpec loader.
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
        elif op == "gaps":
            raw = handlers.gaps_rhythm_handler(project, args or {})
        else:
            a = args or {}
            impls = {
                "evaluate": lambda: handlers.rhythm_evaluate_impl(
                    project,
                    name=a.get("name", ""),
                    action=a.get("action", "evaluate"),
                    scores=a.get("scores", []),
                ),
                "propose": lambda: handlers.rhythm_propose_impl(
                    project, persona_id=a.get("persona", "")
                ),
                "fidelity": lambda: handlers.rhythm_fidelity_impl(project, name=a.get("name", "")),
                "lifecycle": lambda: handlers.rhythm_lifecycle_impl(project),
            }
            result = impls[op]()
            return {"error": result["error"]} if "error" in result else result
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


# Every rhythm-by-name operation answers an unknown name with the same error
# document rather than an empty result.
@pytest.mark.parametrize(
    ("op", "args"),
    [
        pytest.param("get", {"name": "nonexistent"}, id="get"),
        pytest.param("evaluate", {"name": "nonexistent"}, id="evaluate"),
        pytest.param(
            "evaluate",
            {"name": "nonexistent", "action": "submit_scores", "scores": []},
            id="evaluate-submit-scores",
        ),
        pytest.param("fidelity", {"name": "nonexistent"}, id="fidelity"),
    ],
)
def test_unknown_rhythm_is_error(op: str, args: dict):
    assert _run(op, _onboarding_app(), args) == {"error": "Rhythm 'nonexistent' not found"}


# ---------------------------------------------------------------------------
# evaluate — structural checks
# ---------------------------------------------------------------------------


def _check_row(c: dict) -> tuple:
    """(check, scene(s), subject, pass, advisory) — one row per emitted check."""
    scene = tuple(c["scenes"]) if "scenes" in c else c.get("scene")
    subject = c.get("target") or c.get("action") or c.get("surface")
    return (c["check"], scene, subject, c["pass"], c.get("advisory", False))


def _reuse_app(first_expects: str | None, second_expects: str | None) -> MagicMock:
    """`dashboard` reused by two scenes with the given expects."""
    return _app(
        [
            _rhythm(
                SceneSpec(name="s1", surface="dashboard", expects=first_expects),
                SceneSpec(name="s2", surface="dashboard", expects=second_expects),
            )
        ],
        surfaces=[_surface("dashboard")],
    )


# One evaluation contract: every scene emits its structural checks, advisory
# checks (action vocabulary, surface specialisation) never count toward the
# `summary`, and `advisory_warnings` appears only when an advisory fails. No
# scores are stored under /fake, so `scene_scores` is always null here.
@pytest.mark.parametrize(
    ("app", "name", "rows", "summary", "advisory_warnings"),
    [
        # Standard verbs (`submit`) pass silently; entity checks run for the
        # entity-bound scene.
        pytest.param(
            _onboarding_app(),
            "onboarding",
            [
                ("persona_exists", None, "new_user", True, False),
                ("surface_exists", "browse", "course_list", True, False),
                ("surface_exists", "enroll", "course_detail", True, False),
                ("action_standard", "enroll", "submit", True, True),
                ("entity_exists", "enroll", "Enrollment", True, False),
                ("surface_entity_match", "enroll", "course_detail", True, False),
            ],
            "5/5 checks passed",
            None,
            id="standard-actions-no-advisory",
        ),
        # A workspace target uses workspace_exists, never surface_exists.
        pytest.param(
            _app(
                [
                    _rhythm(
                        SceneSpec(
                            name="dashboard", surface="customer_dashboard", actions=["browse"]
                        )
                    )
                ],
                workspaces=["customer_dashboard"],
            ),
            "r1",
            [
                ("persona_exists", None, "user", True, False),
                ("workspace_exists", "dashboard", "customer_dashboard", True, False),
                ("action_standard", "dashboard", "browse", True, True),
            ],
            "2/2 checks passed",
            None,
            id="workspace-target-uses-workspace-check",
        ),
        # Neither a surface nor a workspace → surface_exists fails.
        pytest.param(
            _app([_rhythm(SceneSpec(name="s1", surface="nonexistent"))]),
            "r1",
            [
                ("persona_exists", None, "user", True, False),
                ("surface_exists", "s1", "nonexistent", False, False),
            ],
            "1/2 checks passed",
            None,
            id="unknown-target-fails",
        ),
        # Non-standard verbs fail as advisories only.
        pytest.param(
            _app(
                [
                    _rhythm(
                        SceneSpec(name="s1", surface="sf1", actions=["submit", "wiggle", "yeet"])
                    )
                ],
                surfaces=[_surface("sf1")],
            ),
            "r1",
            [
                ("persona_exists", None, "user", True, False),
                ("surface_exists", "s1", "sf1", True, False),
                ("action_standard", "s1", "submit", True, True),
                ("action_standard", "s1", "wiggle", False, True),
                ("action_standard", "s1", "yeet", False, True),
            ],
            "2/2 checks passed",
            2,
            id="nonstandard-actions-advisory-not-in-summary",
        ),
        # One surface, two scenes, two different expects → specialisation advisory.
        pytest.param(
            _reuse_app("confirmation_statement_visible", "ct600_deadline_with_filing_status"),
            "r1",
            [
                ("persona_exists", None, "user", True, False),
                ("surface_exists", "s1", "dashboard", True, False),
                ("surface_exists", "s2", "dashboard", True, False),
                ("surface_specialization", ("s1", "s2"), "dashboard", False, True),
            ],
            "3/3 checks passed",
            1,
            id="surface-reuse-different-expects-advisory",
        ),
        # Same (or absent) expects on a reused surface → no specialisation check.
        pytest.param(
            _reuse_app("data_visible", "data_visible"),
            "r1",
            [
                ("persona_exists", None, "user", True, False),
                ("surface_exists", "s1", "dashboard", True, False),
                ("surface_exists", "s2", "dashboard", True, False),
            ],
            "3/3 checks passed",
            None,
            id="surface-reuse-same-expects-no-advisory",
        ),
        pytest.param(
            _reuse_app(None, None),
            "r1",
            [
                ("persona_exists", None, "user", True, False),
                ("surface_exists", "s1", "dashboard", True, False),
                ("surface_exists", "s2", "dashboard", True, False),
            ],
            "3/3 checks passed",
            None,
            id="surface-reuse-no-expects-no-advisory",
        ),
    ],
)
def test_evaluate_checks(app, name, rows, summary, advisory_warnings):
    data = _run("evaluate", app, {"name": name})
    assert [_check_row(c) for c in data["checks"]] == rows
    assert data["summary"] == summary
    assert data["scene_scores"] is None
    assert data.get("advisory_warnings") == advisory_warnings
    if advisory_warnings:
        # The failing advisory carries the standard vocabulary as a hint.
        assert {"browse", "submit"} <= set(data["action_vocabulary"])
    else:
        assert "action_vocabulary" not in data
    for check in data["checks"]:
        if check["check"] == "surface_specialization":
            assert check["surface"] in check["message"]


def test_submitted_scores_persist_and_return_on_evaluate(tmp_path):
    """`submit_scores` writes `.dazzle/evaluations/eval-*.json`; a later
    structural `evaluate` returns those scores as `scene_scores`."""
    scores = [
        {
            "scene_name": "browse",
            "phase_name": "discovery",
            "dimensions": [
                {"dimension": d, "score": "pass", "evidence": "ok"}
                for d in ("arrival", "orientation", "action", "completion", "confidence")
            ],
            "gap_type": "none",
            "story_ref": None,
        }
    ]
    app = _onboarding_app()

    stored = _run(
        "evaluate",
        app,
        {"name": "onboarding", "action": "submit_scores", "scores": scores},
        project=tmp_path,
    )
    [eval_file] = (tmp_path / ".dazzle" / "evaluations").glob("eval-*.json")
    assert stored == {"stored": str(eval_file), "count": 1}
    on_disk = json.loads(eval_file.read_text())
    assert on_disk["rhythm"] == "onboarding"
    assert [e["scene_name"] for e in on_disk["evaluations"]] == ["browse"]

    evaluated = _run("evaluate", app, {"name": "onboarding"}, project=tmp_path)
    assert evaluated["summary"] == "5/5 checks passed"
    assert [s["scene_name"] for s in evaluated["scene_scores"]] == ["browse"]


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
# lifecycle
# ---------------------------------------------------------------------------

_STEPS = [
    "model_domain",
    "write_stories",
    "write_rhythms",
    "map_scenes_to_stories",
    "build_from_stories",
    "evaluate_from_scenes",
    "find_gaps",
    "iterate",
]
_NS, _P, _C = "not_started", "partial", "complete"
_MAPPED_SCENE = SceneSpec(name="s1", surface="sf1", story="ST-001")


# One lifecycle contract: each artefact the project carries completes its
# step; maturity follows the completed prefix (1–3 building, 1–5 evaluating,
# 1–7 mature); `current_focus` is the first incomplete step; `iterate` is
# partial once anything is complete; every not-started step carries a
# suggestion.
@pytest.mark.parametrize(
    ("entities", "scenes", "persona_ids", "artefacts", "statuses", "maturity", "focus"),
    [
        pytest.param(
            False, None, [], [], [_NS] * 8, "new_domain", "model_domain", id="empty-project"
        ),
        pytest.param(
            True,
            None,
            [],
            [],
            [_C, _NS, _NS, _NS, _NS, _NS, _NS, _P],
            "new_domain",
            "write_stories",
            id="entities-only",
        ),
        pytest.param(
            True,
            [_MAPPED_SCENE],
            ["user"],
            [],
            [_C, _C, _C, _C, _NS, _NS, _NS, _P],
            "building",
            "build_from_stories",
            id="stories-and-rhythms-building",
        ),
        pytest.param(
            True,
            [_MAPPED_SCENE],
            ["user", "admin"],
            [],
            [_C, _C, _P, _C, _NS, _NS, _NS, _P],
            "new_domain",
            "write_rhythms",
            id="rhythm-misses-a-persona-partial",
        ),
        pytest.param(
            True,
            [_MAPPED_SCENE, SceneSpec(name="s2", surface="sf2")],
            ["user"],
            [],
            [_C, _C, _C, _P, _NS, _NS, _NS, _P],
            "building",
            "map_scenes_to_stories",
            id="scene-without-story-partial",
        ),
        pytest.param(
            True,
            [_MAPPED_SCENE],
            ["user"],
            ["test_designs/design1.json"],
            [_C, _C, _C, _C, _C, _NS, _NS, _P],
            "evaluating",
            "evaluate_from_scenes",
            id="test-designs-evaluating",
        ),
        pytest.param(
            True,
            [_MAPPED_SCENE],
            ["user"],
            [
                "test_designs/design1.json",
                "evaluations/eval-20260101-000000.json",
                "evaluations/gaps-20260101-000000.json",
            ],
            [_C] * 7 + [_P],
            "mature",
            "iterate",
            id="evaluations-and-gaps-mature",
        ),
    ],
)
def test_lifecycle(tmp_path, entities, scenes, persona_ids, artefacts, statuses, maturity, focus):
    app = _app(
        [_rhythm(*scenes)] if scenes else [],
        personas=persona_ids,
        entities=[_entity("Task")] if entities else [],
        stories=[_story("ST-001")] if scenes else [],
    )
    for rel in artefacts:
        path = tmp_path / ".dazzle" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")

    result = _run("lifecycle", app, project=tmp_path)

    assert [s["name"] for s in result["steps"]] == _STEPS
    assert [s["status"] for s in result["steps"]] == statuses
    assert result["maturity"] == maturity
    assert result["current_focus"] == focus
    for step in result["steps"]:
        if step["status"] == _NS:
            assert step["suggestions"], step["name"]


# ---------------------------------------------------------------------------
# propose
# ---------------------------------------------------------------------------


def test_propose_rhythm_includes_ambient_phase():
    dsl = _run("propose", _onboarding_app(), {"persona": "new_user"})["proposed_dsl"]
    assert "phase ambient:" in dsl
    assert "kind: ambient" in dsl


# ---------------------------------------------------------------------------
# fidelity
# ---------------------------------------------------------------------------


def _fidelity_surface(
    name: str, field_names: list[str], action_names: list[str] | None = None
) -> MagicMock:
    section = MagicMock()
    section.elements = [MagicMock(field_name=fn) for fn in field_names]
    surf = _surface(name)
    surf.sections = [section]
    surf.actions = [_named(an) for an in action_names or []]
    return surf


def _fidelity_app(
    *scenes: SceneSpec,
    surfaces: list[MagicMock] | None = None,
    workspaces: list[str] | None = None,
) -> MagicMock:
    return _app([_rhythm(*scenes)], surfaces=surfaces, workspaces=workspaces)


# One scoring contract: fidelity = served / total scenes, where a scene is
# served when it is STRUCTURALLY aligned with the target surface — its
# action(s) are supported and its entity matches (or the target is a
# workspace). An `expects` string that shares no keyword with surface fields
# is a soft ADVISORY, not a gap (#1559), so `scenes_with_advisories` is where
# keyword matching (and its stemming, #457) shows. Collapsed from seven
# scenario tests (#1530).
@pytest.mark.parametrize(
    ("app", "expected"),
    [
        pytest.param(
            _fidelity_app(
                SceneSpec(name="check_balance", surface="wallet_detail", expects="balance_visible"),
                surfaces=[
                    _fidelity_surface("wallet_detail", ["balance", "currency", "last_updated"])
                ],
            ),
            {
                "rhythm_fidelity": 1.0,
                "scenes_served": 1,
                "scenes_proxied": 0,
                "scenes_with_advisories": 0,
            },
            id="served-expects-match",
        ),
        # s2 is proxied by a STRUCTURAL gap: it needs `approve`, the surface
        # only exposes `export`.
        pytest.param(
            _fidelity_app(
                SceneSpec(name="s1", surface="task_list", expects="task_title_visible"),
                SceneSpec(name="s2", surface="company_detail", actions=["approve"]),
                surfaces=[
                    _fidelity_surface("task_list", ["title", "status", "due_date"]),
                    _fidelity_surface("company_detail", ["name", "address"], ["export"]),
                ],
            ),
            {"rhythm_fidelity": 0.5, "scenes_served": 1, "scenes_proxied": 1},
            id="mixed-half-served",
        ),
        pytest.param(
            _fidelity_app(
                SceneSpec(name="arrive", surface="director_dash"), workspaces=["director_dash"]
            ),
            {"rhythm_fidelity": 1.0, "scenes_served": 1, "scenes_proxied": 0},
            id="workspace-target-served",
        ),
        pytest.param(
            _fidelity_app(
                SceneSpec(name="browse", surface="task_list"),
                surfaces=[_fidelity_surface("task_list", ["title"])],
            ),
            {"rhythm_fidelity": 1.0, "scenes_proxied": 0, "scenes_with_advisories": 0},
            id="no-expects-served",
        ),
        # An expects with no field keyword is advisory only: still served.
        pytest.param(
            _fidelity_app(
                SceneSpec(name="s1", surface="company_detail", expects="dividend_history_shown"),
                surfaces=[_fidelity_surface("company_detail", ["name", "address"])],
            ),
            {"rhythm_fidelity": 1.0, "scenes_proxied": 0, "scenes_with_advisories": 1},
            id="expects-mismatch-is-advisory-not-gap-#1559",
        ),
        # Standard action 'approve' fuzzy-matches 'client_approve' /
        # 'approve_return' without an exact 'approve' action (#454).
        pytest.param(
            _fidelity_app(
                SceneSpec(
                    name="vat_approval",
                    surface="vat_return",
                    actions=["approve"],
                    expects="return_approved",
                ),
                surfaces=[
                    _fidelity_surface(
                        "vat_return",
                        ["return", "status", "amount"],
                        ["client_approve", "approve_return", "submit_hmrc"],
                    )
                ],
            ),
            {"rhythm_fidelity": 1.0, "scenes_proxied": 0},
            id="fuzzy-action-match-#454",
        ),
        # Passive actions (browse, review) match any surface (#454).
        pytest.param(
            _fidelity_app(
                SceneSpec(
                    name="check_pnl",
                    surface="pnl_dashboard",
                    actions=["browse", "review"],
                    expects="pnl_visible",
                ),
                surfaces=[
                    _fidelity_surface(
                        "pnl_dashboard", ["pnl", "revenue", "expense"], ["export_csv"]
                    )
                ],
            ),
            {"rhythm_fidelity": 1.0, "scenes_proxied": 0},
            id="passive-actions-always-match-#454",
        ),
        # Stemmed keywords match: 'deadlines' meets field 'deadline_type', so
        # no advisory is raised (#457).
        pytest.param(
            _fidelity_app(
                SceneSpec(
                    name="review_deadlines",
                    surface="deadline_view",
                    expects="upcoming_deadlines_visible_for_next_90_days",
                ),
                surfaces=[
                    _fidelity_surface(
                        "deadline_view", ["deadline_type", "due_date", "entity_type", "status"]
                    )
                ],
            ),
            {"rhythm_fidelity": 1.0, "scenes_proxied": 0, "scenes_with_advisories": 0},
            id="keyword-stemming-#457",
        ),
    ],
)
def test_fidelity_scoring(app: MagicMock, expected: dict):
    result = _run("fidelity", app, {"name": "r1"})
    assert {key: result[key] for key in expected} == expected


def test_fidelity_scene_proxied():
    """Scene whose action the surface can't support is reported as a proxy.

    Proxy status is a STRUCTURAL judgement (#1559): the scene needs an
    `approve` action, but `company_detail` only exposes `export`.
    """
    app = _fidelity_app(
        SceneSpec(name="dividend_review", surface="company_detail", actions=["approve"]),
        surfaces=[
            _fidelity_surface(
                "company_detail", ["name", "registration_number", "address"], ["export"]
            )
        ],
    )
    result = _run("fidelity", app, {"name": "r1"})

    assert result["rhythm_fidelity"] == 0.0
    assert result["scenes_proxied"] == 1
    [proxy] = result["proxy_scenes"]
    assert (proxy["scene"], proxy["phase"], proxy["surface"]) == (
        "dividend_review",
        "p1",
        "company_detail",
    )
    [gap] = proxy["gaps"]
    assert "'approve'" in gap


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
