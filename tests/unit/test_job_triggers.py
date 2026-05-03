"""Tests for #953 cycle 6 — entity-event → job-enqueue triggers.

Cycle 5 shipped the worker loop. Cycle 6 wires the cycle-1
``JobTrigger`` declarations into the runtime: a project author's

    job thumbnail_render:
      trigger: on_create Manuscript when source_pdf is_set

…now enqueues a `thumbnail_render` job whenever a Manuscript is
created with a non-null ``source_pdf``.

These tests cover all three pieces:

  * ``should_fire`` — pure event-vs-trigger matching, including
    the ``field_changed`` and ``when_condition`` branches.
  * ``build_trigger_callbacks`` — the on_created / on_updated /
    on_deleted shape; verifies enqueue happens (or doesn't).
  * ``register_job_triggers`` — wiring against the services dict;
    skip cleanly on missing services.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

from dazzle_back.runtime.job_queue import InMemoryJobQueue
from dazzle_back.runtime.job_triggers import (
    build_trigger_callbacks,
    register_job_triggers,
    should_fire,
)

# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


@dataclass
class _Trigger:
    entity: str
    event: str = "created"
    field: str | None = None
    when_condition: str | None = None


@dataclass
class _JobSpec:
    name: str
    triggers: list[_Trigger] = field(default_factory=list)


def _make_service() -> MagicMock:
    svc = MagicMock()
    svc.on_created = MagicMock()
    svc.on_updated = MagicMock()
    svc.on_deleted = MagicMock()
    return svc


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# should_fire
# ---------------------------------------------------------------------------


class TestShouldFireEventMatch:
    def test_created_matches_create_event(self):
        t = _Trigger(entity="M", event="created")
        assert should_fire(t, event_kind="created", old_data=None, new_data={}) is True

    def test_event_mismatch_returns_false(self):
        t = _Trigger(entity="M", event="created")
        assert should_fire(t, event_kind="updated", old_data={}, new_data={}) is False

    def test_event_case_insensitive(self):
        # `JobTrigger.event` is stored lowercased on the IR; the
        # comparison is .lower() to defend against any future
        # change.
        t = _Trigger(entity="M", event="Created")
        assert should_fire(t, event_kind="created", old_data=None, new_data={}) is True


class TestShouldFireFieldChanged:
    def test_field_changed_fires_when_value_differs(self):
        t = _Trigger(entity="M", event="field_changed", field="status")
        assert (
            should_fire(
                t,
                event_kind="field_changed",
                old_data={"status": "draft"},
                new_data={"status": "submitted"},
            )
            is True
        )

    def test_field_changed_skipped_when_value_unchanged(self):
        t = _Trigger(entity="M", event="field_changed", field="status")
        assert (
            should_fire(
                t,
                event_kind="field_changed",
                old_data={"status": "draft"},
                new_data={"status": "draft"},
            )
            is False
        )

    def test_field_changed_needs_field_name(self):
        t = _Trigger(entity="M", event="field_changed", field=None)
        assert (
            should_fire(
                t,
                event_kind="field_changed",
                old_data={"x": 1},
                new_data={"x": 2},
            )
            is False
        )

    def test_field_changed_meaningless_on_create(self):
        # Field-changed triggers should be routed via update events,
        # not create — no "old" side to compare.
        t = _Trigger(entity="M", event="field_changed", field="status")
        assert (
            should_fire(
                t,
                event_kind="field_changed",
                old_data=None,
                new_data={"status": "draft"},
            )
            is False
        )


class TestShouldFireWhenCondition:
    def test_is_set_true_when_value_truthy(self):
        t = _Trigger(entity="M", event="created", when_condition="source_pdf is_set")
        assert (
            should_fire(
                t,
                event_kind="created",
                old_data=None,
                new_data={"source_pdf": "abc.pdf"},
            )
            is True
        )

    def test_is_set_false_when_value_none(self):
        t = _Trigger(entity="M", event="created", when_condition="source_pdf is_set")
        assert (
            should_fire(
                t,
                event_kind="created",
                old_data=None,
                new_data={"source_pdf": None},
            )
            is False
        )

    def test_is_set_false_when_value_empty_string(self):
        # Empty string is falsy — same semantics as None for this
        # primitive (callers wanting "non-null but empty allowed"
        # need cycle-7's expression eval).
        t = _Trigger(entity="M", event="created", when_condition="source_pdf is_set")
        assert (
            should_fire(
                t,
                event_kind="created",
                old_data=None,
                new_data={"source_pdf": ""},
            )
            is False
        )

    def test_is_null_true_when_value_none(self):
        t = _Trigger(entity="M", event="updated", when_condition="approved_at is_null")
        assert (
            should_fire(
                t,
                event_kind="updated",
                old_data={"approved_at": "2026-01-01"},
                new_data={"approved_at": None},
            )
            is True
        )

    def test_unparseable_condition_fail_closed(self):
        t = _Trigger(entity="M", event="created", when_condition="garbage")
        assert should_fire(t, event_kind="created", old_data=None, new_data={"x": 1}) is False

    def test_unknown_operator_fail_closed(self):
        t = _Trigger(entity="M", event="created", when_condition="x lt 5")
        assert should_fire(t, event_kind="created", old_data=None, new_data={"x": 1}) is False


# ---------------------------------------------------------------------------
# build_trigger_callbacks
# ---------------------------------------------------------------------------


class TestBuildTriggerCallbacks:
    def test_returns_three_callbacks(self):
        q = InMemoryJobQueue()
        cbs = build_trigger_callbacks(job_name="x", triggers=[], queue=q)
        assert set(cbs) == {"on_created", "on_updated", "on_deleted"}

    def test_on_created_enqueues_when_trigger_matches(self):
        async def go():
            q = InMemoryJobQueue()
            t = _Trigger(entity="M", event="created")
            cbs = build_trigger_callbacks(job_name="thumbnail", triggers=[t], queue=q)
            await cbs["on_created"]("abc", {"source_pdf": "x.pdf"}, None, "created")
            return await q.size()

        assert _run(go()) == 1

    def test_on_created_no_enqueue_when_event_mismatch(self):
        async def go():
            q = InMemoryJobQueue()
            t = _Trigger(entity="M", event="updated")  # only fires on update
            cbs = build_trigger_callbacks(job_name="thumbnail", triggers=[t], queue=q)
            await cbs["on_created"]("abc", {}, None, "created")
            return await q.size()

        assert _run(go()) == 0

    def test_on_updated_dispatches_field_changed(self):
        # An update event should evaluate both `updated` AND
        # `field_changed` triggers — the dispatcher does both.
        async def go():
            q = InMemoryJobQueue()
            t = _Trigger(entity="M", event="field_changed", field="status")
            cbs = build_trigger_callbacks(job_name="status_changed", triggers=[t], queue=q)
            await cbs["on_updated"](
                "abc",
                {"status": "submitted"},
                {"status": "draft"},
                "updated",
            )
            return await q.size()

        assert _run(go()) == 1

    def test_when_condition_filters_enqueue(self):
        async def go():
            q = InMemoryJobQueue()
            t = _Trigger(entity="M", event="created", when_condition="source_pdf is_set")
            cbs = build_trigger_callbacks(job_name="thumbnail", triggers=[t], queue=q)
            # No source_pdf → no enqueue.
            await cbs["on_created"]("abc", {"source_pdf": None}, None, "created")
            empty = await q.size()
            # With source_pdf → enqueue.
            await cbs["on_created"]("xyz", {"source_pdf": "x.pdf"}, None, "created")
            after = await q.size()
            return empty, after

        empty, after = _run(go())
        assert empty == 0
        assert after == 1

    def test_payload_carries_entity_id_and_row(self):
        async def go():
            q = InMemoryJobQueue()
            t = _Trigger(entity="M", event="created")
            cbs = build_trigger_callbacks(job_name="x", triggers=[t], queue=q)
            await cbs["on_created"]("row-1", {"k": "v"}, None, "created")
            return await q.dequeue(timeout=0.1)

        msg = _run(go())
        assert msg is not None
        assert msg.payload["entity_id"] == "row-1"
        assert msg.payload["entity_type"] == "M"
        assert msg.payload["event"] == "created"
        assert msg.payload["row"] == {"k": "v"}

    def test_queue_failure_swallowed(self):
        # A submit blow-up shouldn't propagate — the user's mutation
        # path must keep working even if the queue is down.
        class _BrokenQueue:
            async def submit(self, *_: Any, **__: Any) -> str:
                raise RuntimeError("Redis down")

            async def dequeue(self, *, timeout=None):
                return None

            async def size(self) -> int:
                return 0

        async def go():
            t = _Trigger(entity="M", event="created")
            cbs = build_trigger_callbacks(job_name="x", triggers=[t], queue=_BrokenQueue())
            # Must NOT raise.
            await cbs["on_created"]("abc", {}, None, "created")

        _run(go())  # no exception


# ---------------------------------------------------------------------------
# register_job_triggers
# ---------------------------------------------------------------------------


class TestRegisterJobTriggers:
    def test_no_jobs_returns_zero(self):
        assert register_job_triggers({}, [], InMemoryJobQueue()) == 0

    def test_pure_scheduled_jobs_skipped(self):
        # Job with no triggers (cron-only) should be skipped here —
        # cycle-7's scheduler enqueues those instead.
        spec = _JobSpec(name="daily_summary", triggers=[])
        wired = register_job_triggers({}, [spec], InMemoryJobQueue())
        assert wired == 0

    def test_missing_target_service_skipped(self):
        spec = _JobSpec(
            name="thumbnail",
            triggers=[_Trigger(entity="UnknownEntity", event="created")],
        )
        # No "UnknownEntity" service in dict → skip without error.
        wired = register_job_triggers({}, [spec], InMemoryJobQueue())
        assert wired == 0

    def test_registers_for_each_entity(self):
        target_a = _make_service()
        target_b = _make_service()
        spec = _JobSpec(
            name="multi",
            triggers=[
                _Trigger(entity="A", event="created"),
                _Trigger(entity="B", event="updated"),
            ],
        )
        wired = register_job_triggers({"A": target_a, "B": target_b}, [spec], InMemoryJobQueue())
        assert wired == 2  # one (job, entity) pair per side
        assert target_a.on_created.call_count == 1
        assert target_b.on_updated.call_count == 1

    def test_groups_triggers_by_entity(self):
        # Two triggers on the same entity → still one registration
        # call per service method (the callback walks both
        # internally).
        target = _make_service()
        spec = _JobSpec(
            name="x",
            triggers=[
                _Trigger(entity="M", event="created"),
                _Trigger(entity="M", event="field_changed", field="status"),
            ],
        )
        register_job_triggers({"M": target}, [spec], InMemoryJobQueue())
        # Each lifecycle hook called once even though two triggers
        # match the same entity.
        assert target.on_created.call_count == 1
        assert target.on_updated.call_count == 1
        assert target.on_deleted.call_count == 1

    def test_end_to_end_enqueue_via_registered_callback(self):
        # Round-trip: register against a stub service, invoke the
        # captured on_created, verify the queue picked up a message.
        target = _make_service()
        spec = _JobSpec(
            name="thumbnail",
            triggers=[_Trigger(entity="M", event="created")],
        )
        q = InMemoryJobQueue()
        register_job_triggers({"M": target}, [spec], q)
        captured_cb = target.on_created.call_args[0][0]

        async def go():
            await captured_cb("abc", {"source_pdf": "x.pdf"}, None, "created")
            return await q.size()

        assert _run(go()) == 1
