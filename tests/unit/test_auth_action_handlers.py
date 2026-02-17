"""
Tests for auth lifecycle action handlers in TestRunner.execute_step().

Covers the 9 actions used by generated auth lifecycle tests:
post, get, get_with_cookie, assert_status, assert_cookie_set,
assert_no_cookie, assert_cookie_cleared, assert_redirect_url,
assert_unauthenticated.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from dazzle.testing.test_runner import TestResult, TestRunner


@pytest.fixture
def runner() -> TestRunner:
    """Create a TestRunner with a mocked DazzleClient."""
    r = TestRunner(project_path=Path("/fake"), api_port=8000, ui_port=3000)
    mock_client = MagicMock()
    mock_client.ui_url = "http://localhost:3000"
    mock_client.api_url = "http://localhost:8000"
    # Create a real-ish httpx-like client mock
    mock_http = MagicMock()
    mock_http.cookies = MagicMock()
    mock_http.cookies.get = MagicMock(return_value=None)
    mock_client.client = mock_http
    r.client = mock_client
    return r


class _MockCookies:
    """Dict-like cookie jar that supports `in` and `.get()`."""

    def __init__(self, data: dict[str, str]) -> None:
        self._data = data

    def get(self, key: str, default: str | None = None) -> str | None:
        return self._data.get(key, default)

    def __contains__(self, key: object) -> bool:
        return key in self._data


def _make_response(
    status_code: int = 200,
    cookies: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    json_body: dict | None = None,
) -> MagicMock:
    """Create a mock HTTP response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.cookies = _MockCookies(cookies or {})
    if json_body is not None:
        resp.json = MagicMock(return_value=json_body)
    else:
        resp.json = MagicMock(side_effect=Exception("No JSON"))
    return resp


class TestPostAction:
    def test_post_returns_passed_with_status(self, runner: TestRunner) -> None:
        resp = _make_response(status_code=200)
        runner.client.client.post.return_value = resp

        result = runner.execute_step(
            {
                "action": "post",
                "target": "/auth/login",
                "data": {"email": "a@b.com", "password": "x"},
            },
            design={},
        )
        assert result.result == TestResult.PASSED
        assert "200" in result.message
        runner.client.client.post.assert_called_once()

    def test_post_stores_last_response_in_context(self, runner: TestRunner) -> None:
        resp = _make_response(status_code=401)
        runner.client.client.post.return_value = resp
        context: dict = {}

        runner.execute_step(
            {"action": "post", "target": "/auth/login", "data": {}},
            design={},
            context=context,
        )
        assert context["last_response"] is resp


class TestGetAction:
    def test_get_returns_passed(self, runner: TestRunner) -> None:
        resp = _make_response(status_code=200)
        runner.client.client.get.return_value = resp

        result = runner.execute_step(
            {"action": "get", "target": "/app"},
            design={},
        )
        assert result.result == TestResult.PASSED
        assert "200" in result.message

    def test_get_stores_last_response(self, runner: TestRunner) -> None:
        resp = _make_response(status_code=302)
        runner.client.client.get.return_value = resp
        context: dict = {}

        runner.execute_step(
            {"action": "get", "target": "/app"},
            design={},
            context=context,
        )
        assert context["last_response"] is resp


class TestGetWithCookieAction:
    def test_sends_custom_cookie(self, runner: TestRunner) -> None:
        resp = _make_response(status_code=401)
        runner.client.client.get.return_value = resp

        result = runner.execute_step(
            {
                "action": "get_with_cookie",
                "target": "/app",
                "data": {"cookie": "dazzle_session", "value": "invalid-token"},
            },
            design={},
        )
        assert result.result == TestResult.PASSED
        # Verify cookie was passed
        runner.client.client.get.assert_called_once()
        call_kwargs = runner.client.client.get.call_args
        assert call_kwargs.kwargs["cookies"] == {"dazzle_session": "invalid-token"}


class TestAssertStatusAction:
    def test_status_matches(self, runner: TestRunner) -> None:
        resp = _make_response(status_code=200)
        context = {"last_response": resp}

        result = runner.execute_step(
            {"action": "assert_status", "target": "last_response", "data": {"status": 200}},
            design={},
            context=context,
        )
        assert result.result == TestResult.PASSED

    def test_status_mismatch(self, runner: TestRunner) -> None:
        resp = _make_response(status_code=401)
        context = {"last_response": resp}

        result = runner.execute_step(
            {"action": "assert_status", "target": "last_response", "data": {"status": 200}},
            design={},
            context=context,
        )
        assert result.result == TestResult.FAILED
        assert "401" in result.message

    def test_no_previous_response(self, runner: TestRunner) -> None:
        result = runner.execute_step(
            {"action": "assert_status", "target": "last_response", "data": {"status": 200}},
            design={},
            context={},
        )
        assert result.result == TestResult.FAILED
        assert "No previous response" in result.message


class TestAssertCookieSetAction:
    def test_cookie_present_in_response(self, runner: TestRunner) -> None:
        resp = _make_response(cookies={"dazzle_session": "abc123"})
        context = {"last_response": resp}

        result = runner.execute_step(
            {
                "action": "assert_cookie_set",
                "target": "last_response",
                "data": {"cookie": "dazzle_session"},
            },
            design={},
            context=context,
        )
        assert result.result == TestResult.PASSED

    def test_cookie_missing(self, runner: TestRunner) -> None:
        resp = _make_response(cookies={})
        context = {"last_response": resp}

        result = runner.execute_step(
            {
                "action": "assert_cookie_set",
                "target": "last_response",
                "data": {"cookie": "dazzle_session"},
            },
            design={},
            context=context,
        )
        assert result.result == TestResult.FAILED

    def test_cookie_in_client_jar(self, runner: TestRunner) -> None:
        resp = _make_response(cookies={})
        runner.client.client.cookies.get.return_value = "session-val"
        context = {"last_response": resp}

        result = runner.execute_step(
            {
                "action": "assert_cookie_set",
                "target": "last_response",
                "data": {"cookie": "dazzle_session"},
            },
            design={},
            context=context,
        )
        assert result.result == TestResult.PASSED


class TestAssertNoCookieAction:
    def test_cookie_absent(self, runner: TestRunner) -> None:
        resp = _make_response(cookies={})
        context = {"last_response": resp}

        result = runner.execute_step(
            {
                "action": "assert_no_cookie",
                "target": "last_response",
                "data": {"cookie": "dazzle_session"},
            },
            design={},
            context=context,
        )
        assert result.result == TestResult.PASSED

    def test_cookie_present_fails(self, runner: TestRunner) -> None:
        resp = _make_response(cookies={"dazzle_session": "abc"})
        context = {"last_response": resp}

        result = runner.execute_step(
            {
                "action": "assert_no_cookie",
                "target": "last_response",
                "data": {"cookie": "dazzle_session"},
            },
            design={},
            context=context,
        )
        assert result.result == TestResult.FAILED


class TestAssertCookieClearedAction:
    def test_cookie_cleared(self, runner: TestRunner) -> None:
        resp = _make_response(cookies={})
        context = {"last_response": resp}

        result = runner.execute_step(
            {
                "action": "assert_cookie_cleared",
                "target": "last_response",
                "data": {"cookie": "dazzle_session"},
            },
            design={},
            context=context,
        )
        assert result.result == TestResult.PASSED

    def test_cookie_still_set_fails(self, runner: TestRunner) -> None:
        resp = _make_response(cookies={"dazzle_session": "still-valid"})
        runner.client.client.cookies.get.return_value = "still-valid"
        context = {"last_response": resp}

        result = runner.execute_step(
            {
                "action": "assert_cookie_cleared",
                "target": "last_response",
                "data": {"cookie": "dazzle_session"},
            },
            design={},
            context=context,
        )
        assert result.result == TestResult.FAILED


class TestAssertRedirectUrlAction:
    def test_location_header_match(self, runner: TestRunner) -> None:
        resp = _make_response(status_code=302, headers={"location": "/app"})
        context = {"last_response": resp}

        result = runner.execute_step(
            {
                "action": "assert_redirect_url",
                "target": "last_response",
                "data": {"redirect_url": "/app"},
            },
            design={},
            context=context,
        )
        assert result.result == TestResult.PASSED

    def test_location_header_mismatch(self, runner: TestRunner) -> None:
        resp = _make_response(status_code=302, headers={"location": "/login"})
        context = {"last_response": resp}

        result = runner.execute_step(
            {
                "action": "assert_redirect_url",
                "target": "last_response",
                "data": {"redirect_url": "/app"},
            },
            design={},
            context=context,
        )
        assert result.result == TestResult.FAILED

    def test_json_redirect_url(self, runner: TestRunner) -> None:
        resp = _make_response(status_code=200, json_body={"redirect_url": "/app"})
        context = {"last_response": resp}

        result = runner.execute_step(
            {
                "action": "assert_redirect_url",
                "target": "last_response",
                "data": {"redirect_url": "/app"},
            },
            design={},
            context=context,
        )
        assert result.result == TestResult.PASSED

    def test_hx_redirect_header(self, runner: TestRunner) -> None:
        resp = _make_response(status_code=200, headers={"hx-redirect": "/app"})
        context = {"last_response": resp}

        result = runner.execute_step(
            {
                "action": "assert_redirect_url",
                "target": "last_response",
                "data": {"redirect_url": "/app"},
            },
            design={},
            context=context,
        )
        assert result.result == TestResult.PASSED

    def test_trailing_slash_tolerance(self, runner: TestRunner) -> None:
        resp = _make_response(status_code=302, headers={"location": "/app/"})
        context = {"last_response": resp}

        result = runner.execute_step(
            {
                "action": "assert_redirect_url",
                "target": "last_response",
                "data": {"redirect_url": "/app"},
            },
            design={},
            context=context,
        )
        assert result.result == TestResult.PASSED


class TestAssertUnauthenticatedAction:
    def test_401_matches(self, runner: TestRunner) -> None:
        resp = _make_response(status_code=401)
        context = {"last_response": resp}

        result = runner.execute_step(
            {
                "action": "assert_unauthenticated",
                "target": "last_response",
                "data": {"expect": [401, 302]},
            },
            design={},
            context=context,
        )
        assert result.result == TestResult.PASSED

    def test_302_matches(self, runner: TestRunner) -> None:
        resp = _make_response(status_code=302)
        context = {"last_response": resp}

        result = runner.execute_step(
            {
                "action": "assert_unauthenticated",
                "target": "last_response",
                "data": {"expect": [401, 302]},
            },
            design={},
            context=context,
        )
        assert result.result == TestResult.PASSED

    def test_200_fails(self, runner: TestRunner) -> None:
        resp = _make_response(status_code=200)
        context = {"last_response": resp}

        result = runner.execute_step(
            {
                "action": "assert_unauthenticated",
                "target": "last_response",
                "data": {"expect": [401, 302]},
            },
            design={},
            context=context,
        )
        assert result.result == TestResult.FAILED

    def test_no_previous_response(self, runner: TestRunner) -> None:
        result = runner.execute_step(
            {
                "action": "assert_unauthenticated",
                "target": "last_response",
                "data": {"expect": [401, 302]},
            },
            design={},
            context={},
        )
        assert result.result == TestResult.FAILED


class TestUnknownActionWarning:
    def test_unknown_action_returns_skipped(self, runner: TestRunner) -> None:
        result = runner.execute_step(
            {"action": "totally_unknown", "target": "x"},
            design={},
        )
        assert result.result == TestResult.SKIPPED
        assert "Unknown action" in result.message
