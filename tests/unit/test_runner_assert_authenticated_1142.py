"""#1142: assert_authenticated must self-bootstrap via /auth/me.

The canonical ACL pattern emitted by dsl_test_generator is:

    {"action": "login_as", "target": "<persona>"},
    {"action": "assert_authenticated", "target": "<persona>"}

login_as doesn't populate context['last_response'], so the v0.71.39
handler's "inspect last_response" fallback failed every ACL_*_ACCESS
test. v0.71.42 issues GET /auth/me directly when no last_response is
available.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from dazzle.testing.test_runner import TestResult, TestRunner


def _runner() -> TestRunner:
    return TestRunner(project_path=Path("/tmp/_test_1142"))


def _mock_client_with_probe(status: int) -> MagicMock:
    client = MagicMock()
    client.api_url = "http://x"
    client._auth_headers = MagicMock(return_value={"Authorization": "Bearer t"})
    probe = MagicMock(status_code=status, json=lambda: {"id": "u1"}, text="")
    client._request = MagicMock(return_value=probe)
    return client


def test_self_bootstrap_passes_on_2xx_from_auth_me() -> None:
    runner = _runner()
    runner.client = _mock_client_with_probe(200)
    result = runner.execute_step(
        {"action": "assert_authenticated", "target": "customer"},
        design={},
        context={},
    )
    assert result.result is TestResult.PASSED


def test_self_bootstrap_fails_on_401_from_auth_me() -> None:
    runner = _runner()
    runner.client = _mock_client_with_probe(401)
    result = runner.execute_step(
        {"action": "assert_authenticated", "target": "customer"},
        design={},
        context={},
    )
    assert result.result is TestResult.FAILED
    assert "401" in result.message


def test_self_bootstrap_calls_auth_me_with_auth_headers() -> None:
    runner = _runner()
    runner.client = _mock_client_with_probe(200)
    runner.execute_step(
        {"action": "assert_authenticated", "target": "customer"},
        design={},
        context={},
    )
    call = runner.client._request.call_args
    assert call.args == ("GET", "http://x/auth/me")
    assert call.kwargs["headers"] == {"Authorization": "Bearer t"}


def test_self_bootstrap_stashes_probe_response_in_context() -> None:
    """The probe response becomes last_response so a follow-up
    assert_error / assert_visible can introspect it."""
    runner = _runner()
    runner.client = _mock_client_with_probe(200)
    ctx: dict = {}
    runner.execute_step(
        {"action": "assert_authenticated", "target": "customer"},
        design={},
        context=ctx,
    )
    assert ctx["last_response"] is runner.client._request.return_value


def test_existing_last_response_still_inspected() -> None:
    """The "login_as → probe → assert" pattern (where assert_authenticated
    follows an explicit HTTP call) keeps working: a pre-populated
    last_response is checked instead of issuing the probe."""
    runner = _runner()
    runner.client = MagicMock()
    runner.client.api_url = "http://x"
    runner.client._auth_headers = MagicMock(return_value={})
    runner.client._request = MagicMock()  # would fail if called
    existing = MagicMock(status_code=204, json=lambda: {}, text="")

    result = runner.execute_step(
        {"action": "assert_authenticated", "target": ""},
        design={},
        context={"last_response": existing},
    )
    assert result.result is TestResult.PASSED
    # /auth/me was NOT called — the existing response was used.
    runner.client._request.assert_not_called()


def test_self_bootstrap_handles_request_exception_gracefully() -> None:
    """A network error during the /auth/me probe surfaces as a FAIL
    with a useful message, not an unhandled exception that crashes
    the test run."""
    runner = _runner()
    runner.client = MagicMock()
    runner.client.api_url = "http://x"
    runner.client._auth_headers = MagicMock(return_value={})
    runner.client._request = MagicMock(side_effect=RuntimeError("connection refused"))

    result = runner.execute_step(
        {"action": "assert_authenticated", "target": "customer"},
        design={},
        context={},
    )
    assert result.result is TestResult.FAILED
    assert "/auth/me probe failed" in result.message
    assert "connection refused" in result.message
