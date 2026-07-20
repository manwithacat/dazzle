"""CLI: ``dazzle test walk`` — list / validate scene walks (#1638 PR1)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from dazzle.cli.utils import load_project_appspec
from dazzle.testing.walk.discovery import default_walks_dir, discover_walk_paths
from dazzle.testing.walk.validate import validate_walks

walk_app = typer.Typer(
    name="walk",
    help=(
        "Scene walks: deterministic story-linked persona job paths (#1638). "
        "PR1: list + validate. PR2: run."
    ),
    no_args_is_help=True,
)


def _project_root(manifest: str) -> Path:
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent if manifest_path.is_file() else manifest_path
    if not (root / "dazzle.toml").exists():
        typer.echo(f"No dazzle.toml found in {root}", err=True)
        raise typer.Exit(code=1)
    return root


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
    root = _project_root(manifest)
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
    root = _project_root(manifest)
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
