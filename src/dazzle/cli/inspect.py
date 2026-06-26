"""``dazzle inspect <ext-point>`` — introspect framework extension points.

Closes #1120. The framework has clean extension points for renderers,
primitives, route overrides, and OAuth providers — but until v0.71.23
there was no way to ask "what does this app know about right now?"
without attaching a debugger to ``app.state.services.*_registry._handlers``.

This module surfaces the four ext-points (plus the existing api-surface
introspection from v0.66.x #961) under a unified ``dazzle inspect``
command group. Each subcommand has two modes:

- **Manifest-only (default, ~50ms)** — parses ``dazzle.toml`` plus the
  AppSpec, lists everything DECLARED. Fast, no app boot, suitable for
  CI checks and quick inspection. Shows what the framework's link-time
  validator would accept.
- **``--runtime`` (slow, ~3-10s)** — additionally boots the app,
  reaches into ``app.state.services`` (or the equivalent registry),
  and cross-references the declared set against what's actually
  registered at runtime. This is the only mode that catches the
  "declared in TOML but no handler registered" mismatch class —
  exactly the failure mode Penny Dreadful's renderer spike hit
  before #1116 + #1117 shipped.

Output: human pretty-print by default; ``--json`` for agent
consumption (same shape, mechanical JSON).

Per #1120's "rename inspect-api" decision, the existing api-surface
introspection lives under ``dazzle inspect api`` rather than the old
top-level ``dazzle inspect-api``. Clean break — no alias is kept.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import typer

from dazzle.api_surface import (
    dsl_constructs_module,
    ir_types_module,
    mcp_tools_module,
    public_helpers_module,
    runtime_urls_module,
)
from dazzle.core.appspec_loader import load_project_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.renderer_registry import _DEFAULT_RENDERERS

# =============================================================================
# Group: dazzle inspect <ext-point>
# =============================================================================

inspect_app = typer.Typer(
    help=(
        "Introspect framework extension points (renderers, primitives, "
        "routes, oauth-providers) and the public API surface (api). "
        "Defaults to a manifest-only view; pass --runtime to boot the "
        "app and cross-reference what's registered at request time."
    ),
    no_args_is_help=True,
)


# =============================================================================
# Result types — uniform shape across ext-points so the JSON output is
# machine-comparable and the human output can share a printer.
# =============================================================================


@dataclass
class InspectEntry:
    """One inspectable thing — a renderer, primitive, route, OAuth provider.

    ``source`` is one of:
      - ``"framework"`` — built-in default (e.g. the `fragment` renderer)
      - ``"manifest"`` — declared in dazzle.toml
      - ``"runtime"`` — registered at runtime but NOT declared (drift!)
    """

    name: str
    source: str
    detail: str = ""
    registered: bool | None = None
    declared: bool | None = None


@dataclass
class InspectResult:
    """The unified report shape every subcommand returns."""

    ext_point: str
    entries: list[InspectEntry] = field(default_factory=list)
    mismatches: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# =============================================================================
# Common helpers
# =============================================================================


def _resolve_project_root(project_path: Path | None) -> Path:
    """Resolve the project root from the optional CLI arg, falling back
    to the current directory if --project isn't passed."""
    root = (project_path or Path.cwd()).resolve()
    if not (root / "dazzle.toml").exists():
        typer.echo(
            f"No dazzle.toml at {root} — pass --project or cd into a Dazzle project.",
            err=True,
        )
        raise typer.Exit(2)
    return root


def _load_manifest(project_root: Path) -> Any:
    """Load the project manifest. Imported lazily to avoid paying the
    parser cost on `--help`."""

    return load_manifest(project_root / "dazzle.toml")


def _load_appspec(project_root: Path) -> Any:
    """Load and link the full AppSpec. ~50ms for typical projects."""

    return load_project_appspec(project_root)


def _emit(result: InspectResult, output_json: bool) -> None:
    """Serialise + emit the result, then exit non-zero if any mismatches."""
    if output_json:
        payload = {
            "ext_point": result.ext_point,
            "entries": [
                {
                    "name": e.name,
                    "source": e.source,
                    "detail": e.detail,
                    "registered": e.registered,
                    "declared": e.declared,
                }
                for e in result.entries
            ],
            "mismatches": result.mismatches,
            "notes": result.notes,
        }
        typer.echo(json.dumps(payload, indent=2))
    else:
        _print_human(result)

    if result.mismatches:
        sys.exit(1)


def _print_human(result: InspectResult) -> None:
    """Plain-text rendering. No rich dependency; matches the inspect-api
    style so the output works in any terminal."""
    typer.echo(f"{result.ext_point} ({len(result.entries)}):")
    if not result.entries:
        typer.echo("  (none)")
    else:
        name_width = max(len(e.name) for e in result.entries)
        for e in result.entries:
            marker = ""
            if e.declared is True and e.registered is False:
                marker = "  ⚠️  declared in manifest but no runtime handler"
            elif e.declared is False and e.registered is True:
                marker = "  ⚠️  registered at runtime but not declared in manifest"
            typer.echo(f"  - {e.name:<{name_width}}  {e.source:<10}  {e.detail}{marker}")

    for note in result.notes:
        typer.echo(f"\nnote: {note}")

    if result.mismatches:
        typer.echo("")
        typer.echo(f"FAIL: {len(result.mismatches)} mismatch(es):", err=True)
        for m in result.mismatches:
            typer.echo(f"  - {m}", err=True)


# =============================================================================
# inspect renderers
# =============================================================================


@inspect_app.command("renderers")
def renderers_command(
    project: Path | None = typer.Option(
        None, "--project", "-p", help="Project root (default: cwd)"
    ),
    output_json: bool = typer.Option(False, "--json", help="Emit JSON instead of human text"),
    runtime: bool = typer.Option(
        False,
        "--runtime",
        help=(
            "Boot the app and cross-reference declared vs registered renderers. "
            "~3-10s instead of ~50ms; catches the 'declared but not registered' "
            "mismatch class. Off by default."
        ),
    ),
) -> None:
    """List renderers declared in dazzle.toml + framework defaults.

    With ``--runtime``, also lists what's registered at request time
    on ``services.renderer_registry`` and flags any mismatches.
    """
    project_root = _resolve_project_root(project)
    manifest = _load_manifest(project_root)

    declared = set(manifest.renderers.extra)
    framework_defaults = set(_DEFAULT_RENDERERS)

    entries: list[InspectEntry] = []
    for name in sorted(framework_defaults):
        entries.append(
            InspectEntry(
                name=name,
                source="framework",
                detail="framework default",
                declared=True,
                registered=True if not runtime else None,
            )
        )
    for name in sorted(declared):
        entries.append(
            InspectEntry(
                name=name,
                source="manifest",
                detail="declared in [renderers] extra",
                declared=True,
            )
        )

    result = InspectResult(ext_point="renderers", entries=entries)
    if not runtime:
        result.notes.append(
            "Manifest-only view — pass --runtime to cross-reference what's actually "
            "registered on services.renderer_registry at request time."
        )

    if runtime:
        registered_names, boot_error, boot_note = _boot_and_get_registered_names(
            "renderer_registry", project_root
        )
        if boot_note:
            result.notes.append(boot_note)
        if boot_error:
            result.notes.append(f"--runtime: {boot_error}")
        else:
            _cross_reference(entries, result, registered_names, framework_defaults | declared)

    _emit(result, output_json)


# =============================================================================
# inspect primitives
# =============================================================================


@inspect_app.command("primitives")
def primitives_command(
    project: Path | None = typer.Option(None, "--project", "-p", help="Project root"),
    output_json: bool = typer.Option(False, "--json", help="Emit JSON instead of human text"),
    runtime: bool = typer.Option(
        False, "--runtime", help="Boot the app to introspect registered primitives"
    ),
) -> None:
    """List primitives registered on the PrimitiveRegistry.

    Primitives don't have a manifest table (yet) — the declaration
    surface is the ``@primitive`` decorator applied at import time.
    Without ``--runtime`` this command can only show what the
    framework ships built-in.
    """
    project_root = _resolve_project_root(project)

    entries: list[InspectEntry] = []
    result = InspectResult(ext_point="primitives", entries=entries)

    if not runtime:
        result.notes.append(
            "Primitives are registered via the @primitive decorator at import "
            "time — there's no manifest table for them. Pass --runtime to boot "
            "the app and list what's actually registered."
        )
        _emit(result, output_json)
        return

    registered_names, boot_error, boot_note = _boot_and_get_registered_names(
        "primitive_registry", project_root
    )
    if boot_note:
        result.notes.append(boot_note)
    if boot_error:
        result.notes.append(f"--runtime: {boot_error}")
    else:
        for name in sorted(registered_names):
            entries.append(
                InspectEntry(
                    name=name,
                    source="runtime",
                    detail="registered via @primitive",
                    registered=True,
                )
            )

    _ = project_root  # currently unused; manifest plumbing for primitive declarations is a follow-up
    _emit(result, output_json)


# =============================================================================
# inspect routes
# =============================================================================

# Exact paths and prefixes used to bucket a live route. Buckets exist so an
# agent scanning the --runtime output can tell a traceable page route apart
# from framework plumbing (api fragments, health probes, docs).
_DOCS_ROUTES: frozenset[str] = frozenset(
    {"/docs", "/redoc", "/openapi.json", "/spec", "/health", "/db-info"}
)
_AUTH_ROUTES: frozenset[str] = frozenset(
    {"/login", "/signup", "/logout", "/forgot-password", "/reset-password"}
)
_AUTH_PREFIXES: tuple[str, ...] = (
    "/auth/",
    "/2fa/",
    "/login/",
    "/signup/",
    "/forgot-password/",
    "/reset-password/",
)

# Human/JSON output groups routes in this order — page routes (the ones an
# agent traces) first, framework plumbing last.
_ROUTE_CATEGORY_ORDER: dict[str, int] = {
    "workspace": 0,
    "surface": 1,
    "auth": 2,
    "api": 3,
    "docs": 4,
    "internal": 5,
}


def _categorise_route(path: str, workspace_names: frozenset[str]) -> str:
    """Bucket a live route path into workspace / surface / auth / api /
    docs / internal. ``workspace_names`` comes from the AppSpec so a
    ``/<workspace>/<entity>`` route is told apart from a top-level
    ``/<entity>`` surface route."""
    if path.startswith("/api/"):
        return "api"
    if path.startswith(("/_dazzle/", "/__", "/static")):
        return "internal"
    if path in _DOCS_ROUTES or path.startswith("/docs/"):
        return "docs"
    if path in _AUTH_ROUTES or path.startswith(_AUTH_PREFIXES):
        return "auth"
    segments = [s for s in path.split("/") if s]
    if segments and segments[0] in workspace_names:
        return "workspace"
    return "surface"


def _walk_runtime_routes(routes: Any, workspace_names: frozenset[str]) -> list[InspectEntry]:
    """Turn a booted app's route objects into categorised, sorted
    :class:`InspectEntry` rows.

    Accepts anything iterable yielding objects with ``.path`` and
    ``.methods`` (Starlette routes, or test doubles). HEAD/OPTIONS are
    dropped — Starlette auto-adds them, so the method column shows only
    the verb that matters. Page routes sort ahead of framework plumbing.
    """
    entries: list[InspectEntry] = []
    for route in routes:
        path = getattr(route, "path", None)
        if not path:
            continue
        methods = sorted(
            m for m in (getattr(route, "methods", None) or ()) if m not in ("HEAD", "OPTIONS")
        )
        category = _categorise_route(path, workspace_names)
        detail = f"{category}  {' '.join(methods)}".strip() if methods else category
        entries.append(InspectEntry(name=path, source="runtime", detail=detail, registered=True))
    entries.sort(key=lambda e: (_ROUTE_CATEGORY_ORDER.get(e.detail.split()[0], 9), e.name))
    return entries


@inspect_app.command("routes")
def routes_command(
    project: Path | None = typer.Option(None, "--project", "-p", help="Project root"),
    output_json: bool = typer.Option(False, "--json", help="Emit JSON instead of human text"),
    runtime: bool = typer.Option(
        False, "--runtime", help="Boot the app and list mounted route paths"
    ),
) -> None:
    """List project route extensions declared in dazzle.toml.

    Per ``[extensions] routers = [...]`` — each entry is a dotted
    ``module:attr`` spec the runtime mounts at app boot.

    With ``--runtime``, boots the app and lists every mounted route
    path, bucketed by category (workspace / surface / auth / api / docs
    / internal). This is how an agent discovers which URLs are worth
    pointing ``dazzle perf trace`` at — the page routes the framework
    auto-generates from workspaces and surfaces aren't knowable from
    ``dazzle.toml`` alone. ``--runtime`` needs a reachable database
    (set ``DATABASE_URL``); the route table is only complete on a
    booted app.
    """
    project_root = _resolve_project_root(project)
    manifest = _load_manifest(project_root)
    declared = list(manifest.extensions.routers)

    entries: list[InspectEntry] = []
    for spec in declared:
        entries.append(
            InspectEntry(
                name=spec,
                source="manifest",
                detail="declared in [extensions] routers",
                declared=True,
            )
        )

    result = InspectResult(ext_point="routes", entries=entries)
    if not runtime:
        result.notes.append(
            "Manifest-only view — pass --runtime to list every mounted route "
            "path on the live FastAPI app, bucketed by category. That's the "
            "only complete view of the workspace / surface page routes the "
            "framework auto-generates (needs DATABASE_URL set to boot)."
        )
        _emit(result, output_json)
        return

    app, message = _boot_app(project_root)
    if app is None:
        note = f"--runtime boot failed: {message}"
        if message and "database_url" in message.lower():
            note += (
                " — set DATABASE_URL to a reachable Postgres instance so "
                "--runtime can boot the app and enumerate every workspace / "
                "surface / auth route."
            )
        result.notes.append(note)
        _emit(result, output_json)
        return

    if message:  # ADR-0046 fallback note — boot succeeded via create_app
        result.notes.append(message)
    try:
        appspec = _load_appspec(project_root)
        workspace_names = frozenset(ws.name for ws in (getattr(appspec, "workspaces", None) or []))
    except Exception:
        # Categorisation degrades gracefully — workspace routes just fall
        # through to the "surface" bucket without the AppSpec.
        workspace_names = frozenset()

    entries.extend(_walk_runtime_routes(app.routes, workspace_names))

    _emit(result, output_json)


# =============================================================================
# inspect oauth-providers
# =============================================================================


@inspect_app.command("oauth-providers")
def oauth_providers_command(
    project: Path | None = typer.Option(None, "--project", "-p", help="Project root"),
    output_json: bool = typer.Option(False, "--json", help="Emit JSON instead of human text"),
) -> None:
    """List OAuth providers declared in dazzle.toml.

    Per ``[[auth.oauth_providers]]`` blocks. Manifest-only — there's
    no runtime registry for OAuth providers; the framework reads the
    manifest at app boot and wires the routes deterministically.
    """
    project_root = _resolve_project_root(project)
    manifest = _load_manifest(project_root)
    providers = list(manifest.auth.oauth_providers)

    entries = [
        InspectEntry(
            name=p.provider,
            source="manifest",
            detail=(
                f"client_id_env={p.client_id_env} "
                f"client_secret_env={p.client_secret_env} "
                f"scopes={','.join(p.scopes) or '(none)'}"
            ),
            declared=True,
        )
        for p in providers
    ]

    result = InspectResult(ext_point="oauth-providers", entries=entries)
    _emit(result, output_json)


# =============================================================================
# inspect rls — the generated (and --runtime live) RLS policy set
# =============================================================================


def _rls_entry(desc: Any) -> InspectEntry:
    """Turn a :class:`PolicyDescriptor` into an :class:`InspectEntry`.

    The ``detail`` column leads with the entity (table) name so the human and
    JSON output group by table, then the SQL command + PERMISSIVE/RESTRICTIVE —
    the shape the drift gate compares. ``source`` is the descriptor's provenance
    (``framework`` for the fence/baseline, ``scope-rule`` for a per-verb policy).
    """
    kind = "PERMISSIVE" if desc.permissive else "RESTRICTIVE"
    return InspectEntry(
        name=desc.name,
        source=desc.source,
        detail=f"{desc.entity}  {desc.cmd}  {kind}",
        declared=True,
    )


@inspect_app.command("rls")
def rls_command(
    project: Path | None = typer.Option(None, "--project", "-p", help="Project root"),
    output_json: bool = typer.Option(False, "--json", help="Emit JSON instead of human text"),
    runtime: bool = typer.Option(
        False,
        "--runtime",
        help=(
            "Connect to the database and cross-reference the generated policy "
            "set against live pg_policies (needs DATABASE_URL). Off by default "
            "(manifest-only, no DB)."
        ),
    ),
) -> None:
    """List the row-level-security policies the framework generates per tenant-scoped entity.

    Manifest-only by default: derives the expected policy set from the linked
    AppSpec (the same shape ``dazzle db apply-rls`` applies and ``dazzle db
    verify`` gates) — one entry per policy a tenant-scoped entity gets:
    ``tenant_fence`` (RESTRICTIVE, framework) + ``tenant_baseline`` (PERMISSIVE,
    framework) for a tenant-flat entity, or ``tenant_fence`` + per-verb
    ``scope_*`` (PERMISSIVE, scope-rule) for a DSL-``scope:``-governed entity.
    Apps with no row-level tenancy yield an empty result + a note.

    With ``--runtime``, also queries the live database's ``pg_policies`` /
    ``pg_class`` per tenant-scoped table and reports drift (expected-but-missing,
    unexpected-extra, RLS-not-enabled) as ``mismatches``.
    """
    project_root = _resolve_project_root(project)
    appspec = _load_appspec(project_root)

    # convert_entities gives the back-spec entities describe_rls_policies needs
    # (the scoped-vs-flat partition iterates these, mirroring build_all_rls_ddl).
    from dazzle.http.converters.entity_converter import convert_entities
    from dazzle.http.runtime.rls_schema import describe_rls_policies

    entities = convert_entities(appspec.domain.entities)
    descriptors = describe_rls_policies(appspec, entities)

    entries = [_rls_entry(d) for d in descriptors]
    result = InspectResult(ext_point="rls", entries=entries)

    if not descriptors:
        result.notes.append(
            "no row-level tenancy (tenancy: mode: shared_schema) — this app has "
            "no tenant-scoped entities, so no RLS policies are generated."
        )
        _emit(result, output_json)
        return

    if not runtime:
        result.notes.append(
            "Manifest-only view — pass --runtime to cross-reference the generated "
            "policy set against live pg_policies (needs DATABASE_URL set)."
        )
        _emit(result, output_json)
        return

    _rls_runtime_crossref(project_root, appspec, entities, descriptors, result)
    _emit(result, output_json)


def _rls_runtime_crossref(
    project_root: Path,
    appspec: Any,
    entities: list[Any],
    descriptors: list[Any],
    result: InspectResult,
) -> None:
    """Connect to the DB and fold live ``pg_policies`` drift into ``result``.

    A thin live-query: per tenant-scoped table, fetch the live policy names +
    whether RLS is enabled/forced, and record drift (expected-but-missing,
    unexpected-extra policy, RLS-not-enabled) as ``mismatches`` + a ``runtime``
    note. The authoritative, shape-by-shape drift gate (cmd + permissive checks,
    exit-non-zero) is ``dazzle db verify`` (Phase D Task 4 — ``detect_rls_drift``);
    this surface is the operator's at-a-glance "is it live?" view.
    """
    import asyncio

    from dazzle.cli.db import _resolve_url, _run_with_connection
    from dazzle.db.connection import fetchall, fetchrow

    expected_by_table: dict[str, set[str]] = {}
    for d in descriptors:
        expected_by_table.setdefault(d.entity, set()).add(d.name)

    url = _resolve_url("")

    async def _run(conn: Any) -> dict[str, dict[str, Any]]:
        live: dict[str, dict[str, Any]] = {}
        for table in expected_by_table:
            policy_rows = await fetchall(
                conn,
                "SELECT policyname FROM pg_policies WHERE schemaname = 'public' AND tablename = %s",
                (table,),
            )
            class_row = await fetchrow(
                conn,
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relname = %s AND relnamespace = 'public'::regnamespace",
                (table,),
            )
            live[table] = {
                "policies": {r["policyname"] for r in policy_rows},
                "enabled": bool(class_row["relrowsecurity"]) if class_row else False,
                "forced": bool(class_row["relforcerowsecurity"]) if class_row else False,
            }
        return live

    try:
        live = asyncio.run(_run_with_connection(project_root, url, _run))
    except Exception as exc:  # pragma: no cover - boot/connection failure path
        result.notes.append(
            f"--runtime DB query failed: {type(exc).__name__}: {exc} "
            "(needs a reachable DATABASE_URL; for the generated view, omit --runtime)"
        )
        return

    result.notes.append(
        "--runtime: cross-referenced against live pg_policies. For the "
        "authoritative drift gate (cmd + permissive checks, CI exit code) use "
        "`dazzle db verify`."
    )

    # Mark each expected entry registered-or-not against the live set.
    live_pairs: set[tuple[str, str]] = set()
    for table, info in live.items():
        for pname in info["policies"]:
            live_pairs.add((table, pname))

    for entry in result.entries:
        table = entry.detail.split()[0]
        entry.registered = (table, entry.name) in live_pairs

    for table, expected_names in sorted(expected_by_table.items()):
        info = live.get(table, {"policies": set(), "enabled": False, "forced": False})
        if not info["enabled"] or not info["forced"]:
            result.mismatches.append(
                f"`{table}` does not have RLS enabled+forced "
                f"(enabled={info['enabled']}, forced={info['forced']})"
            )
        for missing in sorted(expected_names - info["policies"]):
            result.mismatches.append(
                f"`{table}` is missing expected policy `{missing}` (not applied?)"
            )
        for extra in sorted(info["policies"] - expected_names):
            result.mismatches.append(
                f"`{table}` has unexpected policy `{extra}` (not in the generated set)"
            )
            result.entries.append(
                InspectEntry(
                    name=extra,
                    source="runtime",
                    detail=f"{table}  (live-only)",
                    declared=False,
                    registered=True,
                )
            )


# =============================================================================
# inspect api — rehosts the existing inspect-api subcommands (#961)
# =============================================================================

api_app = typer.Typer(
    help="Inspect / snapshot the framework's public API surface (renamed from `dazzle inspect-api` in #1120).",
    no_args_is_help=True,
)


def _emit_api_snapshot(snapshot: str, baseline_path: Path, write: bool, diff: bool) -> None:
    """Re-implementation of the original inspect_api._emit helper —
    kept local so the rename doesn't need a back-import from the old
    module (which now just re-exports for compat-shim-free clean break)."""
    if write:
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(snapshot, encoding="utf-8")
        typer.echo(f"Wrote {baseline_path.relative_to(baseline_path.parents[2])}")
        return

    if diff:
        if not baseline_path.exists():
            typer.echo(f"(no baseline at {baseline_path} — run with --write)")
            sys.exit(1)
        baseline = baseline_path.read_text(encoding="utf-8")
        if baseline == snapshot:
            typer.echo("No drift.")
            return
        import difflib

        diff_text = "".join(
            difflib.unified_diff(
                baseline.splitlines(keepends=True),
                snapshot.splitlines(keepends=True),
                fromfile=str(baseline_path),
                tofile="(live)",
                n=3,
            )
        )
        typer.echo(diff_text, nl=False)
        sys.exit(1)

    typer.echo(snapshot, nl=False)


@api_app.command("dsl-constructs")
def api_dsl_constructs(
    write: bool = typer.Option(False, "--write", help="Overwrite the on-disk baseline"),
    diff: bool = typer.Option(False, "--diff", help="Print unified diff vs baseline"),
) -> None:
    """Snapshot the DSL constructs surface (cycle 1, #961)."""
    _emit_api_snapshot(
        dsl_constructs_module.snapshot_dsl_constructs(),
        dsl_constructs_module.BASELINE_PATH,
        write,
        diff,
    )


@api_app.command("ir-types")
def api_ir_types(
    write: bool = typer.Option(False, "--write"),
    diff: bool = typer.Option(False, "--diff"),
) -> None:
    """Snapshot the IR types surface (cycle 2, #961)."""
    _emit_api_snapshot(
        ir_types_module.snapshot_ir_types(), ir_types_module.BASELINE_PATH, write, diff
    )


@api_app.command("mcp-tools")
def api_mcp_tools(
    write: bool = typer.Option(False, "--write"),
    diff: bool = typer.Option(False, "--diff"),
) -> None:
    """Snapshot the MCP tool schemas (cycle 3, #961)."""
    _emit_api_snapshot(
        mcp_tools_module.snapshot_mcp_tools(), mcp_tools_module.BASELINE_PATH, write, diff
    )


@api_app.command("public-helpers")
def api_public_helpers(
    write: bool = typer.Option(False, "--write"),
    diff: bool = typer.Option(False, "--diff"),
) -> None:
    """Snapshot the public helpers re-exported from `dazzle.__init__` (cycle 4, #961)."""
    _emit_api_snapshot(
        public_helpers_module.snapshot_public_helpers(),
        public_helpers_module.BASELINE_PATH,
        write,
        diff,
    )


@api_app.command("runtime-urls")
def api_runtime_urls(
    write: bool = typer.Option(False, "--write"),
    diff: bool = typer.Option(False, "--diff"),
) -> None:
    """Snapshot the runtime URL surface (cycle 5, #961)."""
    _emit_api_snapshot(
        runtime_urls_module.snapshot_runtime_urls(),
        runtime_urls_module.BASELINE_PATH,
        write,
        diff,
    )


inspect_app.add_typer(api_app, name="api")


# =============================================================================
# Runtime helpers (--runtime path)
# =============================================================================


def _boot_declared_entrypoint(spec: str, project_root: Path) -> Any:
    """Import the app's declared ``module:attr`` ASGI entrypoint (ADR-0046).

    Returns the app object on success, or a string error message. The
    project root is placed on ``sys.path`` (mirroring route-override
    import) so the entrypoint module resolves the same way it does under
    the app's own server.

    Captures import-time registration (e.g. an app that registers
    renderers synchronously after ``build()`` in its ``server.py``).
    Startup/lifespan-time registration is a best-effort follow-up (ADR-0046
    D4) — not entered here.
    """
    import importlib
    import sys

    module_name, _, attr = spec.partition(":")
    if not module_name or not attr:
        return f"invalid entrypoint spec {spec!r} (expected 'module:attr')"

    # Mirror route_overrides.py: insert the project root for the import, then
    # remove it in finally so repeated/in-process introspection doesn't
    # accumulate sys.path entries. The module stays cached in sys.modules, so
    # removing the path after a successful import is safe.
    root_str = str(project_root)
    added_to_path = root_str not in sys.path
    if added_to_path:
        sys.path.insert(0, root_str)
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        return f"import of {module_name!r} failed: {type(exc).__name__}: {exc}"
    finally:
        if added_to_path and root_str in sys.path:
            sys.path.remove(root_str)
    app = getattr(module, attr, None)
    if app is None:
        return f"module {module_name!r} has no attribute {attr!r}"
    return app


def _boot_app(project_root: Path) -> tuple[Any | None, str | None]:
    """Boot the project's FastAPI app for runtime introspection.

    Returns ``(app, message)``. When the manifest declares a real ASGI
    entrypoint (``[serve] app``, ADR-0046) that boots, returns
    ``(app, None)`` — introspection then reflects exactly what production
    runs. On entrypoint failure, falls back to the framework-default
    ``create_app`` and returns ``(app, note)`` where *note* explains the
    fallback (the boot itself succeeded). On hard failure returns
    ``(None, error)``.
    """
    # ADR-0046: prefer the app's own declared entrypoint so post-build
    # wiring done in the app's server (renderers, middleware, page auth)
    # is visible to introspection. Absent / unbootable → framework default.
    fallback_note: str | None = None
    try:
        manifest = _load_manifest(project_root)
        serve_app = getattr(getattr(manifest, "serve", None), "app", None)
    except Exception:
        serve_app = None
    if serve_app:
        app_or_error = _boot_declared_entrypoint(serve_app, project_root)
        if not isinstance(app_or_error, str):
            return app_or_error, None
        fallback_note = (
            f"declared entrypoint '{serve_app}' did not boot ({app_or_error}); "
            "introspected the framework-default app instead — results may differ "
            "from what your server registers (ADR-0046)"
        )

    try:
        appspec = _load_appspec(project_root)
    except Exception as exc:
        return None, f"failed to load AppSpec: {exc!r}"

    try:
        from dazzle.http.runtime.app_factory import create_app

        # database_url=None lets the factory default to env / fallbacks;
        # boot may still fail if PG isn't reachable, in which case we
        # return the exception to the caller.
        app = create_app(appspec, database_url=None)
    except Exception as exc:
        return None, (
            f"failed to boot app: {type(exc).__name__}: {exc} "
            "(--runtime needs a reachable database; for manifest-only "
            "inspection, omit --runtime)"
        )
    return app, fallback_note


def _boot_and_get_registered_names(
    registry_attr: str,
    project_root: Path,
) -> tuple[set[str], str | None, str | None]:
    """Boot the app and return ``services.<registry_attr>.registered_names()``.

    Returns ``(names, error, note)``. *error* is set only on a hard boot
    failure (and *names* is empty). *note* is an informational message —
    e.g. the ADR-0046 fallback notice — that the caller surfaces without
    treating it as a failure. *project_root* must be the caller's resolved
    root so the ADR-0046 ``[serve] app`` lookup honours ``--project``.
    """
    app, message = _boot_app(project_root)
    if app is None:
        return set(), message, None
    services = getattr(getattr(app, "state", None), "services", None)
    if services is None:
        return set(), "app booted but services not attached to app.state", message
    registry = getattr(services, registry_attr, None)
    if registry is None:
        return set(), f"app booted but services.{registry_attr} not present", message
    names = registry.registered_names() if hasattr(registry, "registered_names") else set()
    return set(names), None, message


def _cross_reference(
    entries: list[InspectEntry],
    result: InspectResult,
    registered_names: set[str],
    declared_names: set[str],
) -> None:
    """After the manifest-only entries are built and we've fetched the
    runtime-registered names, fold the runtime state in: mark declared
    entries as registered=True/False, add any registered-but-not-
    declared entries, and record mismatches."""
    declared_by_name = {e.name: e for e in entries}
    for entry in entries:
        entry.registered = entry.name in registered_names

    for name in sorted(registered_names - declared_names):
        entries.append(
            InspectEntry(
                name=name,
                source="runtime",
                detail="registered at runtime but not declared in manifest",
                declared=False,
                registered=True,
            )
        )
        result.mismatches.append(
            f"`{name}` is registered at runtime but not declared in dazzle.toml"
        )

    for name in sorted(declared_names - registered_names):
        # Only flag if the entry was actually declared (not framework default).
        declared_entry = declared_by_name.get(name)
        if declared_entry is not None and declared_entry.source == "manifest":
            result.mismatches.append(
                f"`{name}` is declared in dazzle.toml but no runtime handler is registered"
                " — if your app registers it in its own ASGI entrypoint (not"
                " `dazzle serve`), declare that entrypoint with `[serve] app ="
                ' "server:app"` so introspection boots the real app (ADR-0046)'
            )
