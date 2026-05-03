"""Tests for #953 cycle 11 — retention orchestrator.

Cycle 10 shipped the generic `sweep_old_rows` helper. Cycle 11
ties it to both built-in retention targets:

  * `JobRun` rows older than `jobrun_retention_days` (default 30)
  * `AuditEntry` rows per `AuditSpec.retention_days`, filtered
    by entity_type so a 90-day Manuscript retention doesn't
    delete a 365-day Order retention's rows.

Tests cover:

  * Both services missing → empty stats
  * Only JobRun present → only JobRun swept
  * Only AuditEntry+audits present → only audit rows swept
  * Both present → both keys in stats
  * AuditSpec retention_days=0 → that audit is skipped
  * AuditSpec entity_name empty → skipped (defensive)
  * jobrun_retention_days=0 → JobRun key absent (sweep helper
    short-circuits without touching the service)
  * Per-entity audit_type filter is applied to the list call
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from dazzle_back.runtime.retention_runner import run_retention_sweep

# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


@dataclass
class _AuditSpec:
    entity: str
    retention_days: int = 0


@dataclass
class _ServiceStub:
    """Records list / delete calls; can return an arbitrary list of
    rows once before going empty."""

    rows: list[Any] = field(default_factory=list)
    list_calls: list[dict[str, Any]] = field(default_factory=list)
    delete_calls: list[Any] = field(default_factory=list)

    async def list(self, **kwargs: Any) -> Any:
        self.list_calls.append(kwargs)
        out = list(self.rows)
        self.rows = []
        return out

    async def delete(self, row_id: Any) -> bool:
        self.delete_calls.append(row_id)
        return True


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Service-presence permutations
# ---------------------------------------------------------------------------


class TestServicePresence:
    def test_both_missing_returns_empty_stats(self):
        stats = _run(run_retention_sweep(services={}, audits=[]))
        assert stats == {}

    def test_only_jobrun_swept(self):
        jr = _ServiceStub(rows=[{"id": "old-1"}, {"id": "old-2"}])
        stats = _run(
            run_retention_sweep(
                services={"JobRun": jr},
                audits=[],
                jobrun_retention_days=30,
            )
        )
        assert stats == {"JobRun": 2}
        assert jr.delete_calls == ["old-1", "old-2"]

    def test_only_audit_swept(self):
        ae = _ServiceStub(rows=[{"id": "audit-1"}])
        stats = _run(
            run_retention_sweep(
                services={"AuditEntry": ae},
                audits=[_AuditSpec(entity="Manuscript", retention_days=90)],
            )
        )
        assert stats == {"AuditEntry:Manuscript": 1}

    def test_both_present_both_swept(self):
        jr = _ServiceStub(rows=[{"id": "j-1"}])
        ae = _ServiceStub(rows=[{"id": "a-1"}, {"id": "a-2"}])
        stats = _run(
            run_retention_sweep(
                services={"JobRun": jr, "AuditEntry": ae},
                audits=[_AuditSpec(entity="Manuscript", retention_days=90)],
            )
        )
        assert stats == {"JobRun": 1, "AuditEntry:Manuscript": 2}


# ---------------------------------------------------------------------------
# Retention=0 honoured
# ---------------------------------------------------------------------------


class TestKeepForeverSentinel:
    def test_audit_retention_zero_skipped(self):
        # AuditSpec with retention_days=0 ("keep forever") should
        # not appear in stats and the AuditEntry service should
        # not be called for it.
        ae = _ServiceStub(rows=[{"id": "x"}])
        stats = _run(
            run_retention_sweep(
                services={"AuditEntry": ae},
                audits=[_AuditSpec(entity="Manuscript", retention_days=0)],
            )
        )
        assert stats == {}
        assert ae.list_calls == []  # never called

    def test_jobrun_retention_zero_no_jobrun_key(self):
        jr = _ServiceStub(rows=[{"id": "old"}])
        stats = _run(
            run_retention_sweep(
                services={"JobRun": jr},
                audits=[],
                jobrun_retention_days=0,
            )
        )
        # cycle-10 sweep_old_rows short-circuits to 0 — orchestrator
        # records that as the JobRun count.
        assert stats == {"JobRun": 0}
        assert jr.list_calls == []  # cycle-10 didn't list either

    def test_empty_entity_name_skipped(self):
        # Defensive: AuditSpec with empty entity name should be
        # skipped without crashing the run.
        ae = _ServiceStub(rows=[{"id": "x"}])
        stats = _run(
            run_retention_sweep(
                services={"AuditEntry": ae},
                audits=[_AuditSpec(entity="", retention_days=30)],
            )
        )
        assert stats == {}
        assert ae.list_calls == []


# ---------------------------------------------------------------------------
# Multi-entity audit filtering
# ---------------------------------------------------------------------------


class TestPerEntityAuditFilter:
    def test_each_audit_filtered_by_entity_type(self):
        # Two audits with different windows on different entities.
        # Each must list with `entity_type` filter pinned to its
        # entity so they don't overwrite each other's data.
        ae = _ServiceStub(rows=[{"id": "a-1"}])
        _run(
            run_retention_sweep(
                services={"AuditEntry": ae},
                audits=[
                    _AuditSpec(entity="Manuscript", retention_days=90),
                    _AuditSpec(entity="Order", retention_days=365),
                ],
            )
        )
        # Two list calls — one per audit spec.
        list_filters = [c["filters"] for c in ae.list_calls]
        entity_types = [f.get("entity_type") for f in list_filters]
        assert "Manuscript" in entity_types
        assert "Order" in entity_types

    def test_cutoff_per_entity_uses_correct_window(self):
        # Verify the at__lt cutoff matches each entity's retention
        # window (90 days for Manuscript, 365 for Order).
        ae = _ServiceStub(rows=[])
        _run(
            run_retention_sweep(
                services={"AuditEntry": ae},
                audits=[
                    _AuditSpec(entity="Manuscript", retention_days=90),
                    _AuditSpec(entity="Order", retention_days=365),
                ],
            )
        )
        for call in ae.list_calls:
            entity = call["filters"]["entity_type"]
            cutoff = call["filters"]["at__lt"]
            expected_days = 90 if entity == "Manuscript" else 365
            expected = datetime.now(UTC) - timedelta(days=expected_days)
            # 5s slop for test execution time.
            assert abs((cutoff - expected).total_seconds()) < 5


# ---------------------------------------------------------------------------
# JobRun integration with cycle-10 sweep_old_rows
# ---------------------------------------------------------------------------


class TestJobRunFilterShape:
    def test_jobrun_uses_created_at_filter(self):
        jr = _ServiceStub(rows=[{"id": "x"}])
        _run(
            run_retention_sweep(
                services={"JobRun": jr},
                audits=[],
                jobrun_retention_days=7,
            )
        )
        # Cycle-10 sweep filters by `<date_field>__lt`; for JobRun
        # the date column is `created_at`.
        call = jr.list_calls[0]
        assert "created_at__lt" in call["filters"]
