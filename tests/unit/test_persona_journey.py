"""Tests for the headless persona journey analysis."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

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
) -> SimpleNamespace:
    return SimpleNamespace(name=name, regions=regions or [], access=access)


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
        actor=actor,
        title=title or story_id,
        description="",
        scope=scope or [],
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
) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        title=title or name,
        steps=steps or [],
        start_step=start_step,
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
        from dazzle.agent.missions.persona_journey import _analyze_workspace_reachability

        persona = _make_persona("admin")
        appspec = _make_appspec(personas=[persona])
        gaps = _analyze_workspace_reachability("admin", persona, appspec)
        assert len(gaps) == 1
        assert gaps[0].gap_type == "workspace_unreachable"
        assert gaps[0].severity == "medium"

    def test_workspace_does_not_exist(self) -> None:
        from dazzle.agent.missions.persona_journey import _analyze_workspace_reachability

        persona = _make_persona("admin", default_workspace="missing_ws")
        appspec = _make_appspec(personas=[persona], workspaces=[])
        gaps = _analyze_workspace_reachability("admin", persona, appspec)
        assert len(gaps) == 1
        assert gaps[0].gap_type == "workspace_unreachable"
        assert gaps[0].severity == "critical"

    def test_workspace_access_denied(self) -> None:
        from dazzle.agent.missions.persona_journey import _analyze_workspace_reachability

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
        from dazzle.agent.missions.persona_journey import _analyze_workspace_reachability

        persona = _make_persona("admin", default_workspace="main_ws")
        ws = _make_workspace("main_ws", regions=[_make_region("sidebar")])
        appspec = _make_appspec(personas=[persona], workspaces=[ws])
        gaps = _analyze_workspace_reachability("admin", persona, appspec)
        assert len(gaps) == 0


# =============================================================================
# Tests: Surface Access
# =============================================================================


class TestSurfaceAccess:
    def test_no_access_control_is_accessible(self) -> None:
        from dazzle.agent.missions.persona_journey import _compute_accessible_surfaces

        appspec = _make_appspec(
            surfaces=[_make_surface("task_list", entity_ref="Task")],
        )
        result = _compute_accessible_surfaces("admin", appspec)
        assert "task_list" in result

    def test_allow_list_includes_persona(self) -> None:
        from dazzle.agent.missions.persona_journey import _compute_accessible_surfaces

        appspec = _make_appspec(
            surfaces=[
                _make_surface(
                    "task_list",
                    entity_ref="Task",
                    access=_make_access(allow_personas=["admin"]),
                ),
            ],
        )
        result = _compute_accessible_surfaces("admin", appspec)
        assert "task_list" in result

    def test_allow_list_excludes_persona(self) -> None:
        from dazzle.agent.missions.persona_journey import _compute_accessible_surfaces

        appspec = _make_appspec(
            surfaces=[
                _make_surface(
                    "task_list",
                    entity_ref="Task",
                    access=_make_access(allow_personas=["admin"]),
                ),
            ],
        )
        result = _compute_accessible_surfaces("viewer", appspec)
        assert "task_list" not in result

    def test_story_entity_surface_blocked(self) -> None:
        from dazzle.agent.missions.persona_journey import _analyze_surface_access

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
        accessible: set[str] = set()  # None accessible
        gaps = _analyze_surface_access("viewer", persona, appspec, accessible)
        assert len(gaps) >= 1
        assert gaps[0].gap_type == "surface_inaccessible"


# =============================================================================
# Tests: Story Surface Coverage
# =============================================================================


class TestStorySurfaceCoverage:
    def test_entities_have_matching_surfaces(self) -> None:
        from dazzle.agent.missions.persona_journey import _analyze_story_surface_coverage

        persona = _make_persona("admin")
        appspec = _make_appspec(
            surfaces=[
                _make_surface("task_list", mode="list", entity_ref="Task"),
                _make_surface("task_create", mode="create", entity_ref="Task"),
            ],
            stories=[
                _make_story("S1", actor="admin", title="Create a new task", scope=["Task"]),
            ],
        )
        accessible = {"task_list", "task_create"}
        gaps = _analyze_story_surface_coverage("admin", persona, appspec, accessible)
        assert len(gaps) == 0

    def test_missing_create_surface_for_entity(self) -> None:
        from dazzle.agent.missions.persona_journey import _analyze_story_surface_coverage

        persona = _make_persona("admin")
        appspec = _make_appspec(
            surfaces=[
                _make_surface("task_list", mode="list", entity_ref="Task"),
            ],
            stories=[
                _make_story("S1", actor="admin", title="Create a new task", scope=["Task"]),
            ],
        )
        accessible = {"task_list"}
        gaps = _analyze_story_surface_coverage("admin", persona, appspec, accessible)
        assert len(gaps) >= 1
        assert gaps[0].gap_type == "story_no_surface"

    def test_non_actor_persona_stories_skipped(self) -> None:
        from dazzle.agent.missions.persona_journey import _analyze_story_surface_coverage

        persona = _make_persona("viewer")
        appspec = _make_appspec(
            surfaces=[],
            stories=[
                _make_story("S1", actor="admin", title="Create task", scope=["Task"]),
            ],
        )
        gaps = _analyze_story_surface_coverage("viewer", persona, appspec, set())
        assert len(gaps) == 0


# =============================================================================
# Tests: Process Surface Wiring
# =============================================================================


class TestProcessSurfaceWiring:
    def test_human_task_surface_exists_and_accessible(self) -> None:
        from dazzle.agent.missions.persona_journey import _analyze_process_surface_wiring

        persona = _make_persona("admin")
        appspec = _make_appspec(
            surfaces=[_make_surface("task_form", mode="create", entity_ref="Task")],
            stories=[_make_story("S1", actor="admin", scope=["Task"])],
            processes=[
                _make_process(
                    "create_task",
                    steps=[_make_human_task_step("fill_form", "task_form")],
                    implements=["S1"],
                ),
            ],
        )
        accessible = {"task_form"}
        gaps = _analyze_process_surface_wiring("admin", persona, appspec, accessible)
        assert len(gaps) == 0

    def test_human_task_surface_missing(self) -> None:
        from dazzle.agent.missions.persona_journey import _analyze_process_surface_wiring

        persona = _make_persona("admin")
        appspec = _make_appspec(
            surfaces=[],
            stories=[_make_story("S1", actor="admin", scope=["Task"])],
            processes=[
                _make_process(
                    "create_task",
                    steps=[_make_human_task_step("fill_form", "missing_form")],
                    implements=["S1"],
                ),
            ],
        )
        gaps = _analyze_process_surface_wiring("admin", persona, appspec, set())
        assert len(gaps) >= 1
        assert gaps[0].gap_type == "process_step_no_surface"
        assert gaps[0].severity == "critical"

    def test_human_task_surface_inaccessible(self) -> None:
        from dazzle.agent.missions.persona_journey import _analyze_process_surface_wiring

        persona = _make_persona("viewer")
        appspec = _make_appspec(
            surfaces=[
                _make_surface(
                    "task_form",
                    mode="create",
                    entity_ref="Task",
                    access=_make_access(allow_personas=["admin"]),
                ),
            ],
            stories=[_make_story("S1", actor="viewer", scope=["Task"])],
            processes=[
                _make_process(
                    "create_task",
                    steps=[_make_human_task_step("fill_form", "task_form")],
                    implements=["S1"],
                ),
            ],
        )
        accessible: set[str] = set()  # viewer can't access task_form
        gaps = _analyze_process_surface_wiring("viewer", persona, appspec, accessible)
        assert len(gaps) >= 1
        assert gaps[0].severity == "high"


# =============================================================================
# Tests: Experience Completeness
# =============================================================================


class TestExperienceCompleteness:
    def test_valid_flow(self) -> None:
        from dazzle.agent.missions.persona_journey import _analyze_experience_completeness

        persona = _make_persona("admin")
        appspec = _make_appspec(
            surfaces=[
                _make_surface("task_list", mode="list", entity_ref="Task"),
                _make_surface("task_create", mode="create", entity_ref="Task"),
            ],
            stories=[_make_story("S1", actor="admin", scope=["Task"])],
            experiences=[
                _make_experience(
                    "onboarding",
                    steps=[
                        _make_exp_step(
                            "step1", surface="task_list", transitions=[_make_transition("step2")]
                        ),
                        _make_exp_step("step2", surface="task_create"),
                    ],
                    start_step="step1",
                ),
            ],
        )
        accessible = {"task_list", "task_create"}
        gaps = _analyze_experience_completeness("admin", persona, appspec, accessible)
        assert len(gaps) == 0

    def test_missing_surface_reference(self) -> None:
        from dazzle.agent.missions.persona_journey import _analyze_experience_completeness

        persona = _make_persona("admin")
        appspec = _make_appspec(
            surfaces=[
                _make_surface("task_list", mode="list", entity_ref="Task"),
            ],
            stories=[_make_story("S1", actor="admin", scope=["Task"])],
            experiences=[
                _make_experience(
                    "onboarding",
                    steps=[
                        _make_exp_step(
                            "step1", surface="task_list", transitions=[_make_transition("step2")]
                        ),
                        _make_exp_step("step2", surface="nonexistent_surface"),
                    ],
                    start_step="step1",
                ),
            ],
        )
        accessible = {"task_list"}
        gaps = _analyze_experience_completeness("admin", persona, appspec, accessible)
        assert any(g.gap_type == "experience_broken_step" for g in gaps)

    def test_broken_transition(self) -> None:
        from dazzle.agent.missions.persona_journey import _analyze_experience_completeness

        persona = _make_persona("admin")
        appspec = _make_appspec(
            surfaces=[
                _make_surface("task_list", mode="list", entity_ref="Task"),
            ],
            stories=[_make_story("S1", actor="admin", scope=["Task"])],
            experiences=[
                _make_experience(
                    "onboarding",
                    steps=[
                        _make_exp_step(
                            "step1",
                            surface="task_list",
                            transitions=[_make_transition("nonexistent_step")],
                        ),
                    ],
                    start_step="step1",
                ),
            ],
        )
        accessible = {"task_list"}
        gaps = _analyze_experience_completeness("admin", persona, appspec, accessible)
        assert any(g.gap_type == "experience_dangling_transition" for g in gaps)


# =============================================================================
# Tests: Orphan Surface Detection
# =============================================================================


class TestOrphanSurfaceDetection:
    def test_surface_referenced_by_workspace_region(self) -> None:
        """Surface whose entity matches region.source is NOT orphaned."""
        from dazzle.agent.missions.persona_journey import _analyze_orphan_surfaces

        persona = _make_persona("admin")
        appspec = _make_appspec(
            surfaces=[
                _make_surface("task_view", mode="view", entity_ref="Task"),
            ],
            workspaces=[
                _make_workspace("main", regions=[_make_region("sidebar", source="Task")]),
            ],
        )
        accessible = {"task_view"}
        gaps = _analyze_orphan_surfaces("admin", persona, appspec, accessible)
        assert len(gaps) == 0

    def test_surface_not_referenced_anywhere(self) -> None:
        """Surface with no workspace region, experience, or process reference is orphaned."""
        from dazzle.agent.missions.persona_journey import _analyze_orphan_surfaces

        persona = _make_persona("admin")
        appspec = _make_appspec(
            surfaces=[
                _make_surface("task_view", mode="view", entity_ref="Task"),
            ],
            workspaces=[],
        )
        accessible = {"task_view"}
        gaps = _analyze_orphan_surfaces("admin", persona, appspec, accessible)
        assert len(gaps) == 1
        assert gaps[0].gap_type == "orphan_surfaces"
        assert "task_view" in gaps[0].description

    def test_list_surface_not_flagged(self) -> None:
        """List surfaces are self-standing index pages — not orphaned."""
        from dazzle.agent.missions.persona_journey import _analyze_orphan_surfaces

        persona = _make_persona("admin")
        appspec = _make_appspec(
            surfaces=[
                _make_surface("task_list", mode="list", entity_ref="Task"),
            ],
            workspaces=[],
        )
        accessible = {"task_list"}
        gaps = _analyze_orphan_surfaces("admin", persona, appspec, accessible)
        assert len(gaps) == 0

    def test_aggregated_into_single_gap(self) -> None:
        """Multiple orphan surfaces produce exactly one aggregated gap."""
        from dazzle.agent.missions.persona_journey import _analyze_orphan_surfaces

        persona = _make_persona("admin")
        appspec = _make_appspec(
            surfaces=[
                _make_surface("task_view", mode="view", entity_ref="Task"),
                _make_surface("task_edit", mode="edit", entity_ref="Task"),
                _make_surface("task_create", mode="create", entity_ref="Task"),
            ],
            workspaces=[],
        )
        accessible = {"task_view", "task_edit", "task_create"}
        gaps = _analyze_orphan_surfaces("admin", persona, appspec, accessible)
        assert len(gaps) == 1
        assert gaps[0].gap_type == "orphan_surfaces"
        assert "3/" in gaps[0].description
        assert len(gaps[0].related_artefacts) == 3

    def test_experience_referenced_surface_not_orphaned(self) -> None:
        """Surface referenced by an experience step is not orphaned."""
        from dazzle.agent.missions.persona_journey import _analyze_orphan_surfaces

        persona = _make_persona("admin")
        appspec = _make_appspec(
            surfaces=[
                _make_surface("task_view", mode="view", entity_ref="Task"),
            ],
            experiences=[
                _make_experience(
                    "onboarding",
                    steps=[_make_exp_step("step1", surface="task_view")],
                    start_step="step1",
                ),
            ],
        )
        accessible = {"task_view"}
        gaps = _analyze_orphan_surfaces("admin", persona, appspec, accessible)
        assert len(gaps) == 0


# =============================================================================
# Tests: Cross-Entity Gaps
# =============================================================================


class TestCrossEntityGaps:
    def test_two_entities_same_workspace(self) -> None:
        from dazzle.agent.missions.persona_journey import _analyze_cross_entity_gaps

        persona = _make_persona("admin")
        appspec = _make_appspec(
            surfaces=[
                _make_surface("task_list", mode="list", entity_ref="Task"),
                _make_surface("user_list", mode="list", entity_ref="User"),
            ],
            workspaces=[
                _make_workspace(
                    "main",
                    regions=[
                        _make_region("tasks", source="Task"),
                        _make_region("users", source="User"),
                    ],
                ),
            ],
            stories=[
                _make_story("S1", actor="admin", scope=["Task", "User"]),
            ],
        )
        accessible = {"task_list", "user_list"}
        gaps = _analyze_cross_entity_gaps("admin", persona, appspec, accessible)
        assert len(gaps) == 0

    def test_two_entities_no_navigation_path(self) -> None:
        from dazzle.agent.missions.persona_journey import _analyze_cross_entity_gaps

        persona = _make_persona("admin")
        appspec = _make_appspec(
            surfaces=[
                _make_surface("task_list", mode="list", entity_ref="Task"),
                _make_surface("user_list", mode="list", entity_ref="User"),
            ],
            workspaces=[
                _make_workspace("ws1", regions=[_make_region("r1", source="Task")]),
                _make_workspace("ws2", regions=[_make_region("r2", source="User")]),
            ],
            stories=[
                _make_story("S1", actor="admin", scope=["Task", "User"]),
            ],
        )
        accessible = {"task_list", "user_list"}
        gaps = _analyze_cross_entity_gaps("admin", persona, appspec, accessible)
        assert len(gaps) >= 1
        assert gaps[0].gap_type == "cross_entity_gap"


# =============================================================================
# Tests: Persona Filtering
# =============================================================================


class TestPersonaFiltering:
    def test_no_stories_no_workspace_skipped(self) -> None:
        """Personas with no stories AND no default_workspace are skipped."""
        from dazzle.agent.missions.persona_journey import run_headless_discovery

        appspec = _make_appspec(
            personas=[
                _make_persona("test_user"),  # no default_workspace, no stories
                _make_persona("admin", default_workspace="main"),
            ],
            workspaces=[_make_workspace("main", regions=[_make_region("sidebar")])],
        )
        report = run_headless_discovery(appspec)
        assert len(report.persona_reports) == 1
        assert report.persona_reports[0].persona_id == "admin"
        assert "test_user" in report.skipped_personas

    def test_no_stories_but_has_workspace_not_skipped(self) -> None:
        """Personas with a default_workspace but no stories are still analyzed."""
        from dazzle.agent.missions.persona_journey import run_headless_discovery

        appspec = _make_appspec(
            personas=[_make_persona("viewer", default_workspace="main")],
            workspaces=[_make_workspace("main", regions=[_make_region("sidebar")])],
        )
        report = run_headless_discovery(appspec)
        assert len(report.persona_reports) == 1
        assert len(report.skipped_personas) == 0

    def test_has_stories_but_no_workspace_not_skipped(self) -> None:
        """Personas with stories but no default_workspace are still analyzed."""
        from dazzle.agent.missions.persona_journey import run_headless_discovery

        appspec = _make_appspec(
            personas=[_make_persona("admin")],
            stories=[_make_story("S1", actor="admin", scope=["Task"])],
        )
        report = run_headless_discovery(appspec)
        assert len(report.persona_reports) == 1
        assert len(report.skipped_personas) == 0

    def test_skipped_personas_in_summary(self) -> None:
        """Skipped personas appear in the markdown summary."""
        from dazzle.agent.missions.persona_journey import run_headless_discovery

        appspec = _make_appspec(
            personas=[
                _make_persona("test_user1"),
                _make_persona("test_user2"),
                _make_persona("admin", default_workspace="main"),
            ],
            workspaces=[_make_workspace("main", regions=[_make_region("sidebar")])],
        )
        report = run_headless_discovery(appspec)
        summary = report.to_summary()
        assert "Skipped 2 persona(s)" in summary
        assert "test_user1" in summary


# =============================================================================
# Tests: run_headless_discovery (integration)
# =============================================================================


class TestRunHeadlessDiscovery:
    def test_returns_report_with_observations(self) -> None:
        from dazzle.agent.missions.persona_journey import run_headless_discovery

        appspec = _make_appspec(
            entities=[_make_entity("Task")],
            personas=[_make_persona("admin", default_workspace="main")],
            workspaces=[_make_workspace("main", regions=[_make_region("sidebar")])],
            surfaces=[],
            stories=[_make_story("S1", actor="admin", title="Create task", scope=["Task"])],
        )
        report = run_headless_discovery(appspec)
        assert len(report.persona_reports) == 1
        observations = report.to_observations()
        assert len(observations) > 0
        # All observations should have headless metadata
        for obs in observations:
            assert obs.metadata.get("headless") is True

    def test_observations_compatible_with_compiler(self) -> None:
        from dazzle.agent.compiler import NarrativeCompiler
        from dazzle.agent.missions.persona_journey import run_headless_discovery

        appspec = _make_appspec(
            entities=[_make_entity("Task")],
            personas=[_make_persona("admin", default_workspace="main")],
            workspaces=[_make_workspace("main", regions=[_make_region("sidebar")])],
            surfaces=[],
            stories=[_make_story("S1", actor="admin", title="Create task", scope=["Task"])],
        )
        report = run_headless_discovery(appspec)
        observations = report.to_observations()
        assert len(observations) > 0

        compiler = NarrativeCompiler(persona="admin")
        proposals = compiler.compile(observations)
        # Should produce at least one proposal from the gaps
        assert len(proposals) >= 1

    def test_persona_ids_filter_works(self) -> None:
        from dazzle.agent.missions.persona_journey import run_headless_discovery

        appspec = _make_appspec(
            personas=[
                _make_persona("admin", default_workspace="main"),
                _make_persona("viewer", default_workspace="main"),
            ],
            workspaces=[_make_workspace("main", regions=[_make_region("sidebar")])],
        )
        report = run_headless_discovery(appspec, persona_ids=["admin"])
        assert len(report.persona_reports) == 1
        assert report.persona_reports[0].persona_id == "admin"

    def test_includes_entity_and_workflow_analysis(self) -> None:
        from dazzle.agent.missions.persona_journey import run_headless_discovery

        appspec = _make_appspec(
            entities=[_make_entity("Task")],
            personas=[_make_persona("admin", default_workspace="main")],
            workspaces=[_make_workspace("main", regions=[_make_region("sidebar")])],
        )
        report = run_headless_discovery(appspec)
        assert report.entity_report is not None
        assert report.workflow_report is not None

    def test_default_workspace_in_observations(self) -> None:
        """Observations include default_workspace in metadata for emitter use."""
        from dazzle.agent.missions.persona_journey import run_headless_discovery

        appspec = _make_appspec(
            entities=[_make_entity("Task")],
            personas=[_make_persona("admin", default_workspace="admin_dashboard")],
            workspaces=[],  # missing workspace → will produce gap
            stories=[_make_story("S1", actor="admin", title="Create task", scope=["Task"])],
        )
        report = run_headless_discovery(appspec)
        observations = report.to_observations()
        assert len(observations) > 0
        # All observations from this persona should have default_workspace
        for obs in observations:
            assert obs.metadata.get("default_workspace") == "admin_dashboard"

    def test_json_serialization(self) -> None:
        from dazzle.agent.missions.persona_journey import run_headless_discovery

        appspec = _make_appspec(
            entities=[_make_entity("Task")],
            personas=[_make_persona("admin", default_workspace="main")],
            workspaces=[_make_workspace("main", regions=[_make_region("sidebar")])],
            surfaces=[],
            stories=[_make_story("S1", actor="admin", title="Create task", scope=["Task"])],
        )
        report = run_headless_discovery(appspec)
        result = report.to_json()
        assert "persona_reports" in result
        assert "skipped_personas" in result
        assert len(result["persona_reports"]) == 1
        assert result["persona_reports"][0]["persona_id"] == "admin"

    def test_markdown_summary(self) -> None:
        from dazzle.agent.missions.persona_journey import run_headless_discovery

        appspec = _make_appspec(
            entities=[_make_entity("Task")],
            personas=[_make_persona("admin", default_workspace="main")],
            workspaces=[_make_workspace("main", regions=[_make_region("sidebar")])],
            surfaces=[],
            stories=[_make_story("S1", actor="admin", title="Create task", scope=["Task"])],
        )
        report = run_headless_discovery(appspec)
        summary = report.to_summary()
        assert "Headless Discovery Report" in summary
        assert "admin" in summary
