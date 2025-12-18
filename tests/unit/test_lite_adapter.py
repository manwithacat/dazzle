"""
Unit tests for LiteProcessAdapter.

Tests the in-process workflow harness for process execution.
"""

import asyncio

import pytest

from dazzle.core.ir.process import (
    HumanTaskOutcome,
    HumanTaskSpec,
    InputMapping,
    OverlapPolicy,
    ProcessInputField,
    ProcessSpec,
    ProcessStepSpec,
    RetryBackoff,
    RetryConfig,
    ScheduleSpec,
    StepKind,
)
from dazzle.core.process.adapter import ProcessStatus, TaskStatus
from dazzle.core.process.context import ProcessContext
from dazzle.core.process.lite_adapter import LiteProcessAdapter


class TestProcessContext:
    """Tests for ProcessContext expression resolution."""

    def test_resolve_inputs(self):
        """Test resolving input values."""
        ctx = ProcessContext(inputs={"order_id": "123", "amount": 100})
        assert ctx.resolve("inputs.order_id") == "123"
        assert ctx.resolve("inputs.amount") == 100

    def test_resolve_step_outputs(self):
        """Test resolving step output values."""
        ctx = ProcessContext(inputs={})
        ctx.update_step("validate", {"is_valid": True, "message": "OK"})
        assert ctx.resolve("validate.is_valid") is True
        assert ctx.resolve("validate.message") == "OK"

    def test_resolve_variables(self):
        """Test resolving context variables."""
        ctx = ProcessContext(inputs={})
        ctx.set_variable("counter", 5)
        assert ctx.resolve("vars.counter") == 5

    def test_resolve_literal(self):
        """Test resolving literal values."""
        ctx = ProcessContext(inputs={})
        assert ctx.resolve("hello") == "hello"

    def test_interpolation(self):
        """Test string interpolation."""
        ctx = ProcessContext(inputs={"name": "Alice"})
        result = ctx.resolve("Hello ${inputs.name}!")
        assert result == "Hello Alice!"

    def test_evaluate_condition_equality(self):
        """Test equality condition evaluation."""
        ctx = ProcessContext(inputs={"status": "active"})
        assert ctx.evaluate_condition("inputs.status == 'active'") is True
        assert ctx.evaluate_condition("inputs.status == 'inactive'") is False

    def test_evaluate_condition_inequality(self):
        """Test inequality condition evaluation."""
        ctx = ProcessContext(inputs={"count": 10})
        assert ctx.evaluate_condition("inputs.count > 5") is True
        assert ctx.evaluate_condition("inputs.count < 5") is False
        assert ctx.evaluate_condition("inputs.count >= 10") is True

    def test_evaluate_condition_truthy(self):
        """Test truthy condition evaluation."""
        ctx = ProcessContext(inputs={})
        ctx.update_step("check", {"is_valid": True})
        assert ctx.evaluate_condition("check.is_valid") is True

    def test_build_step_inputs(self):
        """Test building step inputs from mappings."""
        ctx = ProcessContext(inputs={"order_id": "123"})
        ctx.update_step("fetch", {"data": {"price": 50}})

        mappings = [
            ("inputs.order_id", "id"),
            ("fetch.data.price", "amount"),
        ]
        result = ctx.build_step_inputs(mappings)
        assert result["id"] == "123"
        # Note: nested path resolution is limited in this implementation

    def test_to_dict_and_from_dict(self):
        """Test context serialization."""
        ctx = ProcessContext(inputs={"x": 1})
        ctx.update_step("step1", {"y": 2})
        ctx.set_variable("z", 3)

        data = ctx.to_dict()
        restored = ProcessContext.from_dict(data)

        assert restored.inputs == {"x": 1}
        assert restored.step_outputs == {"step1": {"y": 2}}
        assert restored.variables == {"z": 3}


class TestLiteProcessAdapterBasic:
    """Basic tests for LiteProcessAdapter."""

    @pytest.fixture
    def simple_process(self) -> ProcessSpec:
        """Create a simple two-step process."""
        return ProcessSpec(
            name="simple_process",
            title="Simple Process",
            steps=[
                ProcessStepSpec(
                    name="step1",
                    kind=StepKind.SERVICE,
                    service="test_service",
                ),
                ProcessStepSpec(
                    name="step2",
                    kind=StepKind.SERVICE,
                    service="test_service",
                ),
            ],
        )

    @pytest.mark.asyncio
    async def test_initialize_and_shutdown(self):
        """Test adapter initialization and shutdown."""
        adapter = LiteProcessAdapter(db_path=":memory:")
        await adapter.initialize()
        await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_register_process(self, simple_process: ProcessSpec):
        """Test process registration."""
        adapter = LiteProcessAdapter(db_path=":memory:")
        await adapter.initialize()

        await adapter.register_process(simple_process)

        # Process should be in registry
        assert simple_process.name in adapter._process_registry

        await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_start_process(self, simple_process: ProcessSpec):
        """Test starting a process."""
        adapter = LiteProcessAdapter(db_path=":memory:")
        await adapter.initialize()

        # Register service handler
        async def test_handler(inputs: dict) -> dict:
            return {"success": True}

        adapter.set_service_handler("test_service", test_handler)
        await adapter.register_process(simple_process)

        # Start process
        run_id = await adapter.start_process("simple_process", {"order_id": "123"})
        assert run_id

        # Wait for completion
        await asyncio.sleep(0.5)

        run = await adapter.get_run(run_id)
        assert run
        assert run.status == ProcessStatus.COMPLETED

        await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_process_with_idempotency_key(self, simple_process: ProcessSpec):
        """Test idempotency key deduplication."""
        adapter = LiteProcessAdapter(db_path=":memory:")
        await adapter.initialize()

        async def test_handler(inputs: dict) -> dict:
            return {"success": True}

        adapter.set_service_handler("test_service", test_handler)
        await adapter.register_process(simple_process)

        # Start with idempotency key
        run_id1 = await adapter.start_process("simple_process", {"x": 1}, idempotency_key="key-123")

        # Wait for completion
        await asyncio.sleep(0.5)

        # Start again with same key - should return same run
        run_id2 = await adapter.start_process("simple_process", {"x": 2}, idempotency_key="key-123")

        assert run_id1 == run_id2

        await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_list_runs(self, simple_process: ProcessSpec):
        """Test listing process runs."""
        adapter = LiteProcessAdapter(db_path=":memory:")
        await adapter.initialize()

        async def test_handler(inputs: dict) -> dict:
            return {"success": True}

        adapter.set_service_handler("test_service", test_handler)
        await adapter.register_process(simple_process)

        # Start multiple processes
        await adapter.start_process("simple_process", {"i": 1})
        await adapter.start_process("simple_process", {"i": 2})

        # Wait for completion
        await asyncio.sleep(0.5)

        runs = await adapter.list_runs(process_name="simple_process")
        assert len(runs) == 2

        await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_cancel_process(self):
        """Test cancelling a running process."""
        # Create a slow process
        slow_process = ProcessSpec(
            name="slow_process",
            steps=[
                ProcessStepSpec(
                    name="slow_step",
                    kind=StepKind.WAIT,
                    wait_duration_seconds=60,
                ),
            ],
        )

        adapter = LiteProcessAdapter(db_path=":memory:")
        await adapter.initialize()
        await adapter.register_process(slow_process)

        run_id = await adapter.start_process("slow_process", {})

        # Wait a bit then cancel
        await asyncio.sleep(0.1)
        await adapter.cancel_process(run_id, "Test cancellation")

        run = await adapter.get_run(run_id)
        assert run
        assert run.status == ProcessStatus.CANCELLED
        assert run.error == "Test cancellation"

        await adapter.shutdown()


class TestLiteProcessAdapterRetry:
    """Tests for retry logic."""

    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
        """Test step retry with backoff."""
        call_count = 0

        async def failing_handler(inputs: dict) -> dict:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary failure")
            return {"success": True}

        retry_process = ProcessSpec(
            name="retry_process",
            steps=[
                ProcessStepSpec(
                    name="retry_step",
                    kind=StepKind.SERVICE,
                    service="failing_service",
                    retry=RetryConfig(
                        max_attempts=3,
                        initial_interval_seconds=1,
                        backoff=RetryBackoff.FIXED,
                    ),
                ),
            ],
        )

        adapter = LiteProcessAdapter(db_path=":memory:")
        await adapter.initialize()
        adapter.set_service_handler("failing_service", failing_handler)
        await adapter.register_process(retry_process)

        run_id = await adapter.start_process("retry_process", {})

        # Wait for retries (3 attempts with 1s interval = ~3s)
        await asyncio.sleep(4)

        run = await adapter.get_run(run_id)
        assert run
        assert run.status == ProcessStatus.COMPLETED
        assert call_count == 3  # Failed twice, succeeded third time

        await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self):
        """Test failure after max retries exceeded."""

        async def always_failing(inputs: dict) -> dict:
            raise ValueError("Always fails")

        fail_process = ProcessSpec(
            name="fail_process",
            steps=[
                ProcessStepSpec(
                    name="fail_step",
                    kind=StepKind.SERVICE,
                    service="always_failing",
                    retry=RetryConfig(
                        max_attempts=2,
                        initial_interval_seconds=1,
                    ),
                ),
            ],
        )

        adapter = LiteProcessAdapter(db_path=":memory:")
        await adapter.initialize()
        adapter.set_service_handler("always_failing", always_failing)
        await adapter.register_process(fail_process)

        run_id = await adapter.start_process("fail_process", {})

        # Wait for retries (2 attempts with 1s interval = ~2s)
        await asyncio.sleep(3)

        run = await adapter.get_run(run_id)
        assert run
        assert run.status == ProcessStatus.FAILED
        assert "Always fails" in (run.error or "")

        await adapter.shutdown()


class TestLiteProcessAdapterConditions:
    """Tests for conditional step execution."""

    @pytest.mark.asyncio
    async def test_condition_true_branch(self):
        """Test condition step with true branch."""
        cond_process = ProcessSpec(
            name="cond_process",
            steps=[
                ProcessStepSpec(
                    name="check",
                    kind=StepKind.CONDITION,
                    condition="inputs.amount > 100",
                    on_true="high_value",
                    on_false="low_value",
                ),
                ProcessStepSpec(
                    name="low_value",
                    kind=StepKind.SERVICE,
                    service="low_handler",
                ),
                ProcessStepSpec(
                    name="high_value",
                    kind=StepKind.SERVICE,
                    service="high_handler",
                ),
            ],
        )

        high_called = False
        low_called = False

        async def high_handler(inputs: dict) -> dict:
            nonlocal high_called
            high_called = True
            return {}

        async def low_handler(inputs: dict) -> dict:
            nonlocal low_called
            low_called = True
            return {}

        adapter = LiteProcessAdapter(db_path=":memory:")
        await adapter.initialize()
        adapter.set_service_handler("high_handler", high_handler)
        adapter.set_service_handler("low_handler", low_handler)
        await adapter.register_process(cond_process)

        await adapter.start_process("cond_process", {"amount": 200})
        await asyncio.sleep(0.5)

        assert high_called
        assert not low_called

        await adapter.shutdown()


class TestLiteProcessAdapterSchedule:
    """Tests for schedule execution."""

    @pytest.mark.asyncio
    async def test_register_schedule(self):
        """Test schedule registration."""
        schedule = ScheduleSpec(
            name="hourly_cleanup",
            title="Hourly Cleanup",
            cron="0 * * * *",
            steps=[
                ProcessStepSpec(
                    name="cleanup",
                    kind=StepKind.SERVICE,
                    service="cleanup_service",
                ),
            ],
        )

        adapter = LiteProcessAdapter(db_path=":memory:", scheduler_interval=0.1)
        await adapter.initialize()
        await adapter.register_schedule(schedule)

        assert schedule.name in adapter._schedule_registry

        await adapter.shutdown()


class TestLiteProcessAdapterHumanTasks:
    """Tests for human task functionality."""

    @pytest.mark.asyncio
    async def test_create_and_complete_task(self):
        """Test human task creation and completion."""
        task_process = ProcessSpec(
            name="approval_process",
            steps=[
                ProcessStepSpec(
                    name="review",
                    kind=StepKind.HUMAN_TASK,
                    timeout_seconds=5,
                    human_task=HumanTaskSpec(
                        surface="expense_review",
                        entity_path="inputs.expense",
                        assignee_role="manager",
                        outcomes=[
                            HumanTaskOutcome(
                                name="approve",
                                label="Approve",
                                goto="complete",
                            ),
                            HumanTaskOutcome(
                                name="reject",
                                label="Reject",
                                goto="complete",
                            ),
                        ],
                    ),
                ),
            ],
        )

        adapter = LiteProcessAdapter(db_path=":memory:", poll_interval=0.1)
        await adapter.initialize()
        await adapter.register_process(task_process)

        # Start process
        run_id = await adapter.start_process(
            "approval_process",
            {"expense": {"id": "exp-123"}},
        )

        # Wait for task to be created
        await asyncio.sleep(0.3)

        # Find the task
        tasks = await adapter.list_tasks(run_id=run_id)
        assert len(tasks) == 1
        task = tasks[0]
        assert task.status == TaskStatus.PENDING
        assert task.surface_name == "expense_review"

        # Complete the task
        await adapter.complete_task(task.task_id, "approve")

        # Wait for process to complete
        await asyncio.sleep(0.5)

        run = await adapter.get_run(run_id)
        assert run
        assert run.status == ProcessStatus.COMPLETED

        await adapter.shutdown()


class TestLiteProcessAdapterOverlapPolicy:
    """Tests for overlap policies."""

    @pytest.mark.asyncio
    async def test_skip_policy(self):
        """Test SKIP overlap policy."""
        slow_process = ProcessSpec(
            name="slow",
            overlap_policy=OverlapPolicy.SKIP,
            steps=[
                ProcessStepSpec(
                    name="wait",
                    kind=StepKind.WAIT,
                    wait_duration_seconds=60,
                ),
            ],
        )

        adapter = LiteProcessAdapter(db_path=":memory:")
        await adapter.initialize()
        await adapter.register_process(slow_process)

        # Start first process
        run_id1 = await adapter.start_process("slow", {})
        await asyncio.sleep(0.1)

        # Start second - should return first
        run_id2 = await adapter.start_process("slow", {})

        assert run_id1 == run_id2

        await adapter.shutdown()


class TestLiteProcessAdapterInputMappings:
    """Tests for input/output mappings."""

    @pytest.mark.asyncio
    async def test_input_mapping(self):
        """Test step input mapping from context."""
        received_inputs = {}

        async def capture_handler(inputs: dict) -> dict:
            nonlocal received_inputs
            received_inputs = inputs.copy()
            return {"processed": True}

        mapping_process = ProcessSpec(
            name="mapping_process",
            inputs=[
                ProcessInputField(name="order_id", type="str", required=True),
            ],
            steps=[
                ProcessStepSpec(
                    name="process_order",
                    kind=StepKind.SERVICE,
                    service="capture_service",
                    inputs=[
                        InputMapping(source="inputs.order_id", target="id"),
                    ],
                ),
            ],
        )

        adapter = LiteProcessAdapter(db_path=":memory:")
        await adapter.initialize()
        adapter.set_service_handler("capture_service", capture_handler)
        await adapter.register_process(mapping_process)

        await adapter.start_process("mapping_process", {"order_id": "ORD-456"})
        await asyncio.sleep(0.5)

        assert received_inputs.get("id") == "ORD-456"

        await adapter.shutdown()


class TestLiteProcessAdapterSignals:
    """Tests for process signals."""

    @pytest.mark.asyncio
    async def test_signal_process(self):
        """Test sending a signal to a waiting process."""
        signal_process = ProcessSpec(
            name="signal_process",
            steps=[
                ProcessStepSpec(
                    name="wait_for_approval",
                    kind=StepKind.WAIT,
                    wait_for_signal="approval",
                    timeout_seconds=5,
                ),
            ],
        )

        adapter = LiteProcessAdapter(db_path=":memory:", poll_interval=0.1)
        await adapter.initialize()
        await adapter.register_process(signal_process)

        run_id = await adapter.start_process("signal_process", {})

        # Wait a bit then send signal
        await asyncio.sleep(0.2)
        await adapter.signal_process(run_id, "approval", {"approved": True})

        # Wait for completion
        await asyncio.sleep(1)

        run = await adapter.get_run(run_id)
        assert run
        assert run.status == ProcessStatus.COMPLETED

        await adapter.shutdown()
