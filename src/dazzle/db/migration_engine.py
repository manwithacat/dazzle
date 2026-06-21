"""Migration engine orchestrator for DSL-snapshot migrations (#1431 phase 3).

Public API
----------
``RevisionPlan``
    Frozen dataclass returned by both ``build_plan`` and ``generate_revision``.
    Contains the rendered Alembic op-trees, the current snapshot literal, and
    an ``is_empty`` flag the caller uses to suppress a no-op revision.

``build_plan(prev, curr) -> RevisionPlan``
    Pure function: diff two plain-dict Snapshots and render the result.
    Fully unit-testable without a project on disk.

``generate_revision(script_dir) -> RevisionPlan``
    Thin I/O wrapper: loads the head snapshot from *script_dir*, projects the
    current schema via ``project_current()``, then delegates to ``build_plan``.
    This is the entry-point wired into ``db revision`` (Task 3.3).

Design rationale
----------------
The split between ``build_plan`` (pure) and ``generate_revision`` (I/O wrapper)
follows the testability guideline in the task brief: tests inject plain dicts and
a mock ScriptDirectory, never touching the filesystem or a live project.

Snapshot type conventions (from schema_snapshot.py)
----------------------------------------------------
ColSnap   = {type: str, nullable: bool, default: str|None, pk: bool}
TableSnap = {columns: dict[str, ColSnap], fks: dict[str, str],
             uniques: list[str], indexes: list[str]}
Snapshot  = dict[str, TableSnap]
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from alembic.operations import ops as aops

from dazzle.db.schema_diff import diff
from dazzle.db.schema_render import render
from dazzle.db.schema_snapshot import (
    load_head_snapshot,
    project_current,
    render_snapshot_literal,
)

# ---------------------------------------------------------------------------
# Public result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RevisionPlan:
    """The output of the migration engine for a single revision.

    Attributes
    ----------
    upgrade_ops:
        Alembic ``UpgradeOps`` containing the forward migration operations.
    downgrade_ops:
        Alembic ``DowngradeOps`` containing the rollback operations (reverse
        order of upgrade).
    snapshot_literal:
        The current Snapshot serialised as a deterministic Python literal via
        ``render_snapshot_literal()``.  Task 3.3 embeds this verbatim as
        ``SCHEMA_SNAPSHOT = <literal>`` in the generated migration file.
    is_empty:
        True when the diff produced no operations.  The caller (``db revision``)
        uses this flag to suppress writing a no-op migration file.
    """

    upgrade_ops: aops.UpgradeOps
    downgrade_ops: aops.DowngradeOps
    snapshot_literal: str
    is_empty: bool


# ---------------------------------------------------------------------------
# Pure core: build_plan
# ---------------------------------------------------------------------------


def build_plan(
    prev: dict[str, Any],
    curr: dict[str, Any],
) -> RevisionPlan:
    """Compute a ``RevisionPlan`` from two plain-dict Snapshots.

    This is the pure, unit-testable heart of the engine.  No filesystem,
    database, or Alembic context is required.

    Steps
    -----
    1. ``diff(prev, curr)``  — ordered list of SchemaOps.
    2. ``render(delta)``     — (UpgradeOps, DowngradeOps) Alembic op-trees.
    3. ``render_snapshot_literal(curr)`` — deterministic Python literal.
    4. ``is_empty = (delta == [])``

    Parameters
    ----------
    prev:
        The head snapshot (may be ``{}`` for a brand-new project).
    curr:
        The current schema snapshot derived from the target MetaData.
    """
    delta = diff(prev, curr)
    upgrade_ops, downgrade_ops = render(delta)
    snapshot_literal = render_snapshot_literal(curr)
    return RevisionPlan(
        upgrade_ops=upgrade_ops,
        downgrade_ops=downgrade_ops,
        snapshot_literal=snapshot_literal,
        is_empty=(delta == []),
    )


# ---------------------------------------------------------------------------
# I/O wrapper: generate_revision
# ---------------------------------------------------------------------------


def generate_revision(script_dir: Any) -> RevisionPlan:
    """Orchestrate a full revision cycle against the live project on disk.

    This is the thin I/O wrapper consumed by ``dazzle db revision`` (Task 3.3).
    It loads the two snapshots from external sources and delegates the pure
    computation to ``build_plan``.

    Steps
    -----
    1. ``project_current()``         — project the live target MetaData.
    2. ``load_head_snapshot(script_dir)`` — load the head migration's snapshot.
    3. ``build_plan(prev, curr)``    — pure diff + render.

    Parameters
    ----------
    script_dir:
        An ``alembic.script.ScriptDirectory`` instance (or a compatible mock).
        Passed directly to ``load_head_snapshot``.
    """
    curr = project_current()
    prev = load_head_snapshot(script_dir)
    return build_plan(prev, curr)
