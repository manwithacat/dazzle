"""Tests for #1191 — runtime enforcement of declared retry_backoff.

Two-part coverage:

  * **Job side**: ``job_worker._compute_backoff_delay`` and the
    ``_handle_failure`` sleep contract. Mocks ``asyncio.sleep`` so the
    test suite stays fast regardless of the configured delays.
  * **Process-step side**: ``step_executor.execute_step`` retry loop +
    ``_compute_step_backoff`` formula. Mocks the inner dispatch to
    fail N times then succeed.

Both subsystems cap delays at their own ``MAX_*_BACKOFF`` constant —
the cap tests guard against a high attempt number running away.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

import pytest

from dazzle.core.ir.jobs import JobBackoff
from dazzle.core.process import step_executor
from dazzle.core.process.step_executor import (
    MAX_STEP_BACKOFF_SECONDS,
    _compute_step_backoff,
    execute_step,
)
from dazzle.http.runtime import job_worker
from dazzle.http.runtime.job_queue import InMemoryJobQueue, JobMessage
from dazzle.http.runtime.job_worker import (
    MAX_BACKOFF_SECONDS,
    WorkerOutcome,
    _compute_backoff_delay,
    process_one,
)

# ===========================================================================
# Job-side: _compute_backoff_delay pure function
# ===========================================================================


class TestJobBackoffFormula:
    def test_none_returns_zero(self):
        for attempt in (1, 2, 5, 10):
            assert _compute_backoff_delay(JobBackoff.NONE, attempt) == 0.0

    def test_linear_grows_linearly(self):
        assert _compute_backoff_delay(JobBackoff.LINEAR, 1) == 1.0
        assert _compute_backoff_delay(JobBackoff.LINEAR, 2) == 2.0
        assert _compute_backoff_delay(JobBackoff.LINEAR, 3) == 3.0
        assert _compute_backoff_delay(JobBackoff.LINEAR, 10) == 10.0

    def test_exponential_doubles(self):
        assert _compute_backoff_delay(JobBackoff.EXPONENTIAL, 1) == 1.0
        assert _compute_backoff_delay(JobBackoff.EXPONENTIAL, 2) == 2.0
        assert _compute_backoff_delay(JobBackoff.EXPONENTIAL, 3) == 4.0
        assert _compute_backoff_delay(JobBackoff.EXPONENTIAL, 4) == 8.0
        assert _compute_backoff_delay(JobBackoff.EXPONENTIAL, 5) == 16.0

    def test_cap_enforced_exponential(self):
        # 2 ** (50 - 1) is astronomically large; must be clamped.
        delay = _compute_backoff_delay(JobBackoff.EXPONENTIAL, 50)
        assert delay == MAX_BACKOFF_SECONDS

    def test_cap_enforced_linear(self):
        delay = _compute_backoff_delay(JobBackoff.LINEAR, 10_000)
        assert delay == MAX_BACKOFF_SECONDS

    def test_attempt_zero_is_no_sleep(self):
        # Defensive — caller should pass attempt >= 1.
        assert _compute_backoff_delay(JobBackoff.EXPONENTIAL, 0) == 0.0


# ===========================================================================
# Job-side: process_one re-enqueue path honours the backoff sleep
# ===========================================================================


@dataclass
class _SpecStub:
    name: str
    run: str
    retry: int = 3
    retry_backoff: JobBackoff = JobBackoff.EXPONENTIAL
    dead_letter: str = ""


@dataclass
class _JobServiceStub:
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def update(self, job_run_id: str, fields: dict[str, Any]) -> None:
        self.calls.append((job_run_id, dict(fields)))


def _msg(job_name: str, *, attempt: int = 1) -> JobMessage:
    return JobMessage(
        job_name=job_name,
        payload={},
        attempt=attempt,
        job_run_id="run-1",
    )


def _always_raises(**kwargs: Any) -> None:
    raise RuntimeError("boom")


# Make the failing handler resolvable through ``resolve_handler``.
import sys as _sys  # noqa: E402

_sys.modules[__name__].always_raises = _always_raises  # type: ignore[attr-defined]
_HANDLER_PATH = f"{__name__}:always_raises"


class TestJobWorkerHonoursBackoff:
    def test_none_no_sleep(self):
        spec = _SpecStub(
            name="x",
            run=_HANDLER_PATH,
            retry=3,
            retry_backoff=JobBackoff.NONE,
        )
        svc = _JobServiceStub()
        q = InMemoryJobQueue()

        sleeps: list[float] = []

        async def fake_sleep(d: float) -> None:
            sleeps.append(d)

        with patch.object(job_worker.asyncio, "sleep", fake_sleep):
            outcome = asyncio.run(
                process_one(_msg("x"), job_specs={"x": spec}, job_service=svc, queue=q)
            )

        assert outcome == WorkerOutcome.RETRIED
        # NONE → delay == 0 → no sleep call at all.
        assert sleeps == []

    def test_linear_sleeps_in_sequence(self):
        sleeps: list[float] = []

        async def fake_sleep(d: float) -> None:
            sleeps.append(d)

        with patch.object(job_worker.asyncio, "sleep", fake_sleep):
            for attempt in (1, 2, 3):
                spec = _SpecStub(
                    name="x",
                    run=_HANDLER_PATH,
                    retry=5,
                    retry_backoff=JobBackoff.LINEAR,
                )
                svc = _JobServiceStub()
                q = InMemoryJobQueue()
                asyncio.run(
                    process_one(
                        _msg("x", attempt=attempt),
                        job_specs={"x": spec},
                        job_service=svc,
                        queue=q,
                    )
                )

        assert sleeps == [1.0, 2.0, 3.0]

    def test_exponential_sleeps_double(self):
        sleeps: list[float] = []

        async def fake_sleep(d: float) -> None:
            sleeps.append(d)

        with patch.object(job_worker.asyncio, "sleep", fake_sleep):
            for attempt in (1, 2, 3, 4):
                spec = _SpecStub(
                    name="x",
                    run=_HANDLER_PATH,
                    retry=10,
                    retry_backoff=JobBackoff.EXPONENTIAL,
                )
                svc = _JobServiceStub()
                q = InMemoryJobQueue()
                asyncio.run(
                    process_one(
                        _msg("x", attempt=attempt),
                        job_specs={"x": spec},
                        job_service=svc,
                        queue=q,
                    )
                )

        assert sleeps == [1.0, 2.0, 4.0, 8.0]

    def test_cap_enforced_runaway_exponential(self):
        sleeps: list[float] = []

        async def fake_sleep(d: float) -> None:
            sleeps.append(d)

        spec = _SpecStub(
            name="x",
            run=_HANDLER_PATH,
            retry=20,
            retry_backoff=JobBackoff.EXPONENTIAL,
        )
        svc = _JobServiceStub()
        q = InMemoryJobQueue()
        # attempt=15 → 2**14 = 16384 raw, must clamp.
        with patch.object(job_worker.asyncio, "sleep", fake_sleep):
            asyncio.run(
                process_one(
                    _msg("x", attempt=15),
                    job_specs={"x": spec},
                    job_service=svc,
                    queue=q,
                )
            )

        assert sleeps == [MAX_BACKOFF_SECONDS]


# ===========================================================================
# Process-step side: _compute_step_backoff pure function
# ===========================================================================


class TestStepBackoffFormula:
    def test_fixed_returns_initial(self):
        for attempt in (1, 2, 3):
            assert (
                _compute_step_backoff(
                    strategy="fixed",
                    initial=2.0,
                    coefficient=2.0,
                    attempt=attempt,
                    max_interval=60,
                )
                == 2.0
            )

    def test_linear_multiplies_by_attempt(self):
        assert (
            _compute_step_backoff(
                strategy="linear",
                initial=1.5,
                coefficient=2.0,
                attempt=3,
                max_interval=60,
            )
            == 4.5
        )

    def test_exponential_uses_coefficient(self):
        # attempt 1 → 2 * 3^0 = 2
        # attempt 2 → 2 * 3^1 = 6
        # attempt 3 → 2 * 3^2 = 18
        assert _compute_step_backoff(
            strategy="exponential",
            initial=2.0,
            coefficient=3.0,
            attempt=1,
            max_interval=60,
        ) == pytest.approx(2.0)
        assert _compute_step_backoff(
            strategy="exponential",
            initial=2.0,
            coefficient=3.0,
            attempt=2,
            max_interval=60,
        ) == pytest.approx(6.0)
        assert _compute_step_backoff(
            strategy="exponential",
            initial=2.0,
            coefficient=3.0,
            attempt=3,
            max_interval=60,
        ) == pytest.approx(18.0)

    def test_max_interval_cap(self):
        # Big attempt clamps to max_interval.
        delay = _compute_step_backoff(
            strategy="exponential",
            initial=1.0,
            coefficient=2.0,
            attempt=20,
            max_interval=5.0,
        )
        assert delay == 5.0


# ===========================================================================
# Process-step side: execute_step retry loop
# ===========================================================================


def _make_step(retry: dict | None = None) -> dict:
    step: dict[str, Any] = {"name": "step1", "kind": "service", "service": "Foo.bar"}
    if retry is not None:
        step["retry"] = retry
    return step


class TestExecuteStepRetry:
    def test_no_retry_on_success(self):
        sleeps: list[float] = []
        calls: list[int] = []

        def fake_dispatch(*args, **kwargs):
            calls.append(1)
            return {"output": "ok"}

        with (
            patch.object(step_executor, "_dispatch_step", fake_dispatch),
            patch.object(step_executor.time, "sleep", lambda d: sleeps.append(d)),
        ):
            result = execute_step(None, None, {}, _make_step(retry={"max_attempts": 3}))

        assert result == {"output": "ok"}
        assert calls == [1]
        assert sleeps == []

    def test_retries_then_succeeds(self):
        sleeps: list[float] = []
        attempt_counter = {"n": 0}

        def fake_dispatch(*args, **kwargs):
            attempt_counter["n"] += 1
            if attempt_counter["n"] < 3:
                raise RuntimeError("transient")
            return {"output": "ok"}

        retry = {
            "max_attempts": 3,
            "initial_interval_seconds": 1,
            "backoff": "exponential",
            "backoff_coefficient": 2.0,
            "max_interval_seconds": 60,
        }

        with (
            patch.object(step_executor, "_dispatch_step", fake_dispatch),
            patch.object(step_executor.time, "sleep", lambda d: sleeps.append(d)),
        ):
            result = execute_step(None, None, {}, _make_step(retry=retry))

        assert result == {"output": "ok"}
        assert attempt_counter["n"] == 3
        # 2 sleeps (between 3 attempts), exponential 1 * 2^0 then 1 * 2^1.
        assert sleeps == [1.0, 2.0]

    def test_always_fails_raises_after_max_attempts(self):
        sleeps: list[float] = []
        calls: list[int] = []

        def fake_dispatch(*args, **kwargs):
            calls.append(1)
            raise RuntimeError("permanent")

        retry = {
            "max_attempts": 3,
            "initial_interval_seconds": 1,
            "backoff": "exponential",
            "backoff_coefficient": 2.0,
            "max_interval_seconds": 60,
        }

        with (
            patch.object(step_executor, "_dispatch_step", fake_dispatch),
            patch.object(step_executor.time, "sleep", lambda d: sleeps.append(d)),
        ):
            with pytest.raises(RuntimeError, match="permanent"):
                execute_step(None, None, {}, _make_step(retry=retry))

        # 3 dispatch calls, 2 sleeps in between (the final failure
        # doesn't sleep — it raises).
        assert len(calls) == 3
        assert sleeps == [1.0, 2.0]

    def test_no_retry_block_means_single_attempt(self):
        # Step without `retry:` → max_attempts defaults to 1 → no
        # retry loop; the first failure propagates immediately.
        sleeps: list[float] = []
        calls: list[int] = []

        def fake_dispatch(*args, **kwargs):
            calls.append(1)
            raise RuntimeError("boom")

        with (
            patch.object(step_executor, "_dispatch_step", fake_dispatch),
            patch.object(step_executor.time, "sleep", lambda d: sleeps.append(d)),
        ):
            with pytest.raises(RuntimeError, match="boom"):
                execute_step(None, None, {}, _make_step())

        assert calls == [1]
        assert sleeps == []

    def test_step_backoff_clamped_to_module_max(self):
        # Verify the MAX_STEP_BACKOFF_SECONDS safety net kicks in even
        # when max_interval is configured absurdly high.
        sleeps: list[float] = []
        attempt_counter = {"n": 0}

        def fake_dispatch(*args, **kwargs):
            attempt_counter["n"] += 1
            if attempt_counter["n"] < 2:
                raise RuntimeError("transient")
            return {"output": "ok"}

        retry = {
            "max_attempts": 5,
            "initial_interval_seconds": 10_000,
            "backoff": "fixed",
            "backoff_coefficient": 1.0,
            # Pathological: max_interval larger than the module cap.
            "max_interval_seconds": 10_000_000,
        }

        with (
            patch.object(step_executor, "_dispatch_step", fake_dispatch),
            patch.object(step_executor.time, "sleep", lambda d: sleeps.append(d)),
        ):
            execute_step(None, None, {}, _make_step(retry=retry))

        assert sleeps == [MAX_STEP_BACKOFF_SECONDS]
