"""
Integration tests for TemporalAdapter.

These tests verify the Temporal workflow execution backend works correctly
with dynamically generated workflows from ProcessSpec.

Note: These tests require the Temporal test server or a running Temporal instance.
Run with: pytest -m temporal tests/integration/test_temporal_adapter.py
"""

from __future__ import annotations

import asyncio

import pytest

from dazzle.core.ir.process import (
    CompensationSpec,
    HumanTaskOutcome,
    HumanTaskSpec,
    InputMapping,
    ProcessSpec,
    ProcessStepSpec,
    RetryConfig,
    StepKind,
)
from dazzle.core.process import (
    ProcessConfig,
    ProcessStatus,
    TaskStatus,
    create_adapter,
    get_backend_info,
)
from dazzle.core.process.factory import TemporalConfig

# Skip all tests if temporalio is not installed
pytest.importorskip("temporalio")


@pytest.fixture
def simple_process_spec() -> ProcessSpec:
    """Create a simple process spec for testing."""
    return ProcessSpec(
        name="test_simple_process",
        description="A simple test process",
        trigger="on_create",
        entity_name="TestEntity",
        steps=[
            ProcessStepSpec(
                name="step1",
                kind=StepKind.SERVICE,
                service="test_service",
                inputs=[InputMapping(source="inputs.initial_value", target="value")],
            ),
            ProcessStepSpec(
                name="step2",
                kind=StepKind.WAIT,
                wait_duration_seconds=1,
            ),
            ProcessStepSpec(
                name="step3",
                kind=StepKind.SERVICE,
                service="final_service",
            ),
        ],
    )


@pytest.fixture
def process_with_human_task() -> ProcessSpec:
    """Create a process spec with human task step."""
    return ProcessSpec(
        name="approval_process",
        description="Process with approval step",
        trigger="on_create",
        entity_name="Expense",
        steps=[
            ProcessStepSpec(
                name="submit",
                kind=StepKind.SERVICE,
                service="validate_expense",
            ),
            ProcessStepSpec(
                name="manager_review",
                kind=StepKind.HUMAN_TASK,
                human_task=HumanTaskSpec(
                    surface="expense_review_form",
                    entity_path="inputs.expense_id",
                    assignee_expression="inputs.manager_id",
                    timeout_seconds=3600,
                    outcomes=[
                        HumanTaskOutcome(
                            name="approve", label="Approve", goto="complete", style="primary"
                        ),
                        HumanTaskOutcome(
                            name="reject", label="Reject", goto="fail", style="danger"
                        ),
                    ],
                ),
                timeout_seconds=60,
            ),
            ProcessStepSpec(
                name="finalize",
                kind=StepKind.SERVICE,
                service="process_approval",
            ),
        ],
    )


@pytest.fixture
def process_with_retry() -> ProcessSpec:
    """Create a process spec with retry configuration."""
    return ProcessSpec(
        name="retry_process",
        description="Process with retry logic",
        trigger="manual",
        entity_name="Job",
        steps=[
            ProcessStepSpec(
                name="flaky_step",
                kind=StepKind.SERVICE,
                service="flaky_service",
                retry=RetryConfig(
                    max_attempts=3,
                    initial_interval_seconds=1,
                    max_interval_seconds=10,
                    backoff_coefficient=2.0,
                ),
            ),
        ],
    )


@pytest.fixture
def process_with_compensation() -> ProcessSpec:
    """Create a process spec with compensation handlers."""
    return ProcessSpec(
        name="saga_process",
        description="Process with saga compensation",
        trigger="manual",
        entity_name="Order",
        steps=[
            ProcessStepSpec(
                name="reserve_inventory",
                kind=StepKind.SERVICE,
                service="inventory_service",
                compensate_with="release_inventory",
            ),
            ProcessStepSpec(
                name="charge_payment",
                kind=StepKind.SERVICE,
                service="payment_service",
                compensate_with="refund_payment",
            ),
            ProcessStepSpec(
                name="ship_order",
                kind=StepKind.SERVICE,
                service="shipping_service",
            ),
        ],
        compensations=[
            CompensationSpec(
                name="release_inventory",
                service="inventory_service",
            ),
            CompensationSpec(
                name="refund_payment",
                service="payment_service",
            ),
        ],
    )


class TestProcessFactory:
    """Tests for the process adapter factory."""

    def test_get_backend_info_lite(self) -> None:
        """Test backend info when only lite is available."""
        config = ProcessConfig(backend="lite")
        info = get_backend_info(config)

        assert info["configured_backend"] == "lite"
        assert info["lite_available"] is True

    def test_get_backend_info_with_temporal(self) -> None:
        """Test backend info shows Temporal SDK status."""
        config = ProcessConfig(backend="auto")
        info = get_backend_info(config)

        # Temporal SDK should be installed for these tests
        assert info["temporal_sdk_installed"] is True
        assert "temporal_sdk_version" in info

    def test_create_lite_adapter(self) -> None:
        """Test creating LiteProcessAdapter via factory."""
        config = ProcessConfig(backend="lite")
        adapter = create_adapter(config)

        from dazzle.core.process import LiteProcessAdapter

        assert isinstance(adapter, LiteProcessAdapter)

    def test_create_adapter_auto_without_server(self) -> None:
        """Test auto selection falls back to lite when Temporal unavailable."""
        config = ProcessConfig(
            backend="auto",
            temporal=TemporalConfig(host="nonexistent.local", port=7233),
        )
        adapter = create_adapter(config)

        from dazzle.core.process import LiteProcessAdapter

        assert isinstance(adapter, LiteProcessAdapter)


class TestTemporalAdapterUnit:
    """Unit tests for TemporalAdapter (no server required)."""

    def test_temporal_adapter_import(self) -> None:
        """Test TemporalAdapter can be imported."""
        from dazzle.core.process.temporal_adapter import TemporalAdapter

        assert TemporalAdapter is not None

    def test_temporal_adapter_init(self) -> None:
        """Test TemporalAdapter initialization."""
        from dazzle.core.process.temporal_adapter import TemporalAdapter

        adapter = TemporalAdapter(
            host="localhost",
            port=7233,
            namespace="test",
            task_queue="test-queue",
        )

        assert adapter._host == "localhost"
        assert adapter._port == 7233
        assert adapter._namespace == "test"
        assert adapter._task_queue == "test-queue"
        assert adapter._initialized is False

    def test_workflow_generation(self, simple_process_spec: ProcessSpec) -> None:
        """Test workflow class generation from ProcessSpec."""
        from dazzle.core.process.temporal_adapter import TemporalAdapter

        adapter = TemporalAdapter()

        # Generate workflow class
        workflow_cls = adapter._generate_workflow(simple_process_spec)

        assert workflow_cls is not None
        assert hasattr(workflow_cls, "run")


class TestActivities:
    """Tests for shared Temporal activities."""

    @pytest.mark.asyncio
    async def test_create_human_task_activity(self) -> None:
        """Test human task creation activity."""
        from dazzle.core.process.activities import (
            _task_store,
            clear_task_store,
        )

        # Clear store first
        clear_task_store()

        # Import activity function directly for unit testing
        from dazzle.core.process.activities import _TEMPORAL_AVAILABLE

        if not _TEMPORAL_AVAILABLE:
            pytest.skip("Temporal activities not available")

        # Activities are registered, but we test the underlying logic
        from datetime import UTC, datetime

        # Create a mock task directly in store for testing
        from dazzle.core.process import ProcessTask
        from dazzle.core.process.activities import (
            complete_task_in_db,
            get_task_from_db,
            list_tasks_from_db,
        )

        task = ProcessTask(
            task_id="test-task-1",
            run_id="workflow-123",
            step_name="review_step",
            surface_name="review_form",
            entity_name="Document",
            entity_id="doc-1",
            due_at=datetime.now(UTC),
        )
        _task_store[task.task_id] = task

        # Test get
        result = await get_task_from_db("test-task-1")
        assert result is not None
        assert result.task_id == "test-task-1"

        # Test list
        tasks = await list_tasks_from_db(run_id="workflow-123")
        assert len(tasks) == 1

        # Test complete
        await complete_task_in_db("test-task-1", "approved")
        updated = await get_task_from_db("test-task-1")
        assert updated is not None
        assert updated.status == TaskStatus.COMPLETED
        assert updated.outcome == "approved"

        # Cleanup
        clear_task_store()


@pytest.mark.temporal
@pytest.mark.integration
class TestTemporalAdapterIntegration:
    """
    Integration tests requiring a running Temporal server.

    These tests are skipped if Temporal is not reachable.
    Run Temporal locally: docker-compose -f docker-compose.temporal.yml up -d
    """

    @pytest.fixture(autouse=True)
    def check_temporal_server(self) -> None:
        """Skip tests if Temporal server is not available."""
        import socket

        try:
            sock = socket.create_connection(("localhost", 7233), timeout=2)
            sock.close()
        except OSError:
            pytest.skip("Temporal server not available at localhost:7233")

    @pytest.mark.asyncio
    async def test_connect_to_temporal(self) -> None:
        """Test connecting to Temporal server."""
        from dazzle.core.process.temporal_adapter import TemporalAdapter

        adapter = TemporalAdapter()
        await adapter.initialize()

        assert adapter._initialized is True
        assert adapter._client is not None

        await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_register_process(self, simple_process_spec: ProcessSpec) -> None:
        """Test registering a process spec."""
        from dazzle.core.process.temporal_adapter import TemporalAdapter

        adapter = TemporalAdapter()
        await adapter.initialize()

        try:
            await adapter.register_process(simple_process_spec)

            assert simple_process_spec.name in adapter._registry
            assert simple_process_spec.name in adapter._workflows
        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_start_workflow(self, simple_process_spec: ProcessSpec) -> None:
        """Test starting a workflow execution."""
        from dazzle.core.process.temporal_adapter import TemporalAdapter

        adapter = TemporalAdapter()
        await adapter.initialize()

        try:
            await adapter.register_process(simple_process_spec)
            await adapter.start_worker()

            # Start workflow
            run_id = await adapter.start_process(
                simple_process_spec.name,
                {"initial_value": "test"},
                idempotency_key="test-run-1",
            )

            assert run_id == "test-run-1"

            # Get run status
            run = await adapter.get_run(run_id)
            assert run is not None
            assert run.run_id == run_id

        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_cancel_workflow(self, simple_process_spec: ProcessSpec) -> None:
        """Test canceling a running workflow."""
        from dazzle.core.process.temporal_adapter import TemporalAdapter

        adapter = TemporalAdapter()
        await adapter.initialize()

        try:
            await adapter.register_process(simple_process_spec)
            await adapter.start_worker()

            # Start and immediately cancel
            run_id = await adapter.start_process(
                simple_process_spec.name,
                {"initial_value": "test"},
            )

            await adapter.cancel_process(run_id, "Test cancellation")

            # Verify cancelled
            await asyncio.sleep(1)  # Allow time for cancellation to propagate
            run = await adapter.get_run(run_id)
            assert run is not None
            assert run.status == ProcessStatus.CANCELLED

        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_human_task_signal(self, process_with_human_task: ProcessSpec) -> None:
        """Test human task completion via signal."""
        from dazzle.core.process.temporal_adapter import TemporalAdapter

        adapter = TemporalAdapter()
        await adapter.initialize()

        try:
            await adapter.register_process(process_with_human_task)
            await adapter.start_worker()

            # Start approval workflow
            run_id = await adapter.start_process(
                process_with_human_task.name,
                {"expense_id": "exp-123", "manager_id": "mgr-1"},
            )

            # Wait for workflow to reach human task
            await asyncio.sleep(2)

            # Send completion signal
            await adapter.signal_process(
                run_id,
                "task_completed",
                {
                    "step_name": "manager_review",
                    "outcome": "approve",
                    "outcome_data": {"comment": "Looks good"},
                },
            )

            # Wait for workflow to complete
            await asyncio.sleep(2)

            run = await adapter.get_run(run_id)
            assert run is not None
            # Workflow should have progressed past human task

        finally:
            await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_list_workflows(self, simple_process_spec: ProcessSpec) -> None:
        """Test listing workflow executions."""
        from dazzle.core.process.temporal_adapter import TemporalAdapter

        adapter = TemporalAdapter()
        await adapter.initialize()

        try:
            await adapter.register_process(simple_process_spec)
            await adapter.start_worker()

            # Start multiple workflows
            for i in range(3):
                await adapter.start_process(
                    simple_process_spec.name,
                    {"initial_value": f"test-{i}"},
                )

            # List runs
            runs = await adapter.list_runs(process_name=simple_process_spec.name)
            assert len(runs) >= 3

        finally:
            await adapter.shutdown()


class TestWorkerModule:
    """Tests for the worker entry point module."""

    def test_worker_module_import(self) -> None:
        """Test worker module can be imported."""
        from dazzle.process import worker

        assert hasattr(worker, "main")
        assert hasattr(worker, "run")

    def test_process_module_exports(self) -> None:
        """Test process module exports factory functions."""
        from dazzle.process import (
            LiteProcessAdapter,
            ProcessConfig,
            create_adapter,
            get_backend_info,
        )

        assert ProcessConfig is not None
        assert create_adapter is not None
        assert get_backend_info is not None
        assert LiteProcessAdapter is not None
