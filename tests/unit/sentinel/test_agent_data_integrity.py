"""Tests for the Data Integrity detection agent (DI-01 through DI-08)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dazzle.core.ir import FieldTypeKind
from dazzle.core.ir.governance import DataClassification
from dazzle.sentinel.agents.data_integrity import DataIntegrityAgent
from dazzle.sentinel.models import AgentId, Severity

from .conftest import (
    make_appspec,
    make_entity,
    make_field,
    mock_entity,
    pk_field,
    ref_field,
    str_field,
)


@pytest.fixture
def agent() -> DataIntegrityAgent:
    return DataIntegrityAgent()


# =============================================================================
# DI-01  Cascade delete missing
# =============================================================================


class TestDI01CascadeDeleteMissing:
    def test_flags_has_many_without_behavior(self, agent: DataIntegrityAgent) -> None:
        entity = make_entity(
            "Order",
            [
                pk_field(),
                make_field("items", FieldTypeKind.HAS_MANY, ref_entity="OrderItem"),
            ],
        )
        findings = agent.check_cascade_delete_missing(make_appspec([entity]))
        assert len(findings) == 1
        assert findings[0].heuristic_id == "DI-01"
        assert findings[0].severity == Severity.HIGH
        assert "Order.items" in findings[0].title

    def test_flags_has_one_without_behavior(self, agent: DataIntegrityAgent) -> None:
        entity = make_entity(
            "User",
            [
                pk_field(),
                make_field("profile", FieldTypeKind.HAS_ONE, ref_entity="Profile"),
            ],
        )
        findings = agent.check_cascade_delete_missing(make_appspec([entity]))
        assert len(findings) == 1

    def test_passes_when_behavior_set(self, agent: DataIntegrityAgent) -> None:
        from dazzle.core.ir.fields import RelationshipBehavior

        entity = make_entity(
            "Order",
            [
                pk_field(),
                make_field(
                    "items",
                    FieldTypeKind.HAS_MANY,
                    ref_entity="OrderItem",
                    relationship_behavior=RelationshipBehavior.CASCADE,
                ),
            ],
        )
        findings = agent.check_cascade_delete_missing(make_appspec([entity]))
        assert findings == []

    def test_ignores_non_relationship_fields(self, agent: DataIntegrityAgent) -> None:
        entity = make_entity("Task", [pk_field(), str_field("title")])
        assert agent.check_cascade_delete_missing(make_appspec([entity])) == []


# =============================================================================
# DI-02  Orphaned ref
# =============================================================================


class TestDI02OrphanedRef:
    def test_flags_ref_to_unknown_entity(self, agent: DataIntegrityAgent) -> None:
        entity = make_entity("Order", [pk_field(), ref_field("customer", "Customer")])
        findings = agent.check_orphaned_ref(make_appspec([entity]))
        assert len(findings) == 1
        assert findings[0].heuristic_id == "DI-02"
        assert "Customer" in findings[0].title

    def test_passes_when_target_exists(self, agent: DataIntegrityAgent) -> None:
        customer = make_entity("Customer", [pk_field()])
        order = make_entity("Order", [pk_field(), ref_field("customer", "Customer")])
        findings = agent.check_orphaned_ref(make_appspec([customer, order]))
        assert findings == []

    def test_ignores_non_ref_fields(self, agent: DataIntegrityAgent) -> None:
        entity = make_entity("Task", [pk_field(), str_field("title")])
        assert agent.check_orphaned_ref(make_appspec([entity])) == []


# =============================================================================
# DI-03  Entity without primary key
# =============================================================================


class TestDI03MissingPrimaryKey:
    def test_flags_entity_without_pk(self, agent: DataIntegrityAgent) -> None:
        entity = make_entity("Task", [str_field("title", required=True)])
        findings = agent.check_missing_primary_key(make_appspec([entity]))
        assert len(findings) == 1
        assert findings[0].heuristic_id == "DI-03"
        assert findings[0].severity == Severity.CRITICAL

    def test_passes_with_pk(self, agent: DataIntegrityAgent) -> None:
        entity = make_entity("Task", [pk_field(), str_field("title")])
        assert agent.check_missing_primary_key(make_appspec([entity])) == []


# =============================================================================
# DI-04  Unique-worthy field without UNIQUE
# =============================================================================


class TestDI04MissingUnique:
    @pytest.mark.parametrize("field_name", ["email", "slug", "username", "phone"])
    def test_flags_unique_worthy_fields(self, agent: DataIntegrityAgent, field_name: str) -> None:
        entity = make_entity("User", [pk_field(), str_field(field_name)])
        findings = agent.check_missing_unique_constraint(make_appspec([entity]))
        assert len(findings) == 1
        assert findings[0].heuristic_id == "DI-04"
        assert findings[0].severity == Severity.MEDIUM

    def test_passes_when_already_unique(self, agent: DataIntegrityAgent) -> None:
        entity = make_entity("User", [pk_field(), str_field("email", unique=True)])
        assert agent.check_missing_unique_constraint(make_appspec([entity])) == []

    def test_ignores_non_unique_worthy_names(self, agent: DataIntegrityAgent) -> None:
        entity = make_entity("Task", [pk_field(), str_field("description")])
        assert agent.check_missing_unique_constraint(make_appspec([entity])) == []


# =============================================================================
# DI-05  Dead-end state-machine states
# =============================================================================


class TestDI05DeadEndStates:
    def _sm(self, states: list[str], transitions: list[tuple[str, str]]) -> MagicMock:
        sm = MagicMock()
        sm.states = states
        sm.transitions = []
        for from_s, to_s in transitions:
            t = MagicMock()
            t.from_state = from_s
            t.to_state = to_s
            sm.transitions.append(t)
        return sm

    def test_flags_dead_end_state(self, agent: DataIntegrityAgent) -> None:
        sm = self._sm(
            ["draft", "review", "rejected", "published"],
            [("draft", "review"), ("review", "published"), ("review", "rejected")],
        )
        entity = mock_entity("Article", state_machine=sm)
        findings = agent.check_dead_end_states(make_appspec([entity]))
        assert len(findings) == 1
        assert "rejected" in findings[0].title

    def test_last_state_is_terminal(self, agent: DataIntegrityAgent) -> None:
        sm = self._sm(
            ["draft", "published"],
            [("draft", "published")],
        )
        entity = mock_entity("Article", state_machine=sm)
        assert agent.check_dead_end_states(make_appspec([entity])) == []

    def test_no_state_machine(self, agent: DataIntegrityAgent) -> None:
        entity = mock_entity("Task", state_machine=None)
        assert agent.check_dead_end_states(make_appspec([entity])) == []


# =============================================================================
# DI-06  Cross-entity computed field dependency
# =============================================================================


class TestDI06CrossEntityComputed:
    def _computed(self, name: str, deps: list[str]) -> MagicMock:
        cf = MagicMock()
        cf.name = name
        cf.dependencies = deps
        cf.expression = f"compute({', '.join(deps)})"
        return cf

    def test_flags_cross_entity_dep(self, agent: DataIntegrityAgent) -> None:
        entity = mock_entity(
            "Order",
            computed_fields=[self._computed("total", ["items.price"])],
        )
        findings = agent.check_cross_entity_computed(make_appspec([entity]))
        assert len(findings) == 1
        assert findings[0].heuristic_id == "DI-06"
        assert findings[0].severity == Severity.INFO

    def test_passes_for_local_deps(self, agent: DataIntegrityAgent) -> None:
        entity = mock_entity(
            "Order",
            computed_fields=[self._computed("total", ["price", "quantity"])],
        )
        assert agent.check_cross_entity_computed(make_appspec([entity])) == []

    def test_no_computed_fields(self, agent: DataIntegrityAgent) -> None:
        entity = mock_entity("Task", computed_fields=[])
        assert agent.check_cross_entity_computed(make_appspec([entity])) == []


# =============================================================================
# DI-07  PII/financial fields without audit
# =============================================================================


class TestDI07SensitiveNoAudit:
    def _policies(self, entity: str, field: str, classification: DataClassification) -> MagicMock:
        cls_spec = MagicMock()
        cls_spec.entity = entity
        cls_spec.field = field
        cls_spec.classification = classification
        policies = MagicMock()
        policies.classifications = [cls_spec]
        return policies

    def test_flags_pii_without_audit(self, agent: DataIntegrityAgent) -> None:
        entity = mock_entity("Customer", [pk_field(), str_field("email")])
        policies = self._policies("Customer", "email", DataClassification.PII_DIRECT)
        appspec = make_appspec([entity], policies=policies)
        findings = agent.check_sensitive_fields_without_audit(appspec)
        assert len(findings) == 1
        assert findings[0].heuristic_id == "DI-07"
        assert findings[0].severity == Severity.HIGH

    def test_passes_with_audit_enabled(self, agent: DataIntegrityAgent) -> None:
        audit = MagicMock()
        audit.enabled = True
        entity = mock_entity("Customer", [pk_field(), str_field("email")], audit=audit)
        policies = self._policies("Customer", "email", DataClassification.PII_DIRECT)
        appspec = make_appspec([entity], policies=policies)
        assert agent.check_sensitive_fields_without_audit(appspec) == []

    def test_no_policies(self, agent: DataIntegrityAgent) -> None:
        entity = mock_entity("Task")
        assert agent.check_sensitive_fields_without_audit(make_appspec([entity])) == []


# =============================================================================
# DI-08  Ledger sync_to target field type mismatch
# =============================================================================


class TestDI08LedgerSyncTarget:
    def _ledger(self, name: str, target_entity: str, target_field: str) -> MagicMock:
        sync = MagicMock()
        sync.target_entity = target_entity
        sync.target_field = target_field
        ledger = MagicMock()
        ledger.name = name
        ledger.sync = sync
        return ledger

    def test_flags_missing_target_entity(self, agent: DataIntegrityAgent) -> None:
        ledger = self._ledger("Wallet", "Customer", "balance_cache")
        appspec = make_appspec(ledgers=[ledger])
        findings = agent.check_ledger_sync_target(appspec)
        assert len(findings) == 1
        assert "not found" in findings[0].title

    def test_flags_missing_target_field(self, agent: DataIntegrityAgent) -> None:
        customer = mock_entity("Customer", [pk_field(), str_field("name")])
        ledger = self._ledger("Wallet", "Customer", "balance_cache")
        appspec = make_appspec([customer], ledgers=[ledger])
        findings = agent.check_ledger_sync_target(appspec)
        assert len(findings) == 1
        assert "not found" in findings[0].title

    def test_flags_non_numeric_target(self, agent: DataIntegrityAgent) -> None:
        customer = mock_entity("Customer", [pk_field(), str_field("balance_cache")])
        ledger = self._ledger("Wallet", "Customer", "balance_cache")
        appspec = make_appspec([customer], ledgers=[ledger])
        findings = agent.check_ledger_sync_target(appspec)
        assert len(findings) == 1
        assert "not numeric" in findings[0].title

    def test_passes_with_numeric_target(self, agent: DataIntegrityAgent) -> None:
        customer = mock_entity(
            "Customer",
            [
                pk_field(),
                make_field("balance_cache", FieldTypeKind.DECIMAL),
            ],
        )
        ledger = self._ledger("Wallet", "Customer", "balance_cache")
        appspec = make_appspec([customer], ledgers=[ledger])
        assert agent.check_ledger_sync_target(appspec) == []

    def test_skips_ledger_without_sync(self, agent: DataIntegrityAgent) -> None:
        ledger = MagicMock()
        ledger.name = "Wallet"
        ledger.sync = None
        assert agent.check_ledger_sync_target(make_appspec(ledgers=[ledger])) == []


# =============================================================================
# Full agent run
# =============================================================================


class TestDataIntegrityAgentRun:
    def test_agent_id(self, agent: DataIntegrityAgent) -> None:
        assert agent.agent_id == AgentId.DI

    def test_has_8_heuristics(self, agent: DataIntegrityAgent) -> None:
        assert len(agent.get_heuristics()) == 8

    def test_heuristic_ids(self, agent: DataIntegrityAgent) -> None:
        ids = [meta.heuristic_id for meta, _ in agent.get_heuristics()]
        assert ids == [f"DI-0{i}" for i in range(1, 9)]

    def test_clean_appspec_no_findings(self, agent: DataIntegrityAgent) -> None:
        entity = make_entity("Task", [pk_field(), str_field("title", required=True)])
        result = agent.run(make_appspec([entity]))
        assert result.errors == []
