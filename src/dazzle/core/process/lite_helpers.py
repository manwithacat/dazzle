"""
Helper classes extracted from LiteProcessAdapter to reduce module size.

These classes encapsulate logical groupings of process execution logic:
  StepExecutor       — step execution with retry, dispatch by StepKind
  CompensationRunner — saga compensation in reverse order
  SchedulePoller     — background schedule checking loop

Also defines the exception types used by the lite adapter.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from dazzle.core.ir.process import (
    CompensationSpec,
    ProcessSpec,
    ProcessStepSpec,
    RetryBackoff,
    RetryConfig,
    ScheduleSpec,
    StepKind,
)

from .adapter import ProcessStatus, TaskStatus
from .context import ProcessContext

if TYPE_CHECKING:
    from .lite_adapter import LiteProcessAdapter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions (shared between lite_adapter and helpers)
# ---------------------------------------------------------------------------


class ProcessStepFailed(Exception):
    """Raised when a process step fails after all retries."""

    def __init__(self, step_name: str, message: str):
        self.step_name = step_name
        super().__init__(f"Step '{step_name}' failed: {message}")


class ProcessCancelled(Exception):
    """Raised when a process is cancelled."""

    pass


# ---------------------------------------------------------------------------
# StepExecutor
# ---------------------------------------------------------------------------


class StepExecutor:
    """Executes individual process steps with retry and dispatch by kind.

    Extracted from LiteProcessAdapter._execute_step and related methods.
    """

    def __init__(self, adapter: LiteProcessAdapter) -> None:
        self._adapter = adapter
        self._side_effect_executor: Any | None = None

    def set_side_effect_executor(self, executor: Any) -> None:
        """Set the side-effect executor for processing step effects."""
        self._side_effect_executor = executor

    async def execute_step(
        self,
        run_id: str,
        step: ProcessStepSpec,
        context: ProcessContext,
        spec: ProcessSpec,
    ) -> dict[str, Any]:
        """Execute a single step with retry logic."""
        retry = step.retry or RetryConfig()
        last_error: str | None = None

        for attempt in range(retry.max_attempts):
            try:
                result = await asyncio.wait_for(
                    self._execute_step_impl(run_id, step, context, spec),
                    timeout=step.timeout_seconds,
                )
                return result

            except TimeoutError:
                last_error = f"Step timed out after {step.timeout_seconds}s"

            except ProcessStepFailed:
                raise

            except ConnectionError as e:
                last_error = str(e)
                logger.warning(
                    "Transient error in step %s (attempt %d): %s", step.name, attempt + 1, e
                )

            except Exception as e:
                last_error = str(e)

            # Record failed attempt
            await self._adapter._record_step_execution(
                run_id, step.name, step.kind.value, "failed", error=last_error, attempt=attempt + 1
            )

            # Retry if not last attempt
            if attempt < retry.max_attempts - 1:
                delay = self._calculate_backoff(retry, attempt)
                logger.debug(f"Step {step.name} attempt {attempt + 1} failed, retrying in {delay}s")
                await asyncio.sleep(delay)

        raise ProcessStepFailed(step.name, last_error or "Unknown error")

    async def _execute_step_impl(
        self,
        run_id: str,
        step: ProcessStepSpec,
        context: ProcessContext,
        spec: ProcessSpec,
    ) -> dict[str, Any]:
        """Execute step implementation by kind."""
        # Build step inputs
        step_inputs: dict[str, Any] = {}
        for mapping in step.inputs:
            value = context.resolve(mapping.source)
            step_inputs[mapping.target] = value

        if step.kind == StepKind.SERVICE:
            result = await self._execute_service_step(step, step_inputs, context)

        elif step.kind == StepKind.SEND:
            result = await self._execute_send_step(step, step_inputs, context)

        elif step.kind == StepKind.WAIT:
            result = await self._execute_wait_step(step, context)

        elif step.kind == StepKind.HUMAN_TASK:
            result = await self._execute_human_task_step(run_id, step, context)

        elif step.kind == StepKind.SUBPROCESS:
            result = await self._execute_subprocess_step(step, step_inputs)

        elif step.kind == StepKind.PARALLEL:
            result = await self._execute_parallel_step(run_id, step, context, spec)

        else:
            result = {}

        # Execute step effects after successful completion
        if step.effects and self._side_effect_executor:
            effect_results = await self._run_step_effects(step, context)
            result["_effects"] = effect_results

        return result

    async def _run_step_effects(
        self,
        step: ProcessStepSpec,
        context: ProcessContext,
    ) -> list[dict[str, Any]]:
        """Execute side-effects declared on a step."""
        from dazzle_back.runtime.side_effect_executor import EffectContext

        assert self._side_effect_executor is not None
        effect_ctx = EffectContext(
            trigger_entity=context.get_variable("trigger_entity") or {},
            process_inputs=context.inputs if hasattr(context, "inputs") else {},
            step_outputs=context.get_variable(f"steps.{step.name}") or {},
        )
        results = await self._side_effect_executor.execute_effects(step.effects, effect_ctx)
        return [
            {
                "action": r.action,
                "entity": r.entity_name,
                "success": r.success,
                "affected": r.affected_count,
                "error": r.error,
            }
            for r in results
        ]

    async def _execute_service_step(
        self,
        step: ProcessStepSpec,
        inputs: dict[str, Any],
        context: ProcessContext,
    ) -> dict[str, Any]:
        """Execute a service call step."""
        service_name = step.service
        if not service_name:
            raise ProcessStepFailed(step.name, "No service specified")

        handler = self._adapter._service_handlers.get(service_name)
        if not handler:
            logger.warning(f"No handler for service {service_name}, using no-op")
            return {}

        return await handler(inputs)

    async def _execute_send_step(
        self,
        step: ProcessStepSpec,
        inputs: dict[str, Any],
        context: ProcessContext,
    ) -> dict[str, Any]:
        """Execute a message send step."""
        if not step.channel or not step.message:
            raise ProcessStepFailed(step.name, "No channel or message specified")

        if self._adapter._send_handler:
            await self._adapter._send_handler(step.channel, step.message, inputs)

        return {"sent": True, "channel": step.channel, "message": step.message}

    async def _execute_wait_step(
        self,
        step: ProcessStepSpec,
        context: ProcessContext,
    ) -> dict[str, Any]:
        """Execute a wait step (duration or signal)."""
        if step.wait_duration_seconds:
            await asyncio.sleep(step.wait_duration_seconds)
            return {"waited_seconds": step.wait_duration_seconds}

        if step.wait_for_signal:
            run_id = context.get_variable("run_id")
            deadline = datetime.now(UTC) + timedelta(seconds=step.timeout_seconds)
            while datetime.now(UTC) < deadline:
                signal = await self._adapter._check_signal(run_id, step.wait_for_signal)
                if signal:
                    return {"signal": step.wait_for_signal, "payload": signal}
                await asyncio.sleep(self._adapter._poll_interval)

            raise ProcessStepFailed(
                step.name, f"Timeout waiting for signal: {step.wait_for_signal}"
            )

        return {}

    async def _execute_human_task_step(
        self,
        run_id: str,
        step: ProcessStepSpec,
        context: ProcessContext,
    ) -> dict[str, Any]:
        """Execute a human task step."""
        if not step.human_task:
            raise ProcessStepFailed(step.name, "No human_task configuration")

        task_config = step.human_task

        # Resolve assignee
        assignee_id = None
        if task_config.assignee_expression:
            assignee_id = context.resolve(task_config.assignee_expression)

        # Resolve entity path
        entity_id = ""
        entity_name = ""
        if task_config.entity_path:
            entity_id = context.resolve(f"{task_config.entity_path}.id") or ""
            parts = task_config.entity_path.split(".")
            entity_name = parts[-1] if parts else ""

        # Create task
        task_id = str(uuid.uuid4())
        due_at = datetime.now(UTC) + timedelta(seconds=step.timeout_seconds)

        await self._adapter._create_task(
            task_id=task_id,
            run_id=run_id,
            step_name=step.name,
            surface_name=task_config.surface,
            entity_name=entity_name,
            entity_id=entity_id,
            assignee_id=assignee_id,
            assignee_role=task_config.assignee_role,
            due_at=due_at,
        )

        await self._adapter._emit_event(
            "HumanTaskAssigned",
            run_id,
            task_id=task_id,
            step_name=step.name,
            surface=task_config.surface,
        )

        # Poll for completion
        escalation_seconds = task_config.escalation_timeout_seconds or step.timeout_seconds
        escalation_time = datetime.now(UTC) + timedelta(seconds=escalation_seconds)

        while datetime.now(UTC) < due_at:
            task = await self._adapter.get_task(task_id)
            if not task:
                raise ProcessStepFailed(step.name, "Task not found")

            if task.status == TaskStatus.COMPLETED:
                outcome = task.outcome or "completed"
                outcome_data = task.outcome_data or {}

                for outcome_config in task_config.outcomes:
                    if outcome_config.name == outcome:
                        if outcome_config.sets and self._side_effect_executor:
                            await self._execute_human_task_sets(outcome_config.sets, context)
                        break

                return {"outcome": outcome, "task_id": task_id, **outcome_data}

            # Check escalation
            if datetime.now(UTC) > escalation_time and not task.escalated_at:
                await self._adapter._escalate_task(task_id)

            await asyncio.sleep(self._adapter._poll_interval)

        raise ProcessStepFailed(step.name, "Human task timed out")

    async def _execute_subprocess_step(
        self,
        step: ProcessStepSpec,
        inputs: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a subprocess step."""
        if not step.subprocess:
            raise ProcessStepFailed(step.name, "No subprocess specified")

        run_id = await self._adapter.start_process(step.subprocess, inputs)

        while True:
            run = await self._adapter.get_run(run_id)
            if not run:
                raise ProcessStepFailed(step.name, "Subprocess not found")

            if run.status == ProcessStatus.COMPLETED:
                return {"subprocess_run_id": run_id, "outputs": run.outputs or {}}

            if run.status in (ProcessStatus.FAILED, ProcessStatus.CANCELLED):
                raise ProcessStepFailed(step.name, f"Subprocess {run.status.value}: {run.error}")

            await asyncio.sleep(self._adapter._poll_interval)

    async def _execute_parallel_step(
        self,
        run_id: str,
        step: ProcessStepSpec,
        context: ProcessContext,
        spec: ProcessSpec,
    ) -> dict[str, Any]:
        """Execute parallel steps."""
        if not step.parallel_steps:
            return {}

        tasks = []
        for parallel_step in step.parallel_steps:
            task = asyncio.create_task(self.execute_step(run_id, parallel_step, context, spec))
            tasks.append((parallel_step.name, task))

        results: dict[str, Any] = {}
        errors: list[str] = []

        if step.parallel_policy.value == "fail_fast":
            done, pending = await asyncio.wait(
                [t for _, t in tasks],
                return_when=asyncio.FIRST_EXCEPTION,
            )

            for task in pending:
                task.cancel()

            for name, task in tasks:
                if task.done():
                    try:
                        results[name] = task.result()
                    except Exception as e:
                        errors.append(f"{name}: {e}")
        else:
            await asyncio.gather(*[t for _, t in tasks], return_exceptions=True)

            for name, task in tasks:
                try:
                    results[name] = task.result()
                except Exception as e:
                    errors.append(f"{name}: {e}")

        if errors:
            raise ProcessStepFailed(step.name, f"Parallel failures: {'; '.join(errors)}")

        return results

    async def _execute_human_task_sets(
        self,
        assignments: list[Any],
        context: ProcessContext,
    ) -> None:
        """Execute field assignments from human task outcomes.

        Each assignment has Entity.field -> value format.
        Delegates to SideEffectExecutor for value resolution and service calls.
        """
        from dazzle.core.ir.process import EffectAction, FieldAssignment, StepEffect

        # Group assignments by entity
        entity_assignments: dict[str, list[FieldAssignment]] = {}
        for assignment in assignments:
            if "." in assignment.field_path:
                entity_name = assignment.field_path.split(".")[0]
            else:
                entity_name = ""
                continue
            entity_assignments.setdefault(entity_name, []).append(assignment)

        # Build update effects for each entity
        from dazzle_back.runtime.side_effect_executor import EffectContext

        assert self._side_effect_executor is not None
        effect_ctx = EffectContext(
            trigger_entity=context.get_variable("trigger_entity") or {},
            process_inputs=context.inputs if hasattr(context, "inputs") else {},
        )

        for entity_name, assigns in entity_assignments.items():
            # For human task sets, the entity ID comes from the process context
            entity_id = context.resolve(f"{entity_name}.id")
            if entity_id:
                effect = StepEffect(
                    action=EffectAction.UPDATE,
                    entity_name=entity_name,
                    where=f"id = {entity_id}",
                    assignments=assigns,
                )
                await self._side_effect_executor.execute_effects([effect], effect_ctx)

    @staticmethod
    def _calculate_backoff(retry: RetryConfig, attempt: int) -> float:
        """Calculate backoff delay for retry."""
        if retry.backoff == RetryBackoff.FIXED:
            return float(retry.initial_interval_seconds)

        elif retry.backoff == RetryBackoff.LINEAR:
            return float(retry.initial_interval_seconds * (attempt + 1))

        else:  # EXPONENTIAL
            delay = retry.initial_interval_seconds * (retry.backoff_coefficient**attempt)
            return min(delay, retry.max_interval_seconds)


# ---------------------------------------------------------------------------
# CompensationRunner
# ---------------------------------------------------------------------------


class CompensationRunner:
    """Runs saga compensations in reverse order for completed steps.

    Extracted from LiteProcessAdapter._run_compensations.
    """

    def __init__(self, adapter: LiteProcessAdapter) -> None:
        self._adapter = adapter

    async def run_compensations(
        self,
        run_id: str,
        spec: ProcessSpec,
        completed_steps: list[str],
        context: ProcessContext,
    ) -> None:
        """Run compensation handlers for completed steps in reverse order."""
        if not spec.compensations:
            return

        await self._adapter._update_run_status(run_id, ProcessStatus.COMPENSATING)

        comp_map: dict[str, CompensationSpec] = {}
        for comp in spec.compensations:
            comp_map[comp.name] = comp

        for step_name in reversed(completed_steps):
            step = spec.get_step(step_name)
            if step and step.compensate_with:
                compensation = comp_map.get(step.compensate_with)
                if compensation:
                    try:
                        await self._run_compensation(compensation, context)
                    except Exception as e:
                        logger.error(f"Compensation {compensation.name} failed: {e}")

    async def _run_compensation(
        self,
        comp: CompensationSpec,
        context: ProcessContext,
    ) -> None:
        """Run a single compensation handler."""
        if comp.service:
            handler = self._adapter._service_handlers.get(comp.service)
            if handler:
                inputs: dict[str, Any] = {}
                for mapping in comp.inputs:
                    inputs[mapping.target] = context.resolve(mapping.source)

                await asyncio.wait_for(
                    handler(inputs),
                    timeout=comp.timeout_seconds,
                )


# ---------------------------------------------------------------------------
# SchedulePoller
# ---------------------------------------------------------------------------


class SchedulePoller:
    """Background task that checks and runs scheduled processes.

    Extracted from LiteProcessAdapter._run_scheduler.
    """

    def __init__(self, adapter: LiteProcessAdapter) -> None:
        self._adapter = adapter

    async def run(self) -> None:
        """Background loop: sleep, check schedules, check escalations."""
        while True:
            try:
                await asyncio.sleep(self._adapter._scheduler_interval)
                if self._adapter._shutting_down:
                    break

                now = datetime.now(UTC)

                for name, spec in self._adapter._schedule_registry.items():
                    if await self._should_run_schedule(spec, now):
                        try:
                            run_id = await self._adapter.start_process(name, {})
                            await self._adapter._update_schedule_run(name, run_id)
                        except (TimeoutError, ConnectionError) as e:
                            logger.warning("Transient error scheduling %s: %s", name, e)
                            await self._adapter._record_schedule_error(name, str(e))
                        except Exception as e:
                            await self._adapter._record_schedule_error(name, str(e))

                await self._adapter._check_pending_escalations()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}")

    async def _should_run_schedule(self, spec: ScheduleSpec, now: datetime) -> bool:
        """Check if a schedule should run now."""
        if not self._adapter._db:
            return False

        async with self._adapter._db.execute(
            "SELECT last_run_at, next_run_at FROM schedule_runs WHERE schedule_name = ?",
            (spec.name,),
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return True

        last_run = row["last_run_at"]
        if last_run:
            last_run = datetime.fromisoformat(last_run)

            if spec.interval_seconds:
                return (now - last_run).total_seconds() >= spec.interval_seconds

            if spec.cron:
                return _cron_due(spec.cron, last_run, now)

        return True


def _cron_match_field(field: str, value: int, min_val: int, max_val: int) -> bool:
    """Check if a single cron field matches a datetime component.

    Supports: ``*``, exact numbers, comma-separated lists, ranges (``1-5``),
    and step values (``*/5``, ``1-10/2``).
    """
    for part in field.split(","):
        if "/" in part:
            base, step_str = part.split("/", 1)
            step = int(step_str)
            if base == "*":
                if (value - min_val) % step == 0:
                    return True
            elif "-" in base:
                lo, hi = base.split("-", 1)
                if int(lo) <= value <= int(hi) and (value - int(lo)) % step == 0:
                    return True
        elif part == "*":
            return True
        elif "-" in part:
            lo, hi = part.split("-", 1)
            if int(lo) <= value <= int(hi):
                return True
        else:
            if value == int(part):
                return True
    return False


def _cron_due(cron_expr: str, last_run: datetime, now: datetime) -> bool:
    """Return True if *cron_expr* has a matching minute between *last_run* and *now*.

    Walks forward minute-by-minute from the minute after *last_run* up to *now*.
    The window is capped at 24 hours to avoid runaway iteration.
    """
    parts = cron_expr.strip().split()
    if len(parts) < 5:
        logger.warning("Invalid cron expression (need 5 fields): %s", cron_expr)
        return False

    c_min, c_hour, c_dom, c_mon, c_dow = parts[:5]

    # Cap search to 24 hours to avoid long loops
    window = min((now - last_run).total_seconds(), 86400)
    if window < 60:
        return False

    # Walk minute-by-minute from last_run+1min to now
    check = last_run.replace(second=0, microsecond=0) + timedelta(minutes=1)
    end = now.replace(second=0, microsecond=0)

    while check <= end:
        if (
            _cron_match_field(c_min, check.minute, 0, 59)
            and _cron_match_field(c_hour, check.hour, 0, 23)
            and _cron_match_field(c_dom, check.day, 1, 31)
            and _cron_match_field(c_mon, check.month, 1, 12)
            and _cron_match_field(c_dow, check.isoweekday() % 7, 0, 6)
        ):
            return True
        check += timedelta(minutes=1)

    return False
