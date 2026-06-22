"""#1133: DSL test runner must dispatch the 4 previously-unknown actions
``fill_form`` / ``submit_form`` / ``create_expect_error`` / ``assert_error``
and surface any remaining unknown action types as a single ERROR-level
preflight line instead of per-step WARNING noise.

Pre-fix, generated test designs referencing these actions emitted
hundreds of ``WARNING - Unknown test action 'X' — step skipped`` lines
per ``dazzle test dsl-run`` invocation, and the TD-* tests whose setup
depended on the skipped steps failed silently with "UI check failed"
and no further detail.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from dazzle.testing.step_executor import StepExecutor
from dazzle.testing.test_runner import StepResult, TestResult, TestRunner

# ---------------------------------------------------------------------------
# Dispatch table membership — locks the four actions into the wiring
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "action",
    ["fill_form", "submit_form", "create_expect_error", "assert_error"],
)
def test_action_has_dispatch_entry(action: str) -> None:
    """All four actions must resolve to a handler — silent skip is
    the bug class this issue closes."""
    dispatch = {**StepExecutor._STEP_DISPATCH_SINGLE, **StepExecutor._STEP_DISPATCH_MULTI}
    assert action in dispatch, f"{action!r} missing from runner dispatch tables"


# ---------------------------------------------------------------------------
# fill_form / submit_form — UI-only aliases
# ---------------------------------------------------------------------------


def _runner() -> TestRunner:
    return TestRunner(project_path=Path("/tmp/_test_1133"))


@pytest.mark.parametrize("action", ["fill_form", "submit_form"])
def test_ui_form_actions_skip_cleanly_in_api_mode(action: str) -> None:
    """``fill_form`` / ``submit_form`` need a browser; API-only mode
    must SKIP them with the same shape as ``click`` / ``fill``,
    not emit "Unknown test action"."""
    runner = _runner()
    runner.client = MagicMock()
    result = runner.execute_step({"action": action, "target": "task_form"}, design={})
    assert isinstance(result, StepResult)
    assert result.result is TestResult.SKIPPED
    # The runner's "unknown action" branch returns SKIPPED with a
    # message starting "Unknown test action". The UI-only path returns
    # the more specific "UI action skipped in API test" message.
    assert "UI action skipped" in result.message


# ---------------------------------------------------------------------------
# create_expect_error — validation tests
# ---------------------------------------------------------------------------


def test_create_expect_error_passes_on_4xx() -> None:
    """4xx response → PASS (the request was supposed to be rejected)."""
    runner = _runner()
    runner.client = MagicMock()
    runner.client.api_url = "http://x"
    runner.client.entities._entity_endpoint = MagicMock(return_value="/api/task")
    runner.client._auth_headers = MagicMock(return_value={})
    resp = MagicMock(status_code=422, json=lambda: {"detail": "bad"}, text="bad")
    runner.client._request = MagicMock(return_value=resp)

    ctx: dict = {}
    result = runner.execute_step(
        {"action": "create_expect_error", "target": "entity:Task", "data": {}},
        design={},
        context=ctx,
    )
    assert result.result is TestResult.PASSED
    assert ctx["last_response"] is resp


def test_create_expect_error_fails_on_2xx() -> None:
    """A creation request that *succeeded* (2xx) when it was expected
    to fail is a real bug — must FAIL, not PASS."""
    runner = _runner()
    runner.client = MagicMock()
    runner.client.api_url = "http://x"
    runner.client.entities._entity_endpoint = MagicMock(return_value="/api/task")
    runner.client._auth_headers = MagicMock(return_value={})
    resp = MagicMock(status_code=201, json=lambda: {"id": "1"}, text="")
    runner.client._request = MagicMock(return_value=resp)

    result = runner.execute_step(
        {"action": "create_expect_error", "target": "entity:Task", "data": {}},
        design={},
        context={},
    )
    assert result.result is TestResult.FAILED


# ---------------------------------------------------------------------------
# assert_error — introspect last_response
# ---------------------------------------------------------------------------


def test_assert_error_passes_on_4xx() -> None:
    runner = _runner()
    runner.client = MagicMock()
    resp = MagicMock(status_code=400, json=lambda: {}, text="")
    result = runner.execute_step(
        {"action": "assert_error", "target": ""},
        design={},
        context={"last_response": resp},
    )
    assert result.result is TestResult.PASSED


def test_assert_error_passes_on_detail_key_with_2xx() -> None:
    """FastAPI-shape error body (``{"detail": [...]}``) passes even
    when the wire status was 200 (some APIs put validation errors in
    the body of a 200 response)."""
    runner = _runner()
    runner.client = MagicMock()
    resp = MagicMock(
        status_code=200,
        json=lambda: {"detail": [{"loc": ["body", "title"], "msg": "required"}]},
        text="",
    )
    result = runner.execute_step(
        {"action": "assert_error", "target": ""},
        design={},
        context={"last_response": resp},
    )
    assert result.result is TestResult.PASSED


def test_assert_error_fails_on_clean_2xx_no_error_body() -> None:
    runner = _runner()
    runner.client = MagicMock()
    resp = MagicMock(status_code=200, json=lambda: {"id": "1"}, text="")
    result = runner.execute_step(
        {"action": "assert_error", "target": ""},
        design={},
        context={"last_response": resp},
    )
    assert result.result is TestResult.FAILED


def test_assert_error_fails_when_no_last_response() -> None:
    runner = _runner()
    runner.client = MagicMock()
    result = runner.execute_step(
        {"action": "assert_error", "target": ""},
        design={},
        context={},
    )
    assert result.result is TestResult.FAILED
    assert "No previous response" in result.message


# ---------------------------------------------------------------------------
# Preflight: unknown-action discovery + fail-loud logging
# ---------------------------------------------------------------------------


def test_scan_unknown_actions_returns_only_truly_unknown() -> None:
    """Action names with dispatch entries are NOT reported; novel ones are.

    Note: ``achieve_goal`` was wired up in #1138 — it is now KNOWN.
    The truly-unknown actions in this test are deliberately invented.
    """
    runner = _runner()
    designs = [
        {
            "test_id": "TD-1",
            "title": "t",
            "steps": [
                {"action": "login_as", "target": "admin"},  # known
                {"action": "fill_form", "target": "x"},  # known
                {"action": "create_expect_error", "target": "y"},  # known
                {"action": "trigger_process", "target": "z"},  # unknown
                {"action": "wave_magic_wand", "target": "z"},  # unknown
            ],
        }
    ]
    unknown = runner.steps._scan_unknown_actions(designs)
    assert unknown == {"trigger_process", "wave_magic_wand"}


def test_scan_unknown_actions_returns_empty_when_all_known() -> None:
    """All-known design → empty set, no preflight ERROR line."""
    runner = _runner()
    designs = [
        {
            "steps": [
                {"action": "fill_form", "target": "x"},
                {"action": "submit_form", "target": "x"},
                {"action": "create_expect_error", "target": "y"},
                {"action": "assert_error", "target": ""},
            ]
        }
    ]
    assert runner.steps._scan_unknown_actions(designs) == set()


def test_run_emits_preflight_error_for_unknown_actions(caplog, monkeypatch) -> None:
    """End-to-end: an unknown action in a design surfaces as a single
    ERROR-level preflight line. Pre-fix, the same condition produced
    per-step WARNING noise that drowned out the actual failure modes."""
    runner = _runner()
    designs = [
        {
            "test_id": "TD-X",
            "title": "x",
            "tags": [],
            "steps": [{"action": "wave_magic_wand", "target": "z"}],
        }
    ]
    # Stub the wait_for_ready 20s server probe — preflight fires before
    # it, so a short-circuit lets the test run in milliseconds without
    # changing what's under test.
    from dazzle.testing.test_runner import DazzleClient

    monkeypatch.setattr(DazzleClient, "wait_for_ready", lambda self, max_wait=20: False)
    with caplog.at_level(logging.ERROR, logger="dazzle.testing.test_runner"):
        runner.run_tests_from_designs(designs)

    matches = [
        r
        for r in caplog.records
        if r.levelno >= logging.ERROR and "unknown action type" in r.getMessage()
    ]
    assert matches, (
        f"Expected ERROR-level preflight log; got {[r.getMessage() for r in caplog.records]}"
    )
    assert "wave_magic_wand" in matches[0].getMessage()
