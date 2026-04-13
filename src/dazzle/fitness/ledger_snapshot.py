"""v1 snapshot-diff implementation of ``FitnessLedger``.

Strategy: before each step, read the repr-declared tables via the injected
``SnapshotSource``; after the step, read them again; diff the row sets by id.
Not transactionally isolated — good enough for v1, and fits behind the same
abstract interface as the later SAVEPOINT/WAL variants.

Sync-only per the plan's Task 0 retarget — Dazzle's runtime uses sync psycopg
v3. The adapter that bridges ``SnapshotSource`` to ``PostgresBackend`` lives
in Task 19 (engine wiring), not here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dazzle.fitness.ledger import FitnessLedger, SnapshotSource
from dazzle.fitness.models import FitnessDiff, LedgerStep, RowChange


@dataclass
class _PendingIntent:
    step_no: int
    expect: str
    action_desc: str
    before_snapshot: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


class SnapshotLedger(FitnessLedger):
    """v1 snapshot-diff ledger.

    Before every step the ledger reads each repr-declared table via the
    injected ``SnapshotSource``; after the step it reads again and diffs the
    row sets by ``id``. Not isolated (shared DB), ordering is by dense
    ``step_no`` counter.
    """

    def __init__(
        self,
        source: SnapshotSource,
        repr_fields: dict[str, list[str]],
    ) -> None:
        self._source = source
        self._repr_fields = repr_fields
        self._run_id: str | None = None
        self._steps: list[LedgerStep] = []
        self._created: list[RowChange] = []
        self._updated: list[RowChange] = []
        self._deleted: list[RowChange] = []
        self._pending: _PendingIntent | None = None

    def open(self, run_id: str) -> None:
        self._run_id = run_id
        self._steps = []
        self._created = []
        self._updated = []
        self._deleted = []
        self._pending = None

    def record_intent(self, step: int, expect: str, action_desc: str) -> None:
        if not expect or not expect.strip():
            raise ValueError(
                "record_intent: expect must be non-empty (interlock enforces EXPECT before ACTION)"
            )
        self._pending = _PendingIntent(step_no=step, expect=expect, action_desc=action_desc)

    def observe_step(self, step: int, observed_ui: str) -> None:
        if self._pending is None or self._pending.step_no != step:
            raise ValueError(f"observe_step({step}): no prior record_intent for this step")
        tables = list(self._repr_fields.keys())
        before = self._snapshot(tables)
        after = self._snapshot(tables)
        row_changes = self._diff(before, after)
        for rc in row_changes:
            if rc.kind == "insert":
                self._created.append(rc)
            elif rc.kind == "update":
                self._updated.append(rc)
            elif rc.kind == "delete":
                self._deleted.append(rc)

        ledger_step = LedgerStep(
            step_no=step,
            txn_id=None,  # v1.1+
            expected=self._pending.expect,
            action_summary=self._pending.action_desc,
            observed_ui=observed_ui,
            observed_changes=row_changes,
            delta={"row_change_count": len(row_changes)},
        )
        self._steps.append(ledger_step)
        self._pending = None

    def current_step(self) -> LedgerStep | None:
        return self._steps[-1] if self._steps else None

    def summarize(self) -> FitnessDiff:
        if self._run_id is None:
            raise RuntimeError("summarize(): ledger is not open")
        return FitnessDiff(
            run_id=self._run_id,
            steps=list(self._steps),
            created=list(self._created),
            updated=list(self._updated),
            deleted=list(self._deleted),
            progress=[],  # populated by progress_evaluator
            semantic_repr_config=dict(self._repr_fields),
        )

    def close(self, rollback: bool = False) -> None:
        # v1 snapshot ledger has no transactional state to roll back.
        # We intentionally keep _run_id so that summarize() remains valid
        # after close() — the close is a lifecycle marker, not a reset.
        self._pending = None

    def _snapshot(self, tables: list[str]) -> dict[str, list[dict[str, Any]]]:
        """Read row dicts for each table via the injected source."""
        out: dict[str, list[dict[str, Any]]] = {}
        for t in tables:
            cols = ["id", *self._repr_fields[t]]
            out[t] = list(self._source.fetch_rows(t, cols))
        return out

    def _diff(
        self,
        before: dict[str, list[dict[str, Any]]],
        after: dict[str, list[dict[str, Any]]],
    ) -> list[RowChange]:
        changes: list[RowChange] = []
        for table in self._repr_fields:
            before_rows = {r["id"]: r for r in before.get(table, [])}
            after_rows = {r["id"]: r for r in after.get(table, [])}
            # Inserts
            for rid, row in after_rows.items():
                if rid not in before_rows:
                    changes.append(
                        RowChange(
                            table=table,
                            row_id=str(rid),
                            kind="insert",
                            semantic_repr=self._repr(table, row),
                            field_deltas={k: (None, row.get(k)) for k in self._repr_fields[table]},
                        )
                    )
            # Updates
            for rid, b in before_rows.items():
                if rid in after_rows:
                    a = after_rows[rid]
                    deltas = {
                        k: (b.get(k), a.get(k))
                        for k in self._repr_fields[table]
                        if b.get(k) != a.get(k)
                    }
                    if deltas:
                        changes.append(
                            RowChange(
                                table=table,
                                row_id=str(rid),
                                kind="update",
                                semantic_repr=self._repr(table, a),
                                field_deltas=deltas,
                            )
                        )
            # Deletes
            for rid, row in before_rows.items():
                if rid not in after_rows:
                    changes.append(
                        RowChange(
                            table=table,
                            row_id=str(rid),
                            kind="delete",
                            semantic_repr=self._repr(table, row),
                            field_deltas={k: (row.get(k), None) for k in self._repr_fields[table]},
                        )
                    )
        return changes

    def _repr(self, table: str, row: dict[str, Any]) -> str:
        parts = [f"{k}={row.get(k)!r}" for k in self._repr_fields[table]]
        return f"{table}({', '.join(parts)})"
