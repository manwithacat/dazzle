"""Tests for the headless persona journey analysis."""

from types import SimpleNamespace
from typing import Any

import pytest

from dazzle.agent.missions.persona_journey import (
    PersonaJourneyGap,
    _analyze_cross_entity_gaps,
    _analyze_experience_completeness,
    _analyze_experience_reachability,
    _analyze_navigation_scope,
    _analyze_orphan_surfaces,
    _analyze_process_surface_wiring,
    _analyze_story_surface_coverage,
    _analyze_surface_access,
    _analyze_workspace_reachability,
    _compute_accessible_surfaces,
    _gap_to_observation,
    run_headless_discovery,
)

# =============================================================================
# Fixtures
# =============================================================================


def _make_persona(
    pid: str,
    default_workspace: str | None = None,
    description: str = "",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=pid,
        name=pid,
        description=description,
        default_workspace=default_workspace,
    )


def _make_workspace(
    name: str,
    regions: list[Any] | None = None,
    access: Any | None = None,
    nav_groups: list[Any] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        name=name, regions=regions or [], access=access, nav_groups=nav_groups or []
    )


def _make_region(
    name: str, source: str | None = None, surfaces: list[str] | None = None
) -> SimpleNamespace:
    return SimpleNamespace(name=name, source=source, surfaces=surfaces or [])


def _make_surface(
    name: str,
    title: str = "",
    mode: str = "list",
    entity_ref: str | None = None,
    access: Any | None = None,
    actions: list[Any] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        title=title or name,
        mode=mode,
        entity_ref=entity_ref,
        entity=entity_ref,
        sections=[],
        actions=actions or [],
        access=access,
        ux=None,
    )


def _make_access(
    allow_personas: list[str] | None = None,
    deny_personas: list[str] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        allow_personas=allow_personas or [],
        deny_personas=deny_personas or [],
    )


def _make_story(
    story_id: str,
    actor: str,
    title: str = "",
    scope: list[str] | None = None,
    conditions: list[str] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        story_id=story_id,
        id=story_id,
        persona=actor,
        title=title or story_id,
        description="",
        entities=scope or [],
        conditions=conditions or [],
    )


def _make_process(
    name: str,
    steps: list[Any] | None = None,
    implements: list[str] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        title=name,
        steps=steps or [],
        implements=implements or [],
        trigger=None,
    )


def _make_human_task_step(name: str, surface: str) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        kind="human_task",
        human_task=SimpleNamespace(surface=surface),
    )


def _make_experience(
    name: str,
    title: str = "",
    steps: list[Any] | None = None,
    start_step: str | None = None,
    access: Any | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        title=title or name,
        steps=steps or [],
        start_step=start_step,
        access=access,
    )


def _make_exp_step(
    name: str,
    kind: str = "surface",
    surface: str | None = None,
    transitions: list[Any] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        kind=kind,
        surface=surface,
        transitions=transitions or [],
    )


def _make_transition(next_step: str) -> SimpleNamespace:
    return SimpleNamespace(next_step=next_step)


def _make_entity(name: str, title: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        title=title or name,
        fields=[],
        state_machine=None,
        access=None,
    )


def _make_appspec(
    entities: list[Any] | None = None,
    surfaces: list[Any] | None = None,
    personas: list[Any] | None = None,
    workspaces: list[Any] | None = None,
    processes: list[Any] | None = None,
    experiences: list[Any] | None = None,
    stories: list[Any] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        name="test_app",
        domain=SimpleNamespace(entities=entities or []),
        surfaces=surfaces or [],
        personas=personas or [],
        workspaces=workspaces or [],
        processes=processes or [],
        experiences=experiences or [],
        stories=stories or [],
    )


# =============================================================================
# Tests: Workspace Reachability
# =============================================================================


class TestWorkspaceReachability:
    def test_no_default_workspace(self) -> None:
        persona = _make_persona("admin")
        appspec = _make_appspec(personas=[persona])
        gaps = _analyze_workspace_reachability("admin", persona, appspec)
        assert len(gaps) == 1
        assert gaps[0].gap_type == "workspace_unreachable"
        assert gaps[0].severity == "medium"

    def test_workspace_does_not_exist(self) -> None:
        persona = _make_persona("admin", default_workspace="missing_ws")
        appspec = _make_appspec(personas=[persona], workspaces=[])
        gaps = _analyze_workspace_reachability("admin", persona, appspec)
        assert len(gaps) == 1
        assert gaps[0].gap_type == "workspace_unreachable"
        assert gaps[0].severity == "critical"

    def test_workspace_access_denied(self) -> None:
        persona = _make_persona("viewer", default_workspace="admin_ws")
        ws = _make_workspace(
            "admin_ws",
            regions=[_make_region("main")],
            access=_make_access(allow_personas=["admin"]),
        )
        appspec = _make_appspec(personas=[persona], workspaces=[ws])
        gaps = _analyze_workspace_reachability("viewer", persona, appspec)
        assert any(g.severity == "high" for g in gaps)

    def test_workspace_accessible_with_regions(self) -> None:
        persona = _make_persona("admin", default_workspace="main_ws")
        ws = _make_workspace("main_ws", regions=[_make_region("sidebar")])
        appspec = _make_appspec(personas=[persona], workspaces=[ws])
        assert _analyze_workspace_reachability("admin", persona, appspec) == []


# =============================================================================
# Tests: Surface Access
# =============================================================================


class TestSurfaceAccess:
    @pytest.mark.parametrize(
        ("access", "persona_id", "accessible"),
        [
            pytest.param(None, "admin", True, id="no-access-control"),
            pytest.param(
                _make_access(allow_personas=["admin"]), "admin", True, id="allow-list-includes"
            ),
            pytest.param(
                _make_access(allow_personas=["admin"]), "viewer", False, id="allow-list-excludes"
            ),
        ],
    )
    def test_compute_accessible_surfaces(
        self, access: Any, persona_id: str, accessible: bool
    ) -> None:
        appspec = _make_appspec(
            surfaces=[_make_surface("task_list", entity_ref="Task", access=access)],
        )
        result = _compute_accessible_surfaces(persona_id, appspec)
        assert ("task_list" in result) is accessible

    def test_story_entity_surface_blocked(self) -> None:
        persona = _make_persona("viewer")
        appspec = _make_appspec(
            surfaces=[
                _make_surface(
                    "task_list",
                    entity_ref="Task",
                    access=_make_access(allow_personas=["admin"]),
                ),
            ],
            stories=[_make_story("S1", actor="viewer", scope=["Task"])],
        )
        gaps = _analyze_surface_access("viewer", persona, appspec, set())
        assert len(gaps) >= 1
        assert gaps[0].gap_type == "surface_inaccessible"


# =============================================================================
# Tests: Story Surface Coverage
# =============================================================================


def _create_task_story_appspec(surfaces: list[Any]) -> SimpleNamespace:
    return _make_appspec(
        surfaces=surfaces,
        stories=[_make_story("S1", actor="admin", title="Create a new task", scope=["Task"])],
    )


class TestStorySurfaceCoverage:
    def test_entities_have_matching_surfaces(self) -> None:
        appspec = _create_task_story_appspec(
            [
                _make_surface("task_list", mode="list", entity_ref="Task"),
                _make_surface("task_create", mode="create", entity_ref="Task"),
            ]
        )
        gaps = _analyze_story_surface_coverage(
            "admin", _make_persona("admin"), appspec, {"task_list", "task_create"}
        )
        assert gaps == []

    def test_missing_create_surface_for_entity(self) -> None:
        appspec = _create_task_story_appspec([_make_surface("task_list", entity_ref="Task")])
        gaps = _analyze_story_surface_coverage(
            "admin", _make_persona("admin"), appspec, {"task_list"}
        )
        assert len(gaps) >= 1
        assert gaps[0].gap_type == "story_no_surface"

    def test_non_actor_persona_stories_skipped(self) -> None:
        appspec = _create_task_story_appspec([])
        gaps = _analyze_story_surface_coverage("viewer", _make_persona("viewer"), appspec, set())
        assert gaps == []


# =============================================================================
# Tests: Process Surface Wiring
# =============================================================================


def _human_task_appspec(actor: str, surface_name: str, surfaces: list[Any]) -> SimpleNamespace:
    return _make_appspec(
        surfaces=surfaces,
        stories=[_make_story("S1", actor=actor, scope=["Task"])],
        processes=[
            _make_process(
                "create_task",
                steps=[_make_human_task_step("fill_form", surface_name)],
                implements=["S1"],
            ),
        ],
    )


class TestProcessSurfaceWiring:
    def test_human_task_surface_exists_and_accessible(self) -> None:
        appspec = _human_task_appspec(
            "admin", "task_form", [_make_surface("task_form", mode="create", entity_ref="Task")]
        )
        gaps = _analyze_process_surface_wiring(
            "admin", _make_persona("admin"), appspec, {"task_form"}
        )
        assert gaps == []

    def test_human_task_surface_missing(self) -> None:
        appspec = _human_task_appspec("admin", "missing_form", [])
        gaps = _analyze_process_surface_wiring("admin", _make_persona("admin"), appspec, set())
        assert len(gaps) >= 1
        assert gaps[0].gap_type == "process_step_no_surface"
        assert gaps[0].severity == "critical"

    def test_human_task_surface_inaccessible(self) -> None:
        appspec = _human_task_appspec(
            "viewer",
            "task_form",
            [
                _make_surface(
                    "task_form",
                    mode="create",
                    entity_ref="Task",
                    access=_make_access(allow_personas=["admin"]),
                ),
            ],
        )
        gaps = _analyze_process_surface_wiring("viewer", _make_persona("viewer"), appspec, set())
        assert len(gaps) >= 1
        assert gaps[0].severity == "high"


# =============================================================================
# Tests: Experience Completeness
# =============================================================================


class TestExperienceCompleteness:
    @pytest.mark.parametrize(
        ("second_step", "expected_gap_types"),
        [
            pytest.param(("step2", "task_create"), set(), id="valid-flow"),
            pytest.param(
                ("step2", "nonexistent_surface"),
                {"experience_broken_step"},
                id="missing-surface-reference",
            ),
            pytest.param(None, {"experience_dangling_transition"}, id="broken-transition"),
        ],
    )
    def test_experience_flow(
        self, second_step: tuple[str, str] | None, expected_gap_types: set[str]
    ) -> None:
        if second_step is None:
            steps = [
                _make_exp_step(
                    "step1",
                    surface="task_list",
                    transitions=[_make_transition("nonexistent_step")],
                )
            ]
        else:
            steps = [
                _make_exp_step(
                    "step1", surface="task_list", transitions=[_make_transition(second_step[0])]
                ),
                _make_exp_step(second_step[0], surface=second_step[1]),
            ]
        appspec = _make_appspec(
            surfaces=[
                _make_surface("task_list", mode="list", entity_ref="Task"),
                _make_surface("task_create", mode="create", entity_ref="Task"),
            ],
            stories=[_make_story("S1", actor="admin", scope=["Task"])],
            experiences=[_make_experience("onboarding", steps=steps, start_step="step1")],
        )
        gaps = _analyze_experience_completeness(
            "admin", _make_persona("admin"), appspec, {"task_list", "task_create"}
        )
        assert {g.gap_type for g in gaps} == expected_gap_types


# =============================================================================
# Tests: Experience Reachability
# =============================================================================


def _onboarding_case(
    *,
    persona_id: str = "customer",
    default_workspace: str | None = "customer_dash",
    regions: list[Any] | None = None,
    story_scope: str = "Company",
    access: Any | None = None,
    extra_surfaces: list[Any] | None = None,
    two_steps: bool = False,
) -> tuple[SimpleNamespace, SimpleNamespace, set[str]]:
    """Persona + appspec with one onboarding experience over Company surfaces."""
    surfaces = [
        _make_surface("onboard_welcome", mode="view", entity_ref="Company"),
        *(extra_surfaces or []),
    ]
    steps = [_make_exp_step("welcome", surface="onboard_welcome")]
    if two_steps:
        surfaces.append(_make_surface("onboard_details", mode="create", entity_ref="Company"))
        steps = [
            _make_exp_step(
                "welcome", surface="onboard_welcome", transitions=[_make_transition("details")]
            ),
            _make_exp_step("details", surface="onboard_details"),
        ]
    workspaces = (
        [_make_workspace(default_workspace, regions=regions or [])] if default_workspace else []
    )
    persona = _make_persona(persona_id, default_workspace=default_workspace)
    appspec = _make_appspec(
        entities=[_make_entity("Company")],
        surfaces=surfaces,
        personas=[persona],
        workspaces=workspaces,
        stories=[_make_story("S1", actor=persona_id, scope=[story_scope])],
        experiences=[
            _make_experience("client_onboarding", steps=steps, start_step="welcome", access=access)
        ],
    )
    return persona, appspec, {s.name for s in surfaces}


class TestExperienceReachability:
    @pytest.mark.parametrize(
        ("kwargs", "expected_gaps"),
        [
            pytest.param(
                {"regions": [_make_region("onboarding", source="Company")], "two_steps": True},
                0,
                id="start-surface-in-workspace",
            ),
            pytest.param(
                {"persona_id": "viewer", "default_workspace": "viewer_dash", "story_scope": "Task"},
                0,
                id="other-persona-experience-ignored",
            ),
            pytest.param(
                {"access": SimpleNamespace(allow_personas=["customer"], deny_personas=[])},
                0,
                id="access-allows-persona",
            ),
            pytest.param(
                {"access": SimpleNamespace(allow_personas=[], deny_personas=[])},
                0,
                id="access-empty-allow-no-deny",
            ),
            pytest.param(
                {"access": SimpleNamespace(allow_personas=[], deny_personas=["customer"])},
                1,
                id="access-denies-persona",
            ),
            pytest.param(
                {"access": SimpleNamespace(allow_personas=["admin"], deny_personas=[])},
                1,
                id="access-allows-other-persona",
            ),
        ],
    )
    def test_gap_count(self, kwargs: dict[str, Any], expected_gaps: int) -> None:
        persona, appspec, accessible = _onboarding_case(**kwargs)
        gaps = _analyze_experience_reachability(persona.id, persona, appspec, accessible)
        assert len(gaps) == expected_gaps

    def test_unreachable_experience_flagged_high(self) -> None:
        """No workspace entry point -> HIGH gap with refs to experience, workspace, surface."""
        persona, appspec, accessible = _onboarding_case(
            # Only references Notification, NOT Company
            regions=[_make_region("notifications", source="Notification")],
            extra_surfaces=[_make_surface("notif_list", mode="list", entity_ref="Notification")],
            two_steps=True,
        )
        gaps = _analyze_experience_reachability("customer", persona, appspec, accessible)
        assert len(gaps) == 1
        assert gaps[0].gap_type == "unreachable_experience"
        assert gaps[0].severity == "high"
        assert gaps[0].experience_name == "client_onboarding"
        assert "customer_dash" in gaps[0].description
        assert "2 steps" in gaps[0].description
        assert "experience:client_onboarding" in gaps[0].related_artefacts
        assert "workspace:customer_dash" in gaps[0].related_artefacts
        assert "surface:onboard_welcome" in gaps[0].related_artefacts

    def test_no_workspace_reports_none(self) -> None:
        """Persona with no default_workspace -> workspace shown as 'none'."""
        persona, appspec, accessible = _onboarding_case(default_workspace=None)
        gaps = _analyze_experience_reachability("customer", persona, appspec, accessible)
        assert len(gaps) == 1
        assert "'none'" in gaps[0].description

    def test_multiple_unreachable_experiences(self) -> None:
        """Each unreachable experience produces its own gap (not aggregated)."""
        persona, appspec, _ = _onboarding_case(
            extra_surfaces=[_make_surface("kyc_start", mode="view", entity_ref="Company")]
        )
        appspec.experiences.append(
            _make_experience(
                "kyc_verification",
                steps=[_make_exp_step("start", surface="kyc_start")],
                start_step="start",
            )
        )
        accessible = {"onboard_welcome", "kyc_start"}
        gaps = _analyze_experience_reachability("customer", persona, appspec, accessible)
        assert len(gaps) == 2
        assert {g.experience_name for g in gaps} == {"client_onboarding", "kyc_verification"}

    def test_observation_conversion(self) -> None:
        """unreachable_experience gaps convert to navigation_gap Observations."""
        _, appspec, _ = _onboarding_case()
        report = run_headless_discovery(appspec)
        reachability_obs = [
            o
            for o in report.to_observations()
            if o.metadata.get("gap_type") == "unreachable_experience"
        ]
        assert len(reachability_obs) == 1
        assert reachability_obs[0].category == "navigation_gap"
        assert reachability_obs[0].severity == "high"


# =============================================================================
# Tests: Orphan Surface Detection
# =============================================================================


class TestOrphanSurfaceDetection:
    @pytest.mark.parametrize(
        ("surface", "workspaces", "experiences"),
        [
            pytest.param(
                _make_surface("task_view", mode="view", entity_ref="Task"),
                [_make_workspace("main", regions=[_make_region("sidebar", source="Task")])],
                [],
                id="referenced-by-workspace-region",
            ),
            pytest.param(
                _make_surface("task_list", mode="list", entity_ref="Task"),
                [],
                [],
                id="list-surface-self-standing",
            ),
            pytest.param(
                _make_surface("task_view", mode="view", entity_ref="Task"),
                [],
                [
                    _make_experience(
                        "onboarding",
                        steps=[_make_exp_step("step1", surface="task_view")],
                        start_step="step1",
                    )
                ],
                id="referenced-by-experience-step",
            ),
        ],
    )
    def test_not_orphaned(
        self, surface: Any, workspaces: list[Any], experiences: list[Any]
    ) -> None:
        appspec = _make_appspec(surfaces=[surface], workspaces=workspaces, experiences=experiences)
        gaps = _analyze_orphan_surfaces("admin", _make_persona("admin"), appspec, {surface.name})
        assert gaps == []

    def test_surface_not_referenced_anywhere(self) -> None:
        """Surface with no workspace region, experience, or process reference is orphaned."""
        appspec = _make_appspec(
            surfaces=[_make_surface("task_view", mode="view", entity_ref="Task")]
        )
        gaps = _analyze_orphan_surfaces("admin", _make_persona("admin"), appspec, {"task_view"})
        assert len(gaps) == 1
        assert gaps[0].gap_type == "orphan_surfaces"
        assert "task_view" in gaps[0].description

    def test_aggregated_into_single_gap(self) -> None:
        """Multiple orphan surfaces produce exactly one aggregated gap."""
        appspec = _make_appspec(
            surfaces=[
                _make_surface("task_view", mode="view", entity_ref="Task"),
                _make_surface("task_edit", mode="edit", entity_ref="Task"),
                _make_surface("task_create", mode="create", entity_ref="Task"),
            ],
        )
        accessible = {"task_view", "task_edit", "task_create"}
        gaps = _analyze_orphan_surfaces("admin", _make_persona("admin"), appspec, accessible)
        assert len(gaps) == 1
        assert gaps[0].gap_type == "orphan_surfaces"
        assert "3/" in gaps[0].description
        assert len(gaps[0].related_artefacts) == 3


# =============================================================================
# Tests: Cross-Entity Gaps
# =============================================================================


class TestCrossEntityGaps:
    @pytest.mark.parametrize(
        ("workspaces", "expect_gap"),
        [
            pytest.param(
                [
                    _make_workspace(
                        "main",
                        regions=[
                            _make_region("tasks", source="Task"),
                            _make_region("users", source="User"),
                        ],
                    )
                ],
                False,
                id="same-workspace",
            ),
            pytest.param(
                [
                    _make_workspace("ws1", regions=[_make_region("r1", source="Task")]),
                    _make_workspace("ws2", regions=[_make_region("r2", source="User")]),
                ],
                True,
                id="no-navigation-path",
            ),
            pytest.param(
                [
                    _make_workspace(
                        "main",
                        nav_groups=[
                            SimpleNamespace(
                                label="Main",
                                items=[
                                    SimpleNamespace(entity="Task"),
                                    SimpleNamespace(entity="User"),
                                ],
                            )
                        ],
                    )
                ],
                False,
                id="same-nav-group-477",
            ),
        ],
    )
    def test_cross_entity_gap(self, workspaces: list[Any], expect_gap: bool) -> None:
        appspec = _make_appspec(
            surfaces=[
                _make_surface("task_list", mode="list", entity_ref="Task"),
                _make_surface("user_list", mode="list", entity_ref="User"),
            ],
            workspaces=workspaces,
            stories=[_make_story("S1", actor="admin", scope=["Task", "User"])],
        )
        gaps = _analyze_cross_entity_gaps(
            "admin", _make_persona("admin"), appspec, {"task_list", "user_list"}
        )
        if expect_gap:
            assert len(gaps) >= 1
            assert gaps[0].gap_type == "cross_entity_gap"
        else:
            assert gaps == []


# =============================================================================
# Tests: Persona Filtering
# =============================================================================


def _main_workspace() -> SimpleNamespace:
    return _make_workspace("main", regions=[_make_region("sidebar")])


class TestPersonaFiltering:
    def test_no_stories_no_workspace_skipped(self) -> None:
        """Personas with no stories AND no default_workspace are skipped."""
        appspec = _make_appspec(
            personas=[
                _make_persona("test_user"),  # no default_workspace, no stories
                _make_persona("admin", default_workspace="main"),
            ],
            workspaces=[_main_workspace()],
        )
        report = run_headless_discovery(appspec)
        assert len(report.persona_reports) == 1
        assert report.persona_reports[0].persona_id == "admin"
        assert "test_user" in report.skipped_personas

    @pytest.mark.parametrize(
        "appspec",
        [
            pytest.param(
                _make_appspec(
                    personas=[_make_persona("viewer", default_workspace="main")],
                    workspaces=[_main_workspace()],
                ),
                id="workspace-but-no-stories",
            ),
            pytest.param(
                _make_appspec(
                    personas=[_make_persona("viewer")],
                    stories=[_make_story("S1", actor="viewer", scope=["Task"])],
                ),
                id="stories-but-no-workspace",
            ),
        ],
    )
    def test_partially_configured_persona_not_skipped(self, appspec: SimpleNamespace) -> None:
        report = run_headless_discovery(appspec)
        assert len(report.persona_reports) == 1
        assert len(report.skipped_personas) == 0

    def test_skipped_personas_in_summary(self) -> None:
        """Skipped personas appear in the markdown summary."""
        appspec = _make_appspec(
            personas=[
                _make_persona("test_user1"),
                _make_persona("test_user2"),
                _make_persona("admin", default_workspace="main"),
            ],
            workspaces=[_main_workspace()],
        )
        summary = run_headless_discovery(appspec).to_summary()
        assert "Skipped 2 persona(s)" in summary
        assert "test_user1" in summary


# =============================================================================
# Tests: run_headless_discovery (integration)
# =============================================================================


def _task_story_appspec(default_workspace: str, workspaces: list[Any]) -> SimpleNamespace:
    return _make_appspec(
        entities=[_make_entity("Task")],
        personas=[_make_persona("admin", default_workspace=default_workspace)],
        workspaces=workspaces,
        surfaces=[],
        stories=[_make_story("S1", actor="admin", title="Create task", scope=["Task"])],
    )


class TestRunHeadlessDiscovery:
    def test_report_observations_json_and_summary(self) -> None:
        report = run_headless_discovery(_task_story_appspec("main", [_main_workspace()]))
        assert len(report.persona_reports) == 1
        observations = report.to_observations()
        assert len(observations) > 0
        # All observations should have headless metadata
        for obs in observations:
            assert obs.metadata.get("headless") is True
        result = report.to_json()
        assert "persona_reports" in result
        assert "skipped_personas" in result
        assert len(result["persona_reports"]) == 1
        assert result["persona_reports"][0]["persona_id"] == "admin"
        summary = report.to_summary()
        assert "Headless Discovery Report" in summary
        assert "admin" in summary

    def test_persona_ids_filter_works(self) -> None:
        appspec = _make_appspec(
            personas=[
                _make_persona("admin", default_workspace="main"),
                _make_persona("viewer", default_workspace="main"),
            ],
            workspaces=[_main_workspace()],
        )
        report = run_headless_discovery(appspec, persona_ids=["admin"])
        assert len(report.persona_reports) == 1
        assert report.persona_reports[0].persona_id == "admin"

    def test_includes_entity_and_workflow_analysis(self) -> None:
        appspec = _make_appspec(
            entities=[_make_entity("Task")],
            personas=[_make_persona("admin", default_workspace="main")],
            workspaces=[_main_workspace()],
        )
        report = run_headless_discovery(appspec)
        assert report.entity_report is not None
        assert report.workflow_report is not None

    def test_default_workspace_in_observations(self) -> None:
        """Observations include default_workspace in metadata for emitter use."""
        # missing workspace -> will produce gap
        report = run_headless_discovery(_task_story_appspec("admin_dashboard", []))
        observations = report.to_observations()
        assert len(observations) > 0
        for obs in observations:
            assert obs.metadata.get("default_workspace") == "admin_dashboard"


# =============================================================================
# Pass 9: Navigation Scope Audit
# =============================================================================
def _make_entity_with_access(
    name: str,
    permissions: list[Any] | None = None,
) -> SimpleNamespace:
    """Entity with access control spec for policy-based nav scope tests."""
    access = None
    if permissions:
        access = SimpleNamespace(
            visibility=[],
            permissions=permissions,
        )
    return SimpleNamespace(
        name=name,
        title=name,
        fields=[],
        state_machine=None,
        access=access,
    )


def _make_permission(
    operation: str = "read",
    personas: list[str] | None = None,
    effect: str = "PERMIT",
) -> SimpleNamespace:
    return SimpleNamespace(
        operation=operation,
        personas=personas or [],
        effect=effect,
        require_auth=True,
        condition=None,
    )


def _make_surface_with_ux(
    name: str,
    entity_ref: str | None = None,
    mode: str = "list",
    persona_variants: list[Any] | None = None,
    access: Any | None = None,
) -> SimpleNamespace:
    """Surface with UX block containing persona_variants."""
    ux = None
    if persona_variants:
        ux = SimpleNamespace(persona_variants=persona_variants)
    return SimpleNamespace(
        name=name,
        title=name,
        mode=mode,
        entity_ref=entity_ref,
        entity=entity_ref,
        sections=[],
        actions=[],
        access=access,
        ux=ux,
    )


def _make_persona_variant(persona: str) -> SimpleNamespace:
    return SimpleNamespace(persona=persona)


def _nav_case(
    *,
    persona_id: str = "customer",
    entities: list[Any],
    surfaces: list[Any],
    workspaces: list[Any],
    default_workspace: str | None = "main",
    story_scope: list[str] | None = None,
) -> tuple[SimpleNamespace, SimpleNamespace, set[str]]:
    persona = _make_persona(persona_id, default_workspace=default_workspace)
    appspec = _make_appspec(
        entities=entities,
        surfaces=surfaces,
        personas=[persona],
        workspaces=workspaces,
        stories=[_make_story("S1", actor=persona_id, scope=story_scope)] if story_scope else [],
    )
    return persona, appspec, {s.name for s in surfaces}


def _policy_nav_case(entity_name: str) -> tuple[SimpleNamespace, SimpleNamespace, set[str]]:
    perm = _make_permission(operation="read", personas=["customer"], effect="PERMIT")
    return _nav_case(
        entities=[
            _make_entity("Task"),
            _make_entity_with_access(entity_name, permissions=[perm]),
        ],
        surfaces=[_make_surface("task_list", entity_ref="Task")],
        workspaces=[_make_workspace("main", regions=[_make_region("r1", source="Task")])],
        story_scope=["Task"],
    )


def _nav_not_over_exposed_cases() -> list[Any]:
    """Cases (kwargs for _nav_case) where no nav_over_exposed gap may be raised."""
    main_task = _make_workspace("main", regions=[_make_region("r1", source="Task")])
    return [
        pytest.param(
            {
                "persona_id": "admin",
                "entities": [_make_entity("Task"), _make_entity("Note")],
                "surfaces": [
                    _make_surface("task_list", entity_ref="Task"),
                    _make_surface("note_list", entity_ref="Note"),
                ],
                "workspaces": [
                    _make_workspace(
                        "main",
                        regions=[
                            _make_region("r1", source="Task"),
                            _make_region("r2", source="Note"),
                        ],
                    )
                ],
                "story_scope": ["Task"],
            },
            id="workspace-covers-all",
        ),
        pytest.param(
            {
                "entities": [
                    _make_entity("Task"),
                    _make_entity("AdminConfig"),
                    _make_entity("AuditLog"),
                ],
                "surfaces": [_make_surface("task_list", entity_ref="Task")],
                "workspaces": [main_task],
                "story_scope": ["Task"],
            },
            id="out-of-workspace-entities-left-to-route-access",
        ),
        pytest.param(
            {
                "persona_id": "user",
                "entities": [_make_entity(f"Entity{i}") for i in range(15)],
                "surfaces": [_make_surface("s0", entity_ref="Entity0")],
                "workspaces": [
                    _make_workspace("main", regions=[_make_region("r0", source="Entity0")])
                ],
                "story_scope": ["Entity0"],
            },
            id="many-out-of-workspace-entities",
        ),
        pytest.param(
            {
                "entities": [_make_entity("Task"), _make_entity("AdminPanel")],
                "surfaces": [
                    _make_surface("task_list", entity_ref="Task"),
                    _make_surface("admin_list", entity_ref="AdminPanel"),
                ],
                "workspaces": [
                    _make_workspace(
                        "admin_dash",
                        regions=[_make_region("r1", source="AdminPanel")],
                        access=_make_access(deny_personas=["customer"]),
                    ),
                    _make_workspace("customer_dash", regions=[_make_region("r2", source="Task")]),
                ],
                "default_workspace": "customer_dash",
                "story_scope": ["Task"],
            },
            id="workspace-access-denial-excludes-entities",
        ),
        pytest.param(
            {
                "persona_id": "analyst",
                "entities": [_make_entity("Task"), _make_entity("Report")],
                "surfaces": [
                    _make_surface("task_list", entity_ref="Task"),
                    _make_surface_with_ux(
                        "report_view",
                        entity_ref="Report",
                        persona_variants=[_make_persona_variant("analyst")],
                    ),
                ],
                "workspaces": [main_task],
                "story_scope": ["Task"],
            },
            id="persona-variant-reaches-entity",
        ),
        pytest.param(
            {
                "persona_id": "ghost",
                "entities": [_make_entity("Task")],
                "surfaces": [],
                "workspaces": [],
                "default_workspace": None,
            },
            id="no-workspace-no-stories",
        ),
    ]


class TestNavigationScope:
    """Tests for _analyze_navigation_scope (Pass 9)."""

    @pytest.mark.parametrize("case", _nav_not_over_exposed_cases())
    def test_not_over_exposed(self, case: dict[str, Any]) -> None:
        """Over-exposure is scoped to workspace entities; everything else is no gap."""
        persona, appspec, accessible = _nav_case(**case)
        gaps = _analyze_navigation_scope(persona.id, persona, appspec, accessible)
        assert [g for g in gaps if g.gap_type == "nav_over_exposed"] == []

    def test_policy_access_prevents_over_exposure(self) -> None:
        """Entity with policy PERMIT for persona is not flagged as over-exposed."""
        persona, appspec, accessible = _policy_nav_case("Document")
        gaps = _analyze_navigation_scope("customer", persona, appspec, accessible)
        assert [g for g in gaps if g.gap_type == "nav_over_exposed"] == []

    def test_under_exposure_flagged(self) -> None:
        """Entity with policy access but not in workspace is under-exposed."""
        persona, appspec, accessible = _policy_nav_case("Notification")
        gaps = _analyze_navigation_scope("customer", persona, appspec, accessible)
        under = [g for g in gaps if g.gap_type == "nav_under_exposed"]
        assert len(under) == 1
        assert "Notification" in under[0].description
        assert under[0].severity == "medium"

    def test_observation_conversion(self) -> None:
        """Nav scope gaps convert to the correct Observation categories."""
        over_gap = PersonaJourneyGap(
            persona_id="customer",
            gap_type="nav_over_exposed",
            severity="high",
            description="test over",
        )
        under_gap = PersonaJourneyGap(
            persona_id="customer",
            gap_type="nav_under_exposed",
            severity="medium",
            description="test under",
        )
        assert _gap_to_observation(over_gap).category == "access_gap"
        assert _gap_to_observation(under_gap).category == "navigation_gap"
