"""#1605 D4 — CLI prove (static binding evidence). No mcp package import."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from dazzle.agent_loop import prove_stories
from dazzle.representation import prove_representation_project

prove_app = typer.Typer(
    help="Prove story execution bindings (static evidence; not runtime journeys).",
    no_args_is_help=True,
)


@prove_app.command("story")
def prove_story(
    story_id: str = typer.Argument(
        None,
        help="Story id (omit to check all accepted)",
    ),
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    static: bool = typer.Option(
        True,
        "--static/--runtime",
        help="Static binding (default) or host-readiness runtime prove.",
    ),
    journey: bool = typer.Option(
        False,
        "--journey",
        help="Journey graph prove (hub/open-via/process). Implies beyond static.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Raw JSON only"),
) -> None:
    """Prove story bindings (static), host readiness (runtime), or journey graph.

    - ``--static``: ``pass_static`` / ``fail_static`` — target exists in DSL/host map
    - ``--runtime``: ``pass_runtime`` / ``fail_runtime`` — host service module ready
    - ``--journey``: ``pass_journey`` / ``fail_journey`` — VIEW hub + open-via hops
      coherent; process steps host-ready. **Not** Playwright e2e.
    """
    root = Path(manifest).resolve().parent
    if journey:
        mode = "journey"
    else:
        mode = "static" if static else "runtime"
    data = prove_stories(root, story_id=story_id, mode=mode)
    if json_out:
        typer.echo(json.dumps(data, indent=2, default=str))
    else:
        if data.get("error"):
            typer.echo(data["error"], err=True)
            raise typer.Exit(1)
        kind = data.get("evidence_kind") or mode
        typer.echo(
            f"prove --{kind}: {data.get('passed')}/{data.get('checked')} passed "
            f"(failed={data.get('failed')}"
            + (f", skipped={data.get('skipped')}" if data.get("skipped") is not None else "")
            + ")"
        )
        for r in data.get("results") or []:
            res = r.get("result")
            mark = (
                "OK"
                if str(res).startswith("pass")
                else ("SKIP" if str(res).startswith("skip") else "FAIL")
            )
            typer.echo(f"  [{mark}] {r.get('story_id')}: {res} ({r.get('reason')})")
            for e in r.get("evidence") or []:
                typer.echo(f"         evidence: {e}")
        if data.get("note"):
            typer.echo(f"note: {data['note']}")
    if not data.get("ok"):
        raise typer.Exit(1)


@prove_app.command("representation")
def prove_representation_cmd(
    project: Path = typer.Option(
        Path("."),
        "--project",
        "-p",
        help="Project root (directory with dazzle.toml).",
    ),
    json_out: bool = typer.Option(False, "--json", help="Raw JSON only"),
) -> None:
    """#1617 prove data-representation integrity (static AppSpec).

    Fails on hand-rolled poly pairs, multi open-via without exclusive-anchor
    invariant, or exclusive invariant without first_non_null list open.
    Complements ``dazzle db verify`` (DB row counts for exclusive_conflict).
    """
    root = project.resolve()
    data = prove_representation_project(root)
    if json_out:
        typer.echo(json.dumps(data, indent=2, default=str))
    else:
        if data.get("error"):
            typer.echo(data["error"], err=True)
            raise typer.Exit(1)
        res = data.get("result")
        mark = "OK" if data.get("ok") else "FAIL"
        typer.echo(f"prove representation: [{mark}] {res}")
        for e in data.get("evidence") or []:
            typer.echo(f"  evidence: {e}")
        for r in data.get("reasons") or []:
            typer.echo(f"  reason: {r}")
        for w in data.get("soft_warnings") or []:
            typer.echo(f"  warn: {w.get('kind')}: {w.get('message')}")
        if data.get("note"):
            typer.echo(f"note: {data['note']}")
    if not data.get("ok"):
        raise typer.Exit(1)
