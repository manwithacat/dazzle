"""Tests for the Performance & Resource detection agent (PR-01 through PR-08)."""

from unittest.mock import MagicMock

import pytest

from dazzle.core.ir import FieldTypeKind
from dazzle.core.ir.ledgers import TransactionExecution
from dazzle.core.ir.process import OverlapPolicy
from dazzle.core.ir.views import ViewFieldSpec, ViewSpec
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


def _list_surface(name: str, entity_ref: str) -> MagicMock:
    surface = MagicMock()
    surface.name = name
    surface.mode = "list"
    surface.entity_ref = entity_ref
    return surface


# =============================================================================
# PR-01  N+1 risk on list surface
# =============================================================================


class TestPR01NPlusOneListSurface:
    def test_ref_only_entity_not_flagged(self, agent: PerformanceResourceAgent) -> None:
        """ref fields get auto-eager-load — no N+1 risk."""
        entity = make_entity(
            "Order",
            [
                pk_field(),
                ref_field("customer", "Customer"),
                ref_field("product", "Product"),
                ref_field("warehouse", "Warehouse"),
            ],
        )
        surface = _list_surface("order_list", "Order")
        appspec = make_appspec([entity], surfaces=[surface])
        assert agent.n_plus_1_list_surface(appspec) == []

    def test_flags_entity_with_3_has_many(self, agent: PerformanceResourceAgent) -> None:
        """has_many fields are NOT auto-eager-loaded — N+1 risk remains."""
        entity = make_entity(
            "Order",
            [
                pk_field(),
                make_field("items", FieldTypeKind.HAS_MANY, ref_entity="OrderItem"),
                make_field("payments", FieldTypeKind.HAS_MANY, ref_entity="Payment"),
                make_field("notes", FieldTypeKind.HAS_MANY, ref_entity="Note"),
            ],
        )
        surface = _list_surface("order_list", "Order")
        findings = agent.n_plus_1_list_surface(make_appspec([entity], surfaces=[surface]))
        assert len(findings) == 1
        assert findings[0].heuristic_id == "PR-01"
        assert findings[0].severity == Severity.HIGH
        assert "order_list" in findings[0].title

    def test_flags_3_has_many_even_with_refs(self, agent: PerformanceResourceAgent) -> None:
        """Entity with both ref and has_many — only has_many count."""
        entity = make_entity(
            "Order",
            [
                pk_field(),
                ref_field("customer", "Customer"),
                make_field("items", FieldTypeKind.HAS_MANY, ref_entity="OrderItem"),
                make_field("payments", FieldTypeKind.HAS_MANY, ref_entity="Payment"),
                make_field("notes", FieldTypeKind.HAS_MANY, ref_entity="Note"),
            ],
        )
        surface = _list_surface("order_list", "Order")
        findings = agent.n_plus_1_list_surface(make_appspec([entity], surfaces=[surface]))
        assert len(findings) == 1

    @pytest.mark.parametrize(
        "scenario",
        [
            "mixed_refs_and_has_many",
            "fewer_than_3_refs",
            "non_list_surface",
            "no_entity_ref",
            "no_surfaces",
            "entity_not_found",
        ],
    )
    def test_pr01_returns_empty(self, agent: PerformanceResourceAgent, scenario: str) -> None:
        """Scenarios that should produce zero PR-01 findings."""
        if scenario == "mixed_refs_and_has_many":
            entity = make_entity(
                "Order",
                [
                    pk_field(),
                    ref_field("customer", "Customer"),
                    make_field("items", FieldTypeKind.HAS_MANY, ref_entity="OrderItem"),
                    make_field("invoice", FieldTypeKind.HAS_ONE, ref_entity="Invoice"),
                ],
            )
            appspec = make_appspec([entity], surfaces=[_list_surface("order_list", "Order")])
        elif scenario == "fewer_than_3_refs":
            entity = make_entity(
                "Order",
                [
                    pk_field(),
                    ref_field("customer", "Customer"),
                    ref_field("product", "Product"),
                ],
            )
            appspec = make_appspec([entity], surfaces=[_list_surface("order_list", "Order")])
        elif scenario == "non_list_surface":
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
        elif scenario == "no_entity_ref":
            surface = MagicMock()
            surface.name = "dashboard"
            surface.mode = "list"
            surface.entity_ref = None
            surface.entity = None
            appspec = make_appspec(surfaces=[surface])
        elif scenario == "no_surfaces":
            appspec = make_appspec(surfaces=[])
        else:  # entity_not_found
            appspec = make_appspec(surfaces=[_list_surface("order_list", "NonExistent")])

        assert agent.n_plus_1_list_surface(appspec) == []


# =============================================================================
# PR-02  Ref field without index constraint
# =============================================================================


class TestPR02RefWithoutIndex:
    def test_flags_ref_without_index(self, agent: PerformanceResourceAgent) -> None:
        entity = make_entity("Order", [pk_field(), ref_field("customer", "Customer")])
        findings = agent.ref_without_index(make_appspec([entity]))
        assert len(findings) == 1
        assert findings[0].heuristic_id == "PR-02"
        assert findings[0].severity == Severity.MEDIUM
        assert "Order.customer" in findings[0].title

    def test_passes_when_index_covers_field(self, agent: PerformanceResourceAgent) -> None:
        entity = MagicMock()
        entity.name = "Order"
        entity.fields = [pk_field(), ref_field("customer", "Customer")]
        constraint = MagicMock()
        constraint.kind = "index"
        constraint.fields = ["customer"]
        entity.constraints = [constraint]
        assert agent.ref_without_index(make_appspec([entity])) == []

    def test_ignores_non_ref_fields(self, agent: PerformanceResourceAgent) -> None:
        entity = make_entity("Task", [pk_field(), str_field("title")])
        assert agent.ref_without_index(make_appspec([entity])) == []


# =============================================================================
# PR-03  Process with ALLOW overlap policy
# =============================================================================


class TestPR03ProcessAllowOverlap:
    def test_flags_allow_overlap(self, agent: PerformanceResourceAgent) -> None:
        process = MagicMock()
        process.name = "approve_order"
        process.overlap_policy = OverlapPolicy.ALLOW
        findings = agent.process_allow_overlap(make_appspec(processes=[process]))
        assert len(findings) == 1
        assert findings[0].heuristic_id == "PR-03"
        assert findings[0].severity == Severity.MEDIUM
        assert "approve_order" in findings[0].title

    @pytest.mark.parametrize(
        "policy",
        [OverlapPolicy.SKIP, OverlapPolicy.QUEUE, OverlapPolicy.CANCEL_PREVIOUS],
        ids=["skip", "queue", "cancel_previous"],
    )
    def test_passes_safe_policies(
        self, agent: PerformanceResourceAgent, policy: OverlapPolicy
    ) -> None:
        process = MagicMock()
        process.name = "approve_order"
        process.overlap_policy = policy
        assert agent.process_allow_overlap(make_appspec(processes=[process])) == []

    def test_no_processes(self, agent: PerformanceResourceAgent) -> None:
        assert agent.process_allow_overlap(make_appspec(processes=[])) == []


# =============================================================================
# PR-04  High event topic retention
# =============================================================================


class TestPR04HighTopicRetention:
    def _topic(self, name: str, retention_days: int) -> MagicMock:
        topic = MagicMock()
        topic.name = name
        topic.retention_days = retention_days
        return topic

    def _event_model(self, topics: list) -> MagicMock:
        em = MagicMock()
        em.topics = topics
        return em

    def test_flags_high_retention(self, agent: PerformanceResourceAgent) -> None:
        em = self._event_model([self._topic("orders", 120)])
        findings = agent.high_topic_retention(make_appspec(event_model=em))
        assert len(findings) == 1
        assert findings[0].heuristic_id == "PR-04"
        assert findings[0].severity == Severity.LOW
        assert "120" in findings[0].title
        assert "orders" in findings[0].title

    @pytest.mark.parametrize(
        "retention_days", [90, 30], ids=["at_threshold_90", "below_threshold_30"]
    )
    def test_passes_at_or_below_threshold(
        self, agent: PerformanceResourceAgent, retention_days: int
    ) -> None:
        em = self._event_model([self._topic("orders", retention_days)])
        assert agent.high_topic_retention(make_appspec(event_model=em)) == []

    def test_no_event_model(self, agent: PerformanceResourceAgent) -> None:
        assert agent.high_topic_retention(make_appspec(event_model=None)) == []

    def test_flags_only_offending_topic(self, agent: PerformanceResourceAgent) -> None:
        # Mixed: one passes, one flagged — covers iteration + filter behaviour.
        em = self._event_model([self._topic("events", 30), self._topic("audit", 365)])
        findings = agent.high_topic_retention(make_appspec(event_model=em))
        assert len(findings) == 1
        assert "audit" in findings[0].title


# =============================================================================
# PR-05  Large entity in list surface
# =============================================================================


class TestPR05LargeEntityListSurface:
    def test_flags_entity_with_10_plus_fields(self, agent: PerformanceResourceAgent) -> None:
        fields = [pk_field()] + [str_field(f"field_{i}") for i in range(10)]
        entity = make_entity("BigEntity", fields)
        surface = _list_surface("big_list", "BigEntity")
        findings = agent.large_entity_list_surface(make_appspec([entity], surfaces=[surface]))
        assert len(findings) == 1
        assert findings[0].heuristic_id == "PR-05"
        assert findings[0].severity == Severity.MEDIUM
        assert "big_list" in findings[0].title
        assert "BigEntity" in findings[0].title

    def test_exactly_10_fields_triggers(self, agent: PerformanceResourceAgent) -> None:
        fields = [pk_field()] + [str_field(f"f_{i}") for i in range(9)]
        assert len(fields) == 10
        entity = make_entity("TenFields", fields)
        surface = _list_surface("ten_list", "TenFields")
        findings = agent.large_entity_list_surface(make_appspec([entity], surfaces=[surface]))
        assert len(findings) == 1

    @pytest.mark.parametrize(
        "scenario",
        ["fewer_fields", "non_list_surface", "no_surfaces", "entity_not_found"],
    )
    def test_pr05_returns_empty(self, agent: PerformanceResourceAgent, scenario: str) -> None:
        if scenario == "fewer_fields":
            fields = [pk_field()] + [str_field(f"field_{i}") for i in range(8)]
            entity = make_entity("SmallEntity", fields)
            appspec = make_appspec([entity], surfaces=[_list_surface("small_list", "SmallEntity")])
        elif scenario == "non_list_surface":
            fields = [pk_field()] + [str_field(f"field_{i}") for i in range(12)]
            entity = make_entity("BigEntity", fields)
            surface = MagicMock()
            surface.name = "big_detail"
            surface.mode = "detail"
            surface.entity_ref = "BigEntity"
            appspec = make_appspec([entity], surfaces=[surface])
        elif scenario == "no_surfaces":
            appspec = make_appspec(surfaces=[])
        else:  # entity_not_found
            appspec = make_appspec(surfaces=[_list_surface("ghost_list", "Ghost")])

        assert agent.large_entity_list_surface(appspec) == []

    def test_view_projection_reduces_field_count(self, agent: PerformanceResourceAgent) -> None:
        """Surface with view_ref uses view's field count, not entity's."""
        fields = [pk_field()] + [str_field(f"field_{i}") for i in range(20)]
        entity = make_entity("Contact", fields)
        surface = _list_surface("contact_list", "Contact")
        surface.view_ref = "ContactSummary"
        view = ViewSpec(
            name="ContactSummary",
            source_entity="Contact",
            fields=[
                ViewFieldSpec(name="id"),
                ViewFieldSpec(name="name"),
                ViewFieldSpec(name="email"),
            ],
        )
        appspec = make_appspec([entity], surfaces=[surface], views=[view])
        assert agent.large_entity_list_surface(appspec) == []

    @pytest.mark.parametrize(
        "view_ref",
        ["NonExistentView", None],
        ids=["missing_view_falls_back", "no_view_ref_uses_entity"],
    )
    def test_view_ref_fallback_to_entity_fields(
        self, agent: PerformanceResourceAgent, view_ref: str | None
    ) -> None:
        """Both no-view-ref and unresolved-view-ref fall back to entity field count."""
        fields = [pk_field()] + [str_field(f"field_{i}") for i in range(10)]
        entity = make_entity("BigEntity", fields)
        surface = _list_surface("big_list", "BigEntity")
        surface.view_ref = view_ref
        findings = agent.large_entity_list_surface(make_appspec([entity], surfaces=[surface]))
        assert len(findings) == 1


# =============================================================================
# PR-06  Synchronous transaction execution
# =============================================================================


class TestPR06SyncTransaction:
    def test_flags_sync_execution(self, agent: PerformanceResourceAgent) -> None:
        txn = MagicMock()
        txn.name = "RecordPayment"
        txn.execution = TransactionExecution.SYNC
        findings = agent.sync_transaction(make_appspec(transactions=[txn]))
        assert len(findings) == 1
        assert findings[0].heuristic_id == "PR-06"
        assert findings[0].severity == Severity.MEDIUM
        assert "RecordPayment" in findings[0].title

    def test_passes_async_execution(self, agent: PerformanceResourceAgent) -> None:
        txn = MagicMock()
        txn.name = "RecordPayment"
        txn.execution = TransactionExecution.ASYNC
        assert agent.sync_transaction(make_appspec(transactions=[txn])) == []

    def test_no_transactions(self, agent: PerformanceResourceAgent) -> None:
        assert agent.sync_transaction(make_appspec(transactions=[])) == []


# =============================================================================
# PR-07  Heavily surfaced entity
# =============================================================================


class TestPR07HeavilySurfacedEntity:
    def _surface(self, name: str, entity_ref: str, mode: str = "list") -> MagicMock:
        surface = MagicMock()
        surface.name = name
        surface.entity_ref = entity_ref
        surface.mode = mode
        return surface

    def test_crud_quartet_not_flagged(self, agent: PerformanceResourceAgent) -> None:
        # #1356: one surface per mode is the framework baseline, not a hot path.
        surfaces = [
            self._surface("task_list", "Task", "list"),
            self._surface("task_detail", "Task", "view"),
            self._surface("task_create", "Task", "create"),
            self._surface("task_edit", "Task", "edit"),
        ]
        assert agent.heavily_surfaced_entity(make_appspec(surfaces=surfaces)) == []

    def test_flags_surfaces_beyond_mode_baseline(self, agent: PerformanceResourceAgent) -> None:
        # CRUD quartet + two extra list views → excess 2 → hot.
        surfaces = [
            self._surface("task_list", "Task", "list"),
            self._surface("task_detail", "Task", "view"),
            self._surface("task_create", "Task", "create"),
            self._surface("task_edit", "Task", "edit"),
            self._surface("task_board", "Task", "list"),
            self._surface("task_archive", "Task", "list"),
        ]
        findings = agent.heavily_surfaced_entity(make_appspec(surfaces=surfaces))
        assert len(findings) == 1
        assert findings[0].heuristic_id == "PR-07"
        assert findings[0].severity == Severity.MEDIUM
        assert "Task" in findings[0].title
        assert "6" in findings[0].title

    def test_flags_many_same_mode_surfaces(self, agent: PerformanceResourceAgent) -> None:
        # Five list views of the same entity: excess 4 → hot.
        surfaces = [self._surface(f"task_view_{i}", "Task", "list") for i in range(5)]
        findings = agent.heavily_surfaced_entity(make_appspec(surfaces=surfaces))
        assert len(findings) == 1

    def test_passes_entity_with_3_surfaces(self, agent: PerformanceResourceAgent) -> None:
        surfaces = [
            self._surface("task_list", "Task", "list"),
            self._surface("task_detail", "Task", "view"),
            self._surface("task_edit", "Task", "edit"),
        ]
        assert agent.heavily_surfaced_entity(make_appspec(surfaces=surfaces)) == []

    def test_multiple_entities_only_hot_flagged(self, agent: PerformanceResourceAgent) -> None:
        surfaces = [
            self._surface("task_list", "Task", "list"),
            self._surface("task_board", "Task", "list"),
            self._surface("task_kanban", "Task", "list"),
            self._surface("task_timeline", "Task", "list"),
            self._surface("user_list", "User", "list"),
            self._surface("user_detail", "User", "view"),
        ]
        findings = agent.heavily_surfaced_entity(make_appspec(surfaces=surfaces))
        assert len(findings) == 1
        assert "Task" in findings[0].title

    def test_no_surfaces(self, agent: PerformanceResourceAgent) -> None:
        assert agent.heavily_surfaced_entity(make_appspec(surfaces=[])) == []

    def test_surfaces_without_entity_ref(self, agent: PerformanceResourceAgent) -> None:
        surface = MagicMock()
        surface.name = "dashboard"
        surface.entity_ref = None
        surface.entity = None
        assert agent.heavily_surfaced_entity(make_appspec(surfaces=[surface])) == []


# =============================================================================
# PR-08  Process without explicit timeout
# =============================================================================


class TestPR08ProcessDefaultTimeout:
    def test_flags_default_timeout_with_steps(self, agent: PerformanceResourceAgent) -> None:
        process = MagicMock()
        process.name = "approve_order"
        process.timeout_seconds = 86400
        process.steps = [MagicMock(), MagicMock()]
        findings = agent.process_default_timeout(make_appspec(processes=[process]))
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
        assert agent.process_default_timeout(make_appspec(processes=[process])) == []

    def test_passes_default_timeout_without_steps(self, agent: PerformanceResourceAgent) -> None:
        process = MagicMock()
        process.name = "simple_process"
        process.timeout_seconds = 86400
        process.steps = []
        assert agent.process_default_timeout(make_appspec(processes=[process])) == []

    def test_no_processes(self, agent: PerformanceResourceAgent) -> None:
        assert agent.process_default_timeout(make_appspec(processes=[])) == []


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

    def test_run_collects_findings_and_iteration(self, agent: PerformanceResourceAgent) -> None:
        """Aggregates per-heuristic findings AND exercises iteration —
        replaces individual 'multiple_X' tests."""
        entity = make_entity(
            "Order",
            [
                pk_field(),
                ref_field("customer", "Customer"),
                ref_field("product", "Product"),  # extra ref → multiple PR-02
                make_field("items", FieldTypeKind.HAS_MANY, ref_entity="OrderItem"),
                make_field("payments", FieldTypeKind.HAS_MANY, ref_entity="Payment"),
                make_field("notes", FieldTypeKind.HAS_MANY, ref_entity="Note"),
            ],
        )
        surface = _list_surface("order_list", "Order")
        # Multiple sync transactions → exercises PR-06 iteration.
        txns = [
            (
                lambda n: (
                    lambda t: (
                        setattr(t, "name", n),
                        setattr(t, "execution", TransactionExecution.SYNC),
                        t,
                    )[2]
                )(MagicMock())
            )("RecordPayment"),
            (
                lambda n: (
                    lambda t: (
                        setattr(t, "name", n),
                        setattr(t, "execution", TransactionExecution.SYNC),
                        t,
                    )[2]
                )(MagicMock())
            )("TransferFunds"),
        ]
        # Multiple processes with default timeout → exercises PR-08 iteration.
        procs = []
        for n in ("process_a", "process_b"):
            p = MagicMock()
            p.name = n
            p.timeout_seconds = 86400
            p.steps = [MagicMock()]
            procs.append(p)
        result = agent.run(
            make_appspec([entity], surfaces=[surface], transactions=txns, processes=procs)
        )
        assert result.errors == []
        ids = [f.heuristic_id for f in result.findings]
        assert "PR-01" in ids
        assert ids.count("PR-02") == 2  # iteration over ref fields
        assert ids.count("PR-06") == 2  # iteration over txns
        assert ids.count("PR-08") == 2  # iteration over processes

    def test_run_reports_heuristics_run_count(self, agent: PerformanceResourceAgent) -> None:
        result = agent.run(make_appspec())
        assert result.heuristics_run == 8

    def test_run_has_duration(self, agent: PerformanceResourceAgent) -> None:
        result = agent.run(make_appspec())
        assert result.duration_ms >= 0
