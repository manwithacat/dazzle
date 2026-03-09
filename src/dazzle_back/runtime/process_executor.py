"""
Linear checkpointed process executor.

Executes process steps sequentially with checkpointing.
Supports LLM_INTENT, SERVICE, and CONDITION step kinds.
On restart, completed steps are skipped via checkpoint replay.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from dazzle.core.ir.process import StepKind

if TYPE_CHECKING:
    from dazzle.core.ir.appspec import AppSpec
    from dazzle.core.ir.process import ProcessStepSpec
    from dazzle_back.runtime.llm_executor import LLMIntentExecutor

logger = logging.getLogger(__name__)


@dataclass
class StepResult:
    """Result of executing a single process step."""

    success: bool
    output: Any = None
    error: str | None = None


@dataclass
class ProcessContext:
    """Execution context for a process run.

    Holds trigger data, step outputs, and checkpoint state.
    """

    trigger_data: dict[str, Any] = field(default_factory=dict)
    step_outputs: dict[str, Any] = field(default_factory=dict)
    checkpoints: set[str] = field(default_factory=set)

    def is_checkpointed(self, step_name: str) -> bool:
        return step_name in self.checkpoints

    def checkpoint(self, step_name: str, result: StepResult) -> None:
        self.checkpoints.add(step_name)
        if result.output is not None:
            self.step_outputs[step_name] = result.output

    def resolve_value(self, expr: str) -> Any:
        """Resolve a dotted expression against context.

        Supports:
        - "trigger.entity.field" → trigger_data["entity"]["field"]
        - "step_name.output" → step_outputs[step_name]
        - "step_name.output.field" → step_outputs[step_name]["field"]
        - literal values
        """
        parts = expr.split(".")

        if parts[0] == "trigger" and len(parts) >= 2:
            obj = self.trigger_data
            for part in parts[1:]:
                if isinstance(obj, dict):
                    obj = obj.get(part)
                else:
                    return None
            return obj

        # Step output reference
        step_name = parts[0]
        if step_name in self.step_outputs:
            obj = self.step_outputs[step_name]
            for part in parts[1:]:
                if part == "output":
                    continue  # skip the "output" accessor
                if isinstance(obj, dict):
                    obj = obj.get(part)
                else:
                    return None
            return obj

        return expr  # literal


@dataclass
class ProcessResult:
    """Result of executing a complete process."""

    success: bool
    process_name: str
    steps_completed: int = 0
    steps_total: int = 0
    outputs: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class ProcessExecutor:
    """Linear checkpointed process executor.

    Executes process steps sequentially. Each step is checkpointed
    after completion. On restart, completed steps are skipped.
    """

    def __init__(
        self,
        appspec: AppSpec,
        services: dict[str, Any] | None = None,
        llm_executor: LLMIntentExecutor | None = None,
    ):
        self._appspec = appspec
        self._services = services or {}
        self._llm_executor = llm_executor
        self._processes = {p.name: p for p in (appspec.processes or [])}

    async def execute(
        self,
        process_name: str,
        trigger_data: dict[str, Any] | None = None,
        *,
        checkpoint_data: dict[str, Any] | None = None,
    ) -> ProcessResult:
        """Execute a process by name.

        Args:
            process_name: Name of the process to execute.
            trigger_data: Data from the triggering event.
            checkpoint_data: Previously checkpointed state for resume.
        """
        process = self._processes.get(process_name)
        if not process:
            return ProcessResult(
                success=False,
                process_name=process_name,
                error=f"Process '{process_name}' not found",
            )

        context = ProcessContext(trigger_data=trigger_data or {})

        # Restore checkpoints if resuming
        if checkpoint_data:
            context.checkpoints = set(checkpoint_data.get("checkpoints", []))
            context.step_outputs = checkpoint_data.get("step_outputs", {})

        steps = process.steps
        result = ProcessResult(
            success=True,
            process_name=process_name,
            steps_total=len(steps),
        )

        for step in steps:
            if context.is_checkpointed(step.name):
                result.steps_completed += 1
                continue

            step_result = await self._execute_step(step, context)
            context.checkpoint(step.name, step_result)
            result.steps_completed += 1

            if not step_result.success:
                result.success = False
                result.error = f"Step '{step.name}' failed: {step_result.error}"
                break

        result.outputs = context.step_outputs
        return result

    async def _execute_step(self, step: ProcessStepSpec, context: ProcessContext) -> StepResult:
        """Execute a single step based on its kind."""
        try:
            if step.kind == StepKind.LLM_INTENT:
                return await self._execute_llm_step(step, context)
            elif step.kind == StepKind.SERVICE:
                return await self._execute_service_step(step, context)
            elif step.kind == StepKind.CONDITION:
                return await self._execute_condition_step(step, context)
            else:
                return StepResult(
                    success=False,
                    error=f"Unsupported step kind: {step.kind}",
                )
        except Exception as e:
            logger.exception("Step %s failed", step.name)
            return StepResult(success=False, error=str(e))

    async def _execute_llm_step(self, step: ProcessStepSpec, context: ProcessContext) -> StepResult:
        """Execute an LLM_INTENT step."""
        if not self._llm_executor:
            return StepResult(success=False, error="No LLM executor available")

        intent_name = step.llm_intent
        if not intent_name:
            return StepResult(success=False, error="No llm_intent specified on step")

        # Map inputs from process context
        input_data: dict[str, Any] = {}
        if step.llm_input_map:
            for target_key, source_expr in step.llm_input_map.items():
                input_data[target_key] = context.resolve_value(source_expr)

        result = await self._llm_executor.execute(intent_name, input_data)

        if result.success:
            # Parse output as JSON if possible
            output = result.output
            if output:
                try:
                    output = json.loads(output)
                except (json.JSONDecodeError, TypeError):
                    pass
            return StepResult(success=True, output=output)
        else:
            return StepResult(success=False, error=result.error)

    async def _execute_service_step(
        self, step: ProcessStepSpec, context: ProcessContext
    ) -> StepResult:
        """Execute a SERVICE step."""
        if not step.service:
            return StepResult(success=False, error="No service specified on step")

        # Parse "ServiceName.method" format
        parts = step.service.split(".", 1)
        service_name = parts[0]
        method = parts[1] if len(parts) > 1 else "execute"

        service = self._services.get(service_name)
        if not service:
            return StepResult(
                success=False,
                error=f"Service '{service_name}' not found",
            )

        # Build args from input mappings
        import asyncio

        args: dict[str, Any] = {}
        for mapping in step.inputs:
            args[mapping.target] = context.resolve_value(mapping.source)

        try:
            result = await asyncio.to_thread(
                getattr(service, method, service.execute),
                **args,
            )
            return StepResult(success=True, output=result)
        except Exception as e:
            return StepResult(success=False, error=str(e))

    async def _execute_condition_step(
        self, step: ProcessStepSpec, context: ProcessContext
    ) -> StepResult:
        """Execute a CONDITION step.

        Evaluates the condition and returns a boolean result.
        """
        if not step.condition:
            return StepResult(success=False, error="No condition specified on step")

        condition = step.condition
        parts = condition.split()

        if len(parts) == 3:
            left_expr, op, right_expr = parts
            left = context.resolve_value(left_expr)
            right = context.resolve_value(right_expr)

            # Normalize for comparison
            if isinstance(left, str) and isinstance(right, str):
                left = left.strip("'\"")
                right = right.strip("'\"")

            if op == "==":
                result = left == right
            elif op == "!=":
                result = left != right
            else:
                return StepResult(success=False, error=f"Unknown operator: {op}")
        else:
            # Simple truthy check
            val = context.resolve_value(condition)
            result = bool(val)

        return StepResult(success=True, output=result)

    def get_checkpoint_data(self, context: ProcessContext) -> dict[str, Any]:
        """Serialize checkpoint data for persistence."""
        return {
            "checkpoints": list(context.checkpoints),
            "step_outputs": context.step_outputs,
        }
