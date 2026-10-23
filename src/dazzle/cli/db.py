"""
DAZZLE Database Migration CLI Commands.

Wraps Alembic's programmatic API for managing PostgreSQL schema migrations:
- revision: Generate a new migration from EntitySpec diff
- upgrade:  Apply pending migrations
- downgrade: Rollback migrations
- current:  Show current revision
- history:  Show migration history
- stamp:    Mark a revision as applied without running it
"""

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import typer
from rich.console import Console

from dazzle.cli.dotenv import load_project_dotenv
from dazzle.cli.env import get_active_env
from dazzle.cli.utils import load_project_appspec
from dazzle.core.environment import DAZZLE_ENV_VAR
from dazzle.core.ir import TenancyMode
from dazzle.core.ir.fields import FieldTypeKind
from dazzle.core.ir.fk_graph import FKGraph
from dazzle.db.framework_drift import detect_framework_drift
from dazzle.db.rls_drift import detect_rls_drift
from dazzle.db.schema_snapshot import merge_inherited_snapshot
from dazzle.db.search_apply import apply_search_columns, detect_search_drift
from dazzle.db.tenant_dump import (
    DumpError,
    DumpPosture,
    DumpRefusal,
    default_label,
    read_dump_posture,
    run_dump,
    run_restore_check,
)
from dazzle.http.alembic.tenant_dml import RLS_TRIPWIRE_ATTR
from dazzle.http.converters.entity_converter import convert_entities

if TYPE_CHECKING:
    from dazzle.db.connection import DbTarget

logger = logging.getLogger(__name__)

db_app = typer.Typer(
    help="Database migration commands (Alembic)",
    no_args_is_help=True,
)

console = Console()

#: ``dazzle db upgrade --no-rls-tripwire`` (#1778). Annotated so a direct
#: Python call of ``upgrade_command`` defaults to False, not an OptionInfo.
NoRlsTripwireOption = Annotated[
    bool,
    typer.Option(
        "--no-rls-tripwire",
        help="shared_schema only: do not run the upgrade with row_security = off. "
        "By default unbound DML on an RLS-fenced table errors instead of silently "
        "matching zero rows (#1778).",
    ),
]

#: Shared ``--database-url`` option for every ``dazzle db`` subcommand that
#: targets a database. Precedence (#1775): this flag > ``DATABASE_URL`` env >
#: manifest resolution — never ``.dazzle/runtime.json``.
DatabaseUrlOption = Annotated[
    str,
    typer.Option(
        "--database-url",
        help="Target database URL (overrides DATABASE_URL and dazzle.toml).",
    ),
]


def _get_framework_alembic_dir() -> Path:
    """Locate the framework's alembic directory (env.py, templates, INI)."""
    # Works both in editable installs and pip-installed packages
    try:
        from dazzle import http as dazzle_http

        return (Path(dazzle_http.__file__).resolve().parent / "alembic").resolve()
    except (ImportError, AttributeError):
        # Fallback for dev layout
        return (Path(__file__).resolve().parents[2] / "dazzle" / "http" / "alembic").resolve()


def _get_project_versions_dir() -> Path:
    """Return the project-local migrations directory, creating it if needed."""
    project_root = Path.cwd().resolve()
    versions_dir = project_root / ".dazzle" / "migrations" / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)
    return versions_dir


def _get_alembic_cfg(database_url: str = "") -> Any:
    """Build an Alembic Config with framework env.py + project-local versions.

    The framework's alembic directory provides env.py, migration template,
    and alembic.ini. The version_locations option chains the framework's
    built-in migrations with the project's local migrations directory.
    New revisions are written to the project directory via --version-path.
    """
    from alembic.config import Config as AlembicConfig

    framework_dir = _get_framework_alembic_dir()
    ini_path = framework_dir / "alembic.ini"

    import os

    cfg = AlembicConfig(str(ini_path))
    cfg.set_main_option("script_location", str(framework_dir))

    # Chain framework + project version directories so upgrade/downgrade
    # discovers migrations from both locations. ``path_separator = os`` joins them
    # with ``os.pathsep`` — the non-deprecated splitter (Alembic warns on the legacy
    # space/comma fallback) and robust to a project path that contains a space.
    cfg.set_main_option("path_separator", "os")
    framework_versions = str(framework_dir / "versions")
    project_versions = str(_get_project_versions_dir())
    cfg.set_main_option(
        "version_locations", os.pathsep.join([framework_versions, project_versions])
    )

    # Override sqlalchemy.url from the resolved target (#1775: flag > env > manifest).
    target = _resolve_target(database_url)
    if target.url:
        cfg.set_main_option("sqlalchemy.url", target.url)
    cfg.attributes["dazzle_db_target_source"] = target.source

    return cfg


@db_app.command(name="revision")
def revision_command(
    message: str = typer.Option(
        ...,
        "--message",
        "-m",
        help="Short description of the migration",
    ),
    autogenerate: bool = typer.Option(
        True,
        "--autogenerate/--no-autogenerate",
        help="Auto-detect schema changes from DSL entities",
    ),
) -> None:
    """Generate a new migration revision into the project directory.

    The revision is computed by the #1431 snapshot-diff engine: it diffs the head
    migration's embedded ``SCHEMA_SNAPSHOT`` against the live DSL, the generated
    ``upgrade()``/``downgrade()`` are the engine's rendered ops, and the file
    carries the new state as a module-level ``SCHEMA_SNAPSHOT = <literal>`` constant
    so the *next* revision can diff against it. The engine emits intentful,
    additive ops only — it never produces the destructive whole-schema rewrite that
    metadata-vs-DB diff noise can cause. (For schema the engine can't express —
    triggers, extensions, partial indexes — hand-author the revision with
    ``--no-autogenerate`` and write the ``op.execute(...)`` yourself.)

    The previous snapshot is the nearest one at or below the head: the engine
    walks through ``reconcile-baseline`` merges and hand-authored revisions that
    carry none (#1846). If none is found and the database already has DSL tables,
    the revision is refused (exit 1) rather than re-creating the whole schema.

    **Snapshot embedding seam (Alembic 1.18):** env.py's
    ``_process_revision_directives`` hook replaces the op-trees with the engine's
    ops and stashes the snapshot literal on ``cfg.attributes`` (the documented
    command<->env.py side-channel, already used for ``tenant_schema``). This command
    then *post-writes* ``SCHEMA_SNAPSHOT = <literal>`` into the generated file. We
    chose post-write injection over a custom ``script.py.mako`` placeholder because
    the framework template is shared by tenant migrations (which must not carry the
    constant), and the dual-lineage ``version_path`` plus the separate revision
    ``EnvironmentContext`` make template-arg plumbing the more fragile of the two.

    **Data-migration seam (Task 5.1):** for an *unsafe* schema change — a
    ``NOT NULL`` column add with no server default, or a type change with no safe
    cast — the renderer emits the expand→seam→contract scaffold (add nullable →
    seam → finalize NOT NULL / cast). The seam is carried through the op-tree as a
    placeholder ``op.execute`` marker and post-write-expanded here into a readable
    ``# === DATA MIGRATION (hand-author) ===`` block for the author to fill in (see
    ``_inject_data_seams``).
    """
    from alembic import command

    cfg = _get_alembic_cfg()
    project_versions = str(_get_project_versions_dir())

    # The snapshot-diff engine is the sole generator (env.py's directive hook).
    cfg.attributes["dazzle_use_engine"] = True

    # #1309: alembic refuses to author a revision when multiple heads exist
    # (it can't pick a parent). Give the actionable reconcile guidance instead
    # of the raw "Multiple head revisions" error.
    heads = _get_heads(cfg)
    if len(heads) > 1:
        console.print(
            f"[red]Cannot create a revision: {len(heads)} migration heads are "
            f"present ({', '.join(heads)}).[/red]\n"
            f"[dim]  Run `dazzle db reconcile-baseline` to merge them into a "
            f"single head first (see #1309).[/dim]"
        )
        raise typer.Exit(1)

    try:
        rev = command.revision(
            cfg,
            message=message,
            autogenerate=autogenerate,
            version_path=project_versions,
        )
        # Embed the snapshot literal the hook stashed on cfg.attributes into the
        # generated file (no-op when suppressed / no snapshot).
        _inject_schema_snapshot(rev, cfg.attributes.get("dazzle_schema_snapshot"))
        # Expand the renderer's data-migration seam markers into readable
        # hand-author comment blocks (Task 5.1). No-op when the revision has
        # no unsafe change (no marker present).
        _inject_data_seams(rev)
        # Warn-only internal-consistency check (Task 6.1): verify that the
        # SCHEMA_SNAPSHOT just embedded matches the live DSL projection.
        # Never raises, never blocks the revision.
        _verify_snapshot_consistency(rev, cfg)
        _print_engine_notes(cfg)
        console.print(f"[green]Migration revision created: {message}[/green]")
        console.print(f"[dim]  → {project_versions}/[/dim]")
    except Exception as e:
        console.print(f"[red]Failed to create revision: {e}[/red]")
        raise typer.Exit(1)


def _print_engine_notes(cfg: Any) -> None:
    """Print the engine's snapshot-provenance warnings (#1846); never blocks."""
    for note in (cfg.attributes or {}).get("dazzle_engine_notes") or ():
        console.print(f"[yellow]Note:[/yellow] {note}")


def _target_table_names(cfg: Any) -> list[str] | None:
    """Table names in the target database (``None`` if it can't be inspected).

    Used by ``db migrate --check`` to feed the engine's whole-schema guard
    (#1846); the ``revision``/``migrate`` paths inspect via env.py's connection.
    """
    try:
        from sqlalchemy import create_engine
        from sqlalchemy import inspect as sa_inspect

        url = cfg.get_main_option("sqlalchemy.url")
        if not url:
            return None
        engine = create_engine(url)
        try:
            with engine.connect() as conn:
                schema = cfg.attributes.get("tenant_schema") or None
                return list(sa_inspect(conn).get_table_names(schema=schema))
        finally:
            engine.dispose()
    except Exception:
        logger.debug("could not list target tables", exc_info=True)
        return None


def _verify_snapshot_consistency(rev: Any, cfg: Any) -> None:
    """Warn-only post-generation consistency check (Task 6.1 / #1431).

    After the engine embeds ``SCHEMA_SNAPSHOT`` into a generated revision file,
    this check verifies that the embedded snapshot literal (the engine's intended
    post-state, stashed on ``cfg.attributes['dazzle_schema_snapshot']``) agrees
    with ``project_current()`` — the live DSL-projected schema at the moment the
    revision was generated.

    **What it verifies:**
    The engine's embedded post-state (``SCHEMA_SNAPSHOT``) is consistent with
    the live DSL.  A divergence means either:

    - A concurrent DSL change raced the ``db revision`` invocation (the DSL
      changed between ``generate_revision()`` projecting ``curr`` and this
      check running), OR
    - An engine bug caused ``snapshot_literal`` to encode a different schema
      than what ``project_current()`` currently projects.

    In either case the revision is still written — this is advisory-only.
    The check directs the author to inspect and re-run if needed.

    **Limitations (v1):**
    - Internal consistency only — does NOT compare against the live database.
      A metadata-vs-DB autogenerate compare would need a DB connection and
      is too brittle for a warn-only post-generation gate.
    - The comparison is string-level: the embedded ``snapshot_literal`` is
      parsed back to a dict with ``ast.literal_eval`` (safe — literals only,
      never arbitrary code) and compared with the live projection. If the
      parse fails (malformed literal), the check is skipped with a DEBUG log.
    - ``project_current()`` re-imports the live MetaData from the project in
      the CWD, so it inherits any load failure the engine itself would see.
      Any exception is caught and logged at DEBUG — never re-raised.

    **Always warn-only, never raises, never blocks ``db revision``.**
    """
    # No-op: legacy path / suppressed / empty revision — no snapshot to check.
    snapshot_literal = (cfg.attributes or {}).get("dazzle_schema_snapshot")
    if not snapshot_literal:
        return

    # No-op: Alembic produced no file.
    if rev is None:
        return

    try:
        # Parse the embedded literal back to a dict for comparison.
        # ast.literal_eval is safe: it only evaluates Python literals (dict,
        # str, int, bool, None) — no arbitrary code execution.
        import ast

        from dazzle.db.schema_snapshot import project_current, render_snapshot_literal

        try:
            embedded: dict[str, Any] = ast.literal_eval(snapshot_literal)
        except (ValueError, SyntaxError):
            logger.debug(
                "post-revision consistency check: could not eval snapshot literal — skipping",
                exc_info=True,
            )
            return

        # Project the live schema from the current DSL.
        live = project_current()

        # Normalise both sides through render_snapshot_literal so formatting
        # differences (pprint width, key order) don't produce false positives.
        embedded_norm = render_snapshot_literal(embedded)
        live_norm = render_snapshot_literal(live)

        if embedded_norm != live_norm:
            logger.warning(
                "post-revision snapshot consistency check: the embedded SCHEMA_SNAPSHOT "
                "in the generated revision does not match the current DSL projection. "
                "This may indicate a concurrent DSL change raced `db revision`. "
                "Inspect the revision and re-run if the schema looks wrong. "
                "(revision: %s)",
                getattr(rev, "path", str(rev)),
            )
    except Exception:
        # Swallow all errors — this is advisory only; never block the revision.
        logger.warning(
            "snapshot consistency verification could not run: %s",
            "see exc_info for detail",
            exc_info=True,
        )


def _inject_schema_snapshot(rev: Any, snapshot_literal: str | None) -> None:
    """Post-write the ``SCHEMA_SNAPSHOT = <literal>`` constant into a revision file.

    The #1431 engine stashes the current snapshot literal on
    ``cfg.attributes['dazzle_schema_snapshot']`` from within env.py's directive
    hook; this writes it as a module-level constant so the *next* engine revision
    can diff against it (``schema_snapshot.load_head_snapshot``). No-op when there
    is no snapshot (empty/suppressed revision, or the legacy autogenerate path),
    or when no revision file was produced.

    The constant is appended after the existing module body so it sits alongside
    the alembic ``revision``/``down_revision`` identifiers and is importable via
    ``Script.module`` (how ``load_head_snapshot`` reads it back).
    """
    if not snapshot_literal:
        return
    # command.revision can return Script | list[Script | None]; take the first.
    if isinstance(rev, list):
        rev = rev[0] if rev else None
    if rev is None:
        return
    path = Path(rev.path)
    if not path.exists():
        return

    text = path.read_text(encoding="utf-8")
    if "SCHEMA_SNAPSHOT" in text:
        return  # idempotent — never double-write

    block = (
        "\n\n# DSL-snapshot embedded by the #1431 migration engine. The next "
        "`dazzle db revision`\n# diffs the live DSL against this to compute the "
        "delta. Do not edit by hand.\n"
        f"SCHEMA_SNAPSHOT = {snapshot_literal}\n"
    )
    path.write_text(text + block, encoding="utf-8")


#: The hand-author block ``_inject_data_seams`` writes in place of each seam
#: marker (one entry per line, indentation added by the caller). #1778: DML here
#: runs under RLS with no tenant bound — on a fenced table it silently matches
#: zero rows, and under ``dazzle db upgrade``'s tripwire it raises.
_DATA_SEAM_LINES: tuple[str, ...] = (
    "# === DATA MIGRATION (hand-author) ===",
    "# Backfill / transform existing rows here BEFORE the column is",
    "# finalized NOT NULL or the type cast runs. Replace the example.",
    "#",
    "# shared_schema tenancy: this DML runs with RLS enforced and NO tenant",
    "# bound. On a fenced table a bare op.execute() matches zero rows (no",
    "# error), and `dazzle db upgrade` makes it raise. Run it per tenant:",
    "#   from dazzle.http.alembic.tenant_dml import for_each_tenant",
    '#   for_each_tenant("INSERT INTO my_table (tenant_id, ...) SELECT tenant_id, ... FROM src")',
    "# Other tenancy modes / unfenced tables:",
    '# op.execute("UPDATE my_table SET my_col = ... WHERE my_col IS NULL")',
    "# === END DATA MIGRATION ===",
)


def _inject_data_seams(rev: Any) -> None:
    """Expand the renderer's seam markers into hand-author comment blocks (Task 5.1).

    For an unsafe schema change (a ``NOT NULL`` add with no default, or a type
    change with no safe cast), ``schema_render`` emits the expand/contract scaffold
    with a placeholder ``ExecuteSQLOp`` carrying ``schema_render.SEAM_MARKER``.
    Alembic renders that as a single ``op.execute('<SEAM_MARKER>')`` line in the
    generated ``upgrade()`` body. This post-write step replaces each such line with
    a readable, clearly-marked block the author fills in (``_DATA_SEAM_LINES``).
    Under ``shared_schema`` tenancy the block steers the author to
    ``for_each_tenant`` (#1778): seam DML runs with RLS enforced and no tenant
    bound, so a bare ``op.execute`` on a fenced table matches zero rows.

    Post-write injection (mirroring ``_inject_schema_snapshot``) is the chosen seam
    mechanism: it keeps ``schema_render`` a pure op-tree transform (unit-testable on
    the op stream) while landing the comment block verbatim — a comment block is not
    an Alembic op, so it cannot be carried through ``render_python_code`` directly.
    The matched line's leading indentation is preserved so the block sits correctly
    inside ``upgrade()``. No-op when no marker is present (the safe-change case).
    """
    from dazzle.db.schema_render import SEAM_MARKER

    if isinstance(rev, list):
        rev = rev[0] if rev else None
    if rev is None:
        return
    path = Path(rev.path)
    if not path.exists():
        return

    text = path.read_text(encoding="utf-8")
    if SEAM_MARKER not in text:
        return

    out_lines: list[str] = []
    for line in text.splitlines(keepends=False):
        if SEAM_MARKER in line:
            indent = line[: len(line) - len(line.lstrip())]
            out_lines.extend(f"{indent}{seam_line}" for seam_line in _DATA_SEAM_LINES)
        else:
            out_lines.append(line)
    path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")


#: #1282: Alembic ships `alembic_version.version_num` as `VARCHAR(32)`.
#: The 0019 baseline widens it to `VARCHAR(128)`. The pre-upgrade guard
#: below uses this cap to fail fast on revision ids that would exceed
#: the column width — otherwise the DDL applies and the trailing
#: `UPDATE alembic_version` truncates, leaving schema-vs-version-state
#: divergent. (Previously synced with `0004_widen_alembic_version_num.py`,
#: now folded into the 0019 baseline.)
ALEMBIC_VERSION_NUM_MAX_LEN = 128


def _validate_revision_widths(cfg: object, target: str) -> None:
    """Refuse the upgrade if any pending revision id would overflow the
    `alembic_version.version_num` column (#1282).

    Alembic's own `ScriptDirectory.walk_revisions()` enumerates the
    revision chain; we walk every pending revision (from current head
    to target) and reject the run upfront when any id is wider than the
    column. Without this, the DDL would land but the version-bump
    `UPDATE` would silently fail mid-chain.
    """
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(cfg)  # type: ignore[arg-type]
    too_long: list[tuple[str, int]] = []
    for rev in script.walk_revisions():
        if len(rev.revision) > ALEMBIC_VERSION_NUM_MAX_LEN:
            too_long.append((rev.revision, len(rev.revision)))
    if too_long:
        offenders = "\n".join(f"  - {rid!r} ({n} chars)" for rid, n in too_long)
        raise RuntimeError(
            f"Refusing to upgrade: {len(too_long)} revision id(s) exceed "
            f"the {ALEMBIC_VERSION_NUM_MAX_LEN}-char width of "
            f"alembic_version.version_num.\n"
            f"Affected:\n{offenders}\n"
            f'Rename the file + the `revision = "..."` variable inside it '
            f"to a shorter id, then re-run `dazzle db upgrade`. See #1282."
        )


#: The framework's baseline migration root (#1309). A project whose own first
#: migration predates the framework shipping baselines has `down_revision=None`
#: — a parallel root to this one — so chaining both version dirs yields two
#: heads. Used to give a precise "parallel baseline roots" diagnosis.
_FRAMEWORK_BASELINE_ROOT = "0019_process_runtime_tables"


def _get_heads(cfg: object) -> list[str]:
    """Return the current head revision ids across the chained version dirs."""
    from alembic.script import ScriptDirectory

    return list(ScriptDirectory.from_config(cfg).get_heads())  # type: ignore[arg-type]


def _guard_single_head(cfg: object, target: str) -> str:
    """Refuse an ambiguous ``upgrade head`` when multiple heads exist (#1309).

    Shipping the framework baseline migrations (v0.80.59, #1308) added a second
    alembic head for projects whose own baseline is a parallel root — so
    ``upgrade head`` fails with alembic's raw "Multiple head revisions" error
    and the Heroku release phase breaks. Intercept it here with actionable
    guidance: run ``dazzle db reconcile-baseline`` (generates a project-side
    merge migration → single head). Only guards the literal ``head`` target;
    an explicit ``heads`` or a specific revision is left untouched.

    #1689: after a project has already merged the framework chain, a new
    framework file (0021 off 0020) re-forks a head whose *parent* is in the
    project merge ancestry. That is not a parallel-root problem — apply
    ``heads`` so the increment lands without another merge file.
    """
    if target != "head":
        return target
    heads = _get_heads(cfg)
    if len(heads) <= 1:
        return target
    if _framework_increment_parent_already_merged(cfg, heads):
        console.print(
            "[dim]#1689: extra framework head's parent is already in the project "
            "merge; applying `heads` (no new merge file).[/dim]"
        )
        return "heads"
    has_framework_root = _FRAMEWORK_BASELINE_ROOT in heads or any(
        _revision_traces_to_framework_root(cfg, h) for h in heads
    )
    detail = (
        "parallel baseline roots (framework + project)" if has_framework_root else "multiple heads"
    )
    raise RuntimeError(
        f"Refusing to `upgrade head`: {len(heads)} {detail} are present "
        f"({', '.join(heads)}).\n"
        f"Run `dazzle db reconcile-baseline` to generate a merge migration "
        f"that unifies them into a single head, commit it, then re-run "
        f"`dazzle db upgrade head`. See #1309."
    )


def _down_revisions(script: Any, rev_id: str) -> tuple[str, ...]:
    """Parent revision ids of *rev_id* (empty for a root)."""
    rev = script.get_revision(rev_id)
    down = getattr(rev, "down_revision", None)
    if down is None:
        return ()
    if isinstance(down, (tuple, list)):
        return tuple(str(x) for x in down if x)
    return (str(down),)


def _ancestry_ids(script: Any, head: str) -> set[str]:
    from alembic.util.exc import CommandError

    ids: set[str] = set()
    try:
        for rev in script.iterate_revisions(head, "base"):
            ids.add(rev.revision)
    except CommandError:
        logger.warning("Could not walk ancestry for %s", head, exc_info=True)
    return ids


def _framework_increment_parent_already_merged(cfg: object, heads: list[str]) -> bool:
    """True when the extra head is a framework increment off an already-merged parent (#1689).

    Both heads often trace to ``0019`` (the project merge already includes
    ``0020``). Identify the increment as the single-parent framework rev
    whose parent sits in the other head's ancestry.
    """
    if len(heads) != 2:
        return False
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(cfg)  # type: ignore[arg-type]
    a, b = heads[0], heads[1]
    for extra, base in ((a, b), (b, a)):
        parents = _down_revisions(script, extra)
        if len(parents) != 1:
            continue
        if not _revision_traces_to_framework_root(cfg, extra):
            continue
        if parents[0] in _ancestry_ids(script, base):
            return True
    return False


def _revision_traces_to_framework_root(cfg: object, head: str) -> bool:
    """True if *head*'s ancestry includes the framework baseline root."""
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(cfg)  # type: ignore[arg-type]
    try:
        for rev in script.iterate_revisions(head, "base"):
            if rev.revision == _FRAMEWORK_BASELINE_ROOT:
                return True
    except Exception:
        logger.debug("Could not trace ancestry for head %s", head, exc_info=True)
    return False


def _redact_url(url: str) -> str:
    """Mask any password in a DB URL for safe display (`user:***@host/db`)."""
    import re

    return re.sub(r"(://[^:/@]+:)[^@/]+@", r"\1***@", url)


def _safe_current_revision(cfg: Any) -> str | None:
    """Read the applied revision from ``alembic_version`` (None if unstamped).

    Best-effort: any failure returns ``None`` so reporting never breaks the
    upgrade itself (the upgrade is the source of truth; this is for display).
    """
    try:
        from alembic.runtime.migration import MigrationContext
        from sqlalchemy import create_engine

        url = cfg.get_main_option("sqlalchemy.url")
        if not url:
            return None
        engine = create_engine(url)
        try:
            with engine.connect() as conn:
                return MigrationContext.configure(conn).get_current_revision()
        finally:
            engine.dispose()
    except Exception:
        # Display-only introspection — never let it break the upgrade report.
        logger.debug("Could not read current alembic revision", exc_info=True)
        return None


def _schema_is_materialized(cfg: Any) -> bool:
    """True if the framework baseline table already exists (#1390).

    Signals the "schema materialized but ``alembic_version`` empty" state: the app
    booted (the runtime's ``ensure_dazzle_params_table()`` + DSL-derived tables
    ran) but alembic was never stamped. ``_dazzle_params`` is created by both the
    runtime bootstrap and the ``0019_process_runtime_tables`` baseline migration,
    so its presence means the framework baseline is already on disk. A genuinely
    fresh DB returns False, so the normal baseline chain still runs there.
    """
    try:
        from sqlalchemy import create_engine
        from sqlalchemy import inspect as sa_inspect

        url = cfg.get_main_option("sqlalchemy.url")
        if not url:
            return False
        engine = create_engine(url)
        try:
            with engine.connect() as conn:
                return bool(sa_inspect(conn).has_table("_dazzle_params"))
        finally:
            engine.dispose()
    except Exception:
        logger.debug("Materialization probe failed", exc_info=True)
        return False


def _alembic_version_is_empty(cfg: Any) -> bool:
    """True if ``alembic_version`` is absent or carries no rows (unstamped).

    Row-count based (not ``get_current_revision``) so it stays correct when the
    project has multiple alembic heads — ``get_current_revision`` raises on
    multiple rows, which would otherwise read as "unstamped" and re-stamp (#1390).
    """
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy import inspect as sa_inspect

        url = cfg.get_main_option("sqlalchemy.url")
        if not url:
            return True
        engine = create_engine(url)
        try:
            with engine.connect() as conn:
                if not sa_inspect(conn).has_table("alembic_version"):
                    return True
                count = conn.execute(text("SELECT count(*) FROM alembic_version")).scalar()
                return (count or 0) == 0
        finally:
            engine.dispose()
    except Exception:
        logger.debug("alembic_version emptiness probe failed", exc_info=True)
        return False  # fail safe: don't auto-stamp when the probe is uncertain


def _autostamp_if_materialized(cfg: Any) -> bool:
    """Reconcile an empty ``alembic_version`` against an already-materialized schema.

    When alembic is unstamped (``alembic_version`` empty — the state Dazzle's
    dual-ledger setup produces) but the schema is already on disk, ``alembic``
    would otherwise replay the baseline chain (CREATE TABLE on existing tables)
    and refuse a simple additive diff (#1390). Stamping to ``heads`` aligns
    alembic's metadata with reality so the subsequent autogenerate produces only
    the additive ``ADD COLUMN`` diff. Guarded behind the materialization probe so
    a genuinely fresh DB is untouched. Returns True if it stamped.
    """
    from alembic import command

    if not _alembic_version_is_empty(cfg):
        return False  # already stamped — normal alembic flow, nothing to reconcile
    if not _schema_is_materialized(cfg):
        return False  # genuinely fresh DB — let the baseline chain create everything
    command.stamp(cfg, "heads")
    console.print(
        "[dim]alembic_version was empty but the schema is already materialized — "
        "stamped to heads so only the additive diff is applied (#1390).[/dim]"
    )
    return True


@db_app.command(name="upgrade")
def upgrade_command(
    revision: str = typer.Argument(
        "head",
        help="Target revision (default: head)",
    ),
    no_rls: bool = typer.Option(
        False,
        "--no-rls",
        help="Skip applying RLS policies after the upgrade (apply them separately "
        "with `dazzle db apply-rls`).",
    ),
    database_url: DatabaseUrlOption = "",
    no_rls_tripwire: NoRlsTripwireOption = False,
    no_search: bool = typer.Option(
        False,
        "--no-search",
        help="Skip reconciling the DSL `search:` columns after the upgrade (apply "
        "them separately with `dazzle db apply-search`).",
    ),
) -> None:
    """Apply pending migrations (upgrade to target revision).

    After the migrations, the DSL's ``search:`` columns (generated
    ``search_vector`` + GIN index) are reconciled (#1850): added when missing,
    rebuilt when the field list changed. Pass ``--no-search`` to skip and run
    ``dazzle db apply-search`` separately.

    In ``shared_schema`` tenancy mode, RLS policies are applied automatically
    after the migrations succeed — as the SAME owner-capable role that just ran
    the DDL migrations (so it has the table ownership ``CREATE POLICY`` /
    ``FORCE ROW LEVEL SECURITY`` require). Pass ``--no-rls`` to skip and apply
    them separately with ``dazzle db apply-rls``.

    In ``shared_schema`` mode the upgrade transaction also runs with
    ``row_security = off`` (#1778): DML on a fenced table with no tenant bound
    raises instead of silently matching zero rows. Seam DML goes through
    ``dazzle.http.alembic.tenant_dml.for_each_tenant``. ``--no-rls-tripwire``
    turns this off.
    """
    from alembic import command

    cfg = _get_alembic_cfg(database_url)
    project_root = Path.cwd().resolve()
    appspec = _load_upgrade_appspec(project_root)
    shared_schema = appspec is not None and _is_shared_schema(appspec)
    if shared_schema and not no_rls_tripwire:
        cfg.attributes[RLS_TRIPWIRE_ATTR] = True
    # #1308/#1775: surface the target DB *and which source won* so a misresolved
    # connection (the bug that made `upgrade` silently hit the wrong database)
    # is immediately visible.
    target = cfg.get_main_option("sqlalchemy.url") or ""
    source = cfg.attributes.get("dazzle_db_target_source", "")
    console.print(f"[dim]Target database: {_redact_url(target)} (from {source})[/dim]")

    try:
        revision = _guard_single_head(cfg, revision) or revision
        _validate_revision_widths(cfg, revision)
        before = _safe_current_revision(cfg)
        command.upgrade(cfg, revision)
        after = _safe_current_revision(cfg)
        # #1308: report the actual transition, not a blind "Upgraded to: head".
        # A no-op (before == after) is now stated honestly rather than
        # masquerading as success — the exact trap the issue flagged.
        if before == after:
            console.print(
                f"[yellow]Already at {after or '(base)'} — no pending migrations "
                f"to apply (database unchanged).[/yellow]"
            )
        else:
            console.print(f"[green]Upgraded: {before or '(base)'} → {after or '(base)'}[/green]")
    except Exception as e:
        console.print(f"[red]Upgrade failed: {e}[/red]")
        raise typer.Exit(1)

    # #1850: the DSL-derived search columns are not in any migration (their
    # expression comes from the DSL); production runs no boot DDL, so they are
    # reconciled here, on the same owner-capable role, like RLS below.
    if appspec is not None and not no_search:
        _apply_search_after_upgrade(target, appspec, project_root)

    # Phase D: apply RLS policies after a successful migration, in shared_schema
    # mode, on the SAME owner-capable role that just ran the DDL migrations
    # (CREATE POLICY / FORCE ROW LEVEL SECURITY need table ownership; the runtime
    # dazzle_app role cannot). If this raises, the schema is already migrated, so
    # do NOT silently leave RLS unapplied — log ERROR + re-raise.
    if no_rls or not shared_schema:
        return
    _apply_rls_after_upgrade(target, appspec, project_root)


def _load_upgrade_appspec(project_root: Path) -> Any | None:
    """The project's appspec for ``dazzle db upgrade``, or None outside a project.

    Migrations may be a valid standalone operation (no loadable appspec), in
    which case neither the RLS tripwire nor the post-upgrade apply runs.
    """
    try:
        return load_project_appspec(project_root)
    except Exception:
        logger.debug("Could not load appspec for dazzle db upgrade", exc_info=True)
        return None


def _print_search_actions(actions: list[Any]) -> None:
    """Report applied search actions and the entity tables that do not exist yet."""
    applied = [a for a in actions if a.statements]
    missing = [a.table for a in actions if a.action == "table_missing"]
    if applied:
        summary = ", ".join(f"{a.table}: {a.action}" for a in applied)
        console.print(f"[green]Search columns reconciled ({summary}).[/green]")
    if missing:
        console.print(
            f"[yellow]Search columns skipped — table(s) not created yet: "
            f"{', '.join(missing)}. Run the migrations, then `dazzle db apply-search`.[/yellow]"
        )


def _apply_search_after_upgrade(resolved_url: str, appspec: Any, project_root: Path) -> None:
    """Reconcile the ``search:`` columns after a successful ``dazzle db upgrade`` (#1850).

    A no-op (no connection) when the appspec declares no ``search:`` block and so
    has nothing to add; stale columns from a removed block are then left for
    ``dazzle db apply-search``. Re-raises on failure (ERROR logged).
    """
    if not list(getattr(appspec, "searches", []) or []):
        return
    entities = convert_entities(appspec.domain.entities)

    async def _run(conn: Any) -> Any:
        return await apply_search_columns(conn, appspec, entities)

    try:
        actions = asyncio.run(_run_with_connection(project_root, resolved_url, _run))
    except Exception as e:
        logger.error("Failed to apply search columns after upgrade: %s", e, exc_info=True)
        console.print(
            f"[red]Migration succeeded but applying the search columns failed: {e}[/red]\n"
            "[dim]Re-run `dazzle db apply-search` as the table owner once resolved.[/dim]"
        )
        raise typer.Exit(1)
    _print_search_actions(actions)


def _apply_rls_after_upgrade(resolved_url: str, appspec: Any, project_root: Path) -> None:
    """Apply RLS policies after a successful ``dazzle db upgrade`` (Phase D).

    Called only for ``shared_schema`` apps. Runs on a fresh connection resolved
    from the SAME URL the migrations used — the owner-capable deploy role — so it
    has the table ownership the RLS DDL requires. Re-raises on failure (ERROR
    logged) so a successful migration is never silently left without RLS.
    """

    from dazzle.db.rls_apply import apply_rls_policies

    entities = convert_entities(appspec.domain.entities)

    async def _run(conn: Any) -> Any:
        return await apply_rls_policies(conn, appspec, entities)

    try:
        applied = asyncio.run(_run_with_connection(project_root, resolved_url, _run))
    except Exception as e:
        logger.error("Failed to apply RLS policies after upgrade: %s", e, exc_info=True)
        console.print(
            f"[red]Migration succeeded but applying RLS policies failed: {e}[/red]\n"
            "[dim]The schema is migrated but RLS is NOT enforced. Re-run "
            "`dazzle db apply-rls` as the table owner once resolved.[/dim]"
        )
        raise typer.Exit(1)

    console.print(
        f"[green]Applied {applied} RLS policy statement{'' if applied == 1 else 's'} "
        f"(owner role).[/green]"
    )


@db_app.command(name="reconcile-baseline")
def reconcile_baseline_command() -> None:
    """Merge parallel migration heads into one (#1309).

    Shipping the framework baseline migrations (v0.80.59) added a second alembic
    head for any project whose own first migration predates them (a parallel
    root, ``down_revision = None``). That makes ``dazzle db upgrade head`` and
    ``dazzle db revision`` fail with "Multiple head revisions".

    This generates a project-side **merge migration** whose ``down_revision`` is
    the tuple of all current heads — the canonical alembic answer — collapsing
    the trees back to a single head so every db command works again. The merge
    file is written to the project's ``.dazzle/migrations/versions`` dir (NOT
    the read-only framework dir in the wheel); commit it, then run
    ``dazzle db upgrade head``. (With ``0001`` now idempotent, applying the
    framework chain to an already-populated DB is safe: ``0001`` skips,
    ``0002`` no-ops, ``0003`` replaces a function, ``0004`` widens a column.)
    """
    from alembic.script import ScriptDirectory
    from alembic.util import rev_id as _new_rev_id

    cfg = _get_alembic_cfg()
    script = ScriptDirectory.from_config(cfg)
    heads = list(script.get_heads())

    if len(heads) <= 1:
        console.print(
            f"[green]Single head ({heads[0] if heads else 'none'}) — nothing to reconcile.[/green]"
        )
        return

    inherited, why_not = merge_inherited_snapshot(script, heads)

    project_versions = str(_get_project_versions_dir())
    new_rev = _new_rev_id()
    try:
        merge = script.generate_revision(
            new_rev,
            message="merge framework + project baselines (#1309)",
            head=tuple(heads),  # tuple of heads → a merge revision
            version_path=project_versions,
        )
    except Exception as e:
        console.print(f"[red]Reconcile failed: {e}[/red]")
        raise typer.Exit(1)

    console.print(f"[green]Merge migration created: {new_rev}[/green] — heads unified")
    console.print(f"[dim]  Merged heads: {', '.join(heads)}[/dim]")
    if inherited is not None:
        # #1846: a merge changes no schema, so its post-state is its project
        # parent's snapshot. Embedding it makes the merge self-describing for
        # the next `db revision` (which also walks through snapshot-less merges).
        _inject_schema_snapshot(merge, inherited)
        console.print("[dim]  Embedded the project lineage's SCHEMA_SNAPSHOT (#1846).[/dim]")
    elif why_not:
        console.print(f"[yellow]Note:[/yellow] no SCHEMA_SNAPSHOT embedded: {why_not}")
    console.print(f"[dim]  → {project_versions}/[/dim]")
    console.print("[dim]  Commit the merge file, then run `dazzle db upgrade head`.[/dim]")


@db_app.command(name="snapshot-baseline")
def snapshot_baseline_command() -> None:
    """Stamp the current DSL projection as the head migration's baseline snapshot.

    Use this once when adopting the #1431 migration engine on a project whose
    HEAD migration pre-dates ``SCHEMA_SNAPSHOT``.  Without this step
    ``load_head_snapshot`` returns ``{}`` and the next ``dazzle db revision``
    diffs against an empty baseline — re-creating every table, which fails on
    an existing database.

    This command writes a single empty-upgrade revision (``def upgrade(): pass``
    / ``def downgrade(): pass``) that carries only ``SCHEMA_SNAPSHOT = <current
    DSL projection>`` as a module-level constant.  After applying it, the next
    real ``dazzle db revision`` diffs the live DSL against this snapshot and
    emits only the intentful additive delta.

    Typical adoption workflow::

        dazzle db snapshot-baseline       # write the baseline stamp revision
        dazzle db upgrade                 # apply it (no-op upgrade)
        dazzle db revision -m "add field" # subsequent revisions diff correctly

    The revision is written to the project's ``.dazzle/migrations/versions/``
    directory. Commit it alongside your other migrations.
    """
    from alembic import command
    from alembic.script import ScriptDirectory

    from dazzle.db.schema_snapshot import (
        find_head_snapshot,
        project_current,
        render_snapshot_literal,
    )

    cfg = _get_alembic_cfg()
    project_versions = str(_get_project_versions_dir())

    # Guard: single head required (same as revision_command).
    heads = _get_heads(cfg)
    if len(heads) > 1:
        console.print(
            f"[red]Cannot create a snapshot-baseline: {len(heads)} migration heads are "
            f"present ({', '.join(heads)}).[/red]\n"
            f"[dim]  Run `dazzle db reconcile-baseline` to merge them into a "
            f"single head first (see #1309).[/dim]"
        )
        raise typer.Exit(1)

    # Guard: idempotency — if the head's snapshot is current (on the head itself,
    # or reached only through snapshot-less merges), there is nothing to do.
    # Running snapshot-baseline twice (or on a project whose head was generated by
    # the engine) would write a redundant empty revision. A snapshot found only
    # below hand-authored, snapshot-less revisions is stale (#1846): re-stamp.
    script_dir = ScriptDirectory.from_config(cfg)
    existing = find_head_snapshot(script_dir)
    if existing.snapshot and not existing.unsnapshotted and not existing.ambiguous:
        console.print(
            "[yellow]Head already carries SCHEMA_SNAPSHOT — nothing to do; "
            "snapshot-baseline is for adopting the engine on a project whose "
            "head predates it.[/yellow]"
        )
        return

    # Project the current DSL snapshot upfront so we can report it and inject it.
    try:
        curr = project_current()
        snapshot_literal = render_snapshot_literal(curr)
    except Exception as e:
        console.print(f"[red]Failed to project current DSL schema: {e}[/red]")
        raise typer.Exit(1)

    # Write an empty (no-autogenerate) revision — the _process_revision_directives
    # hook is NOT triggered here (autogenerate=False), so the suppress-empty path
    # never fires and we always get a revision file regardless of delta.
    try:
        rev = command.revision(
            cfg,
            message="snapshot-baseline: stamp current DSL as engine baseline (#1431)",
            autogenerate=False,
            version_path=project_versions,
        )
    except Exception as e:
        console.print(f"[red]Failed to create snapshot-baseline revision: {e}[/red]")
        raise typer.Exit(1)

    # Post-write the SCHEMA_SNAPSHOT constant into the generated file (same
    # injection path as revision_command / _inject_schema_snapshot).
    _inject_schema_snapshot(rev, snapshot_literal)

    table_count = len(curr)
    console.print(
        f"[green]Snapshot-baseline revision created: {table_count} table(s) stamped.[/green]"
    )
    console.print(f"[dim]  → {project_versions}/[/dim]")
    console.print(
        "[dim]  Run `dazzle db upgrade` to apply, then subsequent "
        "`dazzle db revision` invocations will diff from this baseline.[/dim]"
    )


@db_app.command(name="reframework-baseline")
def reframework_baseline_command(
    database_url: str = typer.Option(
        "",
        "--database-url",
        help="Admin Postgres URL for scratch-DB creation (default: DATABASE_URL env var).",
    ),
) -> None:
    """Regenerate the committed framework schema snapshot deterministically.

    Builds a temporary scratch Postgres database via ``ensure_framework_schema``,
    introspects the in-scope tables, and rewrites the
    ``FRAMEWORK_SCHEMA_SNAPSHOT = {...}`` block in
    ``src/dazzle/http/runtime/framework_schema_snapshot.py`` in place.

    **What this command regenerates (only):**
    The committed *snapshot* literal (``FRAMEWORK_SCHEMA_SNAPSHOT``).  The
    baseline migration file (``0019_process_runtime_tables.py``) calls the
    shared DDL core directly and does NOT contain generated SQL — so there is no
    generated baseline DDL to regenerate.

    **Agent workflow (ADR-0044 §7):**
    Change the orchestrator (``ensure_framework_schema``) → run
    ``dazzle db reframework-baseline`` → the three-way parity gate
    (``tests/integration/test_framework_baseline_parity_pg.py``) proves equality.

    **Round-trip property (byte-idempotent):** regenerating against an unchanged
    orchestrator produces a byte-identical snapshot — ``git diff`` is empty.
    This holds because the command applies ``ruff format`` to the rewritten file
    as its final step, matching the project's pre-commit formatter.  Running the
    command twice with no schema change leaves the file unchanged.

    Requires an admin Postgres URL to CREATE and DROP a scratch database.
    Pass ``--database-url`` or set ``DATABASE_URL``/``TEST_DATABASE_URL``.
    """
    import os
    import subprocess
    import uuid

    import psycopg
    import sqlalchemy as sa

    from dazzle.db.schema_snapshot import introspect_schema, render_snapshot_literal
    from dazzle.http.runtime.framework_schema import ensure_framework_schema
    from dazzle.http.runtime.framework_schema_snapshot import IN_SCOPE_TABLES

    # Resolve admin URL — prefer explicit flag, then env vars.
    admin_plain = (
        database_url.strip()
        or os.environ.get("DATABASE_URL", "").strip()
        or os.environ.get("TEST_DATABASE_URL", "").strip()
    )
    if not admin_plain:
        console.print(
            "[red]No database URL available.[/red]\n"
            "[dim]  Pass --database-url or set DATABASE_URL / TEST_DATABASE_URL.[/dim]"
        )
        raise typer.Exit(1)

    # Normalise to a plain psycopg URL (strip +psycopg dialect prefix if present).
    admin_url = admin_plain.replace("postgresql+psycopg://", "postgresql://")

    # Locate the snapshot module file.
    import dazzle.http.runtime.framework_schema_snapshot as _snap_mod

    snap_path = Path(_snap_mod.__file__).resolve()

    name = f"dazzle_refw_{uuid.uuid4().hex[:8]}"
    base, _, _ = admin_url.rpartition("/")
    scratch_url = f"{base}/{name}"
    sa_scratch = scratch_url.replace("postgresql://", "postgresql+psycopg://", 1)

    console.print(f"[dim]Creating scratch database: {name}[/dim]")
    with psycopg.connect(admin_url, autocommit=True) as a:
        a.execute(f'CREATE DATABASE "{name}"')  # nosemgrep

    try:
        # Build the schema via the orchestrator.
        console.print("[dim]Running ensure_framework_schema …[/dim]")
        with psycopg.connect(scratch_url) as conn:
            conn.autocommit = False
            ensure_framework_schema(conn)

        # Introspect the in-scope tables.
        console.print("[dim]Introspecting schema …[/dim]")
        eng = sa.create_engine(sa_scratch)
        try:
            snap = introspect_schema(eng, only=set(IN_SCOPE_TABLES))
        finally:
            eng.dispose()
    finally:
        console.print(f"[dim]Dropping scratch database: {name}[/dim]")
        with psycopg.connect(admin_url, autocommit=True) as a:
            a.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname=%s AND pid<>pg_backend_pid()",
                (name,),
            )
            a.execute(f'DROP DATABASE IF EXISTS "{name}"')  # nosemgrep

    # Render the new snapshot literal.
    new_literal = render_snapshot_literal(snap)

    # Rewrite FRAMEWORK_SCHEMA_SNAPSHOT = {...} in the snapshot module in place.
    #
    # Strategy: split on the exact assignment prefix, then find the end of the
    # dict literal by scanning forward for the first "\n\n" or "\n\n\n" that
    # follows the opening brace — this is format-agnostic (works for both the
    # original human-readable multi-line style and pprint's compact style).
    original = snap_path.read_text()

    _MARKER = "FRAMEWORK_SCHEMA_SNAPSHOT = "
    marker_idx = original.find(_MARKER)
    if marker_idx == -1:
        console.print(
            f"[red]Could not locate FRAMEWORK_SCHEMA_SNAPSHOT assignment in {snap_path}.[/red]\n"
            "[dim]  The file may have been reformatted — inspect manually.[/dim]"
        )
        raise typer.Exit(1)

    # Everything before the marker stays unchanged.
    prefix = original[: marker_idx + len(_MARKER)]

    # The rest is the dict literal followed by the rest of the module.
    after_marker = original[marker_idx + len(_MARKER) :]

    # Find the end of the dict literal: look for the first double-newline after
    # the opening brace.  This handles both multi-line (ends with "\n}\n\n")
    # and compact pprint (ends with "}}\n\n") formats.
    sep_idx = after_marker.find("\n\n")
    if sep_idx == -1:
        console.print(
            f"[red]Could not find end of FRAMEWORK_SCHEMA_SNAPSHOT dict in {snap_path}.[/red]\n"
            "[dim]  The file format is unexpected — inspect manually.[/dim]"
        )
        raise typer.Exit(1)

    # suffix = everything from the double-newline onward (module remainder).
    suffix = after_marker[sep_idx:]

    updated = prefix + new_literal + suffix

    # Write unconditionally, then apply ruff format so the on-disk form matches
    # the project's pre-commit formatter.  The byte-idempotency check runs AFTER
    # formatting so "already up to date" is truthful: it reflects the normalised
    # ruff-formatted output, not the raw pprint output.
    snap_path.write_text(updated)
    try:
        subprocess.run(
            ["uv", "run", "ruff", "format", str(snap_path)],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        console.print(
            f"[yellow]Warning: ruff format failed on {snap_path.name} "
            f"(exit {exc.returncode}); snapshot written but may not be "
            "byte-identical to the committed form.[/yellow]"
        )

    formatted = snap_path.read_text()
    if formatted == original:
        console.print(
            "[green]FRAMEWORK_SCHEMA_SNAPSHOT is already up to date — no changes written.[/green]\n"
            "[dim]  (byte-idempotent: regenerating against unchanged orchestrator "
            "produces identical ruff-formatted snapshot)[/dim]"
        )
        return

    table_count = len(snap)
    console.print(
        f"[green]FRAMEWORK_SCHEMA_SNAPSHOT regenerated: {table_count} table(s).[/green]\n"
        f"[dim]  → {snap_path}[/dim]\n"
        "[dim]  Run `pytest tests/integration/test_framework_baseline_parity_pg.py` "
        "to verify three-way parity.[/dim]"
    )


@db_app.command(name="downgrade")
def downgrade_command(
    revision: str = typer.Argument(
        "-1",
        help="Target revision (default: -1 for one step back)",
    ),
    database_url: DatabaseUrlOption = "",
) -> None:
    """Rollback migrations (downgrade to target revision)."""
    _downgrade(revision, database_url, done="Downgraded to", failed="Downgrade failed")


def _downgrade(revision: str, database_url: str, *, done: str, failed: str) -> None:
    """Shared body of ``db downgrade`` / ``db rollback``."""
    from alembic import command

    cfg = _get_alembic_cfg(database_url)

    try:
        command.downgrade(cfg, revision)
        console.print(f"[green]{done}: {revision}[/green]")
    except Exception as e:
        console.print(f"[red]{failed}: {e}[/red]")
        raise typer.Exit(1)


@db_app.command(name="current")
def current_command(database_url: DatabaseUrlOption = "") -> None:
    """Show the current migration revision."""
    from alembic import command

    cfg = _get_alembic_cfg(database_url)

    try:
        command.current(cfg, verbose=True)
    except Exception as e:
        console.print(f"[red]Failed to get current revision: {e}[/red]")
        raise typer.Exit(1)


@db_app.command(name="history")
def history_command(
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed history",
    ),
    database_url: DatabaseUrlOption = "",
) -> None:
    """Show migration history."""
    from alembic import command

    cfg = _get_alembic_cfg(database_url)

    try:
        command.history(cfg, verbose=verbose)
    except Exception as e:
        console.print(f"[red]Failed to get history: {e}[/red]")
        raise typer.Exit(1)


@db_app.command(name="stamp")
def stamp_command(
    revision: str = typer.Argument(
        ...,
        help="Revision to stamp (e.g. 'head' or a specific revision hash)",
    ),
    database_url: DatabaseUrlOption = "",
) -> None:
    """Mark a revision as applied without running its migration.

    Use when the database already has schema changes applied manually
    and you need to update the Alembic version table to match.
    """
    from alembic import command

    cfg = _get_alembic_cfg(database_url)

    try:
        command.stamp(cfg, revision)
        console.print(f"[green]Stamped at: {revision}[/green]")
    except Exception as e:
        console.print(f"[red]Stamp failed: {e}[/red]")
        raise typer.Exit(1)


@db_app.command(name="baseline")
def baseline_command(
    database_url: DatabaseUrlOption = "",
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Immediately upgrade after generating the baseline revision",
    ),
) -> None:
    """Generate a baseline migration that creates all DSL-declared tables.

    Use this for first-time deployment to a fresh database. The command projects
    the current DSL schema and generates a migration that creates all the
    project's tables (framework-owned tables are created by the framework
    baseline migration, so they are excluded here).

    Generated via the #1431 snapshot-diff engine (the same generator as
    ``db revision``): foreign keys are emitted as separate
    ``op.create_foreign_key`` ops — so circular and self-referential FKs are
    created correctly — and the file carries a ``SCHEMA_SNAPSHOT`` constant, so a
    fresh baseline needs **no** follow-up ``snapshot-baseline`` step before the
    next ``db revision``.

    Workflow for fresh deployment:
        dazzle db baseline --apply          # Generate + apply in one step
        # or:
        dazzle db baseline                  # Generate only
        dazzle db upgrade                   # Apply separately

    Do NOT use 'stamp' + empty baseline for fresh databases — that marks
    the schema as current without creating tables.
    """
    from alembic import command

    cfg = _get_alembic_cfg(database_url)

    # Drive the snapshot-diff engine in baseline mode (empty prev, framework
    # tables excluded). env.py's directive hook reads these and stashes the
    # snapshot literal back on cfg.attributes for post-write injection below.
    cfg.attributes["dazzle_use_engine"] = True
    cfg.attributes["dazzle_baseline"] = True

    # Validate that DSL metadata is loadable and non-empty.
    # NOTE: import the side-effect-free metadata_loader, NOT
    # dazzle.http.alembic.env — that module executes
    # ``config = context.config`` at import time, which raises
    # AttributeError when alembic.context has no active config (i.e. any
    # direct Python import outside an Alembic run).
    try:
        from dazzle.http.alembic.metadata_loader import load_target_metadata

        metadata = load_target_metadata()
        table_count = len(metadata.tables)
        if table_count == 0:
            console.print(
                "[red]No tables found in DSL metadata.[/red]\n"
                "  Ensure you're running from a project directory with dazzle.toml\n"
                "  and DSL files that declare entities."
            )
            raise typer.Exit(1)
        console.print(f"[dim]DSL declares {table_count} tables[/dim]")
    except typer.Exit:
        raise
    except (ImportError, AttributeError):
        console.print("[yellow]Could not validate DSL metadata — proceeding anyway[/yellow]")
    except Exception as exc:
        # A real ParseError / LinkError / FileNotFoundError must stop the
        # command — proceeding would autogenerate against empty metadata
        # and produce a migration that drops every table.
        console.print(f"[red]DSL metadata load failed: {exc}[/red]")
        raise typer.Exit(1)

    project_versions = str(_get_project_versions_dir())

    try:
        rev = command.revision(
            cfg,
            message="baseline: create all tables",
            autogenerate=True,
            version_path=project_versions,
        )
        if rev is None:
            console.print(
                "[yellow]No schema changes detected.[/yellow]\n"
                "  If the target database already has tables, use 'dazzle db stamp head'\n"
                "  instead to mark the existing schema as current."
            )
            return

        # command.revision() can return Script | list[Script | None]; take the first element if list
        if isinstance(rev, list):
            rev = rev[0]
        if rev is None:
            console.print("[yellow]No revision was created.[/yellow]")
            return

        # Embed the engine's SCHEMA_SNAPSHOT (the full post-state, framework
        # tables included) so the next `db revision` diffs against it, and expand
        # any data-migration seam markers — the same post-write seam db revision uses.
        _inject_schema_snapshot(rev, cfg.attributes.get("dazzle_schema_snapshot"))
        _inject_data_seams(rev)

        console.print(f"[green]Baseline revision created: {rev.revision}[/green]")
        console.print(f"[dim]  → {project_versions}/[/dim]")

        if apply:
            command.upgrade(cfg, "head")
            console.print("[green]Baseline applied — all tables created.[/green]")
        else:
            console.print("[dim]Run 'dazzle db upgrade' to apply.[/dim]")

    except Exception as e:
        console.print(f"[red]Baseline failed: {e}[/red]")
        raise typer.Exit(1)


@db_app.command(name="migrate")
def migrate_command(
    database_url: DatabaseUrlOption = "",
    tenant: str = typer.Option("", "--tenant", help="Tenant slug (when isolation=schema)"),
    check: bool = typer.Option(
        False,
        "--check",
        help="Dry-run: show what would change without applying",
    ),
    sql: bool = typer.Option(
        False,
        "--sql",
        help="Print SQL without applying",
    ),
) -> None:
    """Generate and apply pending migrations.

    Generates a revision via the #1431 snapshot-diff engine (diffing the head
    migration's embedded ``SCHEMA_SNAPSHOT`` against the current DSL — the same
    generator as ``db revision``) and applies it. This is ``db revision`` +
    ``db upgrade`` in one step. Use --check for a dry-run preview.

    Examples:
        dazzle db migrate              # Generate + apply
        dazzle db migrate --check      # Preview changes
        dazzle db migrate --tenant X   # Apply to tenant schema
    """
    from alembic import command

    cfg = _get_alembic_cfg(database_url)

    # Generate via the snapshot-diff engine (DSL-vs-snapshot), like `db revision`.
    cfg.attributes["dazzle_use_engine"] = True

    schema = _resolve_tenant_schema(tenant) if tenant else ""
    if schema:
        cfg.attributes["tenant_schema"] = schema

    if check:
        console.print("[bold]Migration check (dry-run):[/bold]\n")
        # #1390: reconcile an empty alembic_version against a materialized schema
        # first, so `check` shows the real additive diff instead of a baseline
        # replay. Stamping aligns metadata with reality — it is not a schema change.
        _autostamp_if_materialized(cfg)
        # Preview via the SAME engine `db migrate` generates with (ADR-0045), so
        # --check is a faithful dry-run of migrate — not Alembic's metadata-vs-DB
        # `command.check`, which would answer a different question.
        from alembic.script import ScriptDirectory

        from dazzle.db.migration_engine import WholeSchemaRevisionRefused, generate_revision

        try:
            plan = generate_revision(
                ScriptDirectory.from_config(cfg), existing_tables=_target_table_names(cfg)
            )
        except WholeSchemaRevisionRefused as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)
        for note in plan.notes:
            console.print(f"[yellow]Note:[/yellow] {note}")
        if plan.is_empty:
            console.print("[green]No pending changes.[/green]")
        else:
            console.print("[yellow]Pending changes detected.[/yellow]")
        return

    if sql:
        # #1390: offline SQL replay runs from base and cannot introspect (the
        # baseline migration's idempotent `has_table` guard crashes on the
        # MockConnection). If the schema is materialized with an empty
        # alembic_version, refuse cleanly with a directed path rather than a
        # NoInspectionAvailable traceback — there is no offline DDL to preview.
        if _alembic_version_is_empty(cfg) and _schema_is_materialized(cfg):
            console.print(
                "[yellow]Offline --sql preview isn't available here:[/yellow] "
                "alembic_version is empty but the schema is already materialized, "
                "so an offline replay would re-run the baseline against existing "
                "tables.\nRun [bold]dazzle db migrate --check[/bold] to preview the "
                "additive diff (online), or [bold]dazzle db migrate[/bold] to "
                "reconcile and apply it."
            )
            raise typer.Exit(1)
        try:
            command.upgrade(cfg, "head", sql=True)
        except Exception as e:
            console.print(
                f"[red]Could not render migration SQL offline:[/red] {e}\n"
                "Use [bold]dazzle db migrate --check[/bold] (online) to preview "
                "pending changes."
            )
            raise typer.Exit(1)
        return

    try:
        # #1390: reconcile an empty alembic_version against a materialized schema
        # before upgrade so we apply the additive delta, not a baseline replay.
        _autostamp_if_materialized(cfg)
        # Generate the revision via the engine. process_revision_directives in
        # env.py suppresses empty revisions, so revision() returns None when the
        # DSL matches the head snapshot.
        rev = command.revision(cfg, message="auto", autogenerate=True)
        _print_engine_notes(cfg)
        if rev is None:
            console.print("[green]No schema changes detected.[/green]")
            return

        # Embed SCHEMA_SNAPSHOT + expand any data-migration seam (same post-write
        # path as `db revision`), so the next migrate/revision diffs correctly.
        _inject_schema_snapshot(rev, cfg.attributes.get("dazzle_schema_snapshot"))
        _inject_data_seams(rev)

        # Apply the new revision (and any other pending)
        command.upgrade(cfg, "head")
        console.print("[green]Migration applied successfully.[/green]")
    except typer.Exit:
        raise
    except Exception as e:
        # A pre-engine project (head migration carries no SCHEMA_SNAPSHOT) makes the
        # engine diff against {} → a full baseline that recreates existing tables.
        # Turn the raw "already exists" crash into the actionable adoption path.
        if "already exists" in str(e).lower():
            console.print(
                "[red]Migration tried to create tables that already exist.[/red]\n"
                "[dim]  This project's head migration has no SCHEMA_SNAPSHOT (it predates "
                "the migration engine), so the engine diffed against an empty baseline.\n"
                "  Run `dazzle db snapshot-baseline` once to adopt the engine, then retry.[/dim]"
            )
            raise typer.Exit(1)
        console.print(f"[red]Migration failed: {e}[/red]")
        raise typer.Exit(1)


@db_app.command(name="rollback")
def rollback_command_wrapper(
    revision: str = typer.Argument(
        "-1",
        help="Target revision or steps back (default: -1)",
    ),
    database_url: DatabaseUrlOption = "",
) -> None:
    """Revert the last migration (or to a specific revision).

    Examples:
        dazzle db rollback             # Undo last migration
        dazzle db rollback -2          # Undo last 2 migrations
        dazzle db rollback abc123      # Downgrade to specific revision
    """
    _downgrade(revision, database_url, done="Rolled back to", failed="Rollback failed")


async def _run_with_connection(
    project_root: Path,
    database_url: str,
    coro_factory: Any,
    schema: str = "",
) -> Any:
    """Connect to DB, run async operation, close connection.

    Args:
        schema: Optional tenant schema name. When provided, sets the
                search_path before running the operation.
    """
    from dazzle.db.connection import get_connection

    conn = await get_connection(explicit_url=database_url, project_root=project_root)
    try:
        if schema:
            # schema is pre-validated via slug_to_schema_name (alphanumeric + underscore only)
            await conn.execute(f"SET search_path TO {schema}, public")  # nosemgrep
        return await coro_factory(conn)
    finally:
        await conn.close()


def _resolve_tenant_schema(tenant: str) -> str:
    """Convert tenant slug to a quoted schema name for SET search_path."""
    from dazzle.tenant.config import slug_to_schema_name, validate_slug

    validate_slug(tenant)
    return slug_to_schema_name(tenant)


def _default_db_env(project_root: Path) -> str:
    """Environment profile `dazzle db` targets when no `--env`/`DAZZLE_ENV` is set.

    #1308: the CLI session env (`get_active_env`) defaults to ``""`` — "no
    profile" — but the app and `dazzle serve` default to the ``development``
    environment (`get_dazzle_env`). With an empty env_name, `resolve_database_url`
    *skips the `[environments.*]` profile branch entirely* and falls through to
    the hardcoded default DB (``postgresql://localhost:5432/dazzle``). So
    ``dazzle db upgrade`` silently operated on a *different* database than the
    one the dev app uses — typically already at head — and reported success
    while applying nothing.

    Fix: when no env is explicitly selected, target the SAME environment the app
    uses (`get_dazzle_env`, which honours ``DAZZLE_ENV`` and defaults to
    ``development``) — but ONLY when ``dazzle.toml`` actually declares that
    ``[environments.<name>]`` profile. Otherwise return ``""`` to preserve the
    profile-less resolution path (DATABASE_URL → ``[database].url`` → default)
    for projects that don't use environment profiles. Fail-safe: any load error
    returns ``""`` (existing behaviour).

    #1329: a bare ``DATABASE_URL`` (e.g. a Heroku dyno that never sets
    ``DAZZLE_ENV``) must still win. A profile's literal ``database_url`` is
    resolved at priority 2 in ``resolve_database_url`` — *before* the priority-3
    ``DATABASE_URL`` env var — so auto-selecting the *implicitly*-defaulted
    ``development`` profile would shadow the dyno's ``DATABASE_URL`` and deploy
    migrations against the wrong (often ``localhost``) database. So we only
    auto-select the default profile when the environment was chosen
    *explicitly* via ``DAZZLE_ENV`` (which keeps its priority-2 win, as the user
    asked for that profile) OR when ``DATABASE_URL`` is absent (the local-dev
    case #1308 fixed). An explicit ``--env`` is handled upstream in
    ``_resolve_url`` (`get_active_env`) and always wins regardless.
    """
    import os

    toml_path = project_root / "dazzle.toml"
    if not toml_path.exists():
        return ""

    dazzle_env_explicit = bool(os.environ.get(DAZZLE_ENV_VAR, "").strip())
    database_url_present = bool(os.environ.get("DATABASE_URL", "").strip())
    if not dazzle_env_explicit and database_url_present:
        # Implicitly-defaulted profile would shadow a present DATABASE_URL —
        # defer to the profile-less path so DATABASE_URL (priority 3) wins.
        return ""

    try:
        from dazzle.core.environment import get_dazzle_env
        from dazzle.core.manifest import load_manifest

        candidate = get_dazzle_env().value
        manifest = load_manifest(toml_path)
    except Exception:
        # Fail-safe: a malformed manifest shouldn't crash url resolution —
        # fall back to the legacy profile-less path.
        logger.debug("Could not resolve default db env from dazzle.toml", exc_info=True)
        return ""
    return candidate if candidate in manifest.environments else ""


def _resolve_target(database_url: str) -> "DbTarget":
    """Resolve the target database and its source: flag > ``DATABASE_URL`` > manifest.

    Loads ``<cwd>/.env`` before resolution so per-project DATABASE_URL
    values take effect without the user having to export them in their
    shell (#814). Shell exports still win because ``load_project_dotenv``
    only sets variables that aren't already set.

    When no environment is explicitly selected (`--env` / ``DAZZLE_ENV``),
    falls back to the app's default environment profile (#1308 — see
    ``_default_db_env``) so db commands hit the same database as `serve`.

    Never reads ``.dazzle/runtime.json`` (#1775) — that file is a running
    server's port/secret discovery and outlives it.
    """
    from dazzle.db.connection import resolve_db_target

    project_root = Path.cwd().resolve()
    load_project_dotenv(project_root)

    env_name = get_active_env() or _default_db_env(project_root)

    return resolve_db_target(
        explicit_url=database_url,
        project_root=project_root,
        env_name=env_name,
    )


def _resolve_url(database_url: str) -> str:
    """Resolved target URL only (see :func:`_resolve_target`)."""
    return _resolve_target(database_url).url


@db_app.command(name="status")
def status_command(
    database_url: DatabaseUrlOption = "",
    tenant: str = typer.Option("", "--tenant", help="Tenant slug (when isolation=schema)"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show row counts per entity and database size."""
    import json as json_mod

    project_root = Path.cwd().resolve()
    appspec = load_project_appspec(project_root)
    entities = appspec.domain.entities
    url = _resolve_url(database_url)
    schema = _resolve_tenant_schema(tenant) if tenant else ""

    from dazzle.db.status import db_status_impl

    async def _run(conn: Any) -> Any:
        return await db_status_impl(entities=entities, conn=conn)

    result = asyncio.run(_run_with_connection(project_root, url, _run, schema=schema))

    if as_json:
        console.print(json_mod.dumps(result, indent=2))
        return

    console.print("\n[bold]Entity           Rows[/bold]")
    console.print("─" * 30)
    for entry in result["entities"]:
        status = "[red]error[/red]" if entry.get("error") else str(entry["rows"])
        console.print(f"  {entry['name']:<18} {status}")
    console.print("─" * 30)
    console.print(
        f"Total: {result['total_entities']} entities, "
        f"{result['total_rows']:,} rows, {result['database_size']}"
    )


@db_app.command(name="verify")
def verify_command(
    database_url: DatabaseUrlOption = "",
    tenant: str = typer.Option("", "--tenant", help="Tenant slug (when isolation=schema)"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    fix_money: bool = typer.Option(
        False,
        "--fix-money",
        help="Auto-apply legacy money-column migration (#840). Destructive — back up the DB first.",
    ),
) -> None:
    """Check FK integrity, schema drift and missing framework objects.

    Reports FK orphans, legacy money columns (#840), signable columns (#1340),
    RLS policy drift (shared_schema), DSL ``search:`` column drift and framework
    tables / columns / indexes the database lacks (#1850). Exits 1 on any finding.
    """
    import json as json_mod

    project_root = Path.cwd().resolve()
    appspec = load_project_appspec(project_root)
    entities = appspec.domain.entities
    url = _resolve_url(database_url)
    schema = _resolve_tenant_schema(tenant) if tenant else ""

    from dazzle.db.money_migration import repair_money_drifts
    from dazzle.db.signable_drift import detect_signable_drift
    from dazzle.db.verify import db_verify_impl

    # Phase D: the RLS drift check compares live pg_policies/pg_class against the
    # generated policy set (describe_rls_policies). It is a no-op for every non-
    # shared_schema app (the expected set is empty), so the converted entities are
    # only needed when row-level tenancy is in play.
    rls_entities: list[Any] = []
    if _is_shared_schema(appspec):
        rls_entities = convert_entities(appspec.domain.entities)

    async def _run(conn: Any) -> Any:
        fk_result = await db_verify_impl(entities=entities, conn=conn)
        money_result = await repair_money_drifts(conn, list(entities), apply=fix_money)
        signable_result = await detect_signable_drift(conn, list(entities))
        rls_result = await detect_rls_drift(conn, appspec, rls_entities)
        out: dict[str, Any] = {
            "fk": fk_result,
            "money": money_result,
            "signable": signable_result,
            "rls": rls_result,
            # #1850: DSL search columns + framework objects a dev boot would create.
            "search": await detect_search_drift(
                conn, appspec, convert_entities(appspec.domain.entities)
            ),
            # Framework tables live in public; a per-tenant schema run skips them.
            "framework": [] if schema else await detect_framework_drift(conn),
        }
        if rls_entities:
            # #1788: warn (never fail) when a plain pg_dump cannot back this DB up.
            out["dumpable"] = (await read_dump_posture(conn)).model_dump()
        return out

    result = asyncio.run(_run_with_connection(project_root, url, _run, schema=schema))

    # #1381: compute the failure condition ONCE and gate BOTH output paths on
    # it — including checks that ERRORED before they could evaluate (error_count).
    # The --json branch previously returned before any exit gate, so a run where
    # every FK check errored ("relation does not exist") printed valid JSON and
    # exited 0 — a vacuous green pass. error_count makes that fail loud.
    _fk = result["fk"]
    _money = result["money"]
    has_issues = bool(
        _fk["total_issues"]
        or _fk.get("error_count", 0)
        or _fk.get("warning_count", 0)
        or (_money["drift_count"] + _money["partial_count"])
        or result["signable"]
        or result["rls"]
        or result["search"]
        or result["framework"]
    )

    if as_json:
        console.print(json_mod.dumps(result, indent=2))
        if has_issues:
            raise typer.Exit(1)
        return

    console.print("\n[bold]FK Integrity:[/bold]")
    fk_result = result["fk"]
    for check in fk_result["checks"]:
        target = f" → {check['ref']}" if check.get("ref") else ""
        if check["status"] == "ok":
            console.print(f"  [green]✓[/green] {check['entity']}.{check['field']}{target}")
        elif check["status"] == "orphans":
            console.print(
                f"  [red]✗[/red] {check['entity']}.{check['field']}{target}: "
                f"{check['orphan_count']} orphans"
            )
        elif check["status"] == "required_null":
            # #1364: required ref is NULL — app-layer `required` was bypassed.
            console.print(
                f"  [red]✗[/red] {check['entity']}.{check['field']}{target}: "
                f"{check['null_count']} NULL(s) in a required ref"
            )
        elif check["status"] == "unanchored":
            # #1364: at-least-one-anchor invariant violated in the DB.
            console.print(
                f"  [red]✗[/red] {check['entity']} ({check['field']}): "
                f"{check['unanchored_count']} unanchored row(s) — all anchor refs NULL"
            )
        elif check["status"] == "exclusive_conflict":
            # #1617 Phase 1: more than one exclusive-anchor FK set on a row.
            console.print(
                f"  [red]✗[/red] {check['entity']} ({check['field']}): "
                f"{check['exclusive_conflict_count']} exclusive conflict(s) — "
                f"more than one anchor ref non-null"
            )
        else:
            console.print(
                f"  [yellow]![/yellow] {check['entity']}.{check['field']}{target}: "
                f"{check.get('error', 'unknown error')}"
            )

    # #1035 (v0.67.21): exit non-zero when `!` column-mismatch warnings
    # are emitted. Pre-fix the CLI counted only "orphans" status in
    # total_issues and printed "All FK references valid." even when the
    # loop emitted N column-mismatch warnings — the literal contradiction
    # masked latent runtime-broken FK paths.
    fk_warnings = fk_result.get("warning_count", 0)
    fk_orphans = fk_result["total_issues"]
    if fk_orphans == 0 and fk_warnings == 0:
        console.print("\n[green]All FK references valid.[/green]")
    else:
        if fk_orphans:
            console.print(f"\n[red]{fk_orphans} FK orphan(s) found.[/red]")
        if fk_warnings:
            console.print(
                f"[yellow]{fk_warnings} column mismatch(es) — see ! lines above.[/yellow]"
            )

    money_result = result["money"]
    if money_result["drift_count"] or money_result["partial_count"]:
        console.print("\n[bold]Legacy money-column drift (#840):[/bold]")
        for drift in money_result["drifts"]:
            label = "[red]drift[/red]" if drift["status"] == "drift" else "[yellow]partial[/yellow]"
            console.print(
                f"  {label} {drift['entity']}.{drift['field']} "
                f"(legacy {drift['legacy_type']}, ccy {drift['currency']})"
            )
            if drift["status"] == "drift" and not fix_money:
                for line in drift["repair_sql"].splitlines():
                    console.print(f"    [dim]{line}[/dim]")
        if fix_money:
            console.print(f"\n[green]Applied {money_result['applied_count']} statement(s).[/green]")
            if money_result["errors"]:
                console.print(f"[red]{len(money_result['errors'])} error(s) during repair:[/red]")
                for err in money_result["errors"]:
                    console.print(f"  {err['entity']}.{err['field']}: {err['error']}")
        else:
            console.print(
                "\n[yellow]Re-run with --fix-money to auto-apply "
                "(back up the DB first — destructive).[/yellow]"
            )
    else:
        console.print("\n[green]No legacy money-column drift.[/green]")

    # #1340: signable entities frozen at a stale schema (missing the auto-
    # injected signing columns) 500 on every create. Surface the drift here
    # with the exact missing columns + the Alembic remediation, instead of an
    # opaque per-create UndefinedColumn 500.
    signable_drifts = result["signable"]
    if signable_drifts:
        console.print("\n[bold]Signable schema drift (#1340):[/bold]")
        for drift in signable_drifts:
            console.print(
                f"  [red]✗[/red] {drift['entity']} is missing signing column(s): "
                f"{', '.join(drift['missing'])}"
            )
        console.print(
            "\n[yellow]A `signable: true` table is frozen at a stale shape. "
            "Reconcile via a migration (ADR-0017):[/yellow]\n"
            '    [dim]dazzle db revision -m "add signing columns" --autogenerate[/dim]\n'
            "    [dim]dazzle db upgrade[/dim]"
        )
    else:
        console.print("\n[green]No signable schema drift.[/green]")

    # Phase D: RLS policy drift — a tenant-scoped table whose live RLS shape
    # (enabled/forced + policy name/cmd/permissive set) diverges from the
    # generated set. Shape-based, not qual-text. The fix is `dazzle db apply-rls`
    # (or `dazzle db upgrade`), run as the table owner. No section for non-
    # shared_schema apps (the expected set is empty → detect returns []).
    rls_drifts = result["rls"]
    if rls_drifts:
        console.print("\n[bold]RLS policy drift (Phase D):[/bold]")
        for drift in rls_drifts:
            console.print(f"  [red]✗[/red] {drift['entity']}:")
            for issue in drift["issues"]:
                console.print(f"      [red]-[/red] {issue}")
        console.print(
            "\n[yellow]Live RLS policies have drifted from the generated set. "
            "Re-apply as the table owner:[/yellow]\n"
            "    [dim]dazzle db apply-rls[/dim]   [dim](or `dazzle db upgrade`)[/dim]"
        )
    elif _is_shared_schema(appspec):
        console.print("\n[green]No RLS policy drift.[/green]")

    _print_search_drift(result["search"])
    if not schema:
        _print_framework_drift(result["framework"])

    if result.get("dumpable") is not None:
        style, message = _dump_posture_line(DumpPosture(**result["dumpable"]))
        console.print(f"\n[bold]Backup posture (#1788):[/bold]\n  [{style}]{message}[/{style}]")

    # #1035 (v0.67.21): exit non-zero when verify surfaced any FK
    # issues — orphans, column mismatches, or money-column drift. The
    # exit code lets `dazzle db verify` be wired into CI / nightly
    # quality swarms without a wrapper that has to re-parse stdout.
    # #1340 extends this to signable schema drift; Phase D to RLS drift.
    # #1381: reuse the single failure condition computed above (includes
    # error_count — checks that errored before they could evaluate).
    if has_issues:
        raise typer.Exit(1)


def _print_search_drift(drifts: list[dict[str, Any]]) -> None:
    """``dazzle db verify`` section for the DSL ``search:`` columns (#1850)."""
    if not drifts:
        console.print("\n[green]No search column drift.[/green]")
        return
    console.print("\n[bold]Search column drift (#1850):[/bold]")
    for drift in drifts:
        console.print(f"  [red]✗[/red] {drift['entity']}: {drift['detail']}")
    console.print(
        "\n[yellow]Reconcile as the table owner:[/yellow]\n"
        "    [dim]dazzle db apply-search[/dim]   [dim](or `dazzle db upgrade`)[/dim]"
    )


def _print_framework_drift(drifts: list[dict[str, Any]]) -> None:
    """``dazzle db verify`` section for missing framework objects (#1850)."""
    if not drifts:
        console.print("\n[green]No missing framework objects.[/green]")
        return
    console.print("\n[bold]Missing framework objects (#1850):[/bold]")
    for drift in drifts:
        if drift["missing_table"]:
            console.print(f"  [red]✗[/red] table {drift['table']}")
            continue
        parts = [f"column {c}" for c in drift["columns"]]
        parts += [f"index {i}" for i in drift["indexes"]]
        console.print(f"  [red]✗[/red] {drift['table']}: {', '.join(parts)}")
    console.print(
        "\n[yellow]The framework migrations have not been applied to this database:[/yellow]\n"
        "    [dim]dazzle db upgrade head[/dim]"
    )


def _is_shared_schema(appspec: Any) -> bool:
    """True when the appspec declares row-level (``shared_schema``) tenancy.

    The RLS apply/inspect/drift surfaces are no-ops for every other isolation
    mode (and for non-tenant apps), mirroring ``build_all_rls_ddl``'s gate.
    """

    tenancy = getattr(appspec, "tenancy", None)
    if tenancy is None:
        return False
    return bool(tenancy.isolation.mode == TenancyMode.SHARED_SCHEMA)


@db_app.command(name="apply-search")
def apply_search_command(
    database_url: DatabaseUrlOption = "",
    tenant: str = typer.Option("", "--tenant", help="Tenant slug (when isolation=schema)"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Reconcile the DSL `search:` columns (generated search_vector + GIN index).

    Adds a missing column, drops and re-adds one whose expression no longer
    matches the ``search:`` field list, creates a missing index and drops a
    generated column whose ``search:`` block was removed. A database that already
    matches gets no DDL. ``dazzle db upgrade`` runs this after the migrations;
    production boots never do (#1850). Run as the table owner.
    """
    import json as json_mod

    project_root = Path.cwd().resolve()
    appspec = load_project_appspec(project_root)
    entities = convert_entities(appspec.domain.entities)
    url = _resolve_url(database_url)
    schema = _resolve_tenant_schema(tenant) if tenant else ""

    async def _run(conn: Any) -> Any:
        return await apply_search_columns(conn, appspec, entities)

    try:
        actions = asyncio.run(_run_with_connection(project_root, url, _run, schema=schema))
    except Exception as e:
        console.print(f"[red]Failed to apply search columns: {e}[/red]")
        raise typer.Exit(1)

    if as_json:
        console.print(
            json_mod.dumps(
                {
                    "actions": [
                        {"entity": a.table, "action": a.action, "statements": list(a.statements)}
                        for a in actions
                    ]
                },
                indent=2,
            )
        )
        return
    if not actions:
        console.print("[green]Search columns already match the DSL — nothing to apply.[/green]")
        return
    _print_search_actions(actions)


@db_app.command(name="apply-rls")
def apply_rls_command(
    database_url: DatabaseUrlOption = "",
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    check_dumpable: bool = typer.Option(
        False,
        "--check-dumpable",
        help="Apply nothing; exit 1 when FORCE RLS is on and the connected role cannot "
        "bypass it, i.e. a plain pg_dump / heroku pg:backups cannot back this database "
        "up (use `dazzle db dump`, #1788).",
    ),
) -> None:
    """Apply row-level-security policies to the database (production enforcement).

    Generates the tenant fence + intra-tenant scope policy DDL from the DSL and
    applies it to the live database. Idempotent (DROP-then-CREATE), so safe to
    re-run.

    CRITICAL — run this as a role that OWNS the tables (the deploy/owner role,
    e.g. ``dazzle_owner``). ``ENABLE/FORCE ROW LEVEL SECURITY`` and
    ``CREATE POLICY`` require table ownership; the runtime ``dazzle_app`` role
    cannot run this DDL. ``dazzle db upgrade`` applies it automatically after
    migrations (same owner role); use this command to apply it separately.

    No ``--tenant`` flag: RLS apply only runs in ``shared_schema`` mode, where
    the policies live on the shared ``public`` tables — it is never a per-tenant
    (schema-isolated) operation.
    """
    import json as json_mod

    project_root = Path.cwd().resolve()
    appspec = load_project_appspec(project_root)

    if not _is_shared_schema(appspec):
        msg = "No row-level tenancy (tenancy: mode: shared_schema); nothing to apply."
        if as_json:
            console.print(json_mod.dumps({"applied": 0, "note": msg}))
        else:
            console.print(f"[dim]{msg}[/dim]")
        return

    if check_dumpable:
        _check_dumpable(_resolve_url(database_url), project_root, as_json=as_json)
        return

    from dazzle.db.rls_apply import apply_rls_policies

    entities = convert_entities(appspec.domain.entities)
    url = _resolve_url(database_url)

    async def _run(conn: Any) -> Any:
        return await apply_rls_policies(conn, appspec, entities)

    # RLS apply always targets the shared public schema — no per-tenant
    # search_path. Wrap loud: the likeliest prod failure is running as the
    # non-owner runtime role (dazzle_app) → InsufficientPrivilege; surface a
    # clean owner-role hint instead of a raw driver traceback (matches the
    # db-upgrade hook's error handling).
    try:
        applied = asyncio.run(_run_with_connection(project_root, url, _run))
    except Exception as e:
        console.print(f"[red]Failed to apply RLS policies: {e}[/red]")
        console.print(
            "[dim]Apply must run as a role that OWNS the tables (e.g. dazzle_owner), "
            "not the runtime dazzle_app.[/dim]"
        )
        raise typer.Exit(1)

    if as_json:
        console.print(json_mod.dumps({"applied": applied}))
        return

    console.print(
        f"\n[green]Applied {applied} RLS policy statement{'' if applied == 1 else 's'}.[/green]"
    )
    console.print(
        "[dim]Note: this must run as a role that owns the tables (the deploy/owner "
        "role) — the runtime dazzle_app role cannot run RLS DDL.[/dim]"
    )


_DUMP_POINTER = (
    "Use `dazzle db dump` (one tenant-bound dump per tenant + manifest) and "
    "`dazzle db restore-check` (#1788)."
)


def _dump_posture_line(posture: Any) -> tuple[str, str]:
    """(rich style, message) describing whether a plain pg_dump can work."""
    if posture.plain_dump_blocked:
        return (
            "yellow",
            f"FORCE ROW LEVEL SECURITY is on for {len(posture.forced_tables)} table(s) and "
            "the connected role cannot bypass it: a plain pg_dump / `heroku pg:backups` "
            "fails, and `pg_dump --enable-row-security` writes the fenced tables empty. "
            + _DUMP_POINTER,
        )
    if posture.forced_tables:
        return (
            "green",
            "The connected role bypasses RLS, so a plain pg_dump sees every row "
            "(`dazzle db dump` needs --role <a non-bypass role> from this role).",
        )
    return ("green", "No FORCE ROW LEVEL SECURITY tables; a plain pg_dump sees every row.")


def _check_dumpable(url: str, project_root: Path, *, as_json: bool) -> None:
    """``apply-rls --check-dumpable``: exit 1 when a plain dump cannot work."""
    import json as json_mod

    posture = asyncio.run(_run_with_connection(project_root, url, read_dump_posture))
    style, message = _dump_posture_line(posture)
    if as_json:
        payload = posture.model_dump()
        payload["plain_dump_blocked"] = posture.plain_dump_blocked
        console.print(json_mod.dumps(payload))
    else:
        console.print(f"[{style}]{message}[/{style}]")
    if posture.plain_dump_blocked:
        raise typer.Exit(1)


def _refuse_plain_dump_if_blocked(url: str, project_root: Path, command: str) -> None:
    """``db snapshot`` / ``db restore`` under FORCE RLS: refuse instead of a hollow baseline.

    A plain ``pg_dump`` run by a role the fence filters either errors or (with
    ``--enable-row-security``) writes every fenced table empty — a zero-row
    baseline that restores "successfully" (#1788). A superuser / BYPASSRLS role
    is not filtered, so the snapshot stays available to it.
    """

    try:
        posture = asyncio.run(_run_with_connection(project_root, url, read_dump_posture))
    except Exception:
        # Unreachable DB: pg_dump / pg_restore report it themselves.
        logger.debug("dump-posture probe failed; leaving it to pg_dump", exc_info=True)
        return
    if posture.plain_dump_blocked:
        typer.echo(
            f"[db {command}] refusing: FORCE ROW LEVEL SECURITY is on for "
            f"{len(posture.forced_tables)} table(s) and the connected role cannot bypass "
            "it, so a plain pg_dump/pg_restore would error or carry zero tenant rows. "
            + _DUMP_POINTER,
            err=True,
        )
        raise typer.Exit(code=2)


@db_app.command(name="dump")
def dump_command(
    out: Path = typer.Option(
        ..., "--out", help="Parent directory; the dump is written to OUT/<label>/"
    ),
    label: str = typer.Option("", "--label", help="Dump label (default: dump-<UTC timestamp>)"),
    role: str = typer.Option(
        "",
        "--role",
        help="SET ROLE for the dump session (required when the connected role is a "
        "superuser or has BYPASSRLS; must itself be NOSUPERUSER NOBYPASSRLS)",
    ),
    pg_bin: str = typer.Option("", "--pg-bin", help="Directory holding pg_dump (default: PATH)"),
    database_url: DatabaseUrlOption = "",
) -> None:
    """Tenant-aware backup of a shared_schema database (#1788).

    One custom-format ``pg_dump`` per tenant with ``dazzle.tenant_id`` bound
    through PGOPTIONS and ``--enable-row-security``, all reading one exported
    snapshot, then ``manifest.json`` (written last) with per-tenant per-table
    row counts. Works where FORCE ROW LEVEL SECURITY defeats a plain pg_dump
    and ``heroku pg:backups`` (single-role hosts). Prove a dump restores with
    ``dazzle db restore-check``.
    """

    project_root = Path.cwd().resolve()
    appspec = load_project_appspec(project_root)
    if not _is_shared_schema(appspec):
        typer.echo(
            "[db dump] refusing: no row-level tenancy (tenancy: mode: shared_schema). "
            "A plain pg_dump backs this database up.",
            err=True,
        )
        raise typer.Exit(code=2)

    url = _resolve_url(database_url)
    drift = _live_rls_drift(url, appspec, project_root)
    if drift:
        typer.echo(
            "[db dump] refusing: live RLS policies have drifted from the DSL, so the "
            "fenced/non-fenced split is suspect:",
            err=True,
        )
        for entry in drift:
            typer.echo(f"  {entry['entity']}: {'; '.join(entry['issues'])}", err=True)
        typer.echo("Run `dazzle db apply-rls` as the table owner, then dump.", err=True)
        raise typer.Exit(code=2)

    resolved_label = label or default_label()
    try:
        manifest, classification = run_dump(
            url=url,
            appspec=appspec,
            out_dir=out / resolved_label,
            label=resolved_label,
            role=role or None,
            pg_bin=pg_bin or None,
        )
    except DumpRefusal as e:
        typer.echo(f"[db dump] refusing: {e}", err=True)
        raise typer.Exit(code=2)
    except DumpError as e:
        typer.echo(f"[db dump] failed: {e}", err=True)
        raise typer.Exit(code=1)

    console.print(f"\n[bold]Dump {manifest.label}[/bold] → {out / manifest.label}")
    for tenant in manifest.tenants:
        rows = sum(manifest.counts[tenant.id].values())
        name = tenant.slug or tenant.id
        console.print(
            f"  {name:<24} {tenant.file:<32} {manifest.files[tenant.file]:>12,} B  {rows} rows"
        )
    console.print(
        f"  globals: {sum(manifest.globals.values())} rows in "
        f"{len(manifest.non_rls_tables)} non-fenced table(s); "
        f"{len(manifest.rls_tables)} fenced table(s)"
    )
    if classification.unaccounted:
        console.print(
            "[yellow]Non-fenced tables not declared by the DSL, the artifact registry or "
            f"Alembic (restored once): {', '.join(classification.unaccounted)}[/yellow]"
        )


def _live_rls_drift(url: str, appspec: Any, project_root: Path) -> list[dict[str, Any]]:
    """``detect_rls_drift`` against the live database (empty = no drift)."""

    entities = convert_entities(appspec.domain.entities)

    async def _run(conn: Any) -> list[dict[str, Any]]:
        return await detect_rls_drift(conn, appspec, entities)

    result: list[dict[str, Any]] = asyncio.run(_run_with_connection(project_root, url, _run))
    return result


@db_app.command(name="restore-check")
def restore_check_command(
    from_dir: Path = typer.Option(
        ..., "--from", help="A `dazzle db dump` directory (the one holding manifest.json)"
    ),
    target_url: str = typer.Option(
        ..., "--target-url", help="Scratch database to restore into (never the source)"
    ),
    drop_first: bool = typer.Option(
        False,
        "--drop-first",
        help="Drop every user schema on the target first (scratch databases only)",
    ),
    pg_bin: str = typer.Option("", "--pg-bin", help="Directory holding pg_restore (default: PATH)"),
) -> None:
    """Restore a `dazzle db dump` into a scratch database and prove every count (#1788).

    ``pre-data`` from the first dump, ``TABLE DATA`` from every dump (fenced
    tables from each, non-fenced tables from the first only), ``post-data``
    once; then every per-tenant and global row count is compared with the
    manifest. Exit 0 only when all match; 1 on a mismatch or a failed step;
    2 on a refusal (no manifest, target is the source, target not empty
    without --drop-first).
    """

    try:
        result = run_restore_check(
            from_dir=from_dir,
            target_url=target_url,
            drop_first=drop_first,
            pg_bin=pg_bin or None,
        )
    except DumpRefusal as e:
        typer.echo(f"[db restore-check] refusing: {e}", err=True)
        raise typer.Exit(code=2)
    except DumpError as e:
        typer.echo(f"[db restore-check] failed: {e}", err=True)
        raise typer.Exit(code=1)

    console.print(f"\n[bold]Restore check {result.label}[/bold]")
    for step in result.steps:
        console.print(f"  {step}")
    if result.mismatches:
        console.print(f"\n[red]{len(result.mismatches)} of {result.checks} counts differ:[/red]")
        console.print(f"  {'table':<32} {'tenant':<38} {'expected':>10} {'actual':>10}")
        for m in result.mismatches:
            console.print(f"  {m.table:<32} {m.tenant:<38} {m.expected!s:>10} {m.actual!s:>10}")
        raise typer.Exit(code=1)
    console.print(f"\n[green]All {result.checks} counts match ({result.rows} rows).[/green]")


@db_app.command(name="reset")
def reset_command(
    database_url: DatabaseUrlOption = "",
    tenant: str = typer.Option("", "--tenant", help="Tenant slug (when isolation=schema)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be truncated"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Truncate entity tables in dependency order (preserves auth)."""
    import json as json_mod

    project_root = Path.cwd().resolve()
    appspec = load_project_appspec(project_root)
    entities = appspec.domain.entities
    url = _resolve_url(database_url)
    schema = _resolve_tenant_schema(tenant) if tenant else ""

    if dry_run:
        result = _reset_entity_tables(project_root, url, entities, schema=schema, dry_run=True)

        if as_json:
            console.print(json_mod.dumps(result, indent=2))
            return

        console.print(
            f"\n[bold]Would truncate {result['would_truncate']} tables ({result['total_rows']:,} rows):[/bold]"
        )
        for t in result["tables"]:
            console.print(f"  {t['name']} ({t['rows']} rows)")
        if result["preserved"]:
            console.print(f"\nPreserved: {', '.join(result['preserved'])}")
        return

    if not yes:
        console.print(f"\nThis will truncate {len(entities)} entity tables.")
        confirm = typer.prompt("Type 'reset' to confirm", default="")
        if confirm != "reset":
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)

    result = _reset_entity_tables(project_root, url, entities, schema=schema)

    if as_json:
        console.print(json_mod.dumps(result, indent=2))
        return

    for t in result["tables"]:
        err = f" [red]error: {t['error']}[/red]" if t.get("error") else " ✓"
        console.print(f"  {t['name']} ({t['rows']} rows){err}")
    console.print(
        f"\n[green]Reset complete: {result['truncated']} tables, {result['total_rows']:,} rows removed.[/green]"
    )


@db_app.command(name="cleanup")
def cleanup_command(
    database_url: DatabaseUrlOption = "",
    tenant: str = typer.Option("", "--tenant", help="Tenant slug (when isolation=schema)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be deleted"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    unanchored: bool = typer.Option(
        False,
        "--unanchored",
        help="#1364: also sweep rows violating an at-least-one-anchor invariant "
        "(`a != null or b != null`). Off by default — unanchored rows may be "
        "mid-flow data, unlike orphans.",
    ),
) -> None:
    """Find and remove FK orphan records."""
    import json as json_mod

    project_root = Path.cwd().resolve()
    appspec = load_project_appspec(project_root)
    entities = appspec.domain.entities
    url = _resolve_url(database_url)
    schema = _resolve_tenant_schema(tenant) if tenant else ""

    from dazzle.db.cleanup import db_cleanup_impl

    if dry_run:

        async def _run_dry(conn: Any) -> Any:
            return await db_cleanup_impl(
                entities=entities, conn=conn, dry_run=True, unanchored=unanchored
            )

        result = asyncio.run(_run_with_connection(project_root, url, _run_dry, schema=schema))

        if as_json:
            console.print(json_mod.dumps(result, indent=2))
            return

        if result["would_delete"] == 0:
            console.print("[green]No orphan records found.[/green]")
            return

        console.print(f"\n[bold]Found {result['would_delete']} orphan records:[/bold]")
        for f in result["findings"]:
            if "unanchored_count" in f:
                console.print(
                    f"  {f['unanchored_count']} × {f['entity']} ({f['field']}: all anchors NULL)"
                )
            else:
                console.print(
                    f"  {f['orphan_count']} × {f['entity']} ({f['field']} → {f['ref']}: missing)"
                )
        console.print("\nRun without --dry-run to delete.")
        return

    if not yes:
        confirm = typer.prompt("Type 'cleanup' to confirm", default="")
        if confirm != "cleanup":
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)

    async def _run(conn: Any) -> Any:
        return await db_cleanup_impl(entities=entities, conn=conn, unanchored=unanchored)

    result = asyncio.run(_run_with_connection(project_root, url, _run, schema=schema))

    if as_json:
        console.print(json_mod.dumps(result, indent=2))
        return

    if result["total_deleted"] == 0:
        console.print("[green]No orphan records found.[/green]")
        return

    for d in result["deletions"]:
        console.print(f"  {d['deleted']} × {d['entity']} ✓")
    console.print(
        f"\n[green]Cleanup complete: {result['total_deleted']} orphans removed "
        f"in {result['iterations']} iteration(s).[/green]"
    )


@db_app.command(name="resanitize-rich-text")
def resanitize_rich_text_command(
    database_url: DatabaseUrlOption = "",
    tenant: str = typer.Option("", "--tenant", help="Tenant slug (when isolation=schema)"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Report rows that would change (the default)"
    ),
    apply: bool = typer.Option(False, "--apply", help="Write the sanitised values"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Re-run the rich-text sanitiser over stored rich-text values.

    Walks every field a surface renders with ``widget=rich_text`` and runs
    ``clean_rich_text`` (the allowlist sanitiser the write path uses since flense
    ship T) over each stored value. Without ``--apply`` it only reports, per
    entity and field, how many rows would change — counts only, never values.
    Values longer than the field's cap after sanitising are reported and left
    untouched. Safe to re-run: an already-clean value is unchanged.
    """
    import json as json_mod

    if dry_run and apply:
        console.print("[red]--dry-run and --apply are mutually exclusive.[/red]")
        raise typer.Exit(2)

    from dazzle.db.resanitize_rich_text import (
        PgRichTextStore,
        resanitize_rich_text,
        rich_text_targets,
    )

    project_root = Path.cwd().resolve()
    appspec = load_project_appspec(project_root)
    targets = rich_text_targets(appspec)
    if not targets:
        if as_json:
            console.print(json_mod.dumps({"applied": False, "fields": []}))
        else:
            console.print("[dim]No rich-text fields (no surface uses widget=rich_text).[/dim]")
        return

    target = _resolve_target(database_url)
    schema = _resolve_tenant_schema(tenant) if tenant else ""
    if not as_json:
        console.print(
            f"[dim]Target database: {_redact_url(target.url)} (from {target.source})[/dim]"
        )

    async def _run(conn: Any) -> Any:
        return await resanitize_rich_text(targets, PgRichTextStore(conn), apply=apply)

    report = asyncio.run(_run_with_connection(project_root, target.url, _run, schema=schema))

    if as_json:
        console.print(json_mod.dumps(report.model_dump(), indent=2))
        return

    verb = "Updated" if apply else "Would update"
    for f in report.fields:
        line = f"  {f.entity}.{f.field}: {f.changed} of {f.scanned} rows"
        if f.over_cap:
            line += f" [yellow]({f.over_cap} over cap, left untouched)[/yellow]"
        console.print(line)
    summary = f"\n{verb} {report.total_changed} rich-text values"
    if report.total_over_cap:
        summary += f"; {report.total_over_cap} over-cap values left untouched"
    console.print(summary + ".")
    if not apply and report.total_changed:
        console.print("Run with --apply to write them.")


@db_app.command(name="snapshot")
def db_snapshot_command(
    name: str = typer.Argument("baseline", help="Snapshot label (default: baseline)"),
    database_url: DatabaseUrlOption = "",
    project: Path | None = typer.Option(None, "--project", help="Project root (default: cwd)"),
) -> None:
    """Capture a pg_dump of the project database to a .sql.gz file.

    Writes `<project>/.dazzle/baselines/<name>.sql.gz`. For named snapshots
    other than 'baseline', the file is used verbatim. For 'baseline', the
    filename is hash-tagged with the Alembic revision and fixture SHA.
    """
    import os

    from dazzle.e2e.baseline import BaselineManager
    from dazzle.e2e.snapshot import Snapshotter

    if project is None:
        project = Path.cwd()

    url = database_url or os.environ.get("DATABASE_URL", "")
    if not url:
        typer.echo("DATABASE_URL not set. Export it or pass --database-url.", err=True)
        raise typer.Exit(code=2)

    _refuse_plain_dump_if_blocked(url, project, "snapshot")

    if name == "baseline":
        mgr = BaselineManager(project, url)
        path = mgr.ensure(fresh=True)
        typer.echo(f"[db snapshot] wrote baseline → {path}")
    else:
        snap = Snapshotter()
        dest = project / ".dazzle" / "baselines" / f"{name}.sql.gz"
        snap.capture(url, dest)
        typer.echo(f"[db snapshot] wrote {name} → {dest}")


@db_app.command(name="restore")
def db_restore_command(
    name: str = typer.Argument("baseline", help="Snapshot label to restore"),
    database_url: DatabaseUrlOption = "",
    project: Path | None = typer.Option(None, "--project", help="Project root (default: cwd)"),
) -> None:
    """Restore a snapshot into the project database via pg_restore --clean."""
    import os

    from dazzle.e2e.baseline import BaselineManager
    from dazzle.e2e.snapshot import Snapshotter

    if project is None:
        project = Path.cwd()

    url = database_url or os.environ.get("DATABASE_URL", "")
    if not url:
        typer.echo("DATABASE_URL not set. Export it or pass --database-url.", err=True)
        raise typer.Exit(code=2)

    _refuse_plain_dump_if_blocked(url, project, "restore")

    if name == "baseline":
        mgr = BaselineManager(project, url)
        path = mgr.restore()
        typer.echo(f"[db restore] restored baseline from {path}")
    else:
        snap = Snapshotter()
        src = project / ".dazzle" / "baselines" / f"{name}.sql.gz"
        if not src.exists():
            typer.echo(f"Snapshot not found: {src}", err=True)
            raise typer.Exit(code=2)
        snap.restore(src, url)
        typer.echo(f"[db restore] restored {name} from {src}")


@db_app.command(name="snapshot-gc")
def db_snapshot_gc_command(
    keep: int = typer.Option(3, "--keep", help="Number of newest snapshots to retain"),
    project: Path | None = typer.Option(None, "--project", help="Project root (default: cwd)"),
) -> None:
    """Delete old baseline snapshot files, keeping the newest `keep`."""
    import os

    from dazzle.e2e.baseline import BaselineManager

    if project is None:
        project = Path.cwd()

    # BaselineManager requires a db_url at construction time, but gc() is a
    # file-only operation that never connects. Use a dummy if DATABASE_URL
    # is absent so the command still works without infrastructure.
    url = os.environ.get("DATABASE_URL", "postgresql://localhost/unused")
    mgr = BaselineManager(project, url)
    deleted = mgr.gc(keep=keep)
    if not deleted:
        typer.echo(f"[db snapshot-gc] nothing to delete (kept newest {keep})")
        return
    for p in deleted:
        typer.echo(f"[db snapshot-gc] deleted {p.name}")


@db_app.command(name="explain-aggregate")
def explain_aggregate_command(
    entity: str = typer.Argument(..., help="Source entity name (e.g. Alert)"),
    group_by: str = typer.Option(
        "",
        "--group-by",
        "-g",
        help="Dimension field(s) — comma-separated for multi-dim. "
        "FK fields auto-LEFT JOIN the target. e.g. 'system,severity'.",
    ),
    measures: str = typer.Option(
        "count=count",
        "--measures",
        "-m",
        help="Comma-separated metric=expr pairs. "
        "Supported exprs: count, sum:<col>, avg:<col>, min:<col>, max:<col>. "
        "Example: 'n=count,avg_score=avg:score'.",
    ),
    limit: int = typer.Option(200, "--limit", "-l", help="Bucket limit (default 200)"),
) -> None:
    """Print the SQL that ``Repository.aggregate`` would execute — no DB hit.

    Debug-velocity tool for authors. When a bar_chart or pivot_table region
    renders wrong values (or no buckets), run this against the same source
    entity + group_by + measures to see the exact query the framework
    emits. Pair with ``psql`` / ``sqlite3 .read`` to run the SQL manually
    and compare row counts to the rendered bars.

    Scope filters are NOT included — explain shows the base query before
    row-level security is applied at request time. Add ``--scope`` later
    if we need to simulate a persona's predicate.
    """
    from dazzle.http.runtime.aggregate import (
        Dimension,
        build_aggregate_sql,
        resolve_fk_display_field,
    )

    project_root = Path.cwd().resolve()
    appspec = load_project_appspec(project_root)

    src_entity = next(
        (e for e in appspec.domain.entities if e.name == entity),
        None,
    )
    if src_entity is None:
        console.print(f"[red]Unknown entity:[/red] {entity}")
        raise typer.Exit(code=1)

    dim_names = [d.strip() for d in group_by.split(",") if d.strip()]
    if not dim_names:
        console.print("[red]--group-by is required[/red] (e.g. '--group-by system,severity')")
        raise typer.Exit(code=1)

    # Resolve each dim — scalar vs FK + target display field.
    dimensions: list[Dimension] = []
    for dim_name in dim_names:
        field = next((f for f in src_entity.fields if f.name == dim_name), None)
        if field is None:
            console.print(f"[red]Unknown field {entity}.{dim_name}[/red]")
            raise typer.Exit(code=1)
        is_fk = field.type.kind == FieldTypeKind.REF
        fk_table = None
        fk_display_field = None
        if is_fk:
            fk_table = field.type.ref_entity
            target = next(
                (e for e in appspec.domain.entities if e.name == fk_table),
                None,
            )
            fk_display_field = resolve_fk_display_field(target)
        dimensions.append(
            Dimension(name=dim_name, fk_table=fk_table, fk_display_field=fk_display_field)
        )

    # Parse measures: 'n=count,avg_score=avg:score' → {'n': 'count', 'avg_score': 'avg:score'}
    # #1359 slice 2: anything that is NOT a recognised aggregate spec is
    # treated as a derived-metric expression (e.g. 'rate=done/total*100') and
    # shown as the Python post-aggregation step — keeping this detector live
    # for the derived-metrics path, not merely documented.
    _AGG_SPECS = ("count", "sum:", "avg:", "min:", "max:")
    measure_dict: dict[str, str] = {}
    derived_dict: dict[str, str] = {}
    for pair in measures.split(","):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        name, _, expr = pair.partition("=")
        expr = expr.strip()
        if expr == "count" or expr.startswith(_AGG_SPECS[1:]):
            measure_dict[name.strip()] = expr
        else:
            derived_dict[name.strip()] = expr

    sql, params = build_aggregate_sql(
        table_name=src_entity.name,
        placeholder_style="%s",
        dimensions=dimensions,
        measures=measure_dict,
        filters=None,
        limit=limit,
    )

    if not sql:
        console.print(
            "[yellow]No SQL generated[/yellow] — no supported measures "
            "(recognised: count, sum:<col>, avg:<col>, min:<col>, max:<col>)."
        )
        return

    console.print("\n[bold]Aggregate SQL[/bold] ([dim]no scope filter — base query[/dim])")
    # Split for readability, but re-insert FROM on the follow-on line so the
    # printed SQL is still a valid standalone statement (#854).
    parts = sql.split(" FROM ", 1)
    console.print(parts[0])
    if len(parts) == 2:
        console.print(f"FROM {parts[1]}")
    console.print("")
    console.print(f"[bold]Params:[/bold] {params}")
    if derived_dict:
        console.print(
            "\n[bold]Post-aggregation (Python, #1359)[/bold] "
            "([dim]evaluated per bucket over the metric values above — "
            "zero extra queries; division by zero → 0[/dim])"
        )
        for name, expr in derived_dict.items():
            console.print(f"  {name} = {expr}")


@db_app.command(name="explain-scope")
def explain_scope_command(
    entity: str = typer.Argument(..., help="Entity name (e.g. AIJob)"),
    verb: str = typer.Argument(..., help="read | list | create | update | delete"),
    persona: str = typer.Option("", "--persona", "-p", help="Filter to one persona"),
) -> None:
    """Print the compiled scope predicate, app-layer WHERE, and RLS policy (or the
    #1447 degradation reason) for <Entity>.<verb> — the #1448 traceability oracle."""
    from dazzle.http.runtime.predicate_compiler import (
        build_entity_type_resolver,
        compile_predicate,
        compile_predicate_policy,
    )

    project_root = Path.cwd().resolve()
    appspec = load_project_appspec(project_root)
    ent = next((e for e in appspec.domain.entities if e.name == entity), None)
    if ent is None or ent.access is None:
        console.print(f"[red]No scoped entity:[/red] {entity}")
        raise typer.Exit(code=1)

    fk_graph = appspec.fk_graph or FKGraph.from_entities(appspec.domain.entities)
    entity_types = build_entity_type_resolver(appspec.domain.entities)
    rules = [
        r
        for r in ent.access.scopes
        if (r.operation.value if hasattr(r.operation, "value") else str(r.operation)) == verb
        and (not persona or persona in (r.personas or []))
    ]
    if not rules:
        console.print(f"[yellow]No {verb} scope rules on {entity}[/yellow]")
        return

    for rule in rules:
        personas = ", ".join(rule.personas or []) or "*"
        console.print(f"\n[bold]{entity}.{verb}[/bold] (as {personas})")
        console.print(f"[dim]predicate:[/dim] {rule.predicate!r}")
        sql, params = compile_predicate(rule.predicate, entity, fk_graph)
        console.print(f"[bold]app-layer WHERE:[/bold] {sql or '(no filter)'}")
        console.print(f"[dim]params:[/dim] {params}")
        try:
            body = compile_predicate_policy(
                rule.predicate, entity, fk_graph, entity_types=entity_types
            )
            console.print(f"[bold]RLS policy:[/bold] {body}")
            console.print("[green]verdict:[/green] RLS")
        except ValueError as exc:
            console.print(f"[yellow]verdict:[/yellow] app-layer (degraded: {exc})")


def _reset_entity_tables(
    project_root: Path,
    url: str,
    entities: list[Any],
    *,
    schema: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Truncate (or, with ``dry_run``, count) entity tables; auth is preserved.

    Shared by ``dazzle db reset`` and the ``dazzle qa trial --fresh-db`` pre-step.
    """
    from dazzle.db.reset import db_reset_impl

    async def _run(conn: Any) -> Any:
        return await db_reset_impl(entities=entities, conn=conn, dry_run=dry_run)

    result: dict[str, Any] = asyncio.run(
        _run_with_connection(project_root, url, _run, schema=schema)
    )
    return result
