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
