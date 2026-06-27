"""Executable contract for the DB-artifact registry (#1495 follow-on, ADR-0047).

Static (no DB). Asserts the registry's declared properties against the code:
  (1) every registered boot_entry self-gates with skip_boot_schema_ddl();
  (2) every framework function issuing app-DB CREATE TABLE/INDEX is registered;
  (3) creator/boot_entry dotted-refs resolve;
  (4) FENCED artifacts carry FORCE RLS in the generator (the framework fences none).
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pathlib
import textwrap

import pytest

from dazzle.db.artifact_registry import (
    DB_ARTIFACTS,
    ArtifactClass,
    RlsPosture,
    concrete_creators,
    framework_boot_entries,
)

pytestmark = pytest.mark.gate

_REPO = pathlib.Path(__file__).resolve().parents[2]


def _resolve(dotted: str) -> object:
    """Resolve a dotted ref module.path.Class.method or module.path.func."""
    parts = dotted.split(".")
    for i in range(len(parts), 0, -1):
        mod_name = ".".join(parts[:i])
        try:
            obj: object = importlib.import_module(mod_name)
        except ModuleNotFoundError:
            continue
        for attr in parts[i:]:
            obj = getattr(obj, attr)
        return obj
    raise ModuleNotFoundError(dotted)


def _calls_skip_boot(dotted: str) -> bool:
    """True iff the function actually GUARDS on skip_boot_schema_ddl — i.e. contains
    ``if skip_boot_schema_ddl(): <return/raise>``. Checks the guard structure, not mere
    name presence, so a copy-paste that calls skip_boot_schema_ddl() without the
    early-return (the result ignored) does NOT pass."""
    fn = _resolve(dotted)
    src = textwrap.dedent(inspect.getsource(fn))  # type: ignore[arg-type]
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Call)
            and isinstance(node.test.func, ast.Name)
            and node.test.func.id == "skip_boot_schema_ddl"
        ):
            # the guarded branch must short-circuit (return/raise) before any DDL
            if any(isinstance(s, ast.Return | ast.Raise) for b in node.body for s in ast.walk(b)):
                return True
    return False


# ── (3) refs resolve ─────────────────────────────────────────────────────


def test_every_creator_and_boot_entry_resolves() -> None:
    for ref in concrete_creators():
        # patterns/dynamic class rows point at modules, not callables — module import
        # is enough; concrete callables resolve fully. Both go through _resolve.
        _resolve(ref)


# ── (1) registered boot-entries self-gate ────────────────────────────────


def test_registered_boot_entries_self_gate() -> None:
    failures = []
    for a in framework_boot_entries():
        assert a.boot_entry is not None
        if a.boot_ddl_gated and not _calls_skip_boot(a.boot_entry):
            failures.append(
                f"{a.name}: boot_entry {a.boot_entry} does not call "
                f"skip_boot_schema_ddl() (the #1495 class)"
            )
    assert not failures, "\n".join(failures)


def test_known_ungated_debt_is_honest() -> None:
    """A row flagged known_ungated_issue must genuinely be ungated today — and when
    its issue is fixed (the boot_entry gains the gate), this test flips red, reminding
    the fixer to clear the marker + set boot_ddl_gated=True."""
    for a in framework_boot_entries():
        if a.known_ungated_issue is None:
            continue
        assert a.boot_ddl_gated is False
        assert a.boot_entry is not None
        assert not _calls_skip_boot(a.boot_entry), (
            f"{a.name}: boot_entry now gates — clear known_ungated_issue "
            f"({a.known_ungated_issue}) and set boot_ddl_gated=True"
        )


# ── (2) completeness sweep — every app-DB DDL function is registered ──────

# The WHOLE framework source tree is scanned (minus tests) — no per-directory
# allowlist that could hide a DDL path in an unscanned dir (the hole that let
# channels/outbox.py — #1499 — evade an earlier 3-dir version of this sweep).
_SCAN_ROOT = "src/dazzle"

# The excluded-classes list, MADE EXECUTABLE — FUNCTION-LEVEL entries only (a
# module-level prefix would silently exempt every FUTURE function added to that
# module). Each entry is a DDL-issuing function that is intentionally NOT an
# app-DB framework table; a NEW DDL function anywhere is flagged until it is
# registered or explicitly added here with a reason.
_ALLOWLIST = frozenset(
    {
        # ── separate ops_integration DB (class OPS_DB; not app-DB framework tables) ──
        "dazzle.http.runtime.ops_database.OpsDatabase._init_schema",
        "dazzle.http.runtime.ops_database.OpsDatabase._apply_migrations",
        "dazzle.http.runtime.deploy_history.DeployHistoryStore._ensure_table",
        "dazzle.http.runtime.spec_versioning.SpecVersionStore._ensure_table",
        # ── app-entity / codegen DDL machinery (class APP_ENTITY; per-DSL, not framework) ──
        "dazzle.http.runtime.pg_backend._create_table_sql",
        "dazzle.http.runtime.pg_backend._create_index_sql",
        "dazzle.http.runtime.relation_loader.get_foreign_key_indexes",
        "dazzle.http.runtime.fts_postgres.PostgresFTSBackend.create_fts_index",
        "dazzle.http.runtime.search_schema.build_search_index_ddl",
        "dazzle.cli.runtime_impl.build._generate_sql_target",  # codegen SQL target
        # ── non-app-DB stores (SQLite / ops) ──
        "dazzle.mcp.knowledge_graph.store.KnowledgeGraph._init_schema",  # SQLite KG (ADR-0008 ok)
        "dazzle.core.process.version_manager.VersionManager.initialize",  # SQLite version store
        # ── process-table http boot path: dead-in-prod, no live caller (ADR-0044) ──
        "dazzle.http.runtime.process_schema.ensure_process_tables",
        # ── alternative creators of ALREADY-REGISTERED framework tables ──
        # (the orchestrator owns the canonical baseline DDL for these two; these are
        # the standalone / lazy-mutation-path creators of the same table.)
        "dazzle.http.runtime.migrations.ensure_dazzle_params_table",  # → _dazzle_params
        "dazzle.http.runtime.atomic_flow_executor.ensure_atomic_audit_table",  # → _dazzle_atomic_audit
    }
)

# Test files legitimately contain DDL fixtures; they are not framework code paths.
_TEST_MARKERS = ("/tests/", "/test_")


def _module_name(path: pathlib.Path) -> str:
    rel = path.relative_to(_REPO / "src").with_suffix("")
    return ".".join(rel.parts)


def _issues_ddl(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True iff the function body contains a STRING LITERAL with CREATE TABLE/INDEX.

    Inspects ast.Constant str values (so comments never match) and skips the
    function's own docstring (so a function that merely *mentions* CREATE INDEX in
    its docstring — e.g. EventOutbox._index_exists — is not a false positive)."""
    docstring_node = (
        fn.body[0].value
        if fn.body
        and isinstance(fn.body[0], ast.Expr)
        and isinstance(fn.body[0].value, ast.Constant)
        else None
    )
    for node in ast.walk(fn):
        if node is docstring_node:
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "CREATE TABLE" in node.value or "CREATE INDEX" in node.value:
                return True
    return False


def _ddl_functions() -> list[tuple[str, str]]:
    """(dotted_ref, file) for every non-test function in the framework tree that
    issues app-DB DDL (a CREATE TABLE/INDEX string literal in its body)."""
    out: list[tuple[str, str]] = []
    for path in sorted((_REPO / _SCAN_ROOT).rglob("*.py")):
        posix = path.as_posix()
        if any(m in posix for m in _TEST_MARKERS):
            continue
        src = path.read_text()
        if "CREATE TABLE" not in src and "CREATE INDEX" not in src:
            continue
        tree = ast.parse(src)
        mod = _module_name(path)
        # map each function node to its enclosing class (if any)
        class_of: dict[ast.AST, str] = {}
        for cls in ast.walk(tree):
            if isinstance(cls, ast.ClassDef):
                for child in cls.body:
                    class_of[child] = cls.name
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and _issues_ddl(node):
                cls_name = class_of.get(node)
                ref = f"{mod}.{cls_name}.{node.name}" if cls_name else f"{mod}.{node.name}"
                out.append((ref, str(path)))
    return out


def _allowlisted(ref: str) -> bool:
    # EXACT match only — function-level entries, no module-prefix blinding.
    return ref in _ALLOWLIST


def test_every_app_db_ddl_function_is_registered() -> None:
    registered = concrete_creators()
    unaccounted = []
    for ref, path in _ddl_functions():
        if ref in registered or _allowlisted(ref):
            continue
        unaccounted.append(
            f"{ref}  ({path}) issues CREATE TABLE/INDEX but is not in the registry "
            f"and not allowlisted — register it (decide its boot_ddl_gated) or add to "
            f"_ALLOWLIST with a reason"
        )
    assert not unaccounted, "\n".join(unaccounted)


# ── (4) RLS posture matches reality (framework fences none of its own tables) ──


def test_framework_internal_tables_are_not_rls_fenced() -> None:
    """RLS (build_all_rls_ddl) is applied only to app entities; the framework does
    NOT FORCE-fence its own internal tables. So every FRAMEWORK_INTERNAL row must be
    NON_FENCED. If that ever changes (a framework table gains a fence), flip its
    registry row to FENCED and update this invariant."""
    for a in DB_ARTIFACTS:
        if a.cls is not ArtifactClass.FRAMEWORK_INTERNAL or a.is_pattern:
            continue
        assert a.rls is RlsPosture.NON_FENCED, (
            f"{a.name}: FRAMEWORK_INTERNAL declared rls={a.rls.value}; the framework "
            f"does not fence its own tables (RLS is app-entity-only) — expected NON_FENCED"
        )
