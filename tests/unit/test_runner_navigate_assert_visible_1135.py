"""#1135: ``WS_*_NAV`` failure diagnostics + ``navigate_to`` actually
navigates.

Two fixes pinned here:

1. ``DazzleClient.check_ui_loads`` returns a ``UICheckResult``
   (status / url / excerpt) instead of a bare ``bool``, and the
   ``assert_visible`` step surfaces the diagnostic shape in
   ``StepResult.message`` on failure. Pre-fix message was the
   single string ``"UI check failed"`` — operators couldn't tell
   30x from 404 from JSON-instead-of-HTML.

2. ``_execute_navigate_to_step`` stashes the resolved route into
   ``context["_current_ui_url"]`` so the subsequent
   ``assert_visible`` actually checks the navigated workspace, not
   ``self.ui_url``. Pre-fix every ``WS_*_NAV`` test smoke-tested the
   same base URL with different persona cookies, which is not what
   the test ID promised.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from dazzle.testing.test_runner import (
    DazzleClient,
    TestResult,
    TestRunner,
    UICheckResult,
)

# ---------------------------------------------------------------------------
# check_ui_loads — structured result
# ---------------------------------------------------------------------------


def _client_with_response(status_code: int, body: str) -> DazzleClient:
    """DazzleClient with its low-level _request stubbed."""
    c = DazzleClient(api_url="http://api", ui_url="http://ui")
    resp = MagicMock(status_code=status_code, text=body)
    c._request = MagicMock(return_value=resp)
    return c


def test_check_ui_loads_returns_ok_on_200_with_title() -> None:
    c = _client_with_response(200, "<html><head><title>X</title></head>")
    result = c.check_ui_loads()
    assert result.ok is True
    assert result.status == 200
    assert result.url == "http://ui"


def test_check_ui_loads_returns_not_ok_on_404() -> None:
    c = _client_with_response(404, "<html>not found</html>")
    result = c.check_ui_loads()
    assert result.ok is False
    assert result.status == 404
    assert "not found" in result.excerpt


def test_check_ui_loads_returns_not_ok_on_200_without_title() -> None:
    """A 200 that doesn't carry ``<title>`` (e.g. raw JSON) isn't a
    page render — the body excerpt should let the operator see what
    was returned instead."""
    c = _client_with_response(200, '{"ok": true}')
    result = c.check_ui_loads()
    assert result.ok is False
    assert result.status == 200
    assert '"ok": true' in result.excerpt


def test_check_ui_loads_accepts_per_call_url() -> None:
    """The workspace-aware caller passes a per-step URL — the helper
    fetches that, not the base ``ui_url``."""
    c = _client_with_response(200, "<title>ws</title>")
    c.check_ui_loads(url="http://ui/app/workspaces/team")
    c._request.assert_called_once_with("GET", "http://ui/app/workspaces/team")


def test_check_ui_loads_returns_exception_repr_on_request_failure() -> None:
    c = DazzleClient(api_url="http://api", ui_url="http://ui")
    c._request = MagicMock(side_effect=ConnectionError("ECONNREFUSED"))
    result = c.check_ui_loads()
    assert result.ok is False
    assert result.status is None
    assert "ECONNREFUSED" in result.excerpt


def test_excerpt_truncated_to_200_chars() -> None:
    c = _client_with_response(500, "x" * 500)
    result = c.check_ui_loads()
    assert len(result.excerpt) == 200


# ---------------------------------------------------------------------------
# _execute_navigate_to_step — stashes route into context
# ---------------------------------------------------------------------------


def _runner() -> TestRunner:
    return TestRunner(project_path=Path("/tmp/_test_1135"))


def test_navigate_to_stashes_resolved_url_in_context() -> None:
    """A ``navigate_to`` step with ``data.route`` must put the
    absolute URL into ``context["_current_ui_url"]`` so the next
    ``assert_visible`` checks the navigated workspace."""
    runner = _runner()
    runner.client = MagicMock(ui_url="http://ui")
    ctx: dict = {}
    runner.execute_step(
        {
            "action": "navigate_to",
            "target": "/app/workspaces/team",
            "data": {"route": "/app/workspaces/team"},
        },
        design={},
        context=ctx,
    )
    assert ctx["_current_ui_url"] == "http://ui/app/workspaces/team"


def test_navigate_to_handles_absolute_url() -> None:
    """An absolute route (already includes scheme + host) replaces
    the base URL rather than appending."""
    runner = _runner()
    runner.client = MagicMock(ui_url="http://ui")
    ctx: dict = {}
    runner.execute_step(
        {
            "action": "navigate_to",
            "target": "external",
            "data": {"route": "http://other-host/x"},
        },
        design={},
        context=ctx,
    )
    assert ctx["_current_ui_url"] == "http://other-host/x"


def test_navigate_to_without_route_leaves_context_alone() -> None:
    """Pre-#1135 behaviour: a ``navigate_to`` step with no route data
    is a no-op (legacy designs that pass the target only). The next
    ``assert_visible`` falls back to the base ``ui_url``."""
    runner = _runner()
    runner.client = MagicMock(ui_url="http://ui")
    ctx: dict = {}
    runner.execute_step(
        {"action": "navigate_to", "target": "/somewhere"},
        design={},
        context=ctx,
    )
    assert "_current_ui_url" not in ctx


# ---------------------------------------------------------------------------
# _execute_assert_visible_step — uses navigated URL, surfaces diagnostics
# ---------------------------------------------------------------------------


def test_assert_visible_uses_navigated_url_from_context() -> None:
    """The asserted GET must hit the URL stashed by ``navigate_to``,
    not the bare ``ui_url``. Pre-#1135 every ``WS_*_NAV`` test fetched
    the same base URL with only the cookie varying — fixing that is
    the second half of this issue."""
    runner = _runner()
    runner.client = MagicMock()
    runner.client.check_ui_loads = MagicMock(
        return_value=UICheckResult(
            ok=True, status=200, url="http://ui/app/workspaces/team", excerpt="<title>x</title>"
        )
    )
    runner.execute_step(
        {"action": "assert_visible", "target": "workspace"},
        design={},
        context={"_current_ui_url": "http://ui/app/workspaces/team"},
    )
    runner.client.check_ui_loads.assert_called_once_with(url="http://ui/app/workspaces/team")


def test_assert_visible_falls_back_to_base_ui_url_when_no_navigate() -> None:
    runner = _runner()
    runner.client = MagicMock()
    runner.client.check_ui_loads = MagicMock(
        return_value=UICheckResult(ok=True, status=200, url="http://ui", excerpt="<title>")
    )
    runner.execute_step(
        {"action": "assert_visible", "target": "anywhere"},
        design={},
        context={},
    )
    runner.client.check_ui_loads.assert_called_once_with(url=None)


def test_assert_visible_failure_message_carries_status_url_excerpt() -> None:
    """The whole point of #1135 — failure messages must include the
    URL, status, and body excerpt so triage doesn't require source
    reading."""
    runner = _runner()
    runner.client = MagicMock()
    runner.client.check_ui_loads = MagicMock(
        return_value=UICheckResult(
            ok=False,
            status=404,
            url="http://ui/app/workspaces/team",
            excerpt="<html>not found</html>",
        )
    )
    result = runner.execute_step(
        {"action": "assert_visible", "target": "ws"},
        design={},
        context={"_current_ui_url": "http://ui/app/workspaces/team"},
    )
    assert result.result is TestResult.FAILED
    # All three diagnostic pieces present:
    assert "http://ui/app/workspaces/team" in result.message
    assert "404" in result.message
    assert "not found" in result.message


def test_assert_visible_passes_with_empty_message_on_ok() -> None:
    """No noise on the happy path — message stays empty so passing
    test logs don't accrete kilobytes of redundant URLs."""
    runner = _runner()
    runner.client = MagicMock()
    runner.client.check_ui_loads = MagicMock(
        return_value=UICheckResult(ok=True, status=200, url="http://ui", excerpt="<title>")
    )
    result = runner.execute_step(
        {"action": "assert_visible", "target": "x"},
        design={},
        context={},
    )
    assert result.result is TestResult.PASSED
    assert result.message == ""
