"""Tests for #956 cycle 5 — auth populates audit_context.current_user_id.

Cycle 4 wired the audit emitter against services with the user-ID
sourced from a ContextVar. Cycle 5 populates that ContextVar from
``_build_access_context`` — called per-request from every Cedar /
auth handler in route_generator. Authenticated mutations now produce
AuditEntry rows with `by_user_id` set; unauthenticated stay at None.

asyncio gives each request task its own ContextVar copy, so the value
is task-local — no explicit reset is needed in the per-request path,
the value is gone when the task ends. These tests verify the set
happens for authenticated users and is skipped for unauthenticated
ones, plus that concurrent tasks see independent values.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

from dazzle_back.runtime.audit_context import (
    get_current_user_id,
    reset_current_user_id,
    set_current_user_id,
)
from dazzle_back.runtime.route_generator import _build_access_context


def _auth(user) -> SimpleNamespace:
    return SimpleNamespace(is_authenticated=user is not None, user=user)


def _user(uid=None, *, roles=None, is_superuser=False) -> SimpleNamespace:
    return SimpleNamespace(
        id=uid or uuid4(),
        roles=roles or [],
        is_superuser=is_superuser,
    )


class TestPopulationFromBuildContext:
    def test_authenticated_user_sets_contextvar(self):
        # Reset to default first so we can observe the set.
        token = set_current_user_id(None)
        try:
            uid = uuid4()
            _build_access_context(_auth(_user(uid, roles=["teacher"])))
            assert get_current_user_id() == str(uid)
        finally:
            reset_current_user_id(token)

    def test_unauthenticated_leaves_contextvar_unchanged(self):
        # Pre-set to a sentinel so we can prove it isn't overwritten.
        token = set_current_user_id("PRE-EXISTING")
        try:
            _build_access_context(_auth(None))
            assert get_current_user_id() == "PRE-EXISTING"
        finally:
            reset_current_user_id(token)

    def test_uuid_user_id_stringified(self):
        # AuditEntry.by_user_id is a string column — make sure UUIDs
        # are converted before binding.
        token = set_current_user_id(None)
        try:
            uid = uuid4()
            _build_access_context(_auth(_user(uid)))
            value = get_current_user_id()
            assert isinstance(value, str)
            assert value == str(uid)
        finally:
            reset_current_user_id(token)


class TestTaskIsolation:
    def test_concurrent_tasks_see_independent_user_ids(self):
        # Each asyncio task gets its own ContextVar copy — sets in one
        # task must not leak into another. This is the property we
        # rely on to skip explicit reset in _build_access_context.
        async def _run_task(uid: str) -> str | None:
            _build_access_context(_auth(_user(uid)))
            # Yield to let the other task interleave.
            await asyncio.sleep(0)
            return get_current_user_id()

        async def _gather() -> tuple[str | None, str | None]:
            return await asyncio.gather(_run_task("user-a"), _run_task("user-b"))

        results = asyncio.run(_gather())
        assert results == ["user-a", "user-b"]

    def test_sequential_calls_in_same_task_overwrite(self):
        # Sequential calls in the same task replace the value. This
        # is the expected behaviour: the latest auth context wins.
        token = set_current_user_id(None)
        try:
            _build_access_context(_auth(_user("first")))
            assert get_current_user_id() == "first"
            _build_access_context(_auth(_user("second")))
            assert get_current_user_id() == "second"
        finally:
            reset_current_user_id(token)
