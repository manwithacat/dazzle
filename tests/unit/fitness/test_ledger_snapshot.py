"""Tests for SnapshotLedger (v1 fitness task 4).

The ledger is sync in v1 — see the plan's Task 0 retarget notes. These tests
abstract the DB via a ``SnapshotSource`` protocol stub; the real adapter to
``PostgresBackend`` lives in Task 19 (engine wiring).
"""

from __future__ import annotations

from typing import Any

import pytest

from dazzle.fitness.ledger import FitnessLedger, SnapshotSource
from dazzle.fitness.ledger_snapshot import SnapshotLedger
from dazzle.fitness.models import FitnessDiff


class FakeSource:
    """Two-state snapshot source: returns ``before`` on the first call per table,
    then ``after`` on every subsequent call.

    This matches how ``SnapshotLedger.observe_step`` polls: once pre-action,
    once post-action.
    """

    def __init__(
        self,
        before: dict[str, list[dict[str, Any]]],
        after: dict[str, list[dict[str, Any]]],
    ) -> None:
        self._before = before
        self._after = after
        self._seen: set[str] = set()

    def fetch_rows(self, table: str, columns: list[str]) -> list[dict[str, Any]]:
        if table in self._seen:
            return list(self._after.get(table, []))
        self._seen.add(table)
        return list(self._before.get(table, []))


@pytest.fixture
def repr_map() -> dict[str, list[str]]:
    return {"ticket": ["title", "status"]}


def test_snapshot_ledger_records_single_step(
    repr_map: dict[str, list[str]],
) -> None:
    source = FakeSource(
        before={
            "ticket": [
                {"id": "t1", "title": "Broken login", "status": "new"},
            ]
        },
        after={
            "ticket": [
                {"id": "t1", "title": "Broken login", "status": "in_progress"},
            ]
        },
    )
    ledger = SnapshotLedger(source=source, repr_fields=repr_map)
    ledger.open("run-1")

    ledger.record_intent(step=1, expect="status advances", action_desc="click")
    ledger.observe_step(step=1, observed_ui="ok")
    ledger.close()

    diff: FitnessDiff = ledger.summarize()
    assert diff.run_id == "run-1"
    assert len(diff.steps) == 1
    assert diff.steps[0].expected == "status advances"
    assert len(diff.updated) == 1
    assert diff.updated[0].table == "ticket"
    assert diff.updated[0].field_deltas["status"] == ("new", "in_progress")


def test_snapshot_ledger_rejects_step_without_intent(
    repr_map: dict[str, list[str]],
) -> None:
    source = FakeSource(before={"ticket": []}, after={"ticket": []})
    ledger = SnapshotLedger(source=source, repr_fields=repr_map)
    ledger.open("run-2")

    with pytest.raises(ValueError, match="intent"):
        ledger.observe_step(step=1, observed_ui="ok")


def test_snapshot_ledger_is_a_fitness_ledger(
    repr_map: dict[str, list[str]],
) -> None:
    source = FakeSource(before={"ticket": []}, after={"ticket": []})
    ledger = SnapshotLedger(source=source, repr_fields=repr_map)
    assert isinstance(ledger, FitnessLedger)
    # The protocol should be usable as a type hint — no runtime check, but
    # we can verify the fake satisfies the attribute shape.
    assert hasattr(source, "fetch_rows")
    _: SnapshotSource = source  # noqa: F841
