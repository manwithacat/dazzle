"""#1210: ``post`` / ``post_json`` cleanup-tracking + uuid4 fixture_id.

Pre-#1210, `dazzle test dsl-run --cleanup` leaked rows created via
``post`` / ``post_json`` test steps because the runner never appended
them to ``DazzleClient._created_entities``. Steps that actually create
entities now opt in via ``cleanup_entity: <EntityName>``; the runner
parses the 2xx response body, extracts ``id``, and registers
``(EntityName, id)`` so the end-of-run cleanup phase deletes it.

Independently, ``create_entity`` previously built ``fixture_id`` from
``int(time.time())`` — two entities created in the same second collided
on key, so only one was tracked. ``fixture_id`` is now ``uuid4().hex``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from dazzle.testing.cleanup_manager import CleanupManager
from dazzle.testing.test_runner import DazzleClient, TestResult, TestRunner


def _make_runner_with_stub_client() -> tuple[TestRunner, MagicMock]:
    runner = TestRunner(project_path=Path("/tmp/_test_1210"))
    client = MagicMock(spec=DazzleClient)
    client.api_url = "http://api.example"
    client.ui_url = "http://ui.example"
    # Real CleanupManager so `track()` actually appends to `.created` (#1446) —
    # a bare mock attr wouldn't record, and `spec=DazzleClient` rejects the
    # instance-only `cleanup` attribute.
    client.cleanup = CleanupManager(client)
    runner.client = client
    return runner, client


def _resp(status_code: int, body: Any) -> MagicMock:
    r = MagicMock()
    r.status_code = status_code
    r.cookies = {}
    r.headers = {}
    r.json = MagicMock(return_value=body)
    return r


# ---- post / post_json cleanup_entity hint -----------------------------------


def test_post_without_cleanup_entity_does_not_track() -> None:
    runner, client = _make_runner_with_stub_client()
    client._request = MagicMock(return_value=_resp(200, {"id": "abc-123"}))

    result = runner.execute_step(
        step={"action": "post", "target": "/svc/packages", "data": {"name": "Gold"}},
        design={},
        context={},
    )

    assert result.result is TestResult.PASSED
    assert client.cleanup.created == []


def test_post_with_cleanup_entity_tracks_returned_id() -> None:
    runner, client = _make_runner_with_stub_client()
    client._request = MagicMock(return_value=_resp(200, {"id": "abc-123"}))

    runner.execute_step(
        step={
            "action": "post",
            "target": "/svc/packages",
            "data": {"name": "Gold"},
            "cleanup_entity": "ServicePackage",
        },
        design={},
        context={},
    )

    assert client.cleanup.created == [("ServicePackage", "abc-123")]


def test_post_json_with_cleanup_entity_tracks_returned_id() -> None:
    runner, client = _make_runner_with_stub_client()
    client._request = MagicMock(return_value=_resp(201, {"id": 42, "name": "x"}))

    runner.execute_step(
        step={
            "action": "post_json",
            "target": "/api/widgets",
            "data": {"name": "x"},
            "cleanup_entity": "Widget",
        },
        design={},
        context={},
    )

    assert client.cleanup.created == [("Widget", "42")]


def test_post_non_2xx_does_not_track_even_with_cleanup_entity() -> None:
    runner, client = _make_runner_with_stub_client()
    client._request = MagicMock(return_value=_resp(400, {"error": "bad payload"}))

    runner.execute_step(
        step={
            "action": "post_json",
            "target": "/api/foos",
            "data": {},
            "cleanup_entity": "Foo",
        },
        design={},
        context={},
    )

    assert client.cleanup.created == []


def test_post_2xx_without_id_in_body_does_not_track() -> None:
    """Defensive: 2xx + cleanup_entity but no ``id`` in body → no track,
    no crash. Some endpoints return ``{"ok": true}`` or similar."""
    runner, client = _make_runner_with_stub_client()
    client._request = MagicMock(return_value=_resp(200, {"ok": True}))

    runner.execute_step(
        step={
            "action": "post_json",
            "target": "/api/widgets",
            "data": {},
            "cleanup_entity": "Widget",
        },
        design={},
        context={},
    )

    assert client.cleanup.created == []


# ---- uuid4 fixture_id collision fix -----------------------------------------


def test_uuid4_fixture_id_eliminates_same_second_collision() -> None:
    """Two ``create_entity`` calls in rapid succession both get tracked.

    Pre-#1210 the fixture_id was ``int(time.time())`` — back-to-back
    creates in the same wall-clock second produced the same key, the
    second response's ``created[fixture_id]`` overwrote the first, and
    only one entity ended up in ``_created_entities``. With uuid4 each
    call generates a distinct key.
    """
    client = DazzleClient(api_url="http://api.example", ui_url="http://ui.example")
    # Simulate /__test__/seed echoing back whatever fixture_id we sent.
    captured_keys: list[str] = []

    def fake_request(method: str, url: str, **kwargs: Any) -> MagicMock:
        fixtures = kwargs["json"]["fixtures"]
        fixture_id = fixtures[0]["id"]
        captured_keys.append(fixture_id)
        return _resp(
            200,
            {"created": {fixture_id: {"id": f"row-{len(captured_keys)}"}}},
        )

    client._request = fake_request  # type: ignore[assignment]

    a = client.create_entity("ServicePackage", {"name": "Gold"})
    b = client.create_entity("ServicePackage", {"name": "Silver"})

    assert a == {"id": "row-1"}
    assert b == {"id": "row-2"}
    # Two distinct fixture_ids generated despite being back-to-back.
    assert len(set(captured_keys)) == 2
    # Both entities tracked for cleanup — the pre-fix bug would have
    # tracked only one due to the same-second key collision.
    assert client.cleanup.created == [
        ("ServicePackage", "row-1"),
        ("ServicePackage", "row-2"),
    ]
