"""
Request recording and assertion helpers for vendor mock testing.

Provides a ``RequestRecorder`` wrapper around a mock app's request log with
convenience methods for asserting request counts, methods, paths, and bodies.
"""

from __future__ import annotations

from typing import Any


class RequestRecorder:
    """Wraps a mock app's request log for test assertions.

    Each recorded request is a dict with keys:
        operation, method, path, query, body, timestamp, status, elapsed_ms

    Args:
        request_log: The ``app.state.request_log`` list from a mock server.
    """

    def __init__(self, request_log: list[dict[str, Any]]) -> None:
        self._log = request_log

    @property
    def requests(self) -> list[dict[str, Any]]:
        """All recorded requests."""
        return list(self._log)

    @property
    def request_count(self) -> int:
        """Total number of recorded requests."""
        return len(self._log)

    @property
    def last_request(self) -> dict[str, Any] | None:
        """The most recently recorded request, or None."""
        return self._log[-1] if self._log else None

    def filter(
        self,
        *,
        method: str | None = None,
        path: str | None = None,
        operation: str | None = None,
        status: int | None = None,
    ) -> list[dict[str, Any]]:
        """Filter recorded requests by criteria.

        Args:
            method: HTTP method (e.g. "POST").
            path: URL path (substring match).
            operation: Operation name from the API pack.
            status: HTTP status code.

        Returns:
            Matching requests.
        """
        results = self._log
        if method is not None:
            results = [r for r in results if r.get("method") == method.upper()]
        if path is not None:
            results = [r for r in results if path in r.get("path", "")]
        if operation is not None:
            results = [r for r in results if r.get("operation") == operation]
        if status is not None:
            results = [r for r in results if r.get("status") == status]
        return results

    def assert_called(self, *, method: str, path: str, times: int | None = None) -> None:
        """Assert that a request matching method and path was recorded.

        Args:
            method: Expected HTTP method.
            path: Expected path (substring match).
            times: If given, assert exactly this many matches.

        Raises:
            AssertionError: If the assertion fails.
        """
        matches = self.filter(method=method, path=path)
        if times is not None:
            assert len(matches) == times, (
                f"Expected {times} {method} {path} request(s), got {len(matches)}. "
                f"Recorded: {[r['method'] + ' ' + r['path'] for r in self._log]}"
            )
        else:
            assert len(matches) > 0, (
                f"Expected at least one {method} {path} request, got none. "
                f"Recorded: {[r['method'] + ' ' + r['path'] for r in self._log]}"
            )

    def assert_not_called(self, *, method: str, path: str) -> None:
        """Assert that no request matching method and path was recorded.

        Raises:
            AssertionError: If a matching request exists.
        """
        matches = self.filter(method=method, path=path)
        assert len(matches) == 0, f"Expected no {method} {path} requests, but found {len(matches)}"

    def assert_body_contains(self, key: str, value: Any | None = None) -> None:
        """Assert the last request body contains a key (and optionally a value).

        Args:
            key: Expected key in the request body.
            value: If given, the expected value for that key.

        Raises:
            AssertionError: If the assertion fails.
        """
        last = self.last_request
        assert last is not None, "No requests recorded"
        body = last.get("body") or {}
        assert key in body, f"Key '{key}' not found in request body: {body}"
        if value is not None:
            assert body[key] == value, f"Expected body['{key}'] == {value!r}, got {body[key]!r}"

    def clear(self) -> None:
        """Clear all recorded requests."""
        self._log.clear()


def get_recorder(app: Any) -> RequestRecorder:
    """Create a RequestRecorder from a mock FastAPI app.

    Args:
        app: A FastAPI app created by ``create_mock_server()``.

    Returns:
        RequestRecorder wrapping the app's request log.
    """
    return RequestRecorder(app.state.request_log)
