"""#1605 D4 — CLI prove (static binding evidence). No mcp package import."""

from __future__ import annotations

import json
from pathlib import Path

import typer

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
        help="Static binding evidence (default). Runtime prove is not implemented.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Raw JSON only"),
) -> None:
    """Static prove: binding target exists in appspec / host files.

    Results use ``pass_static`` / ``fail_static`` — this is **not** a claim
    that the user journey works end-to-end.
    """
    if not static:
        typer.echo(
            "Runtime prove is not implemented yet. Use --static (default).",
            err=True,
        )
        raise typer.Exit(2)

    from dazzle.agent_loop import prove_stories

    root = Path(manifest).resolve().parent
    data = prove_stories(root, story_id=story_id)
    if json_out:
        typer.echo(json.dumps(data, indent=2, default=str))
    else:
        if data.get("error"):
            typer.echo(data["error"], err=True)
            raise typer.Exit(1)
        typer.echo(
            f"prove --static: {data.get('passed')}/{data.get('checked')} passed "
            f"(failed={data.get('failed')}) — binding evidence only"
        )
        for r in data.get("results") or []:
            res = r.get("result")
            mark = "OK" if str(res).startswith("pass") else "FAIL"
            typer.echo(f"  [{mark}] {r.get('story_id')}: {res} ({r.get('reason')})")
            for e in r.get("evidence") or []:
                typer.echo(f"         evidence: {e}")
        if data.get("note"):
            typer.echo(f"note: {data['note']}")
    if not data.get("ok"):
        raise typer.Exit(1)
