"""Tests for the narrative compiler."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from dazzle.agent.compiler import (
    NarrativeCompiler,
    Proposal,
    _check_adjacency,
    _collect_entities,
    _collect_locations,
    _collect_surfaces,
    _generate_narrative,
    _group_key,
    _group_observations,
    _ObservationGroup,
)
from dazzle.agent.transcript import Observation

# =============================================================================
# Fixtures
# =============================================================================


def _obs(
    category: str = "gap",
    severity: str = "medium",
    title: str = "Test gap",
    description: str = "A test gap",
    location: str = "/test",
    related_artefacts: list[str] | None = None,
) -> Observation:
    return Observation(
        category=category,
        severity=severity,
        title=title,
        description=description,
        location=location,
        related_artefacts=related_artefacts or [],
    )


# =============================================================================
# Tests: Grouping
# =============================================================================


class TestGroupKey:
    def test_uses_first_artefact(self) -> None:
        obs = _obs(category="missing_crud", related_artefacts=["entity:Task"])
        assert _group_key(obs) == "missing_crud:Task"

    def test_strips_prefix(self) -> None:
        obs = _obs(category="ux_issue", related_artefacts=["surface:task_list"])
        assert _group_key(obs) == "ux_issue:task_list"

    def test_falls_back_to_location(self) -> None:
        obs = _obs(category="navigation_gap", location="/tasks/123?tab=details")
        assert _group_key(obs) == "navigation_gap:tasks"

    def test_general_fallback(self) -> None:
        obs = _obs(category="gap", location="", related_artefacts=[])
        assert _group_key(obs) == "gap:general"


class TestGroupObservations:
    def test_groups_by_category_and_entity(self) -> None:
        observations = [
            _obs(category="missing_crud", related_artefacts=["entity:Task"], title="No delete"),
            _obs(
                category="missing_crud", related_artefacts=["entity:Task"], title="No bulk delete"
            ),
            _obs(
                category="missing_crud", related_artefacts=["entity:User"], title="No delete user"
            ),
        ]
        groups = _group_observations(observations)
        assert len(groups) == 2  # Task and User groups

    def test_filters_info_severity(self) -> None:
        observations = [
            _obs(severity="info", title="Page works fine"),
            _obs(severity="high", title="Missing field"),
        ]
        groups = _group_observations(observations)
        assert len(groups) == 1
        assert groups[0].observations[0].title == "Missing field"

    def test_empty_observations(self) -> None:
        assert _group_observations([]) == []


class TestObservationGroup:
    def test_max_severity(self) -> None:
        group = _ObservationGroup(
            key="test",
            category="gap",
            observations=[
                _obs(severity="low"),
                _obs(severity="critical"),
                _obs(severity="medium"),
            ],
        )
        assert group.max_severity == "critical"

    def test_priority_score(self) -> None:
        group = _ObservationGroup(
            key="test",
            category="gap",
            observations=[
                _obs(severity="high"),
                _obs(severity="high"),
            ],
        )
        # high=60 × 2 observations = 120
        assert group.priority_score == 120

    def test_single_observation(self) -> None:
        group = _ObservationGroup(
            key="test",
            category="gap",
            observations=[_obs(severity="medium")],
        )
        assert group.max_severity == "medium"
        assert group.priority_score == 30


# =============================================================================
# Tests: Narrative Generation
# =============================================================================


class TestGenerateNarrative:
    def test_missing_crud_narrative(self) -> None:
        group = _ObservationGroup(
            key="missing_crud:Task",
            category="missing_crud",
            observations=[
                _obs(
                    category="missing_crud",
                    title="No delete for Task",
                    description="Task entity has no delete surface",
                    location="/tasks",
                    related_artefacts=["entity:Task"],
                )
            ],
        )
        narrative = _generate_narrative(group, "admin")
        assert "admin" in narrative
        assert "Missing CRUD" in narrative
        assert "/tasks" in narrative

    def test_workflow_gap_narrative(self) -> None:
        group = _ObservationGroup(
            key="workflow_gap:Order",
            category="workflow_gap",
            observations=[_obs(category="workflow_gap", title="Missing approval step")],
        )
        narrative = _generate_narrative(group, "manager")
        assert "manager" in narrative
        assert "workflow" in narrative.lower()

    def test_multiple_observations_noted(self) -> None:
        group = _ObservationGroup(
            key="ux_issue:form",
            category="ux_issue",
            observations=[
                _obs(category="ux_issue", title="Missing validation"),
                _obs(category="ux_issue", title="No error messages"),
            ],
        )
        narrative = _generate_narrative(group)
        assert "2 related observations" in narrative

    def test_includes_entity_context(self) -> None:
        group = _ObservationGroup(
            key="missing_crud:Task",
            category="missing_crud",
            observations=[_obs(related_artefacts=["entity:Task", "surface:task_list"])],
        )
        narrative = _generate_narrative(group)
        assert "Task" in narrative


# =============================================================================
# Tests: Collection Helpers
# =============================================================================


class TestCollectHelpers:
    def test_collect_locations_dedupes(self) -> None:
        group = _ObservationGroup(
            key="test",
            category="gap",
            observations=[
                _obs(location="/tasks"),
                _obs(location="/tasks"),
                _obs(location="/users"),
            ],
        )
        locations = _collect_locations(group)
        assert locations == ["/tasks", "/users"]

    def test_collect_entities_strips_prefix(self) -> None:
        group = _ObservationGroup(
            key="test",
            category="gap",
            observations=[
                _obs(related_artefacts=["entity:Task", "surface:task_list"]),
            ],
        )
        entities = _collect_entities(group)
        assert "Task" in entities
        assert "task_list" in entities

    def test_collect_surfaces(self) -> None:
        group = _ObservationGroup(
            key="test",
            category="gap",
            observations=[
                _obs(related_artefacts=["entity:Task", "surface:task_list", "surface:task_form"]),
            ],
        )
        surfaces = _collect_surfaces(group)
        assert surfaces == ["task_list", "task_form"]


# =============================================================================
# Tests: Adjacency Validation
# =============================================================================


class TestCheckAdjacency:
    def test_no_kg_returns_true(self) -> None:
        group = _ObservationGroup(
            key="test",
            category="gap",
            observations=[_obs(related_artefacts=["entity:Task"])],
        )
        assert _check_adjacency(group, None) is True

    def test_no_entities_returns_true(self) -> None:
        group = _ObservationGroup(
            key="test",
            category="gap",
            observations=[_obs(related_artefacts=[])],
        )
        store = MagicMock()
        assert _check_adjacency(group, store) is True

    def test_entity_found_returns_true(self) -> None:
        group = _ObservationGroup(
            key="test",
            category="gap",
            observations=[_obs(related_artefacts=["entity:Task"])],
        )
        store = MagicMock()
        store.get_entity.side_effect = lambda x: (
            SimpleNamespace(id=x) if x == "entity:Task" else None
        )
        assert _check_adjacency(group, store) is True

    def test_entity_not_found_returns_false(self) -> None:
        group = _ObservationGroup(
            key="test",
            category="gap",
            observations=[_obs(related_artefacts=["entity:Nonexistent"])],
        )
        store = MagicMock()
        store.get_entity.return_value = None
        assert _check_adjacency(group, store) is False


# =============================================================================
# Tests: NarrativeCompiler
# =============================================================================


class TestNarrativeCompiler:
    def test_compile_empty(self) -> None:
        compiler = NarrativeCompiler()
        assert compiler.compile([]) == []

    def test_compile_single(self) -> None:
        compiler = NarrativeCompiler(persona="admin")
        proposals = compiler.compile(
            [
                _obs(
                    category="missing_crud",
                    severity="high",
                    title="No delete for Task",
                    related_artefacts=["entity:Task"],
                ),
            ]
        )
        assert len(proposals) == 1
        assert proposals[0].id == "P-001"
        assert proposals[0].severity == "high"
        assert "admin" in proposals[0].narrative

    def test_compile_groups_same_entity(self) -> None:
        compiler = NarrativeCompiler()
        proposals = compiler.compile(
            [
                _obs(
                    category="missing_crud",
                    severity="high",
                    title="No delete",
                    related_artefacts=["entity:Task"],
                ),
                _obs(
                    category="missing_crud",
                    severity="medium",
                    title="No bulk",
                    related_artefacts=["entity:Task"],
                ),
            ]
        )
        assert len(proposals) == 1
        assert proposals[0].observation_count == 2
        assert proposals[0].severity == "high"  # Max severity

    def test_compile_separates_categories(self) -> None:
        compiler = NarrativeCompiler()
        proposals = compiler.compile(
            [
                _obs(
                    category="missing_crud",
                    severity="high",
                    title="No delete",
                    related_artefacts=["entity:Task"],
                ),
                _obs(
                    category="ux_issue",
                    severity="medium",
                    title="Missing validation",
                    related_artefacts=["entity:Task"],
                ),
            ]
        )
        assert len(proposals) == 2

    def test_compile_sorts_by_priority(self) -> None:
        compiler = NarrativeCompiler()
        proposals = compiler.compile(
            [
                _obs(category="ux_issue", severity="low", title="Minor issue"),
                _obs(category="missing_crud", severity="critical", title="Critical gap"),
            ]
        )
        assert proposals[0].severity == "critical"
        assert proposals[1].severity == "low"

    def test_compile_priority_favors_frequency(self) -> None:
        compiler = NarrativeCompiler()
        proposals = compiler.compile(
            [
                _obs(
                    category="missing_crud",
                    severity="high",
                    title="Single critical",
                    related_artefacts=["entity:A"],
                ),
                _obs(
                    category="ux_issue",
                    severity="medium",
                    title="Repeated 1",
                    related_artefacts=["entity:B"],
                ),
                _obs(
                    category="ux_issue",
                    severity="medium",
                    title="Repeated 2",
                    related_artefacts=["entity:B"],
                ),
                _obs(
                    category="ux_issue",
                    severity="medium",
                    title="Repeated 3",
                    related_artefacts=["entity:B"],
                ),
            ]
        )
        # high×1=60, medium×3=90
        assert proposals[0].category == "ux_issue"
        assert proposals[0].priority == 90

    def test_compile_with_kg_adjacency(self) -> None:
        store = MagicMock()
        store.get_entity.return_value = None  # No entities found

        compiler = NarrativeCompiler(kg_store=store)
        proposals = compiler.compile(
            [
                _obs(
                    category="gap",
                    severity="medium",
                    title="Hallucinated",
                    related_artefacts=["entity:FakeEntity"],
                ),
            ]
        )
        assert len(proposals) == 1
        assert proposals[0].adjacency_valid is False

    def test_compile_renumbers_after_sort(self) -> None:
        compiler = NarrativeCompiler()
        proposals = compiler.compile(
            [
                _obs(category="gap", severity="low", title="Low", related_artefacts=["entity:A"]),
                _obs(
                    category="gap",
                    severity="critical",
                    title="Critical",
                    related_artefacts=["entity:B"],
                ),
            ]
        )
        assert proposals[0].id == "P-001"
        assert proposals[0].severity == "critical"
        assert proposals[1].id == "P-002"


# =============================================================================
# Tests: Report Generation
# =============================================================================


class TestReport:
    def test_report_empty(self) -> None:
        compiler = NarrativeCompiler()
        report = compiler.report([])
        assert "No gaps found" in report

    def test_report_has_summary(self) -> None:
        compiler = NarrativeCompiler(persona="admin")
        proposals = compiler.compile(
            [
                _obs(
                    category="missing_crud",
                    severity="high",
                    title="No delete",
                    related_artefacts=["entity:Task"],
                ),
                _obs(
                    category="ux_issue",
                    severity="medium",
                    title="No validation",
                    related_artefacts=["entity:User"],
                ),
            ]
        )
        report = compiler.report(proposals)
        assert "# Discovery Report" in report
        assert "admin" in report
        assert "Missing CRUD" in report
        assert "UX Issue" in report

    def test_report_flags_out_of_scope(self) -> None:
        compiler = NarrativeCompiler()
        proposals = [
            Proposal(
                id="P-001",
                title="Valid",
                narrative="Valid proposal",
                category="gap",
                priority=60,
                severity="high",
                adjacency_valid=True,
            ),
            Proposal(
                id="P-002",
                title="Invalid",
                narrative="Out of scope",
                category="gap",
                priority=30,
                severity="medium",
                adjacency_valid=False,
            ),
        ]
        report = compiler.report(proposals)
        assert "[OUT OF SCOPE]" in report
        assert "P-002" in report


# =============================================================================
# Tests: JSON Serialization
# =============================================================================


class TestToJson:
    def test_to_json_structure(self) -> None:
        compiler = NarrativeCompiler(persona="admin")
        proposals = compiler.compile(
            [
                _obs(
                    category="missing_crud",
                    severity="high",
                    title="Test",
                    related_artefacts=["entity:Task"],
                ),
            ]
        )
        data = compiler.to_json(proposals)
        assert data["persona"] == "admin"
        assert data["total_proposals"] == 1
        assert len(data["proposals"]) == 1
        assert "summary" in data
        assert data["summary"]["by_category"] == {"missing_crud": 1}
        assert data["summary"]["by_severity"] == {"high": 1}

    def test_proposal_to_json(self) -> None:
        p = Proposal(
            id="P-001",
            title="Test",
            narrative="Narrative",
            category="gap",
            priority=60,
            severity="high",
            affected_entities=["Task"],
            locations=["/tasks"],
        )
        data = p.to_json()
        assert data["id"] == "P-001"
        assert data["affected_entities"] == ["Task"]
        assert data["locations"] == ["/tasks"]
