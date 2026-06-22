"""#1139: create_expect_error must reproduce the unique-field values
that the preceding create step actually POSTed.

The DataGenerator regenerates unique fields whose literal values come
from a stored test design, because design-time literals go stale across
runs. Pre-fix, the create step sent the
regenerated value but create_expect_error sent the original literal —
two different values, no duplicate, the unique constraint was never
tripped, and every VAL_*_UNIQUE test failed with "Expected 4xx, got
200".
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from dazzle.testing.test_runner import TestResult, TestRunner


def _runner() -> TestRunner:
    return TestRunner(project_path=Path("/tmp/_test_1139"))


def test_create_stashes_actually_sent_payload_in_context() -> None:
    """After a successful create the runner must record the
    post-generation payload under ``_last_created_data:<Entity>`` so
    a follow-up create_expect_error can reuse it."""
    runner = _runner()
    runner.client = MagicMock()
    runner.client.entities.create_entity = MagicMock(return_value={"id": "1"})
    # DataGenerator regenerates unique fields — design literal "test_a@x"
    # becomes "regen_b@x" on the wire (#1446: data-gen extracted from the client).
    gen = MagicMock()
    gen.generate = MagicMock(return_value={"email": "regen_b@x", "name": "n"})

    ctx: dict = {}
    with patch("dazzle.testing.step_executor.DataGenerator", return_value=gen):
        runner.execute_step(
            {
                "action": "create",
                "target": "entity:Contact",
                "data": {"email": "test_a@x", "name": "n"},
            },
            design={},
            context=ctx,
        )
    assert ctx["_last_created_data:Contact"] == {"email": "regen_b@x", "name": "n"}


def test_create_expect_error_reuses_stashed_payload() -> None:
    """When _last_created_data:<Entity> is set, create_expect_error
    POSTs THAT payload — not the raw resolved_data — so the duplicate
    actually duplicates."""
    runner = _runner()
    runner.client = MagicMock()
    runner.client.api_url = "http://x"
    runner.client.entities._entity_endpoint = MagicMock(return_value="/api/contact")
    runner.client._auth_headers = MagicMock(return_value={})
    resp = MagicMock(status_code=422, json=lambda: {"detail": "dup"}, text="dup")
    runner.client._request = MagicMock(return_value=resp)

    ctx = {"_last_created_data:Contact": {"email": "regen_b@x", "name": "n"}}
    result = runner.execute_step(
        {
            "action": "create_expect_error",
            "target": "entity:Contact",
            "data": {"email": "test_a@x", "name": "n"},  # stale literal
        },
        design={},
        context=ctx,
    )
    assert result.result is TestResult.PASSED
    # Critical assertion: the second POST used the stashed payload,
    # not the design's stale literal.
    sent_json = runner.client._request.call_args.kwargs["json"]
    assert sent_json == {"email": "regen_b@x", "name": "n"}


def test_create_expect_error_falls_back_to_resolved_data_when_no_stash() -> None:
    """Standalone create_expect_error (no preceding create) still works:
    falls back to resolved_data as before."""
    runner = _runner()
    runner.client = MagicMock()
    runner.client.api_url = "http://x"
    runner.client.entities._entity_endpoint = MagicMock(return_value="/api/contact")
    runner.client._auth_headers = MagicMock(return_value={})
    resp = MagicMock(status_code=422, json=lambda: {"detail": "bad"}, text="bad")
    runner.client._request = MagicMock(return_value=resp)

    result = runner.execute_step(
        {
            "action": "create_expect_error",
            "target": "entity:Contact",
            "data": {"email": "raw@x"},
        },
        design={},
        context={},
    )
    assert result.result is TestResult.PASSED
    sent_json = runner.client._request.call_args.kwargs["json"]
    assert sent_json == {"email": "raw@x"}
