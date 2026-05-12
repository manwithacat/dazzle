"""Minimal cron-expression parser + matcher (#953 cycle 7).

Supports the standard 5-field cron format:

    minute hour day month weekday

with three field forms:

  * ``*`` — every value
  * ``*/N`` — every N (e.g. ``*/5`` in minute = 0,5,10,…,55)
  * a literal integer

Comma-lists, ranges, and named weekdays are intentionally out of
scope for cycle 7 — they cover < 5% of typical schedule
declarations and parsing them adds complexity without unlocking
new use cases. Cycle 8+ can extend if a real DSL declaration
needs them.

The cycle-7b scheduler loop will:

  * `parse_cron` each `JobSpec.schedule.cron` at startup (raise
    early on invalid expressions)
  * Each minute, call `due_jobs` to get the list of jobs to
    enqueue
  * Track `last_fired_minute` per job so a slow tick doesn't
    double-fire when the loop catches up

Timezone handling is deferred — cycle 7 evaluates against UTC.
`JobSchedule.timezone` is captured but not yet honoured; cycle 8+
adds the ZoneInfo lookup.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

# Field bounds: (low_inclusive, high_inclusive)
_FIELD_BOUNDS: list[tuple[int, int]] = [
    (0, 59),  # minute
    (0, 23),  # hour
    (1, 31),  # day
    (1, 12),  # month
    (0, 6),  # weekday (0=Sunday, 6=Saturday — POSIX)
]


@dataclass(frozen=True)
class CronExpression:
    """Parsed 5-field cron expression — frozen sets of valid values
    per field. Used by `cron_matches` for O(1) per-field membership.
    """

    minute: frozenset[int]
    hour: frozenset[int]
    day: frozenset[int]
    month: frozenset[int]
    weekday: frozenset[int]


class CronParseError(ValueError):
    """Raised when a cron expression can't be parsed.

    Caught by the cycle-7b scheduler at startup so a malformed
    `JobSpec.schedule` aborts the deploy with a clear error rather
    than silently never firing.
    """


def parse_cron(expr: str) -> CronExpression:
    """Parse a 5-field cron expression into a `CronExpression`.

    Raises:
        CronParseError: If the expression isn't 5 fields, or any
            field is malformed / out of bounds.
    """
    if not isinstance(expr, str):
        raise CronParseError(f"Expected str, got {type(expr).__name__}")

    fields = expr.strip().split()
    if len(fields) != 5:
        raise CronParseError(
            f"Cron expression {expr!r} must have 5 fields (minute hour day month weekday)"
        )

    parsed: list[frozenset[int]] = []
    for field, (low, high) in zip(fields, _FIELD_BOUNDS, strict=True):
        try:
            parsed.append(_parse_field(field, low, high))
        except ValueError as exc:
            raise CronParseError(f"Invalid cron field {field!r}: {exc}") from exc

    return CronExpression(
        minute=parsed[0],
        hour=parsed[1],
        day=parsed[2],
        month=parsed[3],
        weekday=parsed[4],
    )


def _parse_field(field: str, low: int, high: int) -> frozenset[int]:
    """Parse one cron field. Supports `*`, `*/N`, and literal ints."""
    if field == "*":
        return frozenset(range(low, high + 1))

    if field.startswith("*/"):
        step_str = field[2:]
        if not step_str.isdigit():
            raise ValueError(f"step {step_str!r} must be a positive integer")
        step = int(step_str)
        if step <= 0:
            raise ValueError(f"step must be > 0, got {step}")
        return frozenset(range(low, high + 1, step))

    if not field.lstrip("-").isdigit():
        raise ValueError(
            "only `*`, `*/N`, and literal integers are supported "
            "(comma-lists / ranges out of scope for cycle 7)"
        )
    value = int(field)
    if value < low or value > high:
        raise ValueError(f"{value} out of bounds [{low}, {high}]")
    return frozenset({value})


def cron_matches(cron: CronExpression, when: datetime) -> bool:
    """True when ``when`` matches the parsed cron expression.

    POSIX weekday convention: 0 = Sunday … 6 = Saturday. Python's
    `datetime.weekday()` returns 0 = Monday … 6 = Sunday, so we
    rotate before comparing.
    """
    posix_weekday = (when.weekday() + 1) % 7
    return (
        when.minute in cron.minute
        and when.hour in cron.hour
        and when.day in cron.day
        and when.month in cron.month
        and posix_weekday in cron.weekday
    )


def due_jobs(
    jobs: Iterable[tuple[str, CronExpression]],
    *,
    now: datetime,
    last_fired_minute: dict[str, datetime],
) -> list[str]:
    """Return job names whose cron matches ``now`` and which
    haven't already fired this minute.

    Args:
        jobs: ``(job_name, parsed_cron)`` pairs from the cycle-7b
            scheduler's startup parse.
        now: Current wall-clock time (UTC).
        last_fired_minute: Per-job timestamp of the most recent
            firing, truncated to the minute. Mutated in place by
            the caller (cycle-7b loop) after the returned jobs
            are enqueued — passed in so this function stays pure
            on its own state.

    Returns:
        List of job names ready to enqueue. Empty when no cron
        matches at this minute, or all matching jobs have already
        fired.
    """
    minute_now = now.replace(second=0, microsecond=0)
    due: list[str] = []
    for job_name, cron in jobs:
        if not cron_matches(cron, minute_now):
            continue
        if last_fired_minute.get(job_name) == minute_now:
            continue  # already fired this minute
        due.append(job_name)
    return due
