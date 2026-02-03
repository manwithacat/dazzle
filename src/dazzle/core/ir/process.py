"""
Process specification types for DAZZLE IR.

This module contains workflow and scheduling definitions
for durable process execution.

Temporal Mapping:
- ProcessSpec -> Workflow Definition
- ProcessStepSpec -> Activity
- ProcessTriggerSpec -> Workflow Starter
- CompensationSpec -> Saga compensation activity
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ProcessTriggerKind(str, Enum):
    """Types of events that can trigger a process."""

    ENTITY_EVENT = "entity_event"  # entity created/updated/deleted
    ENTITY_STATUS_TRANSITION = "entity_status_transition"  # status A -> B
    SCHEDULE_CRON = "schedule_cron"  # cron expression
    SCHEDULE_INTERVAL = "schedule_interval"  # every N minutes
    MANUAL = "manual"  # API call
    SIGNAL = "signal"  # external signal
    PROCESS_COMPLETED = "process_completed"  # when another process completes


class StepKind(str, Enum):
    """Types of process steps."""

    SERVICE = "service"  # Call a domain service
    SEND = "send"  # Send a message via channel
    WAIT = "wait"  # Wait for duration or signal
    HUMAN_TASK = "human_task"  # Wait for human action
    SUBPROCESS = "subprocess"  # Start another process
    PARALLEL = "parallel"  # Execute steps in parallel
    CONDITION = "condition"  # Conditional branch


class RetryBackoff(str, Enum):
    """Retry backoff strategies."""

    FIXED = "fixed"
    EXPONENTIAL = "exponential"
    LINEAR = "linear"


class OverlapPolicy(str, Enum):
    """Policy for handling overlapping process runs."""

    SKIP = "skip"  # Skip if already running
    QUEUE = "queue"  # Queue for later execution
    CANCEL_PREVIOUS = "cancel_previous"  # Cancel existing, start new
    ALLOW = "allow"  # Allow concurrent runs


class ParallelFailurePolicy(str, Enum):
    """Policy for handling parallel step failures."""

    FAIL_FAST = "fail_fast"  # Stop all on first failure
    WAIT_ALL = "wait_all"  # Wait for all to complete
    ROLLBACK = "rollback"  # Run compensations on any failure


class RetryConfig(BaseModel):
    """Retry configuration for a step."""

    max_attempts: int = 3
    initial_interval_seconds: int = 1
    backoff: RetryBackoff = RetryBackoff.EXPONENTIAL
    backoff_coefficient: float = 2.0
    max_interval_seconds: int = 60

    model_config = ConfigDict(frozen=True)


class InputMapping(BaseModel):
    """Maps process input to step input."""

    source: str = Field(..., description="Source field or expression")
    target: str = Field(..., description="Target step input field")

    model_config = ConfigDict(frozen=True)


class ProcessInputField(BaseModel):
    """Input field definition for a process."""

    name: str
    type: str = "str"  # uuid, str, int, bool, json, etc.
    required: bool = False
    default: str | None = None
    description: str | None = None

    model_config = ConfigDict(frozen=True)


class ProcessOutputField(BaseModel):
    """Output field definition for a process."""

    name: str
    type: str = "str"
    description: str | None = None

    model_config = ConfigDict(frozen=True)


class FieldAssignment(BaseModel):
    """A field assignment in an outcome (Entity.field -> value)."""

    field_path: str = Field(..., description="e.g., 'ExpenseReport.status'")
    value: str = Field(..., description="Value or expression")

    model_config = ConfigDict(frozen=True)


class HumanTaskOutcome(BaseModel):
    """An outcome button/action for a human task."""

    name: str = Field(..., description="Outcome identifier (e.g., 'approve')")
    label: str = Field(..., description="Button text (e.g., 'Approve Expense')")
    sets: list[FieldAssignment] = Field(
        default_factory=list, description="Field changes on this outcome"
    )
    goto: str = Field(..., description="Next step name, 'complete', or 'fail'")
    confirm: str | None = Field(default=None, description="Optional confirmation prompt")
    style: str = Field(default="primary", description="Button style hint")

    model_config = ConfigDict(frozen=True)


class HumanTaskSpec(BaseModel):
    """Configuration for a human task step."""

    surface: str = Field(..., description="Surface name to render")
    entity_path: str | None = Field(default=None, description="Entity path for the surface")
    assignee_role: str | None = Field(default=None, description="Role to assign task to")
    assignee_expression: str | None = Field(
        default=None, description="Expression to determine assignee"
    )
    timeout_seconds: int = Field(default=604800, description="Task timeout (default 7 days)")
    escalation_timeout_seconds: int | None = Field(
        default=None, description="When to escalate if not completed"
    )
    outcomes: list[HumanTaskOutcome] = Field(
        default_factory=list, description="Possible task outcomes"
    )

    model_config = ConfigDict(frozen=True)


class ProcessTriggerSpec(BaseModel):
    """
    Specification for what triggers a process.

    Examples:
    - entity Order status -> confirmed (status transition)
    - entity Employee created (entity event)
    - cron "0 8 * * *" (schedule)
    """

    kind: ProcessTriggerKind
    entity_name: str | None = Field(default=None, description="Entity name for entity triggers")
    event_type: str | None = Field(
        default=None, description="Event type: created, updated, deleted"
    )
    from_status: str | None = Field(default=None, description="For status transitions")
    to_status: str | None = Field(default=None, description="For status transitions")
    cron: str | None = Field(default=None, description="Cron expression for schedules")
    interval_seconds: int | None = Field(
        default=None, description="Interval for periodic schedules"
    )
    timezone: str = Field(default="UTC", description="Timezone for schedule interpretation")
    process_name: str | None = Field(default=None, description="For PROCESS_COMPLETED triggers")

    model_config = ConfigDict(frozen=True)


class ProcessStepSpec(BaseModel):
    """
    Specification for a single process step.

    Steps can be service calls, message sends, waits,
    human tasks, subprocesses, parallel blocks, or conditions.
    """

    name: str = Field(..., description="Step identifier")
    kind: StepKind = Field(default=StepKind.SERVICE)

    # For SERVICE steps
    service: str | None = Field(default=None, description="Service name to call")

    # For SEND steps
    channel: str | None = Field(default=None, description="Channel name to send to")
    message: str | None = Field(default=None, description="Message type to send")

    # For WAIT steps
    wait_duration_seconds: int | None = Field(default=None, description="Duration to wait")
    wait_for_signal: str | None = Field(default=None, description="Signal name to wait for")

    # For HUMAN_TASK steps
    human_task: HumanTaskSpec | None = Field(default=None, description="Human task configuration")

    # For SUBPROCESS steps
    subprocess: str | None = Field(default=None, description="Process name to start as subprocess")

    # For PARALLEL steps
    parallel_steps: list[ProcessStepSpec] = Field(
        default_factory=list, description="Steps to run in parallel"
    )
    parallel_policy: ParallelFailurePolicy = Field(default=ParallelFailurePolicy.FAIL_FAST)

    # For CONDITION steps
    condition: str | None = Field(default=None, description="Condition expression")
    on_true: str | None = Field(default=None, description="Step to go to if condition is true")
    on_false: str | None = Field(default=None, description="Step to go to if condition is false")

    # Input/output mappings
    inputs: list[InputMapping] = Field(
        default_factory=list, description="Input mappings for the step"
    )
    output_mapping: str | None = Field(default=None, description="Where to store step output")

    # Timeout and retry
    timeout_seconds: int = Field(default=30, description="Step timeout in seconds")
    retry: RetryConfig | None = Field(default=None, description="Retry configuration")

    # Flow control
    on_success: str | None = Field(default=None, description="Step/action on success")
    on_failure: str | None = Field(default=None, description="Step/action on failure")
    compensate_with: str | None = Field(default=None, description="Compensation handler name")

    model_config = ConfigDict(frozen=True)


class CompensationSpec(BaseModel):
    """
    Compensation handler for saga rollback.

    Compensations are run in reverse order when a process fails.
    """

    name: str = Field(..., description="Compensation handler name")
    service: str | None = Field(default=None, description="Service to call for compensation")
    inputs: list[InputMapping] = Field(default_factory=list, description="Input mappings")
    timeout_seconds: int = Field(default=30)

    model_config = ConfigDict(frozen=True)


class ProcessEventEmission(BaseModel):
    """HLESS event emissions from a process."""

    on_start: str | None = Field(default=None, description="Event type on process start")
    on_complete: str | None = Field(default=None, description="Event type on successful completion")
    on_failure: str | None = Field(default=None, description="Event type on failure")

    model_config = ConfigDict(frozen=True)


class ProcessSpec(BaseModel):
    """
    Specification for a durable workflow process.

    ProcessSpec defines multi-step workflows with:
    - Triggers (what starts the process)
    - Steps (activities to execute)
    - Compensation (saga rollback handlers)
    - Timeouts and retries
    - HLESS event emission
    """

    name: str = Field(..., description="Process identifier")
    title: str | None = Field(default=None, description="Human-readable title")
    description: str | None = Field(default=None, description="Process description")

    # Link to acceptance criteria
    implements: list[str] = Field(
        default_factory=list,
        description="Story IDs this process implements (e.g., ['ST-001'])",
    )

    # Trigger configuration
    trigger: ProcessTriggerSpec | None = Field(default=None, description="What starts this process")

    # Input/output
    inputs: list[ProcessInputField] = Field(
        default_factory=list, description="Process input fields"
    )
    outputs: list[ProcessOutputField] = Field(
        default_factory=list, description="Process output fields"
    )

    # Steps
    steps: list[ProcessStepSpec] = Field(default_factory=list, description="Process steps")

    # Compensation handlers
    compensations: list[CompensationSpec] = Field(
        default_factory=list, description="Saga compensation handlers"
    )

    # Timeouts and policies
    timeout_seconds: int = Field(default=86400, description="Overall process timeout (default 24h)")
    overlap_policy: OverlapPolicy = Field(
        default=OverlapPolicy.SKIP,
        description="Policy for overlapping runs",
    )

    # Event emission
    events: ProcessEventEmission = Field(
        default_factory=ProcessEventEmission,
        description="HLESS events to emit",
    )

    model_config = ConfigDict(frozen=True)

    def get_step(self, name: str) -> ProcessStepSpec | None:
        """Get step by name."""
        for step in self.steps:
            if step.name == name:
                return step
            # Check parallel steps
            for parallel_step in step.parallel_steps:
                if parallel_step.name == name:
                    return parallel_step
        return None

    def get_compensation(self, name: str) -> CompensationSpec | None:
        """Get compensation handler by name."""
        for comp in self.compensations:
            if comp.name == name:
                return comp
        return None


class ScheduleSpec(BaseModel):
    """
    Specification for a scheduled job.

    Schedules are a simplified form of process triggered by cron/interval.
    """

    name: str = Field(..., description="Schedule identifier")
    title: str | None = Field(default=None, description="Human-readable title")
    description: str | None = Field(default=None)

    # Link to acceptance criteria
    implements: list[str] = Field(
        default_factory=list,
        description="Story IDs this schedule implements",
    )

    # Schedule configuration
    cron: str | None = Field(default=None, description="Cron expression (e.g., '0 8 * * *')")
    interval_seconds: int | None = Field(default=None, description="Run every N seconds")
    timezone: str = Field(default="UTC")

    # Run policies
    catch_up: bool = Field(
        default=False,
        description="Run missed executions on startup",
    )
    overlap: OverlapPolicy = Field(
        default=OverlapPolicy.SKIP,
        description="Policy for overlapping runs",
    )

    # Steps (like a simplified process)
    steps: list[ProcessStepSpec] = Field(default_factory=list)

    # Timeouts
    timeout_seconds: int = Field(default=3600)

    # Event emission
    events: ProcessEventEmission = Field(default_factory=ProcessEventEmission)

    model_config = ConfigDict(frozen=True)

    def get_step(self, name: str) -> ProcessStepSpec | None:
        """Get step by name."""
        for step in self.steps:
            if step.name == name:
                return step
        return None


class ProcessesContainer(BaseModel):
    """Container for storing processes with version information.

    This is the root object stored in .dazzle/processes/processes.json.
    """

    version: str = "1.0"
    processes: list[ProcessSpec] = Field(default_factory=list)

    model_config = ConfigDict(frozen=False)
