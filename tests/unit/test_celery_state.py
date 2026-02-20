"""Tests for celery_state.py — ProcessStateStore JSON serialization."""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from dazzle.core.process.celery_state import ProcessStateStore, _ProcessEncoder


class TestProcessEncoder:
    """Test _ProcessEncoder handles DB types."""

    def test_uuid(self):
        uid = uuid.UUID("12345678-1234-5678-1234-567812345678")
        result = json.dumps({"id": uid}, cls=_ProcessEncoder)
        assert '"12345678-1234-5678-1234-567812345678"' in result

    def test_datetime(self):
        dt = datetime(2026, 2, 20, 12, 30, 0)
        result = json.dumps({"ts": dt}, cls=_ProcessEncoder)
        assert "2026-02-20T12:30:00" in result

    def test_date(self):
        d = date(2026, 2, 20)
        result = json.dumps({"d": d}, cls=_ProcessEncoder)
        assert "2026-02-20" in result

    def test_decimal(self):
        dec = Decimal("123.45")
        result = json.dumps({"amount": dec}, cls=_ProcessEncoder)
        assert "123.45" in result

    def test_nested_uuids(self):
        data = {
            "entity_id": uuid.uuid4(),
            "items": [uuid.uuid4(), uuid.uuid4()],
            "meta": {"ref": uuid.uuid4()},
        }
        # Should not raise
        result = json.loads(json.dumps(data, cls=_ProcessEncoder))
        assert isinstance(result["entity_id"], str)
        assert all(isinstance(i, str) for i in result["items"])
        assert isinstance(result["meta"]["ref"], str)

    def test_unknown_type_raises(self):
        with pytest.raises(TypeError):
            json.dumps({"x": object()}, cls=_ProcessEncoder)


class TestSaveRunWithUuids:
    """Test ProcessStateStore.save_run() with UUID-containing inputs (#344)."""

    def test_save_run_uuid_inputs(self):
        """UUID objects in run.inputs should be serialized without error."""
        mock_redis = MagicMock()
        store = ProcessStateStore(redis_client=mock_redis)

        from dazzle.core.process.adapter import ProcessRun, ProcessStatus

        run = ProcessRun(
            run_id="run-001",
            process_name="test_process",
            process_version="v1",
            dsl_version="0.1",
            status=ProcessStatus.PENDING,
            inputs={
                "entity_id": uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
                "entity_name": "Task",
                "event_type": "created",
                "id": uuid.UUID("11111111-2222-3333-4444-555555555555"),
                "amount": Decimal("99.99"),
            },
        )

        # Should not raise TypeError
        store.save_run(run)

        # Verify Redis was called with valid JSON
        mock_redis.set.assert_called_once()
        key, json_str = mock_redis.set.call_args[0]
        assert key == "run:run-001"

        parsed = json.loads(json_str)
        assert parsed["inputs"]["entity_id"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        assert parsed["inputs"]["id"] == "11111111-2222-3333-4444-555555555555"
        assert parsed["inputs"]["amount"] == 99.99
