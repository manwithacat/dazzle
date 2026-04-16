"""Tests for TaskStoreBackend protocol + InMemoryTaskStore (#787)."""

from datetime import UTC, datetime

import pytest

from dazzle.core.process.adapter import ProcessTask, TaskStatus
from dazzle.core.process.task_store import (
    InMemoryTaskStore,
    TaskStoreBackend,
    get_task_store,
    set_task_store,
)


def _task(task_id: str, **overrides: object) -> ProcessTask:
    defaults: dict[str, object] = {
        "task_id": task_id,
        "run_id": "run-1",
        "step_name": "review",
        "surface_name": "review_form",
        "entity_name": "Doc",
        "entity_id": "doc-1",
        "status": TaskStatus.PENDING,
        "due_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return ProcessTask(**defaults)  # type: ignore[arg-type]


class TestInMemoryTaskStore:
    @pytest.mark.asyncio
    async def test_save_and_get(self) -> None:
        store = InMemoryTaskStore()
        task = _task("t1")
        await store.save(task)
        assert (await store.get("t1")) is task
        assert (await store.get("missing")) is None

    @pytest.mark.asyncio
    async def test_list_filters(self) -> None:
        store = InMemoryTaskStore()
        await store.save(_task("t1", run_id="run-A", assignee_id="u-1"))
        await store.save(_task("t2", run_id="run-A", assignee_id="u-2"))
        await store.save(_task("t3", run_id="run-B", assignee_id="u-1"))

        by_run = await store.list(run_id="run-A")
        assert {t.task_id for t in by_run} == {"t1", "t2"}

        by_assignee = await store.list(assignee_id="u-1")
        assert {t.task_id for t in by_assignee} == {"t1", "t3"}

        by_status = await store.list(status=TaskStatus.COMPLETED)
        assert by_status == []

    @pytest.mark.asyncio
    async def test_list_limit(self) -> None:
        store = InMemoryTaskStore()
        for i in range(5):
            await store.save(_task(f"t{i}"))
        assert len(await store.list(limit=3)) == 3

    @pytest.mark.asyncio
    async def test_complete(self) -> None:
        store = InMemoryTaskStore()
        await store.save(_task("t1"))

        ok = await store.complete("t1", "approved", {"note": "ok"}, "admin")
        assert ok is True

        updated = await store.get("t1")
        assert updated is not None
        assert updated.status == TaskStatus.COMPLETED
        assert updated.outcome == "approved"
        assert updated.outcome_data == {"note": "ok"}
        assert updated.completed_at is not None

    @pytest.mark.asyncio
    async def test_complete_missing_returns_false(self) -> None:
        store = InMemoryTaskStore()
        ok = await store.complete("missing", "approved")
        assert ok is False

    @pytest.mark.asyncio
    async def test_reassign(self) -> None:
        store = InMemoryTaskStore()
        await store.save(_task("t1", assignee_id="u-1"))

        ok = await store.reassign("t1", "u-2", reason="handoff")
        assert ok is True

        updated = await store.get("t1")
        assert updated is not None
        assert updated.assignee_id == "u-2"

    @pytest.mark.asyncio
    async def test_escalate(self) -> None:
        store = InMemoryTaskStore()
        await store.save(_task("t1"))

        ok = await store.escalate("t1")
        assert ok is True

        updated = await store.get("t1")
        assert updated is not None
        assert updated.status == TaskStatus.ESCALATED
        assert updated.escalated_at is not None

    @pytest.mark.asyncio
    async def test_escalate_missing_returns_false(self) -> None:
        store = InMemoryTaskStore()
        assert (await store.escalate("missing")) is False

    @pytest.mark.asyncio
    async def test_clear(self) -> None:
        store = InMemoryTaskStore()
        await store.save(_task("t1"))
        await store.save(_task("t2"))
        await store.clear()
        assert await store.list() == []


class TestGlobalTaskStore:
    def test_protocol_runtime_checkable(self) -> None:
        assert isinstance(InMemoryTaskStore(), TaskStoreBackend)

    def test_get_returns_in_memory_by_default(self) -> None:
        assert isinstance(get_task_store(), TaskStoreBackend)

    def test_set_and_get(self) -> None:
        original = get_task_store()
        try:
            replacement = InMemoryTaskStore()
            set_task_store(replacement)
            assert get_task_store() is replacement
        finally:
            set_task_store(original)


class TestActivitiesModuleFacade:
    """activities.py re-exports the task store API for backward compat."""

    @pytest.mark.asyncio
    async def test_get_and_list_delegate(self) -> None:
        from dazzle.core.process.activities import clear_task_store, get_task, list_tasks
        from dazzle.core.process.task_store import get_task_store

        await clear_task_store()
        await get_task_store().save(_task("t1", run_id="run-X"))

        fetched = await get_task("t1")
        assert fetched is not None
        assert fetched.task_id == "t1"

        tasks = await list_tasks(run_id="run-X")
        assert len(tasks) == 1

        await clear_task_store()

    @pytest.mark.asyncio
    async def test_complete_and_reassign_delegate(self) -> None:
        from dazzle.core.process.activities import (
            clear_task_store,
            complete_task,
            get_task,
            reassign_task,
        )
        from dazzle.core.process.task_store import get_task_store

        await clear_task_store()
        await get_task_store().save(_task("t1", assignee_id="u-1"))

        assert await reassign_task("t1", "u-2", reason="handoff")
        assert (await get_task("t1")).assignee_id == "u-2"  # type: ignore[union-attr]

        assert await complete_task("t1", "approved", {"note": "ok"}, "admin")
        task = await get_task("t1")
        assert task is not None
        assert task.status == TaskStatus.COMPLETED

        await clear_task_store()
