"""#1149: assert_visible failures synthesise a fix hint when the
shape matches a known design omission (missing login_as or
missing navigate_to).

Pre-#1149 the message was "GET <url> → 302 | ''" — accurate but
opaque. The operator had to read framework source to learn that
302 + no auth meant they forgot login_as. Now the failure
message names the missing step.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from dazzle.testing.test_runner import TestResult, TestRunner, UICheckResult


def _runner_with_client(
    status: int,
    has_login: bool = False,
) -> TestRunner:
    runner = TestRunner(project_path=Path("/tmp/_test_1149"))
    client = MagicMock()
    client.ui_url = "http://stg.example"
    client._auth_token = "tok" if has_login else None
    client.client = MagicMock()
    cookies = MagicMock()
    cookies.get = MagicMock(return_value="sess" if has_login else None)
    client.client.cookies = cookies
    client.check_ui_loads = MagicMock(
        return_value=UICheckResult(
            ok=False,
            status=status,
            url="http://stg.example",
            excerpt="",
        )
    )
    runner.client = client
    return runner


def test_hint_suggests_login_as_on_302_without_auth() -> None:
    runner = _runner_with_client(status=302, has_login=False)
    result = runner.execute_step(
        {"action": "assert_visible", "target": "task"}, design={}, context={}
    )
    assert result.result is TestResult.FAILED
    assert "login_as" in result.message
    assert "302" in result.message


def test_hint_suggests_navigate_to_when_no_navigate_ran() -> None:
    runner = _runner_with_client(status=500, has_login=True)
    result = runner.execute_step(
        {"action": "assert_visible", "target": "task"}, design={}, context={}
    )
    # No _current_ui_url in context → navigate_to hint fires.
    assert result.result is TestResult.FAILED
    assert "navigate_to" in result.message


def test_no_login_hint_when_auth_already_present() -> None:
    """A 302 *with* an auth session is a different bug class —
    don't false-flag login_as in that case."""
    runner = _runner_with_client(status=302, has_login=True)
    result = runner.execute_step(
        {"action": "assert_visible", "target": "task"},
        design={},
        context={"_current_ui_url": "http://stg.example/app/x"},  # avoid navigate hint too
    )
    assert "login_as" not in result.message


def test_both_hints_fire_when_both_missing() -> None:
    runner = _runner_with_client(status=302, has_login=False)
    result = runner.execute_step(
        {"action": "assert_visible", "target": "task"}, design={}, context={}
    )
    assert "login_as" in result.message
    assert "navigate_to" in result.message


def test_no_hint_when_check_passes() -> None:
    runner = TestRunner(project_path=Path("/tmp/_test_1149"))
    client = MagicMock()
    client.check_ui_loads = MagicMock(
        return_value=UICheckResult(
            ok=True,
            status=200,
            url="http://stg.example/app/x",
            excerpt="<title>X</title>",
        )
    )
    runner.client = client
    result = runner.execute_step(
        {"action": "assert_visible", "target": "task"}, design={}, context={}
    )
    assert result.result is TestResult.PASSED
    assert result.message == ""
