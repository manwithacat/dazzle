"""Tests for AppSpec-based evidence extraction."""

from __future__ import annotations

from unittest.mock import MagicMock

from dazzle.compliance.evidence import extract_evidence
from dazzle.compliance.models import EvidenceMap


def _make_appspec(
    *,
    entities: list | None = None,
    personas: list | None = None,
    processes: list | None = None,
    stories: list | None = None,
    policies: object | None = None,
    grant_schemas: list | None = None,
    llm_intents: list | None = None,
    slas: list | None = None,
    schedules: list | None = None,
    archetypes: list | None = None,
) -> MagicMock:
    """Build a minimal mock AppSpec for testing."""
    appspec = MagicMock()
    appspec.domain.entities = entities or []
    appspec.personas = personas or []
    appspec.processes = processes or []
    appspec.stories = stories or []
    appspec.policies = policies
    appspec.grant_schemas = grant_schemas or []
    appspec.llm_intents = llm_intents or []
    appspec.slas = slas or []
    appspec.schedules = schedules or []
    appspec.archetypes = archetypes or []
    return appspec


class TestExtractEvidence:
    def test_empty_appspec_returns_empty_evidence(self) -> None:
        appspec = _make_appspec()
        result = extract_evidence(appspec)
        assert isinstance(result, EvidenceMap)
        assert all(len(v) == 0 for v in result.items.values())

    def test_classify_evidence_from_policies(self) -> None:
        policy = MagicMock()
        policy.classifications = [
            MagicMock(entity="Customer", field="email", classification="PII_DIRECT"),
        ]
        appspec = _make_appspec(policies=policy)
        result = extract_evidence(appspec)
        assert len(result.items.get("classify", [])) == 1
        assert result.items["classify"][0].entity == "Customer"

    def test_permit_evidence_from_entity_access(self) -> None:
        entity = MagicMock()
        entity.name = "Task"
        entity.access = MagicMock()
        entity.access.permissions = [
            MagicMock(operation="create", condition=MagicMock(__str__=lambda s: "authenticated")),
        ]
        entity.access.scopes = []
        entity.access.visibility = []
        entity.state_machine = None
        appspec = _make_appspec(entities=[entity])
        result = extract_evidence(appspec)
        assert len(result.items.get("permit", [])) >= 1

    def test_persona_evidence(self) -> None:
        persona = MagicMock()
        persona.id = "teacher"
        persona.name = "Teacher"
        persona.goals = ["manage classes"]
        appspec = _make_appspec(personas=[persona])
        result = extract_evidence(appspec)
        assert len(result.items.get("persona", [])) == 1
        assert result.items["persona"][0].entity == "teacher"

    def test_process_evidence(self) -> None:
        process = MagicMock()
        process.name = "onboarding"
        process.title = "Onboarding"
        process.steps = [MagicMock(), MagicMock()]
        appspec = _make_appspec(processes=[process])
        result = extract_evidence(appspec)
        assert len(result.items.get("process", [])) == 1

    def test_story_evidence(self) -> None:
        story = MagicMock()
        story.story_id = "create_task"
        story.title = "Create Task"
        story.actor = "teacher"
        appspec = _make_appspec(stories=[story])
        result = extract_evidence(appspec)
        assert len(result.items.get("story", [])) == 1

    def test_transition_evidence(self) -> None:
        sm = MagicMock()
        sm.transitions = [
            MagicMock(from_state="draft", to_state="published"),
        ]
        entity = MagicMock()
        entity.name = "Article"
        entity.access = None
        entity.state_machine = sm
        appspec = _make_appspec(entities=[entity])
        result = extract_evidence(appspec)
        assert len(result.items.get("transitions", [])) >= 1


class TestSlaExtractor:
    def test_extracts_sla_evidence(self) -> None:
        sla = MagicMock()
        sla.name = "response_time"
        sla.entity = "Ticket"
        sla.tiers = [MagicMock(), MagicMock()]
        appspec = _make_appspec(slas=[sla])
        result = extract_evidence(appspec)
        items = result.items.get("sla", [])
        assert len(items) == 1
        assert items[0].entity == "Ticket"
        assert items[0].construct == "sla"
        assert "2 tier(s)" in items[0].detail
        assert "on entity Ticket" in items[0].detail

    def test_sla_without_entity_uses_name(self) -> None:
        sla = MagicMock()
        sla.name = "global_sla"
        sla.entity = ""
        sla.tiers = [MagicMock()]
        appspec = _make_appspec(slas=[sla])
        result = extract_evidence(appspec)
        items = result.items.get("sla", [])
        assert len(items) == 1
        assert items[0].entity == "global_sla"
        assert "on entity" not in items[0].detail

    def test_empty_slas(self) -> None:
        appspec = _make_appspec(slas=[])
        result = extract_evidence(appspec)
        assert result.items.get("sla", []) == []


class TestScheduleExtractor:
    def test_extracts_schedule_evidence(self) -> None:
        schedule = MagicMock()
        schedule.name = "nightly_backup"
        schedule.cron = "0 2 * * *"
        schedule.implements = ["backup_story"]
        appspec = _make_appspec(schedules=[schedule])
        result = extract_evidence(appspec)
        items = result.items.get("schedule", [])
        assert len(items) == 1
        assert items[0].entity == "nightly_backup"
        assert items[0].construct == "schedule"
        assert "cron: 0 2 * * *" in items[0].detail
        assert "implements backup_story" in items[0].detail

    def test_schedule_without_cron_or_implements(self) -> None:
        schedule = MagicMock()
        schedule.name = "manual_job"
        schedule.cron = None
        schedule.implements = []
        appspec = _make_appspec(schedules=[schedule])
        result = extract_evidence(appspec)
        items = result.items.get("schedule", [])
        assert len(items) == 1
        assert "cron" not in items[0].detail
        assert "implements" not in items[0].detail

    def test_empty_schedules(self) -> None:
        appspec = _make_appspec(schedules=[])
        result = extract_evidence(appspec)
        assert result.items.get("schedule", []) == []


class TestArchetypeExtractor:
    def test_extracts_archetype_evidence(self) -> None:
        archetype = MagicMock()
        archetype.name = "Auditable"
        archetype.fields = [MagicMock(), MagicMock(), MagicMock()]
        archetype.invariants = [MagicMock()]
        appspec = _make_appspec(archetypes=[archetype])
        result = extract_evidence(appspec)
        items = result.items.get("archetype", [])
        assert len(items) == 1
        assert items[0].entity == "Auditable"
        assert items[0].construct == "archetype"
        assert "3 field(s)" in items[0].detail
        assert "1 invariant(s)" in items[0].detail

    def test_archetype_without_invariants(self) -> None:
        archetype = MagicMock()
        archetype.name = "Simple"
        archetype.fields = [MagicMock()]
        archetype.invariants = []
        appspec = _make_appspec(archetypes=[archetype])
        result = extract_evidence(appspec)
        items = result.items.get("archetype", [])
        assert len(items) == 1
        assert "invariant" not in items[0].detail

    def test_empty_archetypes(self) -> None:
        appspec = _make_appspec(archetypes=[])
        result = extract_evidence(appspec)
        assert result.items.get("archetype", []) == []
