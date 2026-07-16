"""#1605 D4 — CLI prove (static evidence). Thin wrapper over agent_loop prove."""

from __future__ import annotations

import json
from pathlib import Path

import typer

prove_app = typer.Typer(
    help="Prove story execution bindings (static evidence v1).",
    no_args_is_help=True,
)


@prove_app.command("story")
def prove_story(
    story_id: str = typer.Argument(
        None,
        help="Story id (omit to check all accepted)",
    ),
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    json_out: bool = typer.Option(False, "--json", help="Raw JSON report"),
) -> None:
    """Static prove: binding target exists in appspec / host files."""
    from dazzle.mcp.server.handlers.agent_loop import agent_prove_handler

    root = Path(manifest).resolve().parent
    args: dict = {}
    if story_id:
        args["story_id"] = story_id
    raw = agent_prove_handler(root, args)
    data = json.loads(raw)
    if json_out:
        typer.echo(json.dumps(data, indent=2))
    else:
        if data.get("error"):
            typer.echo(data["error"], err=True)
            raise typer.Exit(1)
        typer.echo(
            f"prove: {data.get('passed')}/{data.get('checked')} passed "
            f"(failed={data.get('failed')})"
        )
        for r in data.get("results") or []:
            mark = "OK" if r.get("result") == "pass" else "FAIL"
            typer.echo(f"  [{mark}] {r.get('story_id')}: {r.get('reason')}")
            for e in r.get("evidence") or []:
                typer.echo(f"         evidence: {e}")
    if not data.get("ok"):
        raise typer.Exit(1)
