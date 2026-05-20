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


class _FakeClient:
    """Records the last request and returns a queued response."""

    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.calls: list[tuple[str, str]] = []

    async def request(self, method: str, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append((method, url))
        return self._response


@pytest.mark.asyncio
async def test_list_probe_issues_get_and_counts_items() -> None:
    client = _FakeClient(_FakeResponse(200, {"items": [{"id": "1"}, {"id": "2"}]}))
    result = await _probe_cell(client, entity="Task", operation="list", baseline_id="x")
    assert client.calls == [("GET", "/api/tasks")]
    assert result.status == 200
    assert result.count == 2


@pytest.mark.asyncio
async def test_read_probe_targets_baseline_id() -> None:
    client = _FakeClient(_FakeResponse(200, {"id": "abc"}))
    result = await _probe_cell(client, entity="Task", operation="read", baseline_id="abc")
    assert client.calls == [("GET", "/api/tasks/abc")]
    assert result.status == 200
    assert result.count is None


@pytest.mark.asyncio
async def test_delete_probe_issues_delete() -> None:
    client = _FakeClient(_FakeResponse(403))
    result = await _probe_cell(client, entity="Task", operation="delete", baseline_id="abc")
    assert client.calls == [("DELETE", "/api/tasks/abc")]
    assert result.status == 403


@pytest.mark.asyncio
async def test_create_probe_issues_post() -> None:
    client = _FakeClient(_FakeResponse(201, {"id": "new"}))
    result = await _probe_cell(client, entity="Task", operation="create", baseline_id=None)
    assert client.calls == [("POST", "/api/tasks")]
    assert result.status == 201


@pytest.mark.asyncio
async def test_list_count_none_when_body_not_json() -> None:
    client = _FakeClient(_FakeResponse(200, None))
    result = await _probe_cell(client, entity="Task", operation="list", baseline_id=None)
    assert result.status == 200
    assert result.count is None
