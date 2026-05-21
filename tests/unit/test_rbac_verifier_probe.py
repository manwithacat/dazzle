"""Unit tests for _probe_cell — RBAC verifier per-cell HTTP probing (#1171)."""

from __future__ import annotations

from typing import Any

import pytest

from dazzle.rbac.verifier import _probe_cell


class _FakeResponse:
    def __init__(self, status_code: int, json_body: Any = None) -> None:
        self.status_code = status_code
        self._json = json_body

    def json(self) -> Any:
        if self._json is None:
            raise ValueError("no json body")
        return self._json


class _FakeCookies:
    """Minimal cookie jar exposing `.get` like httpx.Cookies."""

    def __init__(self, jar: dict[str, str] | None = None) -> None:
        self._jar = jar or {}

    def get(self, name: str, default: Any = None) -> Any:
        return self._jar.get(name, default)


class _FakeClient:
    """Records all requests issued and returns a queued response."""

    def __init__(self, response: _FakeResponse, cookies: dict[str, str] | None = None) -> None:
        self._response = response
        self.calls: list[tuple[str, str]] = []
        self.headers_seen: list[dict[str, str]] = []
        self.cookies = _FakeCookies(cookies)

    async def request(self, method: str, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append((method, url))
        self.headers_seen.append(kwargs.get("headers", {}))
        return self._response


@pytest.mark.asyncio
async def test_list_probe_issues_get_and_counts_items() -> None:
    client = _FakeClient(_FakeResponse(200, {"items": [{"id": "1"}, {"id": "2"}]}))
    result = await _probe_cell(client, entity="Task", operation="list", baseline_id="x")
    assert client.calls == [("GET", "/tasks")]
    assert result.status == 200
    assert result.count == 2


@pytest.mark.asyncio
async def test_read_probe_targets_baseline_id() -> None:
    client = _FakeClient(_FakeResponse(200, {"id": "abc"}))
    result = await _probe_cell(client, entity="Task", operation="read", baseline_id="abc")
    assert client.calls == [("GET", "/tasks/abc")]
    assert result.status == 200
    assert result.count is None


@pytest.mark.asyncio
async def test_delete_probe_issues_delete() -> None:
    client = _FakeClient(_FakeResponse(403))
    result = await _probe_cell(client, entity="Task", operation="delete", baseline_id="abc")
    assert client.calls == [("DELETE", "/tasks/abc")]
    assert result.status == 403


@pytest.mark.asyncio
async def test_create_probe_issues_post() -> None:
    client = _FakeClient(_FakeResponse(201, {"id": "new"}))
    result = await _probe_cell(client, entity="Task", operation="create", baseline_id=None)
    assert client.calls == [("POST", "/tasks")]
    assert result.status == 201


@pytest.mark.asyncio
async def test_list_count_none_when_body_not_json() -> None:
    client = _FakeClient(_FakeResponse(200, None))
    result = await _probe_cell(client, entity="Task", operation="list", baseline_id=None)
    assert result.status == 200
    assert result.count is None


@pytest.mark.asyncio
async def test_update_probe_issues_patch_with_body() -> None:
    client = _FakeClient(_FakeResponse(200, {"id": "abc"}))
    result = await _probe_cell(
        client, entity="Task", operation="update", baseline_id="abc", body={"title": "x"}
    )
    assert client.calls == [("PATCH", "/tasks/abc")]
    assert result.status == 200


@pytest.mark.asyncio
async def test_list_count_handles_root_array_payload() -> None:
    client = _FakeClient(_FakeResponse(200, [{"id": "1"}]))
    result = await _probe_cell(client, entity="Task", operation="list", baseline_id=None)
    assert result.status == 200
    assert result.count == 1


@pytest.mark.asyncio
async def test_create_probe_attaches_csrf_header() -> None:
    """POST probes echo the client's dazzle_csrf cookie as X-CSRF-Token."""
    client = _FakeClient(_FakeResponse(201, {"id": "new"}), cookies={"dazzle_csrf": "tok-1"})
    await _probe_cell(client, entity="Task", operation="create", baseline_id=None)
    assert client.headers_seen == [{"X-CSRF-Token": "tok-1"}]


@pytest.mark.asyncio
async def test_delete_probe_attaches_csrf_header() -> None:
    client = _FakeClient(_FakeResponse(403), cookies={"dazzle_csrf": "tok-2"})
    await _probe_cell(client, entity="Task", operation="delete", baseline_id="abc")
    assert client.headers_seen == [{"X-CSRF-Token": "tok-2"}]


@pytest.mark.asyncio
async def test_list_probe_sends_no_csrf_header() -> None:
    """GET probes (list/read) are not CSRF-protected — no header attached."""
    client = _FakeClient(_FakeResponse(200, {"items": []}), cookies={"dazzle_csrf": "tok-3"})
    await _probe_cell(client, entity="Task", operation="list", baseline_id=None)
    assert client.headers_seen == [{}]
