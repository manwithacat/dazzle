"""
Temporal implementation of ProcessAdapter.

This module provides production-grade workflow execution using Temporal,
with dynamic workflow generation from ProcessSpec definitions.

Requires: pip install dazzle[temporal]
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from dazzle.core.ir.process import ProcessSpec, ProcessStepSpec, ScheduleSpec, StepKind

from .adapter import (
    ProcessAdapter,
    ProcessRun,
    ProcessStatus,
    ProcessTask,
    TaskStatus,
)

if TYPE_CHECKING:
    from temporalio.client import Client
    from temporalio.worker import Worker

logger = logging.getLogger(__name__)


class TemporalNotAvailable(Exception):
    """Raised when Temporal SDK is not installed."""

    def __init__(self) -> None:
        super().__init__("Temporal SDK not installed. Install with: pip install dazzle[temporal]")


class HumanTaskTimeout(Exception):
    """Raised when a human task times out."""

    def __init__(self, step_name: str) -> None:
        self.step_name = step_name
        super().__init__(f"Human task '{step_name}' timed out")


def _check_temporal_available() -> None:
    """Check if Temporal SDK is available."""
    try:
        import temporalio  # noqa: F401
    except ImportError as e:
        raise TemporalNotAvailable() from e


class TemporalAdapter(ProcessAdapter):
    """
    Temporal implementation of ProcessAdapter.

    Generates Temporal workflows dynamically from ProcessSpec definitions,
    enabling production-grade durable execution with:
    - Automatic retries and timeouts
    - Saga compensation for rollbacks
    - Human task support via signals
    - Full visibility via Temporal UI

    Usage:
        adapter = TemporalAdapter(host="localhost", port=7233)
        await adapter.initialize()

        await adapter.register_process(expense_approval_spec)

        run_id = await adapter.start_process("expense_approval", {"expense_id": "123"})
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 7233,
        namespace: str = "default",
        task_queue: str = "dazzle",
        client: Client | None = None,
    ):
        """
        Initialize TemporalAdapter.

        Args:
            host: Temporal server host
            port: Temporal server gRPC port
            namespace: Temporal namespace
            task_queue: Task queue name for workers
            client: Optional pre-configured Temporal client
        """
        _check_temporal_available()

        self._host = host
        self._port = port
        self._namespace = namespace
        self._task_queue = task_queue
        self._external_client = client
        self._client: Client | None = None
        self._worker: Worker | None = None
        self._registry: dict[str, ProcessSpec] = {}
        self._schedules: dict[str, ScheduleSpec] = {}
        self._workflows: dict[str, type] = {}
        self._activities: list[Callable[..., Any]] = []
        self._initialized = False

    async def initialize(self) -> None:
        """Connect to Temporal and prepare for workflow execution."""
        if self._initialized:
            return

        from temporalio.client import Client

        if self._external_client:
            self._client = self._external_client
        else:
            self._client = await Client.connect(
                f"{self._host}:{self._port}",
                namespace=self._namespace,
            )

        self._initialized = True
        logger.info(
            f"Connected to Temporal at {self._host}:{self._port}, namespace={self._namespace}"
        )

    async def start_worker(self) -> None:
        """Start the Temporal worker to execute workflows."""
        if not self._client:
            raise RuntimeError("Adapter not initialized. Call initialize() first.")

        from temporalio.worker import Worker

        # Import shared activities
        from .activities import get_all_activities

        all_activities = list(self._activities) + get_all_activities()

        self._worker = Worker(
            self._client,
            task_queue=self._task_queue,
            workflows=list(self._workflows.values()),
            activities=all_activities,
        )

        logger.info(
            f"Starting Temporal worker on queue '{self._task_queue}' "
            f"with {len(self._workflows)} workflows and {len(all_activities)} activities"
        )

        # Run in background task
        import asyncio

        asyncio.create_task(self._worker.run())

    async def shutdown(self) -> None:
        """Graceful shutdown of worker and client."""
        if self._worker:
            # Request graceful shutdown
            self._worker.shutdown()
            logger.info("Temporal worker shutdown initiated")

        # Note: Temporal SDK handles cleanup automatically
        self._initialized = False

    # Process Registration
    async def register_process(self, spec: ProcessSpec) -> None:
        """
        Register a process definition by generating a Temporal workflow.

        Args:
            spec: ProcessSpec from DSL parsing
        """
        self._registry[spec.name] = spec

        # Generate workflow class from spec
        workflow_class = self._generate_workflow(spec)
        self._workflows[spec.name] = workflow_class

        # Generate activities for service steps
        for step in spec.steps:
            if step.kind == StepKind.SERVICE:
                activity_fn = self._generate_service_activity(spec.name, step)
                self._activities.append(activity_fn)

        logger.info(f"Registered process '{spec.name}' with {len(spec.steps)} steps")

    async def register_schedule(self, spec: ScheduleSpec) -> None:
        """Register a scheduled workflow.

        ScheduleSpec in DAZZLE contains its own steps, not a reference to a process.
        We generate a workflow from the schedule's steps and create a Temporal schedule.
        """
        self._schedules[spec.name] = spec

        if not self._client:
            logger.warning(
                f"Schedule '{spec.name}' registered but client not connected. "
                "Call initialize() to activate schedules."
            )
            return

        # Create Temporal schedule
        from temporalio.client import (
            Schedule,
            ScheduleActionStartWorkflow,
            ScheduleIntervalSpec,
        )
        from temporalio.client import ScheduleSpec as TScheduleSpec

        # Build schedule spec
        intervals: list[ScheduleIntervalSpec] = []
        if spec.cron:
            # TODO: Convert cron to Temporal cron schedule
            pass

        if spec.interval_seconds:
            intervals.append(ScheduleIntervalSpec(every=timedelta(seconds=spec.interval_seconds)))

        schedule_spec = TScheduleSpec(intervals=intervals)

        # ScheduleSpec has its own steps, not a process_name reference
        # We use the schedule name as the workflow name
        action = ScheduleActionStartWorkflow(
            spec.name,  # Use schedule name as workflow name
            args=[{}],  # Empty inputs for scheduled runs
            id=f'scheduled-{spec.name}-{{{{.ScheduleTime.Format "20060102T150405"}}}}',
            task_queue=self._task_queue,
        )

        await self._client.create_schedule(
            spec.name,
            Schedule(action=action, spec=schedule_spec),
        )

        logger.info(f"Registered schedule '{spec.name}'")

    def _generate_workflow(self, spec: ProcessSpec) -> type:
        """
        Dynamically generate a Temporal workflow class from ProcessSpec.

        The generated workflow:
        - Executes steps sequentially (or in parallel for parallel blocks)
        - Handles retries per step configuration
        - Runs compensation on failure (saga pattern)
        - Supports human tasks via signals
        """
        from temporalio import workflow

        process_spec = spec  # Capture for closure

        @workflow.defn(name=spec.name)
        class DynamicWorkflow:
            """Generated workflow for ProcessSpec."""

            def __init__(self) -> None:
                self._context: dict[str, Any] = {}
                self._completed_steps: list[str] = []
                self._task_results: dict[str, dict[str, Any]] = {}
                self._signals_received: dict[str, Any] = {}

            @workflow.run  # type: ignore[misc]
            async def run(self, inputs: dict[str, Any]) -> dict[str, Any]:
                """Execute the workflow."""
                self._context = dict(inputs)
                self._context["__run_id"] = workflow.info().workflow_id

                try:
                    for step in process_spec.steps:
                        await self._execute_step(step)

                    outputs: dict[str, Any] = self._context.get("__outputs", {})
                    return outputs

                except Exception:
                    # Run compensation handlers
                    await self._compensate()
                    raise

            async def _execute_step(self, step: ProcessStepSpec) -> None:
                """Execute a single process step."""
                import asyncio

                # Check condition
                if step.condition:
                    if not self._evaluate_condition(step.condition):
                        workflow.logger.info(f"Skipping step '{step.name}' - condition not met")
                        return

                workflow.logger.info(f"Executing step '{step.name}' (kind={step.kind.value})")

                if step.kind == StepKind.SERVICE:
                    result = await self._execute_service_step(step)
                    self._context[step.name] = result

                elif step.kind == StepKind.HUMAN_TASK:
                    result = await self._execute_human_task_step(step)
                    self._context[step.name] = result

                elif step.kind == StepKind.PARALLEL:
                    # Execute parallel steps concurrently
                    if step.parallel_steps:
                        await asyncio.gather(*[self._execute_step(s) for s in step.parallel_steps])
                        # Results captured in context by each step

                elif step.kind == StepKind.WAIT:
                    duration = step.wait_duration_seconds or 60
                    await workflow.sleep(timedelta(seconds=duration))

                elif step.kind == StepKind.CONDITION:
                    # Handle conditional branching via on_true/on_false
                    if step.condition:
                        if self._evaluate_condition(step.condition):
                            if step.on_true:
                                next_step = process_spec.get_step(step.on_true)
                                if next_step:
                                    await self._execute_step(next_step)
                        elif step.on_false:
                            next_step = process_spec.get_step(step.on_false)
                            if next_step:
                                await self._execute_step(next_step)

                self._completed_steps.append(step.name)

            async def _execute_service_step(self, step: ProcessStepSpec) -> dict[str, Any]:
                """Execute a service step via activity."""
                from temporalio.common import RetryPolicy

                # Build inputs from step configuration
                step_inputs = self._build_step_inputs(step)

                # Build retry policy
                retry_policy = None
                if step.retry:
                    retry_policy = RetryPolicy(
                        maximum_attempts=step.retry.max_attempts,
                        initial_interval=timedelta(seconds=step.retry.initial_interval_seconds),
                        maximum_interval=timedelta(seconds=step.retry.max_interval_seconds),
                        backoff_coefficient=step.retry.backoff_coefficient,
                    )

                timeout = timedelta(seconds=step.timeout_seconds or 300)

                result: dict[str, Any] = await workflow.execute_activity(
                    f"{process_spec.name}.{step.name}",
                    args=[step_inputs],
                    start_to_close_timeout=timeout,
                    retry_policy=retry_policy,
                )
                return result

            async def _execute_human_task_step(self, step: ProcessStepSpec) -> dict[str, Any]:
                """Execute a human task step by waiting for signal."""
                if not step.human_task:
                    raise ValueError(f"Step '{step.name}' has no human_task configuration")

                ht = step.human_task

                # Create human task via activity
                task_params = {
                    "workflow_id": workflow.info().workflow_id,
                    "step_name": step.name,
                    "surface": ht.surface,
                    "entity_path": ht.entity_path,
                    "entity_id": self._resolve_path(ht.entity_path),
                    "assignee_id": self._resolve_path(ht.assignee_expression),
                    "assignee_role": ht.assignee_role,
                    "due_seconds": ht.timeout_seconds,
                    "outcomes": [
                        {"name": o.name, "label": o.label, "style": o.style} for o in ht.outcomes
                    ],
                }

                task_id = await workflow.execute_activity(
                    "create_human_task",
                    args=[task_params],
                    start_to_close_timeout=timedelta(seconds=60),
                )

                # Wait for task completion signal with timeout
                timeout_seconds = step.timeout_seconds or ht.timeout_seconds or 86400
                deadline = workflow.now() + timedelta(seconds=timeout_seconds)

                while workflow.now() < deadline:
                    if step.name in self._task_results:
                        return self._task_results[step.name]

                    # Wait for signal or timeout
                    try:
                        await workflow.wait_condition(
                            lambda: step.name in self._task_results,
                            timeout=timedelta(seconds=min(60, timeout_seconds)),
                        )
                    except TimeoutError:
                        continue

                # Handle timeout - escalate
                await workflow.execute_activity(
                    "escalate_human_task",
                    args=[{"task_id": task_id, "step_name": step.name}],
                    start_to_close_timeout=timedelta(seconds=60),
                )

                raise HumanTaskTimeout(step.name)

            @workflow.signal  # type: ignore[misc]
            async def task_completed(
                self, step_name: str, outcome: str, outcome_data: dict[str, Any] | None = None
            ) -> None:
                """Signal handler for human task completion."""
                self._task_results[step_name] = {
                    "outcome": outcome,
                    "outcome_data": outcome_data or {},
                }
                workflow.logger.info(f"Task '{step_name}' completed with outcome '{outcome}'")

            @workflow.signal  # type: ignore[misc]
            async def external_signal(self, signal_name: str, payload: dict[str, Any]) -> None:
                """Generic signal handler for external events."""
                self._signals_received[signal_name] = payload
                workflow.logger.info(f"Received signal '{signal_name}'")

            @workflow.query  # type: ignore[misc]
            def get_status(self) -> dict[str, Any]:
                """Query handler for workflow status."""
                return {
                    "completed_steps": self._completed_steps,
                    "context_keys": list(self._context.keys()),
                    "pending_tasks": [
                        step.name
                        for step in process_spec.steps
                        if step.kind == StepKind.HUMAN_TASK and step.name not in self._task_results
                    ],
                }

            async def _compensate(self) -> None:
                """Run compensation handlers in reverse order."""
                workflow.logger.info("Running compensation handlers")

                for step_name in reversed(self._completed_steps):
                    step = process_spec.get_step(step_name)
                    if step and step.compensate_with:
                        comp = process_spec.get_compensation(step.compensate_with)
                        if comp:
                            workflow.logger.info(f"Running compensation '{comp.name}'")
                            await workflow.execute_activity(
                                f"{process_spec.name}.compensation.{comp.name}",
                                args=[self._context],
                                start_to_close_timeout=timedelta(
                                    seconds=comp.timeout_seconds or 300
                                ),
                            )

            def _evaluate_condition(self, condition: str) -> bool:
                """Evaluate a step condition against context."""
                # Simple condition evaluation - context variable lookups
                try:
                    # Support "context.var == value" style conditions
                    # This is a simplified evaluator - restricted to context dict only
                    return bool(eval(condition, {"context": self._context}))  # nosec B307
                except Exception:
                    workflow.logger.warning(
                        f"Failed to evaluate condition: {condition}, assuming True"
                    )
                    return True

            def _build_step_inputs(self, step: ProcessStepSpec) -> dict[str, Any]:
                """Build inputs for a service step from context."""
                inputs: dict[str, Any] = {}
                # step.inputs is a list of InputMapping with source/target
                for mapping in step.inputs:
                    inputs[mapping.target] = self._resolve_path(mapping.source)
                return inputs

            def _resolve_path(self, path: str | None) -> Any:
                """Resolve a dotted path against context."""
                if not path:
                    return None

                parts = path.split(".")
                value: Any = self._context

                for part in parts:
                    if isinstance(value, dict):
                        value = value.get(part)
                    else:
                        return None

                return value

        return DynamicWorkflow

    def _generate_service_activity(
        self, process_name: str, step: ProcessStepSpec
    ) -> Callable[[dict[str, Any]], Any]:
        """Generate a Temporal activity for a service step."""
        from temporalio import activity

        activity_name = f"{process_name}.{step.name}"
        service_name = step.service or step.name  # Use step.service, fallback to step name

        @activity.defn(name=activity_name)  # type: ignore[misc]
        async def service_activity(inputs: dict[str, Any]) -> dict[str, Any]:
            """Execute service for step."""
            # TODO: Integrate with service registry
            activity.logger.info(
                f"Executing service '{service_name}' with inputs: {list(inputs.keys())}"
            )

            # Placeholder - actual implementation would call the service
            return {"status": "completed", "inputs_received": list(inputs.keys())}

        # Cast to satisfy type checker - decorated functions are correctly typed at runtime
        result: Callable[[dict[str, Any]], Any] = service_activity
        return result

    # Process Lifecycle
    async def start_process(
        self,
        process_name: str,
        inputs: dict[str, Any],
        idempotency_key: str | None = None,
        dsl_version: str | None = None,
    ) -> str:
        """
        Start a workflow execution.

        Args:
            process_name: Name of the registered process
            inputs: Input values for the workflow
            idempotency_key: Optional workflow ID for deduplication
            dsl_version: DSL version to bind this workflow to (uses versioned task queue)

        Returns:
            workflow_id (run_id): Unique identifier for this execution
        """
        if not self._client:
            raise RuntimeError("Adapter not initialized. Call initialize() first.")

        if process_name not in self._registry:
            raise ValueError(f"Process '{process_name}' not registered")

        workflow_id = idempotency_key or f"{process_name}-{uuid4()}"

        # Use versioned task queue for version isolation
        task_queue = self._task_queue
        if dsl_version:
            task_queue = f"{self._task_queue}_{dsl_version}"

        # Include DSL version in search attributes for querying
        search_attributes = {}
        if dsl_version:
            search_attributes["DslVersion"] = [dsl_version]

        await self._client.start_workflow(
            process_name,
            inputs,
            id=workflow_id,
            task_queue=task_queue,
            search_attributes=search_attributes if search_attributes else None,
        )

        logger.info(
            f"Started workflow '{process_name}' with ID: {workflow_id}"
            + (f" (version: {dsl_version})" if dsl_version else "")
        )

        return workflow_id

    async def get_run(self, run_id: str) -> ProcessRun | None:
        """Get a workflow execution by ID."""
        if not self._client:
            return None

        try:
            handle = self._client.get_workflow_handle(run_id)
            desc = await handle.describe()

            return ProcessRun(
                run_id=run_id,
                process_name=desc.workflow_type or "unknown",
                status=self._map_status(desc.status),
                current_step=None,  # Would need query
                inputs={},
                outputs=None,
                error=None,
                started_at=desc.start_time or datetime.utcnow(),
                completed_at=desc.close_time,
            )
        except Exception as e:
            logger.debug(f"Failed to get workflow {run_id}: {e}")
            return None

    async def list_runs(
        self,
        process_name: str | None = None,
        status: ProcessStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ProcessRun]:
        """List workflow executions."""
        if not self._client:
            return []

        # Build Temporal query
        query_parts = []
        if process_name:
            query_parts.append(f'WorkflowType = "{process_name}"')
        if status:
            temporal_status = self._map_to_temporal_status(status)
            query_parts.append(f'ExecutionStatus = "{temporal_status}"')

        query = " AND ".join(query_parts) if query_parts else None

        runs: list[ProcessRun] = []
        count = 0
        async for workflow in self._client.list_workflows(query=query):
            if count < offset:
                count += 1
                continue
            if len(runs) >= limit:
                break

            runs.append(
                ProcessRun(
                    run_id=workflow.id,
                    process_name=workflow.workflow_type or "unknown",
                    status=self._map_status(workflow.status),
                    started_at=workflow.start_time or datetime.utcnow(),
                    completed_at=workflow.close_time,
                )
            )
            count += 1

        return runs

    async def cancel_process(self, run_id: str, reason: str) -> None:
        """Cancel a running workflow."""
        if not self._client:
            raise RuntimeError("Adapter not initialized")

        handle = self._client.get_workflow_handle(run_id)
        await handle.cancel()
        logger.info(f"Cancelled workflow {run_id}: {reason}")

    async def suspend_process(self, run_id: str) -> None:
        """Suspend is not directly supported in Temporal - use cancel."""
        logger.warning(
            "Suspend not supported for Temporal workflows. "
            "Consider using signals for pause/resume semantics."
        )

    async def resume_process(self, run_id: str) -> None:
        """Resume is not directly supported in Temporal."""
        logger.warning(
            "Resume not supported for Temporal workflows. Use signals for pause/resume semantics."
        )

    # Signals
    async def signal_process(
        self,
        run_id: str,
        signal_name: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Send a signal to a running workflow."""
        if not self._client:
            raise RuntimeError("Adapter not initialized")

        handle = self._client.get_workflow_handle(run_id)
        await handle.signal(signal_name, payload or {})
        logger.info(f"Sent signal '{signal_name}' to workflow {run_id}")

    # Human Tasks
    async def get_task(self, task_id: str) -> ProcessTask | None:
        """Get a human task by ID."""
        # Tasks are stored in database, not Temporal
        from .activities import get_task_from_db

        return await get_task_from_db(task_id)

    async def list_tasks(
        self,
        run_id: str | None = None,
        assignee_id: str | None = None,
        status: TaskStatus | None = None,
        limit: int = 100,
    ) -> list[ProcessTask]:
        """List human tasks."""
        from .activities import list_tasks_from_db

        return await list_tasks_from_db(
            run_id=run_id,
            assignee_id=assignee_id,
            status=status,
            limit=limit,
        )

    async def complete_task(
        self,
        task_id: str,
        outcome: str,
        outcome_data: dict[str, Any] | None = None,
        completed_by: str | None = None,
    ) -> None:
        """Complete a human task by signaling the workflow."""
        # Get task to find workflow
        task = await self.get_task(task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found")

        # Update task in database
        from .activities import complete_task_in_db

        await complete_task_in_db(task_id, outcome, outcome_data, completed_by)

        # Signal the workflow
        if self._client:
            handle = self._client.get_workflow_handle(task.run_id)
            await handle.signal(
                "task_completed",
                task.step_name,
                outcome,
                outcome_data or {},
            )

        logger.info(f"Completed task {task_id} with outcome '{outcome}'")

    async def reassign_task(
        self,
        task_id: str,
        new_assignee_id: str,
        reason: str | None = None,
    ) -> None:
        """Reassign a human task."""
        from .activities import reassign_task_in_db

        await reassign_task_in_db(task_id, new_assignee_id, reason)
        logger.info(f"Reassigned task {task_id} to {new_assignee_id}")

    # Status Mapping
    def _map_status(self, temporal_status: Any) -> ProcessStatus:
        """Map Temporal workflow status to ProcessStatus."""
        from temporalio.client import WorkflowExecutionStatus

        status_map = {
            WorkflowExecutionStatus.RUNNING: ProcessStatus.RUNNING,
            WorkflowExecutionStatus.COMPLETED: ProcessStatus.COMPLETED,
            WorkflowExecutionStatus.FAILED: ProcessStatus.FAILED,
            WorkflowExecutionStatus.CANCELED: ProcessStatus.CANCELLED,
            WorkflowExecutionStatus.TERMINATED: ProcessStatus.CANCELLED,
            WorkflowExecutionStatus.CONTINUED_AS_NEW: ProcessStatus.RUNNING,
            WorkflowExecutionStatus.TIMED_OUT: ProcessStatus.FAILED,
        }
        return status_map.get(temporal_status, ProcessStatus.PENDING)

    def _map_to_temporal_status(self, status: ProcessStatus) -> str:
        """Map ProcessStatus to Temporal query status."""
        status_map = {
            ProcessStatus.RUNNING: "Running",
            ProcessStatus.COMPLETED: "Completed",
            ProcessStatus.FAILED: "Failed",
            ProcessStatus.CANCELLED: "Canceled",
            ProcessStatus.PENDING: "Running",  # Temporal doesn't have pending
        }
        return status_map.get(status, "Running")

    # Version Management
    async def list_runs_by_version(
        self,
        dsl_version: str,
        status: ProcessStatus | None = None,
        limit: int = 100,
    ) -> list[ProcessRun]:
        """List runs for a specific DSL version using search attributes."""
        if not self._client:
            return []

        # Build Temporal query using DslVersion search attribute
        query_parts = [f'DslVersion = "{dsl_version}"']
        if status:
            temporal_status = self._map_to_temporal_status(status)
            query_parts.append(f'ExecutionStatus = "{temporal_status}"')

        query = " AND ".join(query_parts)

        runs: list[ProcessRun] = []
        async for workflow in self._client.list_workflows(query=query):
            if len(runs) >= limit:
                break

            runs.append(
                ProcessRun(
                    run_id=workflow.id,
                    process_name=workflow.workflow_type or "unknown",
                    dsl_version=dsl_version,
                    status=self._map_status(workflow.status),
                    started_at=workflow.start_time or datetime.utcnow(),
                    completed_at=workflow.close_time,
                )
            )

        return runs

    async def count_active_runs_by_version(
        self,
        dsl_version: str,
    ) -> int:
        """Count active (running) workflows for a DSL version."""
        if not self._client:
            return 0

        # Query for running workflows with this version
        query = f'DslVersion = "{dsl_version}" AND ExecutionStatus = "Running"'

        count = 0
        async for _ in self._client.list_workflows(query=query):
            count += 1

        return count
