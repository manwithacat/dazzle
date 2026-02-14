"""Tests for the Performance & Resource detection agent (PR-01 through PR-08)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dazzle.core.ir import FieldTypeKind
from dazzle.core.ir.ledgers import TransactionExecution
from dazzle.core.ir.process import OverlapPolicy
from dazzle.sentinel.agents.performance_resource import PerformanceResourceAgent
from dazzle.sentinel.models import AgentId, Severity

from .conftest import (
    make_appspec,
    make_entity,
    make_field,
    pk_field,
    ref_field,
    str_field,
)


@pytest.fixture
def agent() -> PerformanceResourceAgent:
    return PerformanceResourceAgent()


# =============================================================================
# PR-01  N+1 risk on list surface
# =============================================================================


class TestPR01NPlusOneListSurface:
    def _list_surface(self, name: str, entity_ref: str) -> MagicMock:
        surface = MagicMock()
        surface.name = name
        surface.mode = "list"
        surface.entity_ref = entity_ref
        return surface

    def test_flags_entity_with_3_ref_fields(self, agent: PerformanceResourceAgent) -> None:
        entity = make_entity(
            "Order",
            [
                pk_field(),
                ref_field("customer", "Customer"),
                ref_field("product", "Product"),
                ref_field("warehouse", "Warehouse"),
            ],
        )
        surface = self._list_surface("order_list", "Order")
        appspec = make_appspec([entity], surfaces=[surface])
        findings = agent.n_plus_1_list_surface(appspec)
        assert len(findings) == 1
        assert findings[0].heuristic_id == "PR-01"
        assert findings[0].severity == Severity.HIGH
        assert "order_list" in findings[0].title
        assert "Order" in findings[0].title

    def test_flags_entity_with_has_many_and_has_one(self, agent: PerformanceResourceAgent) -> None:
        entity = make_entity(
            "Order",
            [
                pk_field(),
                ref_field("customer", "Customer"),
                make_field("items", FieldTypeKind.HAS_MANY, ref_entity="OrderItem"),
                make_field("invoice", FieldTypeKind.HAS_ONE, ref_entity="Invoice"),
            ],
        )
        surface = self._list_surface("order_list", "Order")
        appspec = make_appspec([entity], surfaces=[surface])
        findings = agent.n_plus_1_list_surface(appspec)
        assert len(findings) == 1
        assert findings[0].heuristic_id == "PR-01"

    def test_passes_entity_with_fewer_than_3_refs(self, agent: PerformanceResourceAgent) -> None:
        entity = make_entity(
            "Order",
            [
                pk_field(),
                ref_field("customer", "Customer"),
                ref_field("product", "Product"),
            ],
        )
        surface = self._list_surface("order_list", "Order")
        appspec = make_appspec([entity], surfaces=[surface])
        assert agent.n_plus_1_list_surface(appspec) == []

    def test_ignores_non_list_surface(self, agent: PerformanceResourceAgent) -> None:
        entity = make_entity(
            "Order",
            [
                pk_field(),
                ref_field("customer", "Customer"),
                ref_field("product", "Product"),
                ref_field("warehouse", "Warehouse"),
            ],
        )
        surface = MagicMock()
        surface.name = "order_detail"
        surface.mode = "detail"
        surface.entity_ref = "Order"
        appspec = make_appspec([entity], surfaces=[surface])
        assert agent.n_plus_1_list_surface(appspec) == []

    def test_ignores_surface_without_entity(self, agent: PerformanceResourceAgent) -> None:
        surface = MagicMock()
        surface.name = "dashboard"
        surface.mode = "list"
        surface.entity_ref = None
        surface.entity = None
        appspec = make_appspec(surfaces=[surface])
        assert agent.n_plus_1_list_surface(appspec) == []

    def test_no_surfaces(self, agent: PerformanceResourceAgent) -> None:
        appspec = make_appspec(surfaces=[])
        assert agent.n_plus_1_list_surface(appspec) == []

    def test_entity_not_found(self, agent: PerformanceResourceAgent) -> None:
        """Surface references an entity not present in the appspec."""
        surface = self._list_surface("order_list", "NonExistent")
        appspec = make_appspec(surfaces=[surface])
        assert agent.n_plus_1_list_surface(appspec) == []


# =============================================================================
# PR-02  Ref field without index constraint
# =============================================================================


class TestPR02RefWithoutIndex:
    def test_flags_ref_without_index(self, agent: PerformanceResourceAgent) -> None:
        entity = make_entity(
            "Order",
            [pk_field(), ref_field("customer", "Customer")],
        )
        appspec = make_appspec([entity])
        findings = agent.ref_without_index(appspec)
        assert len(findings) == 1
        assert findings[0].heuristic_id == "PR-02"
        assert findings[0].severity == Severity.MEDIUM
        assert "Order.customer" in findings[0].title

    def test_flags_multiple_ref_fields(self, agent: PerformanceResourceAgent) -> None:
        entity = make_entity(
            "Order",
            [
                pk_field(),
                ref_field("customer", "Customer"),
                ref_field("product", "Product"),
            ],
        )
        appspec = make_appspec([entity])
        findings = agent.ref_without_index(appspec)
        assert len(findings) == 2
        names = {f.title for f in findings}
        assert "Ref field 'Order.customer' has no index" in names
        assert "Ref field 'Order.product' has no index" in names

    def test_passes_when_index_covers_field(self, agent: PerformanceResourceAgent) -> None:
        entity = MagicMock()
        entity.name = "Order"
        entity.fields = [pk_field(), ref_field("customer", "Customer")]
        constraint = MagicMock()
        constraint.kind = "index"
        constraint.fields = ["customer"]
        entity.constraints = [constraint]
        appspec = make_appspec([entity])
        assert agent.ref_without_index(appspec) == []

    def test_ignores_non_ref_fields(self, agent: PerformanceResourceAgent) -> None:
        entity = make_entity("Task", [pk_field(), str_field("title")])
        appspec = make_appspec([entity])
        assert agent.ref_without_index(appspec) == []

    def test_no_entities(self, agent: PerformanceResourceAgent) -> None:
        entity = make_entity("Task", [pk_field()])
        appspec = make_appspec([entity])
        assert agent.ref_without_index(appspec) == []


# =============================================================================
# PR-03  Process with ALLOW overlap policy
# =============================================================================


class TestPR03ProcessAllowOverlap:
    def test_flags_allow_overlap(self, agent: PerformanceResourceAgent) -> None:
        process = MagicMock()
        process.name = "approve_order"
        process.overlap_policy = OverlapPolicy.ALLOW
        appspec = make_appspec(processes=[process])
        findings = agent.process_allow_overlap(appspec)
        assert len(findings) == 1
        assert findings[0].heuristic_id == "PR-03"
        assert findings[0].severity == Severity.MEDIUM
        assert "approve_order" in findings[0].title

    def test_passes_skip_policy(self, agent: PerformanceResourceAgent) -> None:
        process = MagicMock()
        process.name = "approve_order"
        process.overlap_policy = OverlapPolicy.SKIP
        appspec = make_appspec(processes=[process])
        assert agent.process_allow_overlap(appspec) == []

    def test_passes_queue_policy(self, agent: PerformanceResourceAgent) -> None:
        process = MagicMock()
        process.name = "approve_order"
        process.overlap_policy = OverlapPolicy.QUEUE
        appspec = make_appspec(processes=[process])
        assert agent.process_allow_overlap(appspec) == []

    def test_passes_cancel_previous_policy(self, agent: PerformanceResourceAgent) -> None:
        process = MagicMock()
        process.name = "approve_order"
        process.overlap_policy = OverlapPolicy.CANCEL_PREVIOUS
        appspec = make_appspec(processes=[process])
        assert agent.process_allow_overlap(appspec) == []

    def test_no_processes(self, agent: PerformanceResourceAgent) -> None:
        appspec = make_appspec(processes=[])
        assert agent.process_allow_overlap(appspec) == []


# =============================================================================
# PR-04  High event topic retention
# =============================================================================


class TestPR04HighTopicRetention:
    def test_flags_high_retention(self, agent: PerformanceResourceAgent) -> None:
        topic = MagicMock()
        topic.name = "orders"
        topic.retention_days = 120
        event_model = MagicMock()
        event_model.topics = [topic]
        appspec = make_appspec(event_model=event_model)
        findings = agent.high_topic_retention(appspec)
        assert len(findings) == 1
        assert findings[0].heuristic_id == "PR-04"
        assert findings[0].severity == Severity.LOW
        assert "120" in findings[0].title
        assert "orders" in findings[0].title

    def test_passes_at_90_days(self, agent: PerformanceResourceAgent) -> None:
        topic = MagicMock()
        topic.name = "orders"
        topic.retention_days = 90
        event_model = MagicMock()
        event_model.topics = [topic]
        appspec = make_appspec(event_model=event_model)
        assert agent.high_topic_retention(appspec) == []

    def test_passes_below_90_days(self, agent: PerformanceResourceAgent) -> None:
        topic = MagicMock()
        topic.name = "orders"
        topic.retention_days = 30
        event_model = MagicMock()
        event_model.topics = [topic]
        appspec = make_appspec(event_model=event_model)
        assert agent.high_topic_retention(appspec) == []

    def test_no_event_model(self, agent: PerformanceResourceAgent) -> None:
        appspec = make_appspec(event_model=None)
        assert agent.high_topic_retention(appspec) == []

    def test_flags_multiple_topics(self, agent: PerformanceResourceAgent) -> None:
        topic_ok = MagicMock()
        topic_ok.name = "events"
        topic_ok.retention_days = 30
        topic_high = MagicMock()
        topic_high.name = "audit"
        topic_high.retention_days = 365
        event_model = MagicMock()
        event_model.topics = [topic_ok, topic_high]
        appspec = make_appspec(event_model=event_model)
        findings = agent.high_topic_retention(appspec)
        assert len(findings) == 1
        assert "audit" in findings[0].title


# =============================================================================
# PR-05  Large entity in list surface
# =============================================================================


class TestPR05LargeEntityListSurface:
    def _list_surface(self, name: str, entity_ref: str) -> MagicMock:
        surface = MagicMock()
        surface.name = name
        surface.mode = "list"
        surface.entity_ref = entity_ref
        return surface

    def test_flags_entity_with_10_plus_fields(self, agent: PerformanceResourceAgent) -> None:
        fields = [pk_field()] + [str_field(f"field_{i}") for i in range(10)]
        entity = make_entity("BigEntity", fields)
        surface = self._list_surface("big_list", "BigEntity")
        appspec = make_appspec([entity], surfaces=[surface])
        findings = agent.large_entity_list_surface(appspec)
        assert len(findings) == 1
        assert findings[0].heuristic_id == "PR-05"
        assert findings[0].severity == Severity.MEDIUM
        assert "big_list" in findings[0].title
        assert "BigEntity" in findings[0].title

    def test_passes_entity_with_fewer_than_10_fields(self, agent: PerformanceResourceAgent) -> None:
        fields = [pk_field()] + [str_field(f"field_{i}") for i in range(8)]
        entity = make_entity("SmallEntity", fields)
        surface = self._list_surface("small_list", "SmallEntity")
        appspec = make_appspec([entity], surfaces=[surface])
        assert agent.large_entity_list_surface(appspec) == []

    def test_ignores_non_list_surface(self, agent: PerformanceResourceAgent) -> None:
        fields = [pk_field()] + [str_field(f"field_{i}") for i in range(12)]
        entity = make_entity("BigEntity", fields)
        surface = MagicMock()
        surface.name = "big_detail"
        surface.mode = "detail"
        surface.entity_ref = "BigEntity"
        appspec = make_appspec([entity], surfaces=[surface])
        assert agent.large_entity_list_surface(appspec) == []

    def test_exactly_10_fields_triggers(self, agent: PerformanceResourceAgent) -> None:
        fields = [pk_field()] + [str_field(f"f_{i}") for i in range(9)]
        assert len(fields) == 10
        entity = make_entity("TenFields", fields)
        surface = self._list_surface("ten_list", "TenFields")
        appspec = make_appspec([entity], surfaces=[surface])
        findings = agent.large_entity_list_surface(appspec)
        assert len(findings) == 1

    def test_no_surfaces(self, agent: PerformanceResourceAgent) -> None:
        appspec = make_appspec(surfaces=[])
        assert agent.large_entity_list_surface(appspec) == []

    def test_entity_not_found(self, agent: PerformanceResourceAgent) -> None:
        surface = self._list_surface("ghost_list", "Ghost")
        appspec = make_appspec(surfaces=[surface])
        assert agent.large_entity_list_surface(appspec) == []


# =============================================================================
# PR-06  Synchronous transaction execution
# =============================================================================


class TestPR06SyncTransaction:
    def test_flags_sync_execution(self, agent: PerformanceResourceAgent) -> None:
        txn = MagicMock()
        txn.name = "RecordPayment"
        txn.execution = TransactionExecution.SYNC
        appspec = make_appspec(transactions=[txn])
        findings = agent.sync_transaction(appspec)
        assert len(findings) == 1
        assert findings[0].heuristic_id == "PR-06"
        assert findings[0].severity == Severity.MEDIUM
        assert "RecordPayment" in findings[0].title

    def test_passes_async_execution(self, agent: PerformanceResourceAgent) -> None:
        txn = MagicMock()
        txn.name = "RecordPayment"
        txn.execution = TransactionExecution.ASYNC
        appspec = make_appspec(transactions=[txn])
        assert agent.sync_transaction(appspec) == []

    def test_flags_multiple_sync_transactions(self, agent: PerformanceResourceAgent) -> None:
        txn1 = MagicMock()
        txn1.name = "RecordPayment"
        txn1.execution = TransactionExecution.SYNC
        txn2 = MagicMock()
        txn2.name = "TransferFunds"
        txn2.execution = TransactionExecution.SYNC
        txn_async = MagicMock()
        txn_async.name = "LogEvent"
        txn_async.execution = TransactionExecution.ASYNC
        appspec = make_appspec(transactions=[txn1, txn2, txn_async])
        findings = agent.sync_transaction(appspec)
        assert len(findings) == 2
        names = {f.title for f in findings}
        assert any("RecordPayment" in t for t in names)
        assert any("TransferFunds" in t for t in names)

    def test_no_transactions(self, agent: PerformanceResourceAgent) -> None:
        appspec = make_appspec(transactions=[])
        assert agent.sync_transaction(appspec) == []


# =============================================================================
# PR-07  Heavily surfaced entity
# =============================================================================


class TestPR07HeavilySurfacedEntity:
    def _surface(self, name: str, entity_ref: str) -> MagicMock:
        surface = MagicMock()
        surface.name = name
        surface.entity_ref = entity_ref
        return surface

    def test_flags_entity_with_4_surfaces(self, agent: PerformanceResourceAgent) -> None:
        surfaces = [
            self._surface("task_list", "Task"),
            self._surface("task_board", "Task"),
            self._surface("task_kanban", "Task"),
            self._surface("task_timeline", "Task"),
        ]
        appspec = make_appspec(surfaces=surfaces)
        findings = agent.heavily_surfaced_entity(appspec)
        assert len(findings) == 1
        assert findings[0].heuristic_id == "PR-07"
        assert findings[0].severity == Severity.MEDIUM
        assert "Task" in findings[0].title
        assert "4" in findings[0].title

    def test_flags_entity_with_5_surfaces(self, agent: PerformanceResourceAgent) -> None:
        surfaces = [self._surface(f"task_view_{i}", "Task") for i in range(5)]
        appspec = make_appspec(surfaces=surfaces)
        findings = agent.heavily_surfaced_entity(appspec)
        assert len(findings) == 1
        assert "5" in findings[0].title

    def test_passes_entity_with_3_surfaces(self, agent: PerformanceResourceAgent) -> None:
        surfaces = [
            self._surface("task_list", "Task"),
            self._surface("task_detail", "Task"),
            self._surface("task_edit", "Task"),
        ]
        appspec = make_appspec(surfaces=surfaces)
        assert agent.heavily_surfaced_entity(appspec) == []

    def test_multiple_entities_only_hot_flagged(self, agent: PerformanceResourceAgent) -> None:
        surfaces = [
            self._surface("task_list", "Task"),
            self._surface("task_board", "Task"),
            self._surface("task_kanban", "Task"),
            self._surface("task_timeline", "Task"),
            self._surface("user_list", "User"),
            self._surface("user_detail", "User"),
        ]
        appspec = make_appspec(surfaces=surfaces)
        findings = agent.heavily_surfaced_entity(appspec)
        assert len(findings) == 1
        assert "Task" in findings[0].title

    def test_no_surfaces(self, agent: PerformanceResourceAgent) -> None:
        appspec = make_appspec(surfaces=[])
        assert agent.heavily_surfaced_entity(appspec) == []

    def test_surfaces_without_entity_ref(self, agent: PerformanceResourceAgent) -> None:
        surface = MagicMock()
        surface.name = "dashboard"
        surface.entity_ref = None
        surface.entity = None
        appspec = make_appspec(surfaces=[surface])
        assert agent.heavily_surfaced_entity(appspec) == []


# =============================================================================
# PR-08  Process without explicit timeout
# =============================================================================


class TestPR08ProcessDefaultTimeout:
    def test_flags_default_timeout_with_steps(self, agent: PerformanceResourceAgent) -> None:
        process = MagicMock()
        process.name = "approve_order"
        process.timeout_seconds = 86400
        process.steps = [MagicMock(), MagicMock()]
        appspec = make_appspec(processes=[process])
        findings = agent.process_default_timeout(appspec)
        assert len(findings) == 1
        assert findings[0].heuristic_id == "PR-08"
        assert findings[0].severity == Severity.LOW
        assert "approve_order" in findings[0].title
        assert "2 steps" in findings[0].description

    def test_passes_with_custom_timeout(self, agent: PerformanceResourceAgent) -> None:
        process = MagicMock()
        process.name = "approve_order"
        process.timeout_seconds = 3600
        process.steps = [MagicMock()]
        appspec = make_appspec(processes=[process])
        assert agent.process_default_timeout(appspec) == []

    def test_passes_default_timeout_without_steps(self, agent: PerformanceResourceAgent) -> None:
        process = MagicMock()
        process.name = "simple_process"
        process.timeout_seconds = 86400
        process.steps = []
        appspec = make_appspec(processes=[process])
        assert agent.process_default_timeout(appspec) == []

    def test_no_processes(self, agent: PerformanceResourceAgent) -> None:
        appspec = make_appspec(processes=[])
        assert agent.process_default_timeout(appspec) == []

    def test_flags_multiple_processes(self, agent: PerformanceResourceAgent) -> None:
        p1 = MagicMock()
        p1.name = "process_a"
        p1.timeout_seconds = 86400
        p1.steps = [MagicMock()]
        p2 = MagicMock()
        p2.name = "process_b"
        p2.timeout_seconds = 86400
        p2.steps = [MagicMock(), MagicMock(), MagicMock()]
        p3 = MagicMock()
        p3.name = "process_c"
        p3.timeout_seconds = 7200
        p3.steps = [MagicMock()]
        appspec = make_appspec(processes=[p1, p2, p3])
        findings = agent.process_default_timeout(appspec)
        assert len(findings) == 2
        names = {f.title for f in findings}
        assert any("process_a" in t for t in names)
        assert any("process_b" in t for t in names)


# =============================================================================
# Full agent run
# =============================================================================


class TestPerformanceResourceAgentRun:
    def test_agent_id(self, agent: PerformanceResourceAgent) -> None:
        assert agent.agent_id == AgentId.PR

    def test_has_8_heuristics(self, agent: PerformanceResourceAgent) -> None:
        assert len(agent.get_heuristics()) == 8

    def test_heuristic_ids(self, agent: PerformanceResourceAgent) -> None:
        ids = [meta.heuristic_id for meta, _ in agent.get_heuristics()]
        assert ids == [f"PR-0{i}" for i in range(1, 9)]

    def test_clean_appspec_no_findings(self, agent: PerformanceResourceAgent) -> None:
        entity = make_entity("Task", [pk_field(), str_field("title", required=True)])
        result = agent.run(make_appspec([entity]))
        assert result.errors == []
        assert result.findings == []

    def test_run_collects_findings_from_multiple_heuristics(
        self, agent: PerformanceResourceAgent
    ) -> None:
        """An appspec triggering multiple heuristics produces combined findings."""
        # Entity with ref (triggers PR-02) on a list surface with many refs (triggers PR-01)
        entity = make_entity(
            "Order",
            [
                pk_field(),
                ref_field("customer", "Customer"),
                ref_field("product", "Product"),
                ref_field("warehouse", "Warehouse"),
            ],
        )
        surface = MagicMock()
        surface.name = "order_list"
        surface.mode = "list"
        surface.entity_ref = "Order"

        # Sync transaction (triggers PR-06)
        txn = MagicMock()
        txn.name = "RecordPayment"
        txn.execution = TransactionExecution.SYNC

        appspec = make_appspec(
            [entity],
            surfaces=[surface],
            transactions=[txn],
        )
        result = agent.run(appspec)
        assert result.errors == []
        heuristic_ids = {f.heuristic_id for f in result.findings}
        assert "PR-01" in heuristic_ids  # N+1 risk
        assert "PR-02" in heuristic_ids  # ref without index
        assert "PR-06" in heuristic_ids  # sync transaction

    def test_run_reports_heuristics_run_count(self, agent: PerformanceResourceAgent) -> None:
        appspec = make_appspec()
        result = agent.run(appspec)
        assert result.heuristics_run == 8

    def test_run_has_duration(self, agent: PerformanceResourceAgent) -> None:
        appspec = make_appspec()
        result = agent.run(appspec)
        assert result.duration_ms >= 0
