"""Tests for #953 cycle 4 — `process_one` worker function.

Cycle 3 built the queue + handler resolver. Cycle 4 adds the
single-job processor that ties them together with the JobRun status
state machine: pending → running → completed / failed / dead_letter,
plus retry re-enqueue.

Tests cover:

  * Successful run writes completed + timing
  * Sync handler invoked via `to_thread`-equivalent
  * Async handler awaited
  * Exception with retries-remaining → re-enqueue with attempt+1,
    current row marked failed (with retry note)
  * Exception with retries-exhausted + no dead_letter spec → failed
  * Exception with retries-exhausted + dead_letter spec → dead_letter
  * Misconfigured handler path → failed (never retry)
  * Missing JobSpec for the dequeued message → failed (NO_SPEC)
  * JobRun service failures don't crash the worker (best-effort)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from dazzle_back.runtime.job_queue import InMemoryJobQueue, JobMessage
from dazzle_back.runtime.job_worker import WorkerOutcome, process_one

# ---------------------------------------------------------------------------
# Test handlers (importable as module:attr — process_one will resolve them)
# ---------------------------------------------------------------------------


_call_log: list[tuple[str, dict[str, Any]]] = []


def sync_handler_ok(**kwargs: Any) -> str:
    _call_log.append(("sync_handler_ok", dict(kwargs)))
    return "ok"


def sync_handler_raises(**kwargs: Any) -> None:
    _call_log.append(("sync_handler_raises", dict(kwargs)))
    raise RuntimeError("boom")


async def async_handler_ok(**kwargs: Any) -> str:
    _call_log.append(("async_handler_ok", dict(kwargs)))
    await asyncio.sleep(0)
    return "ok"


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


@dataclass
class _SpecStub:
    name: str
    run: str
    retry: int = 0
    dead_letter: str = ""


@dataclass
class _JobServiceStub:
    """Records every update call so tests can assert on the
    state-machine transitions."""

    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    fail_with: Exception | None = None

    async def update(self, job_run_id: str, fields: dict[str, Any]) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.calls.append((job_run_id, dict(fields)))


def _msg(job_name: str, *, attempt: int = 1, payload: dict | None = None) -> JobMessage:
    return JobMessage(
        job_name=job_name,
        payload=payload or {},
        attempt=attempt,
        job_run_id="run-1",
    )


def _run(coro):
    _call_log.clear()
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestSuccess:
    def test_sync_handler_completes(self):
        spec = _SpecStub(name="x", run="tests.unit.test_job_worker:sync_handler_ok")
        svc = _JobServiceStub()
        q = InMemoryJobQueue()

        outcome = _run(
            process_one(
                _msg("x", payload={"a": 1}),
                job_specs={"x": spec},
                job_service=svc,
                queue=q,
            )
        )
        assert outcome == WorkerOutcome.COMPLETED
        # Handler invoked with the payload.
        assert ("sync_handler_ok", {"a": 1}) in _call_log
        # State machine: running → completed.
        statuses = [c[1].get("status") for c in svc.calls]
        assert statuses == ["running", "completed"]
        # Completed row has finished_at + duration_ms.
        completed = svc.calls[-1][1]
        assert "finished_at" in completed
        assert "duration_ms" in completed
        assert completed["duration_ms"] >= 0

    def test_async_handler_awaited(self):
        spec = _SpecStub(name="x", run="tests.unit.test_job_worker:async_handler_ok")
        svc = _JobServiceStub()
        q = InMemoryJobQueue()

        outcome = _run(
            process_one(
                _msg("x", payload={"k": "v"}),
                job_specs={"x": spec},
                job_service=svc,
                queue=q,
            )
        )
        assert outcome == WorkerOutcome.COMPLETED
        assert ("async_handler_ok", {"k": "v"}) in _call_log

    def test_running_row_carries_attempt_number(self):
        spec = _SpecStub(name="x", run="tests.unit.test_job_worker:sync_handler_ok")
        svc = _JobServiceStub()
        q = InMemoryJobQueue()
        _run(
            process_one(
                _msg("x", attempt=3),
                job_specs={"x": spec},
                job_service=svc,
                queue=q,
            )
        )
        # First call is the "running" transition; it must carry the
        # attempt counter so admins reading JobRun rows can see it.
        assert svc.calls[0][1]["attempt_number"] == 3


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------


class TestRetry:
    def test_retry_eligible_re_enqueues(self):
        spec = _SpecStub(
            name="x",
            run="tests.unit.test_job_worker:sync_handler_raises",
            retry=2,
        )
        svc = _JobServiceStub()
        q = InMemoryJobQueue()

        outcome = _run(
            process_one(
                _msg("x", attempt=1),
                job_specs={"x": spec},
                job_service=svc,
                queue=q,
            )
        )
        assert outcome == WorkerOutcome.RETRIED
        # Current row marked failed with "retrying" note.
        failed = svc.calls[-1][1]
        assert failed["status"] == "failed"
        assert "retrying" in failed["error_message"]

        # Queue has the next attempt with attempt+1.
        async def peek():
            return await q.dequeue(timeout=0.1)

        next_msg = asyncio.run(peek())
        assert next_msg is not None
        assert next_msg.attempt == 2
        assert next_msg.job_name == "x"

    def test_retry_exhausted_failed_without_dead_letter(self):
        spec = _SpecStub(
            name="x",
            run="tests.unit.test_job_worker:sync_handler_raises",
            retry=1,  # max_attempts = 2
            dead_letter="",
        )
        svc = _JobServiceStub()
        q = InMemoryJobQueue()

        outcome = _run(
            process_one(
                _msg("x", attempt=2),
                job_specs={"x": spec},
                job_service=svc,
                queue=q,
            )
        )
        assert outcome == WorkerOutcome.FAILED
        final = svc.calls[-1][1]
        assert final["status"] == "failed"
        assert "RuntimeError" in final["error_message"]
        # Nothing re-enqueued.
        assert asyncio.run(q.size()) == 0

    def test_retry_exhausted_dead_letter_when_spec_declares(self):
        spec = _SpecStub(
            name="x",
            run="tests.unit.test_job_worker:sync_handler_raises",
            retry=1,
            dead_letter="ManuscriptDeadLetter",
        )
        svc = _JobServiceStub()
        q = InMemoryJobQueue()

        outcome = _run(
            process_one(
                _msg("x", attempt=2),
                job_specs={"x": spec},
                job_service=svc,
                queue=q,
            )
        )
        assert outcome == WorkerOutcome.DEAD_LETTER
        final = svc.calls[-1][1]
        assert final["status"] == "dead_letter"

    def test_retry_zero_means_one_attempt_only(self):
        # retry=0 → max_attempts=1, so attempt 1 failure is terminal.
        spec = _SpecStub(
            name="x",
            run="tests.unit.test_job_worker:sync_handler_raises",
            retry=0,
        )
        svc = _JobServiceStub()
        q = InMemoryJobQueue()

        outcome = _run(
            process_one(
                _msg("x", attempt=1),
                job_specs={"x": spec},
                job_service=svc,
                queue=q,
            )
        )
        assert outcome == WorkerOutcome.FAILED


# ---------------------------------------------------------------------------
# Misconfiguration
# ---------------------------------------------------------------------------


class TestMisconfiguration:
    def test_missing_spec_marks_failed(self):
        svc = _JobServiceStub()
        q = InMemoryJobQueue()
        outcome = _run(
            process_one(
                _msg("not_declared"),
                job_specs={},
                job_service=svc,
                queue=q,
            )
        )
        assert outcome == WorkerOutcome.NO_SPEC
        # Single update call, status=failed with helpful message.
        assert len(svc.calls) == 1
        assert svc.calls[0][1]["status"] == "failed"
        assert "No JobSpec" in svc.calls[0][1]["error_message"]

    def test_handler_not_found_never_retries(self):
        # Non-existent module → JobHandlerNotFound. Worker must NOT
        # re-enqueue (the spec is broken; retrying won't help).
        spec = _SpecStub(
            name="x",
            run="definitely_not_a_real_module:func",
            retry=5,
        )
        svc = _JobServiceStub()
        q = InMemoryJobQueue()
        outcome = _run(
            process_one(
                _msg("x"),
                job_specs={"x": spec},
                job_service=svc,
                queue=q,
            )
        )
        assert outcome == WorkerOutcome.FAILED
        assert asyncio.run(q.size()) == 0  # Never re-enqueued.


# ---------------------------------------------------------------------------
# Best-effort JobRun updates
# ---------------------------------------------------------------------------


class TestJobServiceFailures:
    def test_jobrun_update_failure_does_not_crash_worker(self):
        # JobRun service is broken. The worker must still complete
        # processing without raising — best-effort observability.
        spec = _SpecStub(name="x", run="tests.unit.test_job_worker:sync_handler_ok")
        svc = _JobServiceStub(fail_with=RuntimeError("DB down"))
        q = InMemoryJobQueue()

        # No exception should escape.
        outcome = _run(
            process_one(
                _msg("x"),
                job_specs={"x": spec},
                job_service=svc,
                queue=q,
            )
        )
        assert outcome == WorkerOutcome.COMPLETED

    def test_none_job_service_tolerated(self):
        # During early bootstrap before services exist — still works.
        spec = _SpecStub(name="x", run="tests.unit.test_job_worker:sync_handler_ok")
        q = InMemoryJobQueue()
        outcome = _run(
            process_one(
                _msg("x"),
                job_specs={"x": spec},
                job_service=None,
                queue=q,
            )
        )
        assert outcome == WorkerOutcome.COMPLETED
