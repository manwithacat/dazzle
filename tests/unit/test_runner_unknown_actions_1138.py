"""#1138: 5 more action types must dispatch to handlers instead of
falling through to the "Unknown test action" warning branch.

``transition`` / ``transition_expect_error`` / ``assert_state`` SKIP
cleanly (the cross-step entity-id contract isn't standardised yet —
a SKIP is strictly better than a noisy WARNING + opaque downstream
failure). ``assert_authenticated`` gets a real handler (positive
inverse of ``assert_unauthenticated``). ``achieve_goal`` aliases
``_execute_ui_only_step`` since goal recipes are multi-step UI flows.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from dazzle.testing.step_executor import StepExecutor
from dazzle.testing.test_runner import StepResult, TestResult, TestRunner


def _runner() -> TestRunner:
    return TestRunner(project_path=Path("/tmp/_test_1138"))


@pytest.mark.parametrize(
    "action",
    [
        "transition",
        "transition_expect_error",
        "assert_state",
        "assert_authenticated",
        "achieve_goal",
    ],
)
def test_action_has_dispatch_entry(action: str) -> None:
    """The 5 previously-unknown actions must all resolve to a handler."""
    dispatch = {**StepExecutor._STEP_DISPATCH_SINGLE, **StepExecutor._STEP_DISPATCH_MULTI}
    assert action in dispatch, f"{action!r} missing from runner dispatch tables"


def test_unknown_action_scan_no_longer_reports_the_five() -> None:
    """All 5 actions previously surfaced in the ERROR-level preflight
    line; with dispatch entries in place, the scan must return empty."""
    runner = _runner()
    designs = [
        {
            "steps": [
                {"action": "transition", "target": "t"},
                {"action": "transition_expect_error", "target": "t"},
                {"action": "assert_state", "target": "entity:Task"},
                {"action": "assert_authenticated", "target": ""},
                {"action": "achieve_goal", "target": "g"},
            ]
        }
    ]
    assert runner.steps._scan_unknown_actions(designs) == set()


# ---------------------------------------------------------------------------
# transition / transition_expect_error / assert_state — SKIP stubs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "action,expected_msg_fragment",
    [
        ("transition", "Transition requires"),
        ("transition_expect_error", "transition_expect_error requires"),
        ("assert_state", "assert_state requires"),
    ],
)
def test_state_machine_actions_skip_cleanly(action: str, expected_msg_fragment: str) -> None:
    runner = _runner()
    runner.client = MagicMock()
    result = runner.execute_step({"action": action, "target": "entity:Task"}, design={}, context={})
    assert isinstance(result, StepResult)
    assert result.result is TestResult.SKIPPED
    assert expected_msg_fragment in result.message


# ---------------------------------------------------------------------------
# assert_authenticated — real handler, positive inverse of assert_unauthenticated
# ---------------------------------------------------------------------------


def test_assert_authenticated_passes_on_200() -> None:
    runner = _runner()
    runner.client = MagicMock()
    resp = MagicMock(status_code=200, json=lambda: {}, text="")
    result = runner.execute_step(
        {"action": "assert_authenticated", "target": ""},
        design={},
        context={"last_response": resp},
    )
    assert result.result is TestResult.PASSED


def test_assert_authenticated_fails_on_401() -> None:
    """The shape that distinguishes assert_authenticated from
    assert_unauthenticated: 401 PASSES the inverse, FAILS this one."""
    runner = _runner()
    runner.client = MagicMock()
    resp = MagicMock(status_code=401, json=lambda: {}, text="")
    result = runner.execute_step(
        {"action": "assert_authenticated", "target": ""},
        design={},
        context={"last_response": resp},
    )
    assert result.result is TestResult.FAILED


def test_assert_authenticated_self_bootstraps_via_auth_me_when_no_response() -> None:
    """#1142: the canonical ACL pattern is `login_as` then
    `assert_authenticated`. login_as doesn't populate last_response,
    so the handler now probes `/auth/me` directly. 2xx → PASS."""
    runner = _runner()
    runner.client = MagicMock()
    runner.client.api_url = "http://x"
    runner.client._auth_headers = MagicMock(return_value={"Authorization": "Bearer t"})
    probe_resp = MagicMock(status_code=200, json=lambda: {"id": "u1"}, text="")
    runner.client._request = MagicMock(return_value=probe_resp)

    ctx: dict = {}
    result = runner.execute_step(
        {"action": "assert_authenticated", "target": "customer"},
        design={},
        context=ctx,
    )
    assert result.result is TestResult.PASSED
    # The probe target is /auth/me, called with the auth headers.
    call = runner.client._request.call_args
    assert call.args[0] == "GET"
    assert call.args[1] == "http://x/auth/me"
    # Response is stashed for downstream assert_error introspection.
    assert ctx["last_response"] is probe_resp


def test_assert_authenticated_honours_explicit_expect() -> None:
    """Designs can pin a narrower expected set via ``expect``."""
    runner = _runner()
    runner.client = MagicMock()
    resp = MagicMock(status_code=204, json=lambda: {}, text="")
    result = runner.execute_step(
        {
            "action": "assert_authenticated",
            "target": "",
            "data": {"expect": [200]},  # exclude 204
        },
        design={},
        context={"last_response": resp},
    )
    assert result.result is TestResult.FAILED


# ---------------------------------------------------------------------------
# achieve_goal — UI-only alias
# ---------------------------------------------------------------------------


def test_achieve_goal_skips_as_ui_only() -> None:
    runner = _runner()
    runner.client = MagicMock()
    result = runner.execute_step(
        {"action": "achieve_goal", "target": "submit_application"},
        design={},
        context={},
    )
    assert result.result is TestResult.SKIPPED
    assert "UI action skipped" in result.message
