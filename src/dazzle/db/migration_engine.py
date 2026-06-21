"""Migration engine orchestrator for DSL-snapshot migrations (#1431 phase 3).

Public API
----------
``RevisionPlan``
    Frozen dataclass returned by both ``build_plan`` and ``generate_revision``.
    Contains the rendered Alembic op-trees, the current snapshot literal, and
    an ``is_empty`` flag the caller uses to suppress a no-op revision.

``build_plan(prev, curr, hints=None) -> RevisionPlan``
    Pure function: diff two plain-dict Snapshots and render the result.
    Fully unit-testable without a project on disk.

``generate_revision(script_dir, appspec=None) -> RevisionPlan``
    Thin I/O wrapper: loads the head snapshot from *script_dir*, projects the
    current schema via ``project_current()``, and self-loads the project's
    ``AppSpec`` for rename hints when *appspec* is not supplied, then delegates
    to ``build_plan``.  This is the entry-point wired into ``db revision``
    (Task 3.3).

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

from dazzle.db.schema_diff import RenameHints, diff
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
# Rename hint extraction
# ---------------------------------------------------------------------------


def extract_rename_hints(appspec: Any) -> RenameHints:
    """Extract rename hints from an ``AppSpec`` into the ``RenameHints`` shape.

    Reads ``EntitySpec.renamed_from`` (table-level) and
    ``FieldSpec.renamed_from`` (column-level) off every entity in
    ``appspec.domain.entities``.

    The snapshot stores table keys as ``entity.name`` verbatim and column keys
    as ``field.name`` verbatim, so the mapping is::

        tables:  {entity.name: entity.renamed_from}
        columns: {(entity.name, field.name): field.renamed_from}

    Entries where ``renamed_from`` is ``None`` are omitted.

    Parameters
    ----------
    appspec:
        A ``dazzle.core.ir.AppSpec`` instance.  Typed as ``Any`` here to avoid
        a circular import — the db layer must not import from core.ir at module
        level.
    """
    tables: dict[str, str] = {}
    columns: dict[tuple[str, str], str] = {}

    for entity in appspec.domain.entities:
        if entity.renamed_from is not None:
            tables[entity.name] = entity.renamed_from
        for field in entity.fields:
            if field.renamed_from is not None:
                columns[(entity.name, field.name)] = field.renamed_from

    return {"tables": tables, "columns": columns}


# ---------------------------------------------------------------------------
# Pure core: build_plan
# ---------------------------------------------------------------------------


def build_plan(
    prev: dict[str, Any],
    curr: dict[str, Any],
    hints: RenameHints | None = None,
) -> RevisionPlan:
    """Compute a ``RevisionPlan`` from two plain-dict Snapshots.

    This is the pure, unit-testable heart of the engine.  No filesystem,
    database, or Alembic context is required.

    Steps
    -----
    1. ``diff(prev, curr, hints)``  — ordered list of SchemaOps (rename-aware).
    2. ``render(delta)``            — (UpgradeOps, DowngradeOps) Alembic op-trees.
    3. ``render_snapshot_literal(curr)`` — deterministic Python literal.
    4. ``is_empty = (delta == [])``

    Parameters
    ----------
    prev:
        The head snapshot (may be ``{}`` for a brand-new project).
    curr:
        The current schema snapshot derived from the target MetaData.
    hints:
        Optional rename hints (see ``extract_rename_hints``).  When ``None``
        the diff treats every name change as a drop+add.
    """
    delta = diff(prev, curr, hints)
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


def _load_project_appspec_for_hints() -> Any:
    """Self-load the project's ``AppSpec`` from the CWD for rename-hint extraction.

    Mirrors ``dazzle.http.alembic.metadata_loader.load_target_metadata``: both
    build the schema from the Dazzle project in ``Path.cwd()`` via the canonical
    manifest → discover → parse → build pipeline (``load_project_appspec`` is the
    factored-out form of that exact pipeline).  Loading the AppSpec here therefore
    yields the *same* AppSpec that backs the projected ``curr`` snapshot, so the
    rename hints line up with the schema they are resolved against.

    Returns ``None`` (no rename resolution) in the same safe-fallback cases
    ``load_target_metadata`` returns empty MetaData — no ``dazzle.toml`` in the
    CWD, or any parse/link/IO failure — so ``db revision`` never crashes when run
    outside a project or against a half-formed one.
    """
    from pathlib import Path

    project_root = Path.cwd()
    if not (project_root / "dazzle.toml").exists():
        return None
    try:
        from dazzle.core.appspec_loader import load_project_appspec

        return load_project_appspec(project_root)
    except Exception:
        # A non-project / fresh / half-formed context: degrade to drop+add
        # rather than crashing the revision (matches metadata_loader's policy).
        return None


def generate_revision(script_dir: Any, appspec: Any = None) -> RevisionPlan:
    """Orchestrate a full revision cycle against the live project on disk.

    This is the thin I/O wrapper consumed by ``dazzle db revision`` (Task 3.3).
    It loads the two snapshots from external sources and delegates the pure
    computation to ``build_plan``.

    Steps
    -----
    1. ``project_current()``              — project the live target MetaData.
    2. ``load_head_snapshot(script_dir)`` — load the head migration's snapshot.
    3. Resolve the ``AppSpec`` for rename hints: use the explicit *appspec* arg
       when given, otherwise **self-load** it from the CWD via
       ``_load_project_appspec_for_hints`` (the env.py path passes no appspec, so
       without this the real ``db revision`` would lose rename resolution and turn
       every rename into drop+add — data loss; #1431 Task 4.3).
    4. ``extract_rename_hints(appspec)``  — extract ``was:`` hints (if resolved).
    5. ``build_plan(prev, curr, hints)``  — pure diff + render.

    Parameters
    ----------
    script_dir:
        An ``alembic.script.ScriptDirectory`` instance (or a compatible mock).
        Passed directly to ``load_head_snapshot``.
    appspec:
        Optional ``AppSpec``.  When supplied, rename hints are extracted from it
        directly (tests + any caller with an AppSpec in hand).  When ``None``,
        the AppSpec is self-loaded from the project in the CWD; if no project is
        present (or it fails to load) rename resolution is skipped and name
        changes become drop+add.
    """
    curr = project_current()
    prev = load_head_snapshot(script_dir)
    if appspec is None:
        appspec = _load_project_appspec_for_hints()
    hints = extract_rename_hints(appspec) if appspec is not None else None
    return build_plan(prev, curr, hints)
