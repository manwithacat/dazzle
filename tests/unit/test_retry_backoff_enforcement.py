"""Tests for #1191 — runtime enforcement of declared retry_backoff.

Process-step side: ``step_executor.execute_step`` retry loop +
``_compute_step_backoff`` formula. Mocks the inner dispatch to fail N times
then succeed. Delays cap at ``MAX_STEP_BACKOFF_SECONDS`` — the cap tests
guard against a high attempt number running away. (The job-side half went
with the `job` construct, parked under DD-008.)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from dazzle.core.process import step_executor
from dazzle.core.process.step_executor import (
    MAX_STEP_BACKOFF_SECONDS,
    _compute_step_backoff,
    execute_step,
)

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
