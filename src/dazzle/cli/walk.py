"""CLI: ``dazzle test walk`` — list / validate scene walks (#1638 PR1)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from dazzle.cli.utils import load_project_appspec, project_root_from_manifest
from dazzle.core.manifest import resolve_api_url
from dazzle.testing.walk.discovery import default_walks_dir, discover_walk_paths
from dazzle.testing.walk.loader import load_walk
from dazzle.testing.walk.pack import pack_dry_run
from dazzle.testing.walk.runner import run_walk_sync
from dazzle.testing.walk.validate import validate_walk, validate_walks

walk_app = typer.Typer(
    name="walk",
    help=(
        "Scene walks: deterministic story-linked persona job paths (#1638). "
        "list | validate | run | pack-dry-run."
    ),
    no_args_is_help=True,
)


def _resolve_paths(
    root: Path,
    walks_dir: str | None,
    walk: str | None,
) -> list[Path]:
    wdir = Path(walks_dir).resolve() if walks_dir else None
    if walk:
        candidate = Path(walk)
        if candidate.is_file():
            return [candidate.resolve()]
        matches = [p for p in discover_walk_paths(root, walks_dir=wdir) if p.stem == walk]
        if not matches:
            typer.echo(f"Walk not found: {walk}", err=True)
            raise typer.Exit(code=1)
        return matches
    return discover_walk_paths(root, walks_dir=wdir)


def _try_appspec(root: Path, *, enabled: bool) -> Any:
    if not enabled:
        return None
    try:
        return load_project_appspec(root)
    except Exception as e:
        typer.echo(f"Warning: could not load AppSpec ({e}); schema-only checks", err=True)
        return None


def _list_json(paths: list[Path]) -> None:
    walks, _issues = validate_walks(paths)
    by_id = {w.walk_id: w for w in walks}
    rows: list[dict[str, Any]] = []
    for p in paths:
        w = by_id.get(p.stem)
        rows.append(
            {
                "walk_id": p.stem,
                "path": str(p),
                "persona": w.persona if w else None,
                "stories": w.story_ids() if w else [],
                "scenes": len(w.scenes) if w else 0,
                "core_only": w.core_only() if w else None,
                "load_ok": w is not None,
            }
        )
    typer.echo(json.dumps(rows, indent=2))


def _list_text(paths: list[Path], display_dir: Path) -> None:
    typer.echo(f"Walks dir: {display_dir}")
    if not paths:
        typer.echo("(no *.yaml walks found)")
        return
    walks, _ = validate_walks(paths)
    by_stem = {w.walk_id: w for w in walks}
    for p in paths:
        w = by_stem.get(p.stem)
        if w is None:
            typer.echo(f"  {p.stem:28s}  LOAD_ERROR  {p}")
            continue
        stories = ",".join(w.story_ids()) or "-"
        core = "core" if w.core_only() else "ext"
        typer.echo(
            f"  {w.walk_id:28s}  persona={w.persona:12s}  "
            f"scenes={len(w.scenes)}  stories={stories:12s}  {core}  {p.name}"
        )


@walk_app.command("list")
def walk_list(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    walks_dir: str | None = typer.Option(
        None,
        "--walks-dir",
        help="Override walks directory (default: fixtures/scene_walks)",
    ),
    json_output: bool = typer.Option(False, "--json", help="JSON array of walks"),
) -> None:
    """List scene walk fixtures under the project.

    Examples:
        dazzle test walk list
        dazzle test walk list -m examples/simple_task/dazzle.toml
        dazzle test walk list --json
    """
    root = project_root_from_manifest(manifest)
    paths = _resolve_paths(root, walks_dir, walk=None)
    display = Path(walks_dir).resolve() if walks_dir else default_walks_dir(root)
    if json_output:
        _list_json(paths)
    else:
        _list_text(paths, display)


@walk_app.command("validate")
def walk_validate(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    walks_dir: str | None = typer.Option(
        None,
        "--walks-dir",
        help="Override walks directory (default: fixtures/scene_walks)",
    ),
    walk: str | None = typer.Option(
        None,
        "--walk",
        "-w",
        help="Validate a single walk id (stem) or path",
    ),
    core_only: bool = typer.Option(
        False,
        "--core-only",
        help="Error on extension api_* actions (showcase CI)",
    ),
    require_story: bool = typer.Option(
        False,
        "--require-story",
        help="Error when a scene omits story:",
    ),
    no_appspec: bool = typer.Option(
        False,
        "--no-appspec",
        help="Skip persona/story AppSpec checks",
    ),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Validate scene walk YAML (schema + optional AppSpec cross-checks).

    Exit 1 when any error-level issue is found. Warnings do not fail CI.

    Examples:
        dazzle test walk validate -m examples/simple_task/dazzle.toml
        dazzle test walk validate --core-only --require-story
        dazzle test walk validate -w land_and_see_tasks
    """
    root = project_root_from_manifest(manifest)
    paths = _resolve_paths(root, walks_dir, walk)
    if not paths:
        typer.echo(
            f"No walks under {Path(walks_dir).resolve() if walks_dir else default_walks_dir(root)}",
            err=True,
        )
        raise typer.Exit(code=1)

    appspec = _try_appspec(root, enabled=not no_appspec)
    _walks, issues = validate_walks(
        paths,
        appspec=appspec,
        require_core_only=core_only,
        require_story=require_story,
    )
    errors = [i for i in issues if i.level == "error"]
    warnings = [i for i in issues if i.level == "warning"]

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "walks": len(paths),
                    "errors": len(errors),
                    "warnings": len(warnings),
                    "issues": [
                        {
                            "path": i.path,
                            "walk_id": i.walk_id,
                            "level": i.level,
                            "code": i.code,
                            "message": i.message,
                        }
                        for i in issues
                    ],
                },
                indent=2,
            )
        )
    else:
        typer.echo(
            f"Validated {len(paths)} walk(s): {len(errors)} error(s), {len(warnings)} warning(s)"
        )
        for i in issues:
            typer.echo(i.format(), err=(i.level == "error"))

    raise typer.Exit(code=1 if errors else 0)


def _resolve_base_url(root: Path, base_url: str | None) -> str:
    if base_url:
        return base_url.rstrip("/")
    try:
        return resolve_api_url().rstrip("/")
    except Exception:
        return "http://127.0.0.1:8000"


def _print_run_result(run_result: Any) -> None:
    typer.echo(run_result.summary())
    for scene in run_result.scenes:
        mark = "ok" if scene.ok else "FAIL"
        typer.echo(f"  scene {scene.scene_id}: {mark}")
        for ar in scene.actions:
            am = "  +" if ar.ok else "  -"
            typer.echo(f"    {am} {ar.type}: {ar.message}")


def _run_result_dict(run_result: Any) -> dict[str, Any]:
    return {
        "walk_id": run_result.walk_id,
        "persona": run_result.persona,
        "ok": run_result.ok,
        "dry_run": run_result.dry_run,
        "base_url": run_result.base_url,
        "error": run_result.error,
        "scenes": [
            {
                "id": s.scene_id,
                "ok": s.ok,
                "story": s.story,
                "actions": [{"type": a.type, "ok": a.ok, "message": a.message} for a in s.actions],
            }
            for s in run_result.scenes
        ],
    }


def _run_one_walk(
    path: Path,
    *,
    root: Path,
    url: str,
    dry_run: bool,
    playwright: bool,
    core_only: bool,
    timeout: float,
    quiet: bool,
) -> dict[str, Any]:
    w = load_walk(path)
    errors = [i for i in validate_walk(w, require_core_only=core_only) if i.level == "error"]
    if errors:
        msg = "; ".join(i.message for i in errors)
        if not quiet:
            typer.echo(f"FAIL {w.walk_id}: preflight — {msg}", err=True)
        return {"walk_id": w.walk_id, "ok": False, "error": msg, "dry_run": dry_run}

    run_result = run_walk_sync(
        w,
        base_url=url,
        project_root=root,
        dry_run=dry_run,
        use_playwright=playwright,
        timeout_s=timeout,
    )
    if not quiet:
        _print_run_result(run_result)
    return _run_result_dict(run_result)


@walk_app.command("run")
def walk_run(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    walks_dir: str | None = typer.Option(None, "--walks-dir"),
    walk: str | None = typer.Option(
        None,
        "--walk",
        "-w",
        help="Run a single walk id (stem) or path (default: all walks)",
    ),
    base_url: str | None = typer.Option(
        None,
        "--base-url",
        "-u",
        help="App base URL (default: resolve_api_url / localhost:8000)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Plan only — no network (validates load + lists steps)",
    ),
    playwright: bool = typer.Option(
        False,
        "--playwright",
        help="Enable playwright_click / playwright_wait (requires playwright)",
    ),
    core_only: bool = typer.Option(
        False,
        "--core-only/--allow-extension",
        help="Refuse walks with extension api_* actions (default: allow; #1639)",
    ),
    json_output: bool = typer.Option(False, "--json"),
    timeout: float = typer.Option(30.0, "--timeout", help="HTTP timeout seconds"),
) -> None:
    """Run scene walks against a live app (HTTP core + api_* extensions).

    Auth uses SessionManager (``/__test__/authenticate`` in test mode, or
    login fallback). Start the app with ``dazzle serve --test-mode`` (or
    equivalent) so persona sessions can be created.

    ``api_*`` setup/assert verbs are supported (#1639). Use ``--core-only``
    for showcase apps that must not use extensions.

    Examples:
        dazzle test walk run -m examples/simple_task/dazzle.toml --dry-run --core-only
        dazzle test walk run -m examples/simple_task/dazzle.toml -u http://127.0.0.1:8765
        dazzle test walk run -w vat_approve_customer -u $URL --playwright
    """
    root = project_root_from_manifest(manifest)
    paths = _resolve_paths(root, walks_dir, walk)
    if not paths:
        typer.echo("No walks found", err=True)
        raise typer.Exit(code=1)

    url = _resolve_base_url(root, base_url)
    results = [
        _run_one_walk(
            p,
            root=root,
            url=url,
            dry_run=dry_run,
            playwright=playwright,
            core_only=core_only,
            timeout=timeout,
            quiet=json_output,
        )
        for p in paths
    ]
    any_fail = any(not r.get("ok") for r in results)
    if json_output:
        typer.echo(json.dumps({"results": results, "ok": not any_fail}, indent=2))
    raise typer.Exit(code=1 if any_fail else 0)


def _emit_pack_json(result: Any, *, seed: bool) -> None:
    payload: dict[str, Any] = {
        "pack": result.pack,
        "ok": result.ok,
        "guides": result.guides,
        "walk_ids": result.walk_ids,
        "residuals": result.residuals,
        "claim_errors": len([i for i in result.claim_issues if i.level == "error"]),
        "walk_failures": sum(1 for w in result.walk_results if not w.ok),
    }
    if not seed:
        payload["claim_issues"] = [
            {
                "guide_id": i.guide_id,
                "level": i.level,
                "code": i.code,
                "message": i.message,
            }
            for i in result.claim_issues
        ]
        payload["walk_summaries"] = [w.summary() for w in result.walk_results]
    typer.echo(json.dumps(payload, indent=2))


def _emit_pack_text(result: Any, *, execute: bool) -> None:
    mode = "execute" if execute else "dry-run"
    status = "PASS" if result.ok else "FAIL"
    typer.echo(
        f"{status} pack={result.pack} [{mode}] "
        f"guides={len(result.guides)} walks={len(result.walk_ids)} "
        f"residuals={len(result.residuals)}"
    )
    for i in result.claim_issues:
        typer.echo(i.format(), err=(i.level == "error"))
    for wr in result.walk_results:
        typer.echo(f"  {wr.summary()}")
    if result.residuals:
        typer.echo(f"\n{len(result.residuals)} residual(s) for agent seed:")
        for g in result.residuals:
            typer.echo(f"  - [{g['kind']}] {g['description']}")


@walk_app.command("pack-dry-run")
def walk_pack_dry_run(
    pack: str = typer.Option(
        ...,
        "--pack",
        "-p",
        help="Pack letter from job claim registry (e.g. A, B)",
    ),
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    execute: bool = typer.Option(
        False,
        "--execute",
        help="Live-run walks (default: dry-run / no network)",
    ),
    base_url: str | None = typer.Option(None, "--base-url", "-u"),
    seed: bool = typer.Option(
        False,
        "--seed",
        help="Print residuals as agent seed gaps (JSON); does not write backlog",
    ),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Dry-run all scene walks bound to claims in a pack (A/B/C).

    Filters ``fixtures/job_claims.yaml`` by ``pack:``, validates those claims,
    and dry-runs (or ``--execute``) each bound walk. Residuals are suitable
    for ``dazzle agent seed improve`` (kind=walk_claim).

    Examples:
        dazzle test walk pack-dry-run -m examples/simple_task/dazzle.toml --pack A
        dazzle test walk pack-dry-run --pack A --seed --json
    """
    root = project_root_from_manifest(manifest)
    appspec = _try_appspec(root, enabled=True)
    try:
        result = pack_dry_run(
            root,
            pack,
            appspec=appspec,
            execute=execute,
            base_url=base_url or _resolve_base_url(root, None),
        )
    except FileNotFoundError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1)

    if seed or json_output:
        _emit_pack_json(result, seed=seed)
    else:
        _emit_pack_text(result, execute=execute)
    raise typer.Exit(code=0 if result.ok else 1)
