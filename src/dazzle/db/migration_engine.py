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

import logging
from collections.abc import Callable, Collection
from dataclasses import dataclass, replace
from typing import Any

from alembic.operations import ops as aops

from dazzle.db.schema_diff import RenameHints, diff
from dazzle.db.schema_render import render
from dazzle.db.schema_snapshot import (
    SnapshotLocation,
    find_head_snapshot,
    project_current,
    render_snapshot_literal,
)

logger = logging.getLogger(__name__)

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
    notes:
        Operator-facing warnings about the previous snapshot (#1846): revisions
        passed over that carry no snapshot, or a merge whose parents disagree.
        ``db revision`` prints them; they never block the revision.
    """

    upgrade_ops: aops.UpgradeOps
    downgrade_ops: aops.DowngradeOps
    snapshot_literal: str
    is_empty: bool
    notes: tuple[str, ...] = ()


class WholeSchemaRevisionRefused(RuntimeError):
    """Raised instead of diffing an empty previous snapshot against a populated DB (#1846)."""


def guard_whole_schema_revision(
    prev: dict[str, Any],
    curr: dict[str, Any],
    existing_tables: Collection[str] | None,
) -> None:
    """Refuse a revision that would re-create tables the database already has.

    An empty *prev* renders every table in *curr* as ``create_table``. That is
    right for a genuinely fresh project (none of those tables in the database
    yet) and never right when the database already holds some of them: the
    result is a whole-schema revision (#1846, #1851) that fails on the first
    existing table at best, and is trimmed wrongly by hand at worst.
    *existing_tables* is the target database's table names; ``None`` (not
    inspected, e.g. offline mode) skips the guard. There is no override flag:
    the remedy is to give the engine a snapshot (``dazzle db snapshot-baseline``),
    not to force the diff.
    """
    if prev or existing_tables is None:
        return
    present = sorted(set(curr) & set(existing_tables))
    if not present:
        return
    shown = ", ".join(present[:8])
    if len(present) > 8:
        shown += f", and {len(present) - 8} more"
    raise WholeSchemaRevisionRefused(
        "refusing to generate a whole-schema revision: no migration reachable from "
        "the head carries a SCHEMA_SNAPSHOT, so every DSL table would be emitted as "
        f"create_table, but the database already has {len(present)} of them ({shown}). "
        "Put the DSL back to what the database holds, run `dazzle db snapshot-baseline` "
        "and `dazzle db upgrade` to stamp it as the engine baseline, re-apply the DSL "
        "change, then run `dazzle db revision` again (#1846)."
    )


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
# Baseline: full create from an empty prior snapshot
# ---------------------------------------------------------------------------


def generate_baseline_plan(
    table_filter: Callable[[str], bool] | None = None,
) -> RevisionPlan:
    """Build the engine's plan for a **fresh-database baseline** revision.

    A baseline creates every project table from nothing, so the diff is against
    an empty ``prev`` (``{}``). Two distinct projections are used:

    * The **create ops** diff ``{}`` against the *framework-excluded* projection
      (``table_filter``), so the baseline creates only the project's own tables —
      framework-owned tables (auth/audit/event/process/deploy) are created by the
      framework baseline migration, not here. FKs land as separate
      ``op.create_foreign_key`` ops (the engine's native behaviour), so cyclic /
      self-referential FKs work without the legacy inline-create hoist (#1460).
    * The **embedded** ``SCHEMA_SNAPSHOT`` is the *full* projection (framework
      tables included) — it describes the actual post-migration schema state, so
      the next ``db revision`` diffs full-vs-full and framework tables cancel out
      rather than re-appearing as additions. This matches what ``snapshot-baseline``
      stamps, which is why an engine baseline no longer needs that follow-up step.

    ``table_filter`` is the table-name predicate (typically
    ``framework_tables.include_object`` adapted to a name check); when ``None`` no
    tables are excluded (every table is treated as project-owned).
    """
    full = project_current()
    creatable = project_current(table_filter=table_filter)
    delta = diff({}, creatable, None)
    upgrade_ops, downgrade_ops = render(delta)
    return RevisionPlan(
        upgrade_ops=upgrade_ops,
        downgrade_ops=downgrade_ops,
        snapshot_literal=render_snapshot_literal(full),
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
        logger.debug(
            "could not load project appspec for rename hints; proceeding without",
            exc_info=True,
        )
        return None


def snapshot_notes(loc: SnapshotLocation) -> tuple[str, ...]:
    """Operator-facing warnings about where the previous snapshot came from (#1846)."""
    notes: list[str] = []
    if loc.snapshot and loc.unsnapshotted:
        notes.append(
            f"diffing against the SCHEMA_SNAPSHOT of {loc.revision}; "
            f"{len(loc.unsnapshotted)} later revision(s) carry no snapshot "
            f"({', '.join(loc.unsnapshotted)}). If they changed DSL-modelled tables, "
            "those changes reappear in this revision: review it, or run "
            "`dazzle db snapshot-baseline` before making the DSL change."
        )
    if loc.ambiguous:
        notes.append(
            f"merge parents carry different SCHEMA_SNAPSHOTs; diffing against "
            f"{loc.revision}. Review the revision for changes from the other branch."
        )
    return tuple(notes)


def generate_revision(
    script_dir: Any,
    appspec: Any = None,
    *,
    existing_tables: Collection[str] | None = None,
) -> RevisionPlan:
    """Orchestrate a full revision cycle against the live project on disk.

    This is the thin I/O wrapper consumed by ``dazzle db revision`` (Task 3.3).
    It loads the two snapshots from external sources and delegates the pure
    computation to ``build_plan``.

    Steps
    -----
    1. ``project_current()``              — project the live target MetaData.
    2. ``find_head_snapshot(script_dir)`` — the nearest project snapshot at or
       below the head; walks through ``reconcile-baseline`` merges (#1846).
    3. ``guard_whole_schema_revision``    — refuse an empty previous snapshot when
       the database already has project tables (*existing_tables*).
    4. Resolve the ``AppSpec`` for rename hints: use the explicit *appspec* arg
       when given, otherwise **self-load** it from the CWD via
       ``_load_project_appspec_for_hints`` (the env.py path passes no appspec, so
       without this the real ``db revision`` would lose rename resolution and turn
       every rename into drop+add — data loss; #1431 Task 4.3).
    5. ``extract_rename_hints(appspec)``  — extract ``was:`` hints (if resolved).
    6. ``build_plan(prev, curr, hints)``  — pure diff + render.

    Parameters
    ----------
    script_dir:
        An ``alembic.script.ScriptDirectory`` instance (or a compatible mock).
        Passed directly to ``find_head_snapshot``.
    appspec:
        Optional ``AppSpec``.  When supplied, rename hints are extracted from it
        directly (tests + any caller with an AppSpec in hand).  When ``None``,
        the AppSpec is self-loaded from the project in the CWD; if no project is
        present (or it fails to load) rename resolution is skipped and name
        changes become drop+add.
    existing_tables:
        Table names in the target database, or ``None`` when it was not
        inspected (the whole-schema guard is then skipped).
    """
    curr = project_current()
    loc = find_head_snapshot(script_dir)
    prev = loc.snapshot
    guard_whole_schema_revision(prev, curr, existing_tables)
    if appspec is None:
        appspec = _load_project_appspec_for_hints()
    hints = extract_rename_hints(appspec) if appspec is not None else None
    plan = build_plan(prev, curr, hints)
    notes = snapshot_notes(loc)
    return replace(plan, notes=notes) if notes else plan
