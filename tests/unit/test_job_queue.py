"""Tests for #953 cycle 3 — generic job queue + handler resolution.

Cycle 2 added the JobRun destination table; cycle 3 builds the
queue / handler primitives the cycle-4 worker loop will pull from.

These tests cover both new modules:

  * `JobMessage`, `InMemoryJobQueue` — submit + dequeue + size +
    timeout behaviour
  * `resolve_handler` — module:attr / module.attr forms, file-path
    rejection, allow-list validation, callable check
"""

from __future__ import annotations

import asyncio

import pytest

from dazzle_back.runtime.job_handler import JobHandlerNotFound, resolve_handler
from dazzle_back.runtime.job_queue import InMemoryJobQueue, JobMessage

# ---------------------------------------------------------------------------
# JobMessage
# ---------------------------------------------------------------------------


class TestJobMessage:
    def test_defaults(self):
        m = JobMessage(job_name="x")
        assert m.payload == {}
        assert m.attempt == 1
        assert m.job_run_id == ""

    def test_frozen(self):
        m = JobMessage(job_name="x")
        with pytest.raises((AttributeError, Exception)):
            m.attempt = 2  # type: ignore[misc]


# ---------------------------------------------------------------------------
# InMemoryJobQueue
# ---------------------------------------------------------------------------


def _run(coro):
    return asyncio.run(coro)


class TestInMemoryJobQueue:
    def test_submit_returns_job_run_id(self):
        q = InMemoryJobQueue()
        job_run_id = _run(q.submit("daily_summary"))
        assert isinstance(job_run_id, str)
        assert len(job_run_id) > 0

    def test_submit_then_dequeue_roundtrip(self):
        async def go():
            q = InMemoryJobQueue()
            await q.submit("daily_summary", payload={"date": "2026-05-03"})
            return await q.dequeue(timeout=0.1)

        msg = _run(go())
        assert msg is not None
        assert msg.job_name == "daily_summary"
        assert msg.payload == {"date": "2026-05-03"}
        assert msg.attempt == 1

    def test_dequeue_timeout_returns_none(self):
        async def go():
            q = InMemoryJobQueue()
            return await q.dequeue(timeout=0.01)

        assert _run(go()) is None

    def test_size_tracks_pending(self):
        async def go():
            q = InMemoryJobQueue()
            await q.submit("a")
            await q.submit("b")
            return await q.size()

        assert _run(go()) == 2

    def test_payload_defaulted_to_empty_dict(self):
        async def go():
            q = InMemoryJobQueue()
            await q.submit("x")
            return await q.dequeue(timeout=0.1)

        msg = _run(go())
        assert msg is not None
        assert msg.payload == {}

    def test_payload_copied_not_aliased(self):
        # Mutating the caller's payload after submit must not
        # change the enqueued message.
        async def go():
            q = InMemoryJobQueue()
            src = {"k": "v"}
            await q.submit("x", payload=src)
            src["k"] = "MUTATED"
            return await q.dequeue(timeout=0.1)

        msg = _run(go())
        assert msg is not None
        assert msg.payload == {"k": "v"}

    def test_attempt_passes_through(self):
        async def go():
            q = InMemoryJobQueue()
            await q.submit("x", attempt=3)
            return await q.dequeue(timeout=0.1)

        msg = _run(go())
        assert msg is not None
        assert msg.attempt == 3

    def test_each_submit_gets_unique_id(self):
        async def go():
            q = InMemoryJobQueue()
            id1 = await q.submit("x")
            id2 = await q.submit("x")
            return id1, id2

        id1, id2 = _run(go())
        assert id1 != id2


# ---------------------------------------------------------------------------
# resolve_handler
# ---------------------------------------------------------------------------


class TestResolveHandlerSuccess:
    def test_resolves_via_colon_separator(self):
        # `os:getcwd` resolves to os.getcwd
        handler = resolve_handler("os:getcwd")
        assert callable(handler)

    def test_resolves_via_dot_separator(self):
        handler = resolve_handler("os.getcwd")
        assert callable(handler)

    def test_returned_callable_is_invocable(self):
        handler = resolve_handler("os.getcwd")
        # Sanity check — actually call it.
        assert isinstance(handler(), str)


class TestResolveHandlerErrors:
    def test_empty_path_raises(self):
        with pytest.raises(JobHandlerNotFound, match="empty"):
            resolve_handler("")

    def test_file_path_with_slash_rejected(self):
        with pytest.raises(JobHandlerNotFound, match="file path"):
            resolve_handler("scripts/render.py")

    def test_file_path_with_py_extension_rejected(self):
        with pytest.raises(JobHandlerNotFound, match="file path"):
            resolve_handler("render.py")

    def test_file_path_with_backslash_rejected(self):
        with pytest.raises(JobHandlerNotFound, match="file path"):
            resolve_handler("scripts\\render.py")

    def test_no_dot_or_colon_rejected(self):
        # Cannot tell module from attr — must use a separator.
        with pytest.raises(JobHandlerNotFound, match="dotted path"):
            resolve_handler("just_a_name")

    def test_empty_around_colon(self):
        with pytest.raises(JobHandlerNotFound, match="empty module or attr"):
            resolve_handler("os:")
        with pytest.raises(JobHandlerNotFound, match="empty module or attr"):
            resolve_handler(":getcwd")

    def test_invalid_chars_rejected(self):
        # Only lowercase identifier chars + dots reach importlib —
        # uppercase, hyphens, special characters, etc. all rejected.
        with pytest.raises(JobHandlerNotFound, match="invalid characters"):
            resolve_handler("OS:getcwd")
        with pytest.raises(JobHandlerNotFound, match="invalid characters"):
            resolve_handler("my-module:func")

    def test_unknown_module_raises(self):
        with pytest.raises(JobHandlerNotFound, match="Cannot import"):
            resolve_handler("definitely_not_a_real_module:func")

    def test_unknown_attr_raises(self):
        with pytest.raises(JobHandlerNotFound, match="no attribute"):
            resolve_handler("os:nope_not_real")

    def test_non_callable_attr_rejected(self):
        # `os.name` is a string — resolver must reject.
        with pytest.raises(JobHandlerNotFound, match="non-callable"):
            resolve_handler("os:name")
