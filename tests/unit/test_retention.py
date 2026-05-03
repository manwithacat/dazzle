"""Tests for #953 cycle 10 — generic retention-sweep helper.

`sweep_old_rows` is the reusable primitive for both `JobRun`
(#953) and `AuditEntry` (#956). Cycle 11+ wires it into the
cycle-7b scheduler so old rows get cleaned up periodically.

Tests cover:

  * `older_than_days=0` is a no-op (matches IR convention for
    "keep forever")
  * None service tolerated (early-bootstrap)
  * List + delete called against the service
  * List failure stops the sweep cleanly
  * Per-row delete failures don't kill the sweep
  * Paged-response shape (dict with "items") supported
  * Pydantic-model rows supported (id attribute)
  * Pagination terminates when a short page is returned
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from dazzle_back.runtime.retention import sweep_old_rows

# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


@dataclass
class _StubService:
    """Records list/delete calls so tests can assert on them.
    Default behaviour: returns the rows passed in once, then empty."""

    rows: list[Any] = field(default_factory=list)
    list_calls: list[dict[str, Any]] = field(default_factory=list)
    delete_calls: list[Any] = field(default_factory=list)
    list_fail: Exception | None = None
    delete_fail_for: set[Any] = field(default_factory=set)

    async def list(self, **kwargs: Any) -> Any:
        self.list_calls.append(kwargs)
        if self.list_fail is not None:
            raise self.list_fail
        # Return the queued rows once; subsequent calls return [].
        out = list(self.rows)
        self.rows = []
        return out

    async def delete(self, row_id: Any) -> bool:
        self.delete_calls.append(row_id)
        if row_id in self.delete_fail_for:
            raise RuntimeError(f"delete fail for {row_id}")
        return True


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestNoOpPaths:
    def test_zero_days_returns_zero_without_calling_service(self):
        svc = _StubService(rows=[{"id": "a"}])
        deleted = _run(sweep_old_rows(svc, date_field="at", older_than_days=0))
        assert deleted == 0
        assert svc.list_calls == []  # never called

    def test_negative_days_is_no_op(self):
        # Defensive: negative also means "keep forever" rather
        # than "delete from the future" or similar nonsense.
        svc = _StubService(rows=[{"id": "a"}])
        deleted = _run(sweep_old_rows(svc, date_field="at", older_than_days=-5))
        assert deleted == 0
        assert svc.list_calls == []

    def test_none_service_returns_zero(self):
        deleted = _run(sweep_old_rows(None, date_field="at", older_than_days=30))
        assert deleted == 0

    def test_empty_result_returns_zero(self):
        svc = _StubService(rows=[])
        deleted = _run(sweep_old_rows(svc, date_field="at", older_than_days=30))
        assert deleted == 0
        assert len(svc.list_calls) == 1  # listed once, found nothing


class TestHappyPath:
    def test_deletes_each_listed_row(self):
        svc = _StubService(rows=[{"id": "a"}, {"id": "b"}, {"id": "c"}])
        deleted = _run(sweep_old_rows(svc, date_field="at", older_than_days=30))
        assert deleted == 3
        assert svc.delete_calls == ["a", "b", "c"]

    def test_filter_uses_date_field_lt(self):
        svc = _StubService(rows=[{"id": "a"}])
        _run(sweep_old_rows(svc, date_field="created_at", older_than_days=7))
        # Filter key follows Django-style `__lt` so the underlying
        # repository can translate to `created_at < ?`.
        call = svc.list_calls[0]
        assert "created_at__lt" in call["filters"]
        cutoff = call["filters"]["created_at__lt"]
        # Cutoff is roughly now - 7 days (allow 5s slop for test
        # execution time).
        expected = datetime.now(UTC) - timedelta(days=7)
        assert abs((cutoff - expected).total_seconds()) < 5

    def test_pydantic_model_rows_supported(self):
        from pydantic import BaseModel

        class _Row(BaseModel):
            id: str

        svc = _StubService(rows=[_Row(id="x"), _Row(id="y")])
        deleted = _run(sweep_old_rows(svc, date_field="at", older_than_days=30))
        assert deleted == 2

    def test_paged_response_shape_supported(self):
        # Service may return `{"items": [...], "total": N}` —
        # helper unwraps the items.
        svc = _StubService(rows=[])  # initial state empty

        async def list_paged(**_kwargs: Any) -> Any:
            # First call returns one page, second call returns empty.
            if not svc.list_calls:
                svc.list_calls.append(_kwargs)
                return {"items": [{"id": "a"}, {"id": "b"}], "total": 2}
            svc.list_calls.append(_kwargs)
            return {"items": []}

        svc.list = list_paged  # type: ignore[assignment]
        deleted = _run(sweep_old_rows(svc, date_field="at", older_than_days=30))
        assert deleted == 2

    def test_short_page_terminates_sweep(self):
        # Page size 200, page returns 3 — sweep should stop after
        # one page rather than re-querying.
        svc = _StubService(rows=[{"id": "a"}, {"id": "b"}, {"id": "c"}])
        _run(sweep_old_rows(svc, date_field="at", older_than_days=30, page_size=200))
        assert len(svc.list_calls) == 1


class TestErrorResilience:
    def test_list_failure_stops_sweep_cleanly(self):
        svc = _StubService(rows=[{"id": "a"}])
        svc.list_fail = RuntimeError("DB down")
        deleted = _run(sweep_old_rows(svc, date_field="at", older_than_days=30))
        # Returns zero (couldn't list anything to delete) without
        # raising. Operator sees the failure in the WARNING log.
        assert deleted == 0

    def test_per_row_delete_failure_does_not_kill_sweep(self):
        # Mid-sweep delete fails on row "b". Rows "a" and "c"
        # should still be deleted; final count = 2.
        svc = _StubService(rows=[{"id": "a"}, {"id": "b"}, {"id": "c"}])
        svc.delete_fail_for = {"b"}
        deleted = _run(sweep_old_rows(svc, date_field="at", older_than_days=30))
        assert deleted == 2
        # All three were attempted — the failure on "b" didn't
        # short-circuit the loop.
        assert svc.delete_calls == ["a", "b", "c"]

    def test_row_without_id_skipped(self):
        # Defensive: malformed row dicts without `id` should be
        # skipped, not crash with KeyError.
        svc = _StubService(rows=[{"id": "a"}, {"name": "no_id"}, {"id": "c"}])
        deleted = _run(sweep_old_rows(svc, date_field="at", older_than_days=30))
        assert deleted == 2
        assert svc.delete_calls == ["a", "c"]


class TestPagination:
    def test_full_page_continues_to_next(self):
        # When the service returns exactly `page_size` rows, the
        # sweep should query page 2 (even though our stub's
        # second call returns empty by default).
        svc = _StubService(rows=[{"id": str(i)} for i in range(5)])
        _run(sweep_old_rows(svc, date_field="at", older_than_days=30, page_size=5))
        # Two list calls — page 1 (5 rows), page 2 (empty stop).
        assert len(svc.list_calls) == 2
        assert svc.list_calls[0]["page"] == 1
        assert svc.list_calls[1]["page"] == 2
