"""
Unit tests for process diagram generation.

Tests the Mermaid diagram generation for ProcessSpec.

Uses direct module import to avoid triggering mcp.server import from dazzle.mcp.__init__.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

from dazzle.core.ir.process import (
    CompensationSpec,
    HumanTaskOutcome,
    HumanTaskSpec,
    ProcessSpec,
    ProcessStepSpec,
    ProcessTriggerKind,
    ProcessTriggerSpec,
    StepKind,
)

# ============================================================================
# Direct module import to avoid mcp.server dependency
# ============================================================================

_process_module = None


def _import_module():
    """Import process handlers module directly."""
    global _process_module

    if _process_module is not None:
        return

    # Mock the MCP server packages to prevent import errors
    _mocked = [
        "mcp",
        "mcp.server",
        "mcp.server.fastmcp",
        "dazzle.mcp",
        "dazzle.mcp.server",
        "dazzle.mcp.server.handlers",
        "dazzle.mcp.server.handlers.common",
        "dazzle.mcp.server.handlers.utils",
        "dazzle.mcp.server.progress",
    ]
    _orig = {k: sys.modules.get(k) for k in _mocked}
    for k in _mocked:
        sys.modules[k] = MagicMock(pytest_plugins=[])

    # Import the diagrams submodule directly (avoids loading the full package)
    src_path = Path(__file__).parent.parent.parent / "src"
    pkg_dir = src_path / "dazzle" / "mcp" / "server" / "handlers" / "process"

    # Import _helpers first so diagrams.py's `from . import _helpers` resolves
    helpers_path = pkg_dir / "_helpers.py"
    helpers_spec = importlib.util.spec_from_file_location(
        "dazzle.mcp.server.handlers.process._helpers",
        helpers_path,
        submodule_search_locations=[],
    )
    _helpers_module = importlib.util.module_from_spec(helpers_spec)
    _helpers_module.__package__ = "dazzle.mcp.server.handlers.process"
    sys.modules["dazzle.mcp.server.handlers.process._helpers"] = _helpers_module

    process_pkg = MagicMock(pytest_plugins=[])
    process_pkg._helpers = _helpers_module
    sys.modules["dazzle.mcp.server.handlers.process"] = process_pkg

    helpers_spec.loader.exec_module(_helpers_module)

    module_path = pkg_dir / "diagrams.py"

    spec = importlib.util.spec_from_file_location(
        "dazzle.mcp.server.handlers.process.diagrams",
        module_path,
        submodule_search_locations=[],
    )
    _process_module = importlib.util.module_from_spec(spec)
    _process_module.__package__ = "dazzle.mcp.server.handlers.process"
    sys.modules["dazzle.mcp.server.handlers.process.diagrams"] = _process_module
    spec.loader.exec_module(_process_module)

    # Restore sys.modules to prevent pollution of other tests
    for k, v in _orig.items():
        if v is None:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v


# Import the module
_import_module()


def _generate_process_mermaid(proc, include_compensations=False, diagram_type="flowchart"):
    return _process_module._generate_process_mermaid(
        proc, include_compensations=include_compensations, diagram_type=diagram_type
    )


def _get_step_label(step):
    return _process_module._get_step_label(step)


def _get_trigger_label(proc):
    return _process_module._get_trigger_label(proc)


class TestGetTriggerLabel:
    """Tests for trigger label generation."""

    def test_entity_event_trigger(self):
        """Test entity event trigger label."""
        proc = ProcessSpec(
            name="test",
            trigger=ProcessTriggerSpec(
                kind=ProcessTriggerKind.ENTITY_EVENT,
                entity_name="Order",
                event_type="created",
            ),
        )
        label = _get_trigger_label(proc)
        assert label == "Order.created"

    def test_status_transition_trigger(self):
        """Test status transition trigger label."""
        proc = ProcessSpec(
            name="test",
            trigger=ProcessTriggerSpec(
                kind=ProcessTriggerKind.ENTITY_STATUS_TRANSITION,
                entity_name="Task",
                from_status="pending",
                to_status="completed",
            ),
        )
        label = _get_trigger_label(proc)
        assert "Task" in label
        assert "pending" in label
        assert "completed" in label

    def test_cron_trigger(self):
        """Test cron schedule trigger label."""
        proc = ProcessSpec(
            name="test",
            trigger=ProcessTriggerSpec(
                kind=ProcessTriggerKind.SCHEDULE_CRON,
                cron="0 8 * * *",
            ),
        )
        label = _get_trigger_label(proc)
        assert "cron" in label
        assert "0 8 * * *" in label

    def test_manual_trigger(self):
        """Test manual trigger label."""
        proc = ProcessSpec(
            name="test",
            trigger=ProcessTriggerSpec(kind=ProcessTriggerKind.MANUAL),
        )
        label = _get_trigger_label(proc)
        assert label == "Manual"

    def test_no_trigger(self):
        """Test label when no trigger defined."""
        proc = ProcessSpec(name="test")
        label = _get_trigger_label(proc)
        assert label == "Manual Start"


class TestGetStepLabel:
    """Tests for step label generation."""

    def test_service_step_label(self):
        """Test service step uses service name."""
        step = ProcessStepSpec(name="validate", kind=StepKind.SERVICE, service="validate_order")
        label = _get_step_label(step)
        assert label == "validate_order"

    def test_send_step_label(self):
        """Test send step shows message."""
        step = ProcessStepSpec(
            name="notify", kind=StepKind.SEND, channel="email", message="order_confirmation"
        )
        label = _get_step_label(step)
        assert "Send" in label
        assert "order_confirmation" in label

    def test_wait_signal_label(self):
        """Test wait step waiting for signal."""
        step = ProcessStepSpec(name="wait", kind=StepKind.WAIT, wait_for_signal="payment_confirmed")
        label = _get_step_label(step)
        assert "Wait" in label
        assert "payment_confirmed" in label

    def test_wait_duration_label(self):
        """Test wait step with duration."""
        step = ProcessStepSpec(name="wait", kind=StepKind.WAIT, wait_duration_seconds=30)
        label = _get_step_label(step)
        assert "Wait" in label
        assert "30" in label

    def test_human_task_label(self):
        """Test human task step shows icon."""
        step = ProcessStepSpec(
            name="approve",
            kind=StepKind.HUMAN_TASK,
            human_task=HumanTaskSpec(surface="approval_form", assignee_role="manager"),
        )
        label = _get_step_label(step)
        assert "approval_form" in label

    def test_subprocess_label(self):
        """Test subprocess step shows target."""
        step = ProcessStepSpec(name="sub", kind=StepKind.SUBPROCESS, subprocess="child_process")
        label = _get_step_label(step)
        assert "child_process" in label

    def test_condition_label(self):
        """Test condition step shows expression."""
        step = ProcessStepSpec(
            name="check", kind=StepKind.CONDITION, condition="order.total > 1000"
        )
        label = _get_step_label(step)
        assert "?" in label
        assert "order.total" in label


class TestGenerateProcessMermaid:
    """Tests for Mermaid diagram generation."""

    def test_empty_process(self):
        """Test diagram for process with no steps."""
        proc = ProcessSpec(name="empty_process", title="Empty Process")
        diagram = _generate_process_mermaid(proc)

        assert "flowchart TD" in diagram
        assert "empty_process" in diagram
        assert "START" in diagram
        assert "COMPLETE" in diagram

    def test_simple_linear_process(self):
        """Test diagram for simple linear process."""
        proc = ProcessSpec(
            name="linear_process",
            title="Linear Process",
            steps=[
                ProcessStepSpec(name="step1", kind=StepKind.SERVICE, service="service_a"),
                ProcessStepSpec(name="step2", kind=StepKind.SERVICE, service="service_b"),
                ProcessStepSpec(name="step3", kind=StepKind.SERVICE, service="service_c"),
            ],
        )
        diagram = _generate_process_mermaid(proc)

        assert "flowchart TD" in diagram
        assert "step1" in diagram
        assert "step2" in diagram
        assert "step3" in diagram
        assert "START --> step1" in diagram
        assert "step1 --> step2" in diagram
        assert "step2 --> step3" in diagram
        assert "step3 --> COMPLETE" in diagram

    def test_process_with_trigger(self):
        """Test diagram shows trigger in start node."""
        proc = ProcessSpec(
            name="triggered_process",
            trigger=ProcessTriggerSpec(
                kind=ProcessTriggerKind.ENTITY_EVENT,
                entity_name="Order",
                event_type="created",
            ),
            steps=[
                ProcessStepSpec(name="process", kind=StepKind.SERVICE, service="process_order"),
            ],
        )
        diagram = _generate_process_mermaid(proc)

        assert "Order.created" in diagram

    def test_process_with_human_task(self):
        """Test diagram renders human tasks correctly."""
        proc = ProcessSpec(
            name="approval_process",
            steps=[
                ProcessStepSpec(
                    name="review",
                    kind=StepKind.HUMAN_TASK,
                    human_task=HumanTaskSpec(
                        surface="review_form",
                        assignee_role="reviewer",
                        outcomes=[
                            HumanTaskOutcome(name="approve", label="Approve", goto="complete"),
                            HumanTaskOutcome(name="reject", label="Reject", goto="reject_handler"),
                        ],
                    ),
                ),
            ],
        )
        diagram = _generate_process_mermaid(proc)

        assert "review" in diagram
        # Human tasks use trapezoid shape
        assert "[/" in diagram

    def test_process_with_condition(self):
        """Test diagram renders conditions as branches."""
        proc = ProcessSpec(
            name="conditional_process",
            steps=[
                ProcessStepSpec(
                    name="check_amount",
                    kind=StepKind.CONDITION,
                    condition="amount > 1000",
                    on_true="high_value",
                    on_false="standard",
                ),
                ProcessStepSpec(name="high_value", kind=StepKind.SERVICE, service="high_value_svc"),
                ProcessStepSpec(name="standard", kind=StepKind.SERVICE, service="standard_svc"),
            ],
        )
        diagram = _generate_process_mermaid(proc)

        assert "check_amount" in diagram
        # Condition uses diamond shape
        assert "{" in diagram
        # Should have Yes/No branches
        assert "Yes" in diagram
        assert "No" in diagram

    def test_process_with_parallel_steps(self):
        """Test diagram renders parallel blocks."""
        proc = ProcessSpec(
            name="parallel_process",
            steps=[
                ProcessStepSpec(
                    name="parallel_block",
                    kind=StepKind.PARALLEL,
                    parallel_steps=[
                        ProcessStepSpec(name="task_a", kind=StepKind.SERVICE, service="svc_a"),
                        ProcessStepSpec(name="task_b", kind=StepKind.SERVICE, service="svc_b"),
                    ],
                ),
            ],
        )
        diagram = _generate_process_mermaid(proc)

        assert "parallel_block" in diagram
        assert "task_a" in diagram
        assert "task_b" in diagram
        # Parallel uses subgraph
        assert "subgraph" in diagram
        assert "direction LR" in diagram

    def test_process_with_compensations(self):
        """Test diagram includes compensations when requested."""
        proc = ProcessSpec(
            name="saga_process",
            steps=[
                ProcessStepSpec(
                    name="step1",
                    kind=StepKind.SERVICE,
                    service="svc1",
                    compensate_with="undo_step1",
                ),
            ],
            compensations=[
                CompensationSpec(name="undo_step1", service="rollback_svc1"),
            ],
        )

        # Without compensations
        diagram_no_comp = _generate_process_mermaid(proc, include_compensations=False)
        assert "compensations" not in diagram_no_comp

        # With compensations
        diagram_with_comp = _generate_process_mermaid(proc, include_compensations=True)
        assert "compensations" in diagram_with_comp
        assert "undo_step1" in diagram_with_comp

    def test_process_with_error_flow(self):
        """Test diagram shows error flow edges."""
        proc = ProcessSpec(
            name="error_handling",
            steps=[
                ProcessStepSpec(
                    name="risky_step",
                    kind=StepKind.SERVICE,
                    service="risky_svc",
                    on_failure="error_handler",
                ),
                ProcessStepSpec(
                    name="error_handler", kind=StepKind.SERVICE, service="handle_error"
                ),
            ],
        )
        diagram = _generate_process_mermaid(proc)

        # Should have dotted error edge
        assert "-.->|error|" in diagram

    def test_state_diagram_type(self):
        """Test generating state diagram variant."""
        proc = ProcessSpec(
            name="state_process",
            steps=[
                ProcessStepSpec(name="pending", kind=StepKind.SERVICE, service="svc1"),
                ProcessStepSpec(name="processing", kind=StepKind.SERVICE, service="svc2"),
            ],
        )
        diagram = _generate_process_mermaid(proc, diagram_type="stateDiagram")

        assert "stateDiagram-v2" in diagram
        assert "[*] --> pending" in diagram
        assert "pending:" in diagram
        assert "processing:" in diagram

    def test_styling_classes(self):
        """Test that styling classes are applied."""
        proc = ProcessSpec(
            name="styled_process",
            steps=[
                ProcessStepSpec(name="svc", kind=StepKind.SERVICE, service="my_svc"),
                ProcessStepSpec(
                    name="task",
                    kind=StepKind.HUMAN_TASK,
                    human_task=HumanTaskSpec(surface="form"),
                ),
                ProcessStepSpec(name="wait", kind=StepKind.WAIT, wait_duration_seconds=10),
            ],
        )
        diagram = _generate_process_mermaid(proc)

        assert "classDef serviceStep" in diagram
        assert "classDef humanTask" in diagram
        assert "classDef waitStep" in diagram
        assert "class svc serviceStep" in diagram
        assert "class task humanTask" in diagram
        assert "class wait waitStep" in diagram
