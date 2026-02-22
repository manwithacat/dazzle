"""Tests for EventBusProcessAdapter and step_executor.

Covers:
- Step executor extraction (standalone from Celery)
- EventBusProcessAdapter lifecycle
- Delayed event envelope
- Factory auto-detection preferring eventbus over celery
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from dazzle.core.process.adapter import ProcessRun, ProcessStatus, ProcessTask, TaskStatus

# =============================================================================
# Step executor tests
# =============================================================================


class TestStepExecutor:
    """Test the extracted step executor module."""

    def _make_store(self) -> MagicMock:
        store = MagicMock()
        store.get_process_spec.return_value = {
            "name": "test_process",
            "steps": [
                {"name": "step1", "kind": "send", "channel": "email"},
            ],
        }
        return store

    def _make_run(self, **kwargs) -> ProcessRun:
        defaults = {
            "run_id": str(uuid.uuid4()),
            "process_name": "test_process",
            "status": ProcessStatus.PENDING,
            "inputs": {"entity_id": "123"},
        }
        defaults.update(kwargs)
        return ProcessRun(**defaults)

    def test_execute_send_step(self):
        from dazzle.core.process.step_executor import execute_step

        store = self._make_store()
        run = self._make_run()
        step = {"name": "notify", "kind": "send", "channel": "email"}

        result = execute_step(store, run, {}, step)
        assert result["output"]["sent"] is True
        assert result["output"]["channel"] == "email"

    def test_execute_wait_step(self):
        from dazzle.core.process.step_executor import execute_step

        store = self._make_store()
        run = self._make_run()
        step = {"name": "wait_for_signal", "kind": "wait"}

        result = execute_step(store, run, {}, step)
        assert result["wait"] is True

    def test_execute_human_task_step_creates_task(self):
        from dazzle.core.process.step_executor import execute_step

        store = self._make_store()
        run = self._make_run()
        step = {
            "name": "review",
            "kind": "human_task",
            "surface": "review_form",
            "timeout_seconds": 3600,
        }
        callback = MagicMock()

        result = execute_step(store, run, {}, step, on_task_created=callback)
        assert result["wait"] is True
        assert "task_id" in result
        store.save_task.assert_called_once()
        callback.assert_called_once()

    def test_execute_human_task_without_callback(self):
        from dazzle.core.process.step_executor import execute_step

        store = self._make_store()
        run = self._make_run()
        step = {"name": "review", "kind": "human_task", "surface": "form"}

        result = execute_step(store, run, {}, step, on_task_created=None)
        assert result["wait"] is True
        store.save_task.assert_called_once()

    def test_execute_unknown_step_kind(self):
        from dazzle.core.process.step_executor import execute_step

        store = self._make_store()
        run = self._make_run()
        step = {"name": "mystery", "kind": "nonexistent"}

        result = execute_step(store, run, {}, step)
        assert result == {}

    def test_execute_process_steps_completes(self):
        from dazzle.core.process.step_executor import execute_process_steps

        store = self._make_store()
        run = self._make_run()

        result = execute_process_steps(store, run)
        assert result["status"] == "completed"
        assert run.status == ProcessStatus.COMPLETED

    def test_execute_process_steps_waits_on_human_task(self):
        from dazzle.core.process.step_executor import execute_process_steps

        store = self._make_store()
        store.get_process_spec.return_value = {
            "name": "test_process",
            "steps": [
                {"name": "review", "kind": "human_task", "surface": "form"},
            ],
        }
        run = self._make_run()

        result = execute_process_steps(store, run)
        assert result["status"] == "waiting"
        assert run.status == ProcessStatus.WAITING

    def test_execute_process_steps_missing_spec(self):
        from dazzle.core.process.step_executor import execute_process_steps

        store = self._make_store()
        store.get_process_spec.return_value = None
        run = self._make_run()

        result = execute_process_steps(store, run)
        assert result["status"] == "failed"
        assert run.status == ProcessStatus.FAILED

    def test_fail_run(self):
        from dazzle.core.process.step_executor import fail_run

        store = self._make_store()
        run = self._make_run()

        fail_run(store, run, "something went wrong")
        assert run.status == ProcessStatus.FAILED
        assert run.error == "something went wrong"
        assert run.completed_at is not None
        store.save_run.assert_called_once()

    def test_check_task_timeout_not_due(self):
        from dazzle.core.process.step_executor import check_task_timeout

        store = MagicMock()
        task = ProcessTask(
            task_id="t1",
            run_id="r1",
            step_name="review",
            surface_name="form",
            entity_name="Order",
            entity_id="123",
            status=TaskStatus.PENDING,
            due_at=datetime.now(UTC) + timedelta(hours=1),
        )
        store.get_task.return_value = task

        result = check_task_timeout(store, "t1")
        assert result["not_due"] is True

    def test_check_task_timeout_escalates(self):
        from dazzle.core.process.step_executor import check_task_timeout

        store = MagicMock()
        task = ProcessTask(
            task_id="t1",
            run_id="r1",
            step_name="review",
            surface_name="form",
            entity_name="Order",
            entity_id="123",
            status=TaskStatus.PENDING,
            due_at=datetime.now(UTC) - timedelta(hours=1),
        )
        store.get_task.return_value = task

        result = check_task_timeout(store, "t1")
        assert result["status"] == "escalated"
        assert result["needs_followup"] is True
        assert task.status == TaskStatus.ESCALATED

    def test_check_task_timeout_expires(self):
        from dazzle.core.process.step_executor import check_task_timeout

        store = MagicMock()
        task = ProcessTask(
            task_id="t1",
            run_id="r1",
            step_name="review",
            surface_name="form",
            entity_name="Order",
            entity_id="123",
            status=TaskStatus.ESCALATED,
            due_at=datetime.now(UTC) - timedelta(hours=1),
        )
        store.get_task.return_value = task

        run = ProcessRun(
            run_id="r1",
            process_name="test",
            status=ProcessStatus.WAITING,
        )
        store.get_run.return_value = run

        result = check_task_timeout(store, "t1")
        assert result["status"] == "expired"
        assert task.status == TaskStatus.EXPIRED

    def test_check_task_timeout_completed_skips(self):
        from dazzle.core.process.step_executor import check_task_timeout

        store = MagicMock()
        task = ProcessTask(
            task_id="t1",
            run_id="r1",
            step_name="review",
            surface_name="form",
            entity_name="Order",
            entity_id="123",
            status=TaskStatus.COMPLETED,
            due_at=datetime.now(UTC) - timedelta(hours=1),
        )
        store.get_task.return_value = task

        result = check_task_timeout(store, "t1")
        assert result["skipped"] is True

    def test_check_task_timeout_not_found(self):
        from dazzle.core.process.step_executor import check_task_timeout

        store = MagicMock()
        store.get_task.return_value = None

        result = check_task_timeout(store, "missing")
        assert "error" in result

    def test_run_compensation(self):
        from dazzle.core.process.step_executor import run_compensation

        store = self._make_store()
        run = self._make_run(status=ProcessStatus.RUNNING)
        spec = {
            "steps": [
                {"name": "step1", "kind": "send", "channel": "email"},
                {
                    "name": "step2",
                    "kind": "send",
                    "channel": "sms",
                    "on_failure": {"name": "undo_step2", "kind": "send", "channel": "undo"},
                },
            ],
        }

        run_compensation(store, run, spec, ["step1", "step2"], "test error")
        assert run.status == ProcessStatus.COMPENSATING

    def test_foreach_step(self):
        from dazzle.core.process.step_executor import execute_step

        store = self._make_store()
        run = self._make_run()
        run.context["items"] = [{"name": "a"}, {"name": "b"}]

        step = {
            "name": "loop",
            "kind": "foreach",
            "foreach_source": "items",
            "foreach_steps": [
                {"name": "notify", "kind": "send", "channel": "email"},
            ],
        }

        result = execute_step(store, run, {}, step)
        assert result["output"]["processed"] == 2
        assert result["output"]["errors"] == 0


# =============================================================================
# EventEnvelope delayed delivery tests
# =============================================================================


class TestDelayedEventEnvelope:
    """Test deliver_at on EventEnvelope."""

    def test_create_delayed(self):
        from dazzle_back.events.envelope import EventEnvelope

        future = datetime.now(UTC) + timedelta(hours=1)
        envelope = EventEnvelope.create_delayed(
            event_type="process.task.timeout",
            key="task-123",
            payload={"task_id": "task-123"},
            deliver_at=future,
        )
        assert envelope.deliver_at == future
        assert envelope.event_type == "process.task.timeout"

    def test_deliver_at_serialization(self):
        from dazzle_back.events.envelope import EventEnvelope

        future = datetime.now(UTC) + timedelta(hours=1)
        envelope = EventEnvelope.create_delayed(
            event_type="process.task.timeout",
            key="task-123",
            payload={"task_id": "task-123"},
            deliver_at=future,
        )

        data = envelope.to_dict()
        assert data["deliver_at"] is not None

        restored = EventEnvelope.from_dict(data)
        assert restored.deliver_at is not None
        assert abs((restored.deliver_at - future).total_seconds()) < 1

    def test_normal_envelope_no_deliver_at(self):
        from dazzle_back.events.envelope import EventEnvelope

        envelope = EventEnvelope.create(
            event_type="app.Order.created",
            key="order-1",
            payload={"id": "order-1"},
        )
        assert envelope.deliver_at is None

        data = envelope.to_dict()
        assert data["deliver_at"] is None

        restored = EventEnvelope.from_dict(data)
        assert restored.deliver_at is None


# =============================================================================
# Factory tests
# =============================================================================


class TestFactoryEventBusBackend:
    """Test factory auto-detection and explicit backend selection."""

    def test_auto_detect_prefers_eventbus_over_celery(self):
        from dazzle.core.process.factory import ProcessConfig, _detect_backend

        config = ProcessConfig()
        with patch.dict("os.environ", {"REDIS_URL": "redis://localhost:6379/0"}):
            backend = _detect_backend(config)
        assert backend == "eventbus"

    def test_explicit_eventbus_backend(self):
        from dazzle.core.process.factory import ProcessConfig, create_adapter

        config = ProcessConfig(backend="eventbus")
        with (
            patch.dict("os.environ", {"REDIS_URL": "redis://localhost:6379/0"}),
            patch("dazzle.core.process.eventbus_adapter.ProcessStateStore"),
        ):
            adapter = create_adapter(config)
        from dazzle.core.process.eventbus_adapter import EventBusProcessAdapter

        assert isinstance(adapter, EventBusProcessAdapter)

    def test_explicit_celery_still_works(self):
        """Celery backend is still available when explicitly requested."""
        from dazzle.core.process.factory import ProcessConfig, create_adapter

        config = ProcessConfig(backend="celery")
        with (
            patch.dict("os.environ", {"REDIS_URL": "redis://localhost:6379/0"}),
            patch("dazzle.core.process.celery_adapter.CeleryProcessAdapter") as mock_cls,
        ):
            mock_cls.return_value = MagicMock()
            create_adapter(config)

    def test_backend_info_includes_eventbus(self):
        from dazzle.core.process.factory import ProcessConfig, get_backend_info

        config = ProcessConfig()
        with patch.dict("os.environ", {"REDIS_URL": "redis://localhost:6379/0"}):
            info = get_backend_info(config)
        assert info["eventbus_available"] is True

    def test_backend_info_no_redis(self):
        from dazzle.core.process.factory import ProcessConfig, get_backend_info

        config = ProcessConfig()
        with patch.dict("os.environ", {}, clear=True):
            info = get_backend_info(config)
        assert info["eventbus_available"] is False


# =============================================================================
# EventBusProcessAdapter unit tests
# =============================================================================


class TestEventBusProcessAdapter:
    """Test EventBusProcessAdapter without real Redis."""

    def _make_adapter(self):
        from dazzle.core.process.eventbus_adapter import EventBusProcessAdapter

        store = MagicMock()
        adapter = EventBusProcessAdapter(store=store)
        adapter._store = store
        return adapter, store

    @pytest.mark.asyncio
    async def test_start_process(self):
        adapter, store = self._make_adapter()
        store.list_runs.return_value = []

        with patch.object(adapter, "_publish_event"):
            run_id = await adapter.start_process("my_process", {"key": "value"})

        assert run_id  # Should be a UUID string
        store.save_run.assert_called_once()
        saved_run = store.save_run.call_args[0][0]
        assert saved_run.process_name == "my_process"
        assert saved_run.status == ProcessStatus.PENDING

    @pytest.mark.asyncio
    async def test_start_process_idempotency(self):
        adapter, store = self._make_adapter()
        existing_run = ProcessRun(
            run_id="existing-123",
            process_name="my_process",
            status=ProcessStatus.RUNNING,
            idempotency_key="dedup-key",
        )
        store.list_runs.return_value = [existing_run]

        run_id = await adapter.start_process("my_process", {}, idempotency_key="dedup-key")
        assert run_id == "existing-123"
        store.save_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancel_process(self):
        adapter, store = self._make_adapter()
        run = ProcessRun(
            run_id="r1",
            process_name="test",
            status=ProcessStatus.RUNNING,
        )
        store.get_run.return_value = run

        await adapter.cancel_process("r1", "user requested")
        assert run.status == ProcessStatus.CANCELLED
        assert "Cancelled" in (run.error or "")
        store.save_run.assert_called()

    @pytest.mark.asyncio
    async def test_cancel_completed_process_no_op(self):
        adapter, store = self._make_adapter()
        run = ProcessRun(
            run_id="r1",
            process_name="test",
            status=ProcessStatus.COMPLETED,
        )
        store.get_run.return_value = run

        await adapter.cancel_process("r1", "too late")
        store.save_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_complete_task(self):
        adapter, store = self._make_adapter()
        task = ProcessTask(
            task_id="t1",
            run_id="r1",
            step_name="review",
            surface_name="form",
            entity_name="Order",
            entity_id="123",
            status=TaskStatus.PENDING,
            due_at=datetime.now(UTC) + timedelta(hours=1),
        )
        store.get_task.return_value = task

        with patch.object(adapter, "_publish_event"):
            await adapter.complete_task("t1", "approved", {"notes": "LGTM"})

        assert task.status == TaskStatus.COMPLETED
        assert task.outcome == "approved"
        store.save_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_complete_task_already_completed(self):
        adapter, store = self._make_adapter()
        task = ProcessTask(
            task_id="t1",
            run_id="r1",
            step_name="review",
            surface_name="form",
            entity_name="Order",
            entity_id="123",
            status=TaskStatus.COMPLETED,
            due_at=datetime.now(UTC),
        )
        store.get_task.return_value = task

        await adapter.complete_task("t1", "approved")
        store.save_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_signal_process_resumes_waiting(self):
        adapter, store = self._make_adapter()
        run = ProcessRun(
            run_id="r1",
            process_name="test",
            status=ProcessStatus.WAITING,
        )
        store.get_run.return_value = run

        with patch.object(adapter, "_publish_event"):
            await adapter.signal_process("r1", "payment_received", {"amount": 100})

        assert run.context["signal_payment_received"] == {"amount": 100}
        assert run.status == ProcessStatus.PENDING

    @pytest.mark.asyncio
    async def test_reassign_task(self):
        adapter, store = self._make_adapter()
        task = ProcessTask(
            task_id="t1",
            run_id="r1",
            step_name="review",
            surface_name="form",
            entity_name="Order",
            entity_id="123",
            status=TaskStatus.ASSIGNED,
            due_at=datetime.now(UTC) + timedelta(hours=1),
        )
        store.get_task.return_value = task

        await adapter.reassign_task("t1", "user-456")
        assert task.assignee_id == "user-456"
        assert task.status == TaskStatus.ASSIGNED

    def test_cron_matches(self):
        from dazzle.core.process.eventbus_adapter import EventBusProcessAdapter

        # Every minute
        assert EventBusProcessAdapter._cron_matches("* * * * *", datetime(2026, 2, 22, 10, 30))
        # Specific minute
        assert EventBusProcessAdapter._cron_matches("30 * * * *", datetime(2026, 2, 22, 10, 30))
        assert not EventBusProcessAdapter._cron_matches("15 * * * *", datetime(2026, 2, 22, 10, 30))
        # Every 5 minutes
        assert EventBusProcessAdapter._cron_matches("*/5 * * * *", datetime(2026, 2, 22, 10, 30))
        assert not EventBusProcessAdapter._cron_matches(
            "*/5 * * * *", datetime(2026, 2, 22, 10, 31)
        )

    @pytest.mark.asyncio
    async def test_register_process(self):
        adapter, store = self._make_adapter()
        from dazzle.core.ir.process import ProcessSpec

        spec = ProcessSpec(name="test_proc", steps=[])
        await adapter.register_process(spec)
        store.register_process.assert_called_once_with(spec)

    @pytest.mark.asyncio
    async def test_list_runs(self):
        adapter, store = self._make_adapter()
        store.list_runs.return_value = []
        result = await adapter.list_runs(process_name="test")
        store.list_runs.assert_called_once()
        assert result == []
