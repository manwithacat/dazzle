"""Tests for checkpoint-skip in execute_process_steps (at-least-once replay safety).

A re-claimed run (worker crash + lease reclaim) re-enters execute_process_steps
with run.context already populated for completed steps. Without checkpoint-skip,
those steps would re-execute — violating idempotency for non-idempotent side effects
(service calls, sends).

These tests verify:
1. A step whose output is already in run.context is NOT re-executed.
2. A fresh run executes all steps; on second call (replay), no step re-runs.
3. A step that PAUSEs (human_task / wait → status WAITING) is NOT marked
   complete — so on resume it re-enters the step correctly.
"""

import uuid
from unittest.mock import MagicMock, patch

from dazzle.core.process.adapter import ProcessRun, ProcessStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_store(steps: list[dict]) -> MagicMock:
    store = MagicMock()
    store.get_process_spec.return_value = {
        "name": "test_process",
        "steps": steps,
    }
    return store


def _make_run(**kwargs) -> ProcessRun:
    defaults = {
        "run_id": str(uuid.uuid4()),
        "process_name": "test_process",
        "status": ProcessStatus.PENDING,
        "inputs": {},
        "context": {},
    }
    defaults.update(kwargs)
    return ProcessRun(**defaults)


# ---------------------------------------------------------------------------
# Test 1: step already in context → skipped (side-effect spy NOT called)
# ---------------------------------------------------------------------------


def test_checkpoint_skip_already_completed_step():
    """Step whose output is already in run.context must NOT be re-executed."""
    from dazzle.core.process.step_executor import execute_process_steps

    # step_a already completed — its output is in context
    # step_b is new and must execute
    steps = [
        {"name": "step_a", "kind": "send", "channel": "email"},
        {"name": "step_b", "kind": "send", "channel": "sms"},
    ]
    store = _make_store(steps)
    run = _make_run(context={"step_a": {"sent": True, "channel": "email"}})

    spy_calls: list[str] = []

    original_dispatch = None

    def spy_dispatch(store_, run_, spec_, step_, *, on_task_created=None):
        spy_calls.append(step_.get("name", "unknown"))
        return original_dispatch(store_, run_, spec_, step_, on_task_created=on_task_created)

    import dazzle.core.process.step_executor as mod

    original_dispatch = mod._dispatch_step

    with patch.object(mod, "_dispatch_step", side_effect=spy_dispatch):
        result = execute_process_steps(store, run)

    assert result["status"] == "completed", f"Unexpected result: {result}"
    # step_a must NOT have been dispatched (it was in context already)
    assert "step_a" not in spy_calls, f"step_a was re-dispatched: {spy_calls}"
    # step_b must have run
    assert "step_b" in spy_calls, f"step_b was not dispatched: {spy_calls}"


# ---------------------------------------------------------------------------
# Test 2: idempotent replay — second call skips all completed steps
# ---------------------------------------------------------------------------


def test_idempotent_replay_second_call_skips_all():
    """After a full run, replaying execute_process_steps must skip every step."""
    from dazzle.core.process.step_executor import execute_process_steps

    steps = [
        {"name": "step_a", "kind": "send", "channel": "email"},
        {"name": "step_b", "kind": "send", "channel": "sms"},
    ]
    store = _make_store(steps)

    # First call — fresh run
    run = _make_run()
    first_result = execute_process_steps(store, run)
    assert first_result["status"] == "completed"

    # After first call, both steps' outputs must be recorded in context
    assert "step_a" in run.context, "step_a output not recorded in context after first run"
    assert "step_b" in run.context, "step_b output not recorded in context after first run"

    # Reset status to simulate re-delivery (worker reclaim)
    run.status = ProcessStatus.PENDING

    spy_calls: list[str] = []

    import dazzle.core.process.step_executor as mod

    original_dispatch = mod._dispatch_step

    def spy_dispatch(store_, run_, spec_, step_, *, on_task_created=None):
        spy_calls.append(step_.get("name", "unknown"))
        return original_dispatch(store_, run_, spec_, step_, on_task_created=on_task_created)

    with patch.object(mod, "_dispatch_step", side_effect=spy_dispatch):
        second_result = execute_process_steps(store, run)

    assert second_result["status"] == "completed"
    # Neither step should have been re-dispatched
    assert spy_calls == [], f"Steps were re-dispatched on replay: {spy_calls}"


# ---------------------------------------------------------------------------
# Test 3: paused step (human_task) is NOT marked complete
# ---------------------------------------------------------------------------


def test_paused_step_not_marked_complete():
    """A step that causes a WAIT (human_task) must NOT be written to run.context.

    On resume the step must re-enter (the task resolution provides the outcome).
    """
    from dazzle.core.process.step_executor import execute_process_steps

    steps = [
        {"name": "step_a", "kind": "send", "channel": "email"},
        {"name": "review", "kind": "human_task", "surface": "review_form"},
        {"name": "step_c", "kind": "send", "channel": "sms"},
    ]
    store = _make_store(steps)
    run = _make_run()

    result = execute_process_steps(store, run)

    assert result["status"] == "waiting"
    assert run.status == ProcessStatus.WAITING
    # step_a completed → must be in context
    assert "step_a" in run.context, "step_a should be in context after completing"
    # 'review' paused → must NOT be in context (not yet complete)
    assert "review" not in run.context, (
        "paused human_task step 'review' must NOT be recorded as complete in context"
    )
    # step_c never ran
    assert "step_c" not in run.context
