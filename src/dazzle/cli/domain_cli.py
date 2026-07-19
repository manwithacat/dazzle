"""CLI: dazzle domain — agent-audience domain brief pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from dazzle.domain_brief import (
    extract_from_path,
    extract_from_text,
    find_founder_brief,
    load_domain,
    promote_checklist,
    research_and_save,
    save_domain,
    score_gaps,
)

domain_app = typer.Typer(
    help="Agent-audience domain brief (cognition draft before DSL).",
    no_args_is_help=True,
)


def _root(project: Path | None) -> Path:
    return (project or Path.cwd()).resolve()


@domain_app.command("extract")
def extract_cmd(
    project: Path | None = typer.Option(None, "--project", "-p", help="Project root"),
    spec: Path | None = typer.Option(
        None, "--spec", "-s", help="Founder brief path (default: SPEC.md / scan)"
    ),
    text: str | None = typer.Option(None, "--text", help="Inline founder brief"),
    write: bool = typer.Option(True, "--write/--no-write", help="Write AGENT_DOMAIN.md + json"),
) -> None:
    """Extract AGENT_DOMAIN from founder prose (offline, chrome-safe)."""
    root = _root(project)
    if text:
        domain = extract_from_text(text, source_path="inline")
    else:
        path = spec
        if path is None:
            path = find_founder_brief(root)
        if path is None:
            typer.echo(
                "No founder brief found (SPEC.md / idea.md / …). Pass --spec or --text.", err=True
            )
            raise typer.Exit(1)
        domain = extract_from_path(path)

    gaps = score_gaps(domain)
    if write:
        paths = save_domain(root, domain)
        typer.echo(f"Wrote {paths['markdown']}")
        typer.echo(f"Wrote {paths['json']}")
    else:
        typer.echo(json.dumps(domain.to_dict(), indent=2))

    typer.echo(
        f"personas={gaps.personas} grounded_nouns={gaps.grounded_nouns} "
        f"desks={gaps.desks} ready_to_promote={gaps.ready_to_promote}"
    )
    if domain.rejected_chrome:
        typer.echo(f"rejected_chrome: {', '.join(domain.rejected_chrome[:20])}")
    for g in gaps.gaps:
        if g.severity == "error":
            typer.echo(f"  ! {g.code}: {g.message}")


@domain_app.command("show")
def show_cmd(
    project: Path | None = typer.Option(None, "--project", "-p"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Show current AGENT_DOMAIN."""
    root = _root(project)
    domain = load_domain(root)
    if domain is None:
        typer.echo("No AGENT_DOMAIN.md / agent_domain.json — run: dazzle domain extract", err=True)
        raise typer.Exit(1)
    if json_out:
        typer.echo(json.dumps(domain.to_dict(), indent=2))
    else:
        from dazzle.domain_brief.store import render_markdown

        typer.echo(render_markdown(domain))


@domain_app.command("gaps")
def gaps_cmd(
    project: Path | None = typer.Option(None, "--project", "-p"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Report gaps that block promote → DSL."""
    root = _root(project)
    domain = load_domain(root)
    if domain is None:
        typer.echo("No AGENT_DOMAIN — run dazzle domain extract first.", err=True)
        raise typer.Exit(1)
    report = score_gaps(domain)
    if json_out:
        typer.echo(json.dumps(report.to_dict(), indent=2))
    else:
        typer.echo(f"ready_to_promote={report.ready_to_promote}")
        for g in report.gaps:
            typer.echo(f"  [{g.severity}] {g.code}: {g.message}")
    if not report.ready_to_promote:
        raise typer.Exit(2)


@domain_app.command("research")
def research_cmd(
    project: Path | None = typer.Option(None, "--project", "-p"),
    note: str | None = typer.Option(None, "--note", help="Append research note"),
    answer: str | None = typer.Option(
        None, "--answer", help="question_id=text — answer and clear open question"
    ),
    clear: str | None = typer.Option(None, "--clear", help="Clear open question by id"),
    owner: str | None = typer.Option(
        None, "--owner", help="field:noun_or_desk — set owner_field_hint"
    ),
    write: bool = typer.Option(True, "--write/--no-write"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Amend AGENT_DOMAIN (answers/notes/owners). Never invents chrome nouns or writes DSL."""
    root = _root(project)
    kwargs: dict[str, object] = {"write": write}
    if note:
        kwargs["note"] = note
    if answer and "=" in answer:
        qid, _, text = answer.partition("=")
        kwargs["answer_question_id"] = qid.strip()
        kwargs["answer_text"] = text.strip()
    elif answer:
        typer.echo("--answer requires question_id=text", err=True)
        raise typer.Exit(1)
    if clear:
        kwargs["clear_question_id"] = clear
    if owner and ":" in owner:
        field, _, target = owner.partition(":")
        kwargs["set_owner_field"] = field.strip()
        kwargs["owner_for"] = target.strip()
    elif owner:
        typer.echo("--owner requires field:noun_or_desk", err=True)
        raise typer.Exit(1)

    result = research_and_save(root, **kwargs)
    if not result.get("ok"):
        typer.echo(result.get("error") or "research failed", err=True)
        raise typer.Exit(1)
    if json_out:
        typer.echo(json.dumps(result, indent=2))
        return
    typer.echo(f"applied={result.get('applied')} refused={result.get('refused')}")
    if result.get("written"):
        typer.echo(f"wrote {result['written'].get('markdown')}")
    gaps = result.get("gaps") or {}
    typer.echo(f"ready_to_promote={gaps.get('ready_to_promote')}")
    if result.get("refused"):
        raise typer.Exit(2)


@domain_app.command("promote")
def promote_cmd(
    project: Path | None = typer.Option(None, "--project", "-p"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Checklist for hand-authoring DSL from AGENT_DOMAIN (does not write DSL)."""
    root = _root(project)
    domain = load_domain(root)
    if domain is None:
        typer.echo("No AGENT_DOMAIN — run dazzle domain extract first.", err=True)
        raise typer.Exit(1)
    check = promote_checklist(domain)
    if json_out:
        typer.echo(json.dumps(check, indent=2))
    else:
        typer.echo(check["warning"])
        typer.echo(f"ready={check['ready']}")
        for step in check["dsl_steps"]:
            typer.echo(f"  {step}")
        if not check["ready"]:
            typer.echo("Blockers:")
            for g in check["gaps"]["gaps"]:
                if g["severity"] == "error":
                    typer.echo(f"  ! {g['code']}: {g['message']}")
    if not check["ready"]:
        raise typer.Exit(2)
