"""
ProcessManager - Integrates process execution with DNR runtime.

This module connects ProcessSpec definitions from the AppSpec to the
process adapter (LiteProcessAdapter or TemporalAdapter) and handles
entity event triggers.
"""

from __future__ import annotations

import logging
from typing import Any

from dazzle.core.ir.appspec import AppSpec
from dazzle.core.ir.process import ProcessSpec, ProcessTriggerKind, ScheduleSpec
from dazzle.core.process.adapter import (
    ProcessAdapter,
    ProcessRun,
    ProcessStatus,
    ProcessTask,
    TaskStatus,
)

# Default status field name for entities without an explicit state machine
_DEFAULT_STATUS_FIELD = "status"

logger = logging.getLogger(__name__)


class ProcessManager:
    """
    Manages process lifecycle in the DNR runtime.

    Responsibilities:
    - Register all processes and schedules from AppSpec
    - Set up entity event triggers
    - Provide API for process operations
    - Connect entity lifecycle events to process triggers
    """

    def __init__(
        self,
        adapter: ProcessAdapter,
        app_spec: AppSpec | None = None,
        process_specs: list[ProcessSpec] | None = None,
    ):
        """
        Initialize the process manager.

        Args:
            adapter: Process execution adapter (Lite or Temporal)
            app_spec: Application specification with processes and schedules (optional)
            process_specs: List of process specs to register (alternative to app_spec)
        """
        self._app_spec = app_spec
        self._adapter = adapter
        self._process_specs = process_specs or []
        self._schedule_specs: list[ScheduleSpec] = []

        # If app_spec provided, extract processes and schedules from it
        if app_spec:
            self._process_specs = list(app_spec.processes)
            self._schedule_specs = list(app_spec.schedules)

        # Trigger mappings
        self._entity_event_triggers: dict[str, list[ProcessSpec]] = {}
        self._status_transition_triggers: dict[str, list[ProcessSpec]] = {}

        # Build entity → status_field mapping from domain state machines
        self._entity_status_fields: dict[str, str] = {}
        if app_spec:
            domain = getattr(app_spec, "domain", None)
            if domain:
                for ent in getattr(domain, "entities", []):
                    sm = getattr(ent, "state_machine", None)
                    if sm:
                        self._entity_status_fields[ent.name] = getattr(
                            sm, "status_field", _DEFAULT_STATUS_FIELD
                        )

    async def initialize(self) -> None:
        """Register all processes and set up triggers."""
        # Register processes
        for proc in self._process_specs:
            await self._adapter.register_process(proc)
            self._register_trigger(proc)
            logger.debug(f"Registered process: {proc.name}")

        # Register schedules
        for sched in self._schedule_specs:
            await self._adapter.register_schedule(sched)
            logger.debug(f"Registered schedule: {sched.name}")

        logger.info(
            f"ProcessManager initialized with {len(self._process_specs)} processes "
            f"and {len(self._schedule_specs)} schedules"
        )

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        await self._adapter.shutdown()

    def _register_trigger(self, proc: ProcessSpec) -> None:
        """Register event triggers for a process."""
        trigger = proc.trigger
        if not trigger:
            return

        if trigger.kind == ProcessTriggerKind.ENTITY_EVENT:
            # Entity created/updated/deleted events
            if trigger.entity_name and trigger.event_type:
                key = f"{trigger.entity_name}:{trigger.event_type}"
                self._entity_event_triggers.setdefault(key, []).append(proc)
                logger.debug(f"Registered entity event trigger: {key} -> {proc.name}")

        elif trigger.kind == ProcessTriggerKind.ENTITY_STATUS_TRANSITION:
            # Status transition events
            if trigger.entity_name and trigger.from_status and trigger.to_status:
                key = f"{trigger.entity_name}:{trigger.from_status}:{trigger.to_status}"
                self._status_transition_triggers.setdefault(key, []).append(proc)
                logger.debug(f"Registered status transition trigger: {key} -> {proc.name}")

    # Entity Event Handling
    async def on_entity_created(
        self,
        entity_name: str,
        entity_id: str,
        entity_data: dict[str, Any],
    ) -> list[str]:
        """
        Handle entity created event.

        Returns:
            List of started process run IDs
        """
        return await self._handle_entity_event(entity_name, "created", entity_id, entity_data)

    async def on_entity_updated(
        self,
        entity_name: str,
        entity_id: str,
        entity_data: dict[str, Any],
        old_data: dict[str, Any] | None = None,
    ) -> list[str]:
        """
        Handle entity updated event.

        Returns:
            List of started process run IDs
        """
        run_ids = await self._handle_entity_event(entity_name, "updated", entity_id, entity_data)

        # Check for status transitions using entity's configured status field
        status_field = self._entity_status_fields.get(entity_name, _DEFAULT_STATUS_FIELD)
        if old_data and status_field in entity_data and status_field in old_data:
            old_status = old_data[status_field]
            new_status = entity_data[status_field]
            if old_status != new_status:
                transition_runs = await self._handle_status_transition(
                    entity_name, old_status, new_status, entity_id, entity_data
                )
                run_ids.extend(transition_runs)

        return run_ids

    async def on_entity_deleted(
        self,
        entity_name: str,
        entity_id: str,
        entity_data: dict[str, Any],
    ) -> list[str]:
        """
        Handle entity deleted event.

        Returns:
            List of started process run IDs
        """
        return await self._handle_entity_event(entity_name, "deleted", entity_id, entity_data)

    async def _handle_entity_event(
        self,
        entity_name: str,
        event_type: str,
        entity_id: str,
        entity_data: dict[str, Any],
    ) -> list[str]:
        """Handle a generic entity event."""
        key = f"{entity_name}:{event_type}"
        processes = self._entity_event_triggers.get(key, [])

        run_ids = []
        for proc in processes:
            try:
                run_id = await self._adapter.start_process(
                    proc.name,
                    {
                        "entity_id": entity_id,
                        "entity_name": entity_name,
                        "event_type": event_type,
                        **entity_data,
                    },
                )
                run_ids.append(run_id)
                logger.info(f"Started process {proc.name} for {key}: {run_id}")
            except Exception as e:
                logger.error(f"Failed to start process {proc.name} for {key}: {e}")

        return run_ids

    async def _handle_status_transition(
        self,
        entity_name: str,
        old_status: str,
        new_status: str,
        entity_id: str,
        entity_data: dict[str, Any],
    ) -> list[str]:
        """Handle a status transition event."""
        key = f"{entity_name}:{old_status}:{new_status}"
        processes = self._status_transition_triggers.get(key, [])

        run_ids = []
        for proc in processes:
            try:
                run_id = await self._adapter.start_process(
                    proc.name,
                    {
                        "entity_id": entity_id,
                        "entity_name": entity_name,
                        "old_status": old_status,
                        "new_status": new_status,
                        **entity_data,
                    },
                )
                run_ids.append(run_id)
                logger.info(f"Started process {proc.name} for transition {key}: {run_id}")
            except Exception as e:
                logger.error(f"Failed to start process {proc.name} for transition {key}: {e}")

        return run_ids

    # Process Operations API
    async def start_process(
        self,
        process_name: str,
        inputs: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> str:
        """Start a process manually."""
        return await self._adapter.start_process(process_name, inputs, idempotency_key)

    async def get_run(self, run_id: str) -> ProcessRun | None:
        """Get a process run by ID."""
        return await self._adapter.get_run(run_id)

    async def list_runs(
        self,
        process_name: str | None = None,
        status: ProcessStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ProcessRun]:
        """List process runs."""
        return await self._adapter.list_runs(process_name, status, limit, offset)

    async def cancel_process(self, run_id: str, reason: str) -> None:
        """Cancel a running process."""
        await self._adapter.cancel_process(run_id, reason)

    async def signal_process(
        self,
        run_id: str,
        signal_name: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Send a signal to a running process."""
        await self._adapter.signal_process(run_id, signal_name, payload)

    # Human Task Operations
    async def get_task(self, task_id: str) -> ProcessTask | None:
        """Get a human task by ID."""
        return await self._adapter.get_task(task_id)

    async def list_tasks(
        self,
        run_id: str | None = None,
        assignee_id: str | None = None,
        status: TaskStatus | None = None,
        limit: int = 100,
    ) -> list[ProcessTask]:
        """List human tasks with optional filtering."""
        tasks = await self._adapter.list_tasks(run_id, assignee_id, limit=limit)

        # Filter by status if specified
        if status is not None:
            tasks = [t for t in tasks if t.status == status]

        return tasks

    async def complete_task(
        self,
        task_id: str,
        outcome: str,
        outcome_data: dict[str, Any] | None = None,
        completed_by: str | None = None,
    ) -> None:
        """Complete a human task."""
        await self._adapter.complete_task(task_id, outcome, outcome_data, completed_by)

    async def reassign_task(
        self,
        task_id: str,
        new_assignee_id: str,
        reason: str | None = None,
    ) -> None:
        """Reassign a human task."""
        await self._adapter.reassign_task(task_id, new_assignee_id, reason)

    # Introspection
    def get_process_spec(self, name: str) -> ProcessSpec | None:
        """Get process specification by name."""
        for proc in self._process_specs:
            if proc.name == name:
                return proc
        return None

    def get_schedule_spec(self, name: str) -> ScheduleSpec | None:
        """Get schedule specification by name."""
        for sched in self._schedule_specs:
            if sched.name == name:
                return sched
        return None

    def list_process_names(self) -> list[str]:
        """List all registered process names."""
        return [proc.name for proc in self._process_specs]

    def list_schedule_names(self) -> list[str]:
        """List all registered schedule names."""
        return [sched.name for sched in self._schedule_specs]

    def register_process(self, spec: ProcessSpec) -> None:
        """Register a new process spec (for dynamic registration)."""
        self._process_specs.append(spec)

    def register_schedule(self, spec: ScheduleSpec) -> None:
        """Register a new schedule spec (for dynamic registration)."""
        self._schedule_specs.append(spec)
