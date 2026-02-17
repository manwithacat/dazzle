"""
Unit tests for story scope fidelity analysis.

Tests cover:
- Full scope coverage (all entities referenced in process steps)
- Partial coverage (some entities missing)
- Stories without scope (no_scope status)
- Stories without implementing process (no_process status)
- Entity matching heuristics (PascalCase/snake_case, service prefix, step name)
- Pagination and filtering
- Rejected story exclusion
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Pre-mock the mcp SDK package
for _mod in ("mcp", "mcp.server", "mcp.server.fastmcp", "mcp.server.stdio"):
    sys.modules.setdefault(_mod, MagicMock(pytest_plugins=[]))

_mock_types = MagicMock(pytest_plugins=[])
_mock_types.Tool = MagicMock
_mock_types.Resource = MagicMock
_mock_types.TextContent = MagicMock
sys.modules.setdefault("mcp.types", _mock_types)

import pytest  # noqa: E402

from dazzle.core.ir.process import (  # noqa: E402
    HumanTaskSpec,
    ProcessSpec,
    ProcessStepSpec,
    StepKind,
)
from dazzle.core.ir.stories import (  # noqa: E402
    StorySpec,
    StoryStatus,
    StoryTrigger,
)
from dazzle.mcp.server.handlers.process.scope_fidelity import (  # noqa: E402
    _collect_process_entity_tokens,
    _entity_matches_tokens,
    _pascal_to_snake,
    scope_fidelity_handler,
)

# =============================================================================
# Unit tests for entity matching helpers
# =============================================================================


class TestPascalToSnake:
    def test_simple(self) -> None:
        assert _pascal_to_snake("Task") == "task"

    def test_multi_word(self) -> None:
        assert _pascal_to_snake("ComplianceDeadline") == "compliance_deadline"

    def test_already_lower(self) -> None:
        assert _pascal_to_snake("order") == "order"

    def test_acronym(self) -> None:
        assert _pascal_to_snake("VATReturn") == "v_a_t_return"


class TestEntityMatchesTokens:
    def test_exact_match(self) -> None:
        assert _entity_matches_tokens("Task", {"Task", "Order"})

    def test_case_insensitive(self) -> None:
        assert _entity_matches_tokens("Task", {"task"})

    def test_service_prefix(self) -> None:
        assert _entity_matches_tokens("Task", {"Task.create", "Order.list"})

    def test_step_name_contains(self) -> None:
        assert _entity_matches_tokens("Task", {"load_task_context"})

    def test_snake_case_match(self) -> None:
        assert _entity_matches_tokens("ComplianceDeadline", {"check_compliance_deadline"})

    def test_no_match(self) -> None:
        assert not _entity_matches_tokens("Invoice", {"Task.create", "Order.list"})

    def test_substring_in_service(self) -> None:
        assert _entity_matches_tokens("VAT", {"process_vat_return"})


class TestCollectProcessEntityTokens:
    def test_extracts_service_names(self) -> None:
        proc = ProcessSpec(
            name="order_workflow",
            steps=[
                ProcessStepSpec(name="create_order", kind=StepKind.SERVICE, service="Order.create"),
                ProcessStepSpec(
                    name="send_notification", kind=StepKind.SERVICE, service="Notification.send"
                ),
            ],
        )
        tokens = _collect_process_entity_tokens(proc)
        assert "Order.create" in tokens
        assert "Order" in tokens
        assert "Notification.send" in tokens
        assert "Notification" in tokens

    def test_extracts_step_names(self) -> None:
        proc = ProcessSpec(
            name="task_workflow",
            steps=[ProcessStepSpec(name="load_task_details")],
        )
        tokens = _collect_process_entity_tokens(proc)
        assert "load_task_details" in tokens

    def test_extracts_human_task_entity_path(self) -> None:
        proc = ProcessSpec(
            name="approval_flow",
            steps=[
                ProcessStepSpec(
                    name="review_task",
                    kind=StepKind.HUMAN_TASK,
                    human_task=HumanTaskSpec(
                        surface="task_review",
                        entity_path="Task",
                    ),
                ),
            ],
        )
        tokens = _collect_process_entity_tokens(proc)
        assert "Task" in tokens
        assert "task_review" in tokens

    def test_extracts_parallel_steps(self) -> None:
        proc = ProcessSpec(
            name="parallel_workflow",
            steps=[
                ProcessStepSpec(
                    name="parallel_block",
                    kind=StepKind.PARALLEL,
                    parallel_steps=[
                        ProcessStepSpec(name="update_order", service="Order.update"),
                        ProcessStepSpec(name="log_audit", service="AuditLog.create"),
                    ],
                ),
            ],
        )
        tokens = _collect_process_entity_tokens(proc)
        assert "Order" in tokens
        assert "AuditLog" in tokens


# =============================================================================
# Integration tests for scope_fidelity_handler
# =============================================================================


def _make_story(
    story_id: str,
    title: str,
    scope: list[str],
    status: StoryStatus = StoryStatus.ACCEPTED,
) -> StorySpec:
    return StorySpec(
        story_id=story_id,
        title=title,
        actor="User",
        trigger=StoryTrigger.FORM_SUBMITTED,
        scope=scope,
        status=status,
    )


def _make_process(
    name: str,
    implements: list[str],
    steps: list[ProcessStepSpec] | None = None,
) -> ProcessSpec:
    return ProcessSpec(
        name=name,
        implements=implements,
        steps=steps or [],
    )


@pytest.fixture
def mock_app_spec_full_coverage() -> MagicMock:
    """AppSpec where processes fully cover all story scope entities."""
    app_spec = MagicMock()
    app_spec.stories = [
        _make_story("ST-001", "Create and assign task", ["Task", "User"]),
    ]
    app_spec.processes = [
        _make_process(
            "task_workflow",
            implements=["ST-001"],
            steps=[
                ProcessStepSpec(name="create_task", service="Task.create"),
                ProcessStepSpec(name="assign_user", service="User.read"),
            ],
        ),
    ]
    return app_spec


@pytest.fixture
def mock_app_spec_partial_coverage() -> MagicMock:
    """AppSpec where processes only cover some scope entities."""
    app_spec = MagicMock()
    app_spec.stories = [
        _make_story(
            "ST-001",
            "Triage morning workload",
            ["Task", "ComplianceDeadline", "VATReturn", "BookkeepingPeriod"],
        ),
    ]
    app_spec.processes = [
        _make_process(
            "task_workflow",
            implements=["ST-001"],
            steps=[
                ProcessStepSpec(name="load_tasks", service="Task.list"),
                ProcessStepSpec(
                    name="check_compliance_deadline", service="ComplianceDeadline.read"
                ),
            ],
        ),
    ]
    return app_spec


@pytest.fixture
def mock_app_spec_no_scope() -> MagicMock:
    """AppSpec with a story that has no scope."""
    app_spec = MagicMock()
    app_spec.stories = [
        _make_story("ST-001", "User logs in", []),  # no scope
    ]
    app_spec.processes = [
        _make_process("login_flow", implements=["ST-001"]),
    ]
    return app_spec


@pytest.fixture
def mock_app_spec_no_process() -> MagicMock:
    """AppSpec with a story that has no implementing process."""
    app_spec = MagicMock()
    app_spec.stories = [
        _make_story("ST-001", "Generate report", ["Report", "Template"]),
    ]
    app_spec.processes = []  # no processes
    return app_spec


@pytest.fixture
def mock_app_spec_mixed() -> MagicMock:
    """AppSpec with a mix of full, partial, no_scope, no_process, and rejected stories."""
    app_spec = MagicMock()
    app_spec.stories = [
        _make_story("ST-001", "Full coverage", ["Task"]),
        _make_story("ST-002", "Partial coverage", ["Task", "Invoice"]),
        _make_story("ST-003", "No scope", []),
        _make_story("ST-004", "No process", ["Report"]),
        _make_story("ST-005", "Rejected", ["Order"], status=StoryStatus.REJECTED),
    ]
    app_spec.processes = [
        _make_process(
            "task_flow",
            implements=["ST-001", "ST-002"],
            steps=[
                ProcessStepSpec(name="do_task", service="Task.create"),
            ],
        ),
    ]
    return app_spec


def _run_handler(app_spec: MagicMock, args: dict | None = None) -> dict:
    """Helper to run scope_fidelity_handler with mocked AppSpec."""
    with (
        patch(
            "dazzle.mcp.server.handlers.process._helpers.load_app_spec",
            return_value=app_spec,
        ),
        patch(
            "dazzle.core.process_persistence.load_processes",
            return_value=[],
        ),
    ):
        result = scope_fidelity_handler(Path("/fake"), args or {})
    return json.loads(result)


class TestScopeFidelityHandler:
    def test_full_coverage(self, mock_app_spec_full_coverage: MagicMock) -> None:
        data = _run_handler(mock_app_spec_full_coverage)
        assert data["full"] == 1
        assert data["partial"] == 0
        assert data["scope_coverage_percent"] == 100.0
        assert data["total_scope_gaps"] == 0

        story = data["stories"][0]
        assert story["status"] == "full"
        assert set(story["covered_entities"]) == {"Task", "User"}
        assert story["missing_entities"] == []

    def test_partial_coverage(self, mock_app_spec_partial_coverage: MagicMock) -> None:
        data = _run_handler(mock_app_spec_partial_coverage)
        assert data["full"] == 0
        assert data["partial"] == 1
        assert data["scope_coverage_percent"] == 50.0  # 2 out of 4
        assert data["total_scope_gaps"] == 2

        story = data["stories"][0]
        assert story["status"] == "partial"
        assert "Task" in story["covered_entities"]
        assert "ComplianceDeadline" in story["covered_entities"]
        assert "VATReturn" in story["missing_entities"]
        assert "BookkeepingPeriod" in story["missing_entities"]

    def test_no_scope(self, mock_app_spec_no_scope: MagicMock) -> None:
        data = _run_handler(mock_app_spec_no_scope)
        assert data["no_scope"] == 1
        assert data["stories"][0]["status"] == "no_scope"

    def test_no_process(self, mock_app_spec_no_process: MagicMock) -> None:
        data = _run_handler(mock_app_spec_no_process)
        assert data["no_process"] == 1
        story = data["stories"][0]
        assert story["status"] == "no_process"
        assert story["missing_entities"] == ["Report", "Template"]

    def test_mixed_statuses(self, mock_app_spec_mixed: MagicMock) -> None:
        data = _run_handler(mock_app_spec_mixed)
        assert data["full"] == 1  # ST-001
        assert data["partial"] == 1  # ST-002 (Invoice missing)
        assert data["no_scope"] == 1  # ST-003
        assert data["no_process"] == 1  # ST-004
        assert data["rejected_excluded"] == 1  # ST-005
        assert data["total_stories"] == 4  # excluding rejected

    def test_rejected_excluded(self, mock_app_spec_mixed: MagicMock) -> None:
        data = _run_handler(mock_app_spec_mixed)
        story_ids = [s["story_id"] for s in data["stories"]]
        assert "ST-005" not in story_ids
        assert data["rejected_excluded"] == 1

    def test_gaps_only_filter(self, mock_app_spec_mixed: MagicMock) -> None:
        data = _run_handler(mock_app_spec_mixed, {"status_filter": "gaps_only"})
        statuses = {s["status"] for s in data["stories"]}
        assert statuses <= {"partial", "no_process"}

    def test_full_filter(self, mock_app_spec_mixed: MagicMock) -> None:
        data = _run_handler(mock_app_spec_mixed, {"status_filter": "full"})
        assert all(s["status"] == "full" for s in data["stories"])

    def test_pagination(self, mock_app_spec_mixed: MagicMock) -> None:
        data = _run_handler(mock_app_spec_mixed, {"limit": 2, "offset": 0})
        assert data["showing"] == 2
        assert data["has_more"] is True

        data2 = _run_handler(mock_app_spec_mixed, {"limit": 2, "offset": 2})
        assert data2["showing"] == 2
        assert data2["has_more"] is False

    def test_recommendation_on_gaps(self, mock_app_spec_partial_coverage: MagicMock) -> None:
        data = _run_handler(mock_app_spec_partial_coverage)
        assert "recommendation" in data
        assert "scope gaps" in data["recommendation"]

    def test_no_recommendation_when_all_covered(
        self, mock_app_spec_full_coverage: MagicMock
    ) -> None:
        data = _run_handler(mock_app_spec_full_coverage)
        assert "recommendation" not in data

    def test_no_stories_error(self) -> None:
        app_spec = MagicMock()
        app_spec.stories = []
        with (
            patch(
                "dazzle.mcp.server.handlers.process._helpers.load_app_spec",
                return_value=app_spec,
            ),
            patch(
                "dazzle.core.stories_persistence.load_story_index",
                return_value=[],
            ),
        ):
            result = scope_fidelity_handler(Path("/fake"), {})
        data = json.loads(result)
        assert "error" in data


class TestScopeFidelityGapDetails:
    """Test that gap details contain useful hints."""

    def test_gap_has_entity_and_hint(self, mock_app_spec_partial_coverage: MagicMock) -> None:
        data = _run_handler(mock_app_spec_partial_coverage)
        gaps = data["stories"][0]["gaps"]
        assert len(gaps) == 2
        for gap in gaps:
            assert "entity" in gap
            assert "hint" in gap
            assert gap["entity"] in ("VATReturn", "BookkeepingPeriod")
