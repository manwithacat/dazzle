"""Background-job IR types (#953 cycle 1).

Generic deferred-task primitive. The DSL surface mirrors the
``llm_intent`` pattern (which is the LLM-specific specialisation of
the same shape) but stays generic enough to cover image processing,
scheduled aggregation, slow integration calls, and the cycle-5
notification-send queue (#952).

Cycle 1 lands the parsed surface only — the Redis queue + worker
loop come in cycle 3, the scheduler in cycle 4. Today, ``JobSpec``
flows from the DSL through the linker into ``AppSpec.jobs`` so
downstream tooling can introspect the job catalogue.

DSL shape::

    job thumbnail_render "Generate thumbnail":
      trigger: on_create Manuscript when source_pdf is_set
      run: scripts/render_thumbnail.py
      retry: 3
      retry_backoff: exponential
      dead_letter: ManuscriptDeadLetter
      timeout: 60s

    job daily_summary "Daily metrics roll-up":
      schedule: cron("0 1 * * *")
      run: scripts/daily_summary.py
      timeout: 5m
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class JobBackoff(StrEnum):
    """Retry backoff strategy."""

    NONE = "none"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"


class JobTrigger(BaseModel):
    """Entity-event trigger that fires a job.

    Attributes:
        entity: Entity name (e.g. "Manuscript").
        event: Event type — "created" | "updated" | "deleted" |
            "field_changed".
        field: Field name for ``field_changed`` events (e.g.
            "source_pdf"). Empty for entity-level events.
        when_condition: Optional guard predicate as raw DSL text
            (e.g. "source_pdf is_set"). Evaluated against the entity
            row before enqueuing — cycle 3 wires the actual evaluator.
    """

    entity: str
    event: str = "created"
    field: str | None = None
    when_condition: str | None = None

    model_config = ConfigDict(frozen=True)


class JobSchedule(BaseModel):
    """Cron-style schedule for periodic jobs.

    Attributes:
        cron: Standard 5-field cron expression
            (``minute hour day month weekday``).
        timezone: IANA timezone for cron evaluation; empty falls back
            to UTC. Cycle 4 wires the scheduler.
    """

    cron: str
    timezone: str = ""

    model_config = ConfigDict(frozen=True)


class JobSpec(BaseModel):
    """Background-job definition.

    A job is either *triggered* (one or more :class:`JobTrigger`
    entries fire it on entity events) or *scheduled* (a
    :class:`JobSchedule` runs it periodically). Cycle 1 supports
    declaring both forms; cycle 3-4 wires runtime.

    Attributes:
        name: Stable identifier — used by the worker to look up the
            handler and as the ``JobRun.job_name`` foreign key.
        title: Human-readable title (defaults to *name* in UI when
            empty).
        run: Module / file path to the handler. Cycle 3 resolves
            this against the project root + an entry-point convention.
        triggers: List of entity-event triggers that fire this job.
            Empty for purely scheduled jobs.
        schedule: Cron schedule. None for purely triggered jobs.
        retry: Maximum attempts on transient failure. 0 disables
            retry (default 3 — matches the existing LLMIntent retry
            convention).
        retry_backoff: Backoff strategy between retries.
        dead_letter: Entity name where exhausted jobs are recorded
            for manual triage. Empty falls back to a framework
            ``JobRun.status="dead_letter"`` row (cycle 2).
        timeout_seconds: Wall-clock limit per attempt. Worker kills
            the handler subprocess on timeout and records a transient
            failure.
    """

    name: str
    title: str | None = None
    run: str = ""
    triggers: list[JobTrigger] = Field(default_factory=list)
    schedule: JobSchedule | None = None
    retry: int = Field(default=3, ge=0, le=20)
    retry_backoff: JobBackoff = JobBackoff.EXPONENTIAL
    dead_letter: str = ""
    timeout_seconds: int = Field(default=60, ge=1, le=86_400)

    model_config = ConfigDict(frozen=True)
