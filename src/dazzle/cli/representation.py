"""#1617 representation judgement CLI — decide / classify / catalogue.

No MCP dependency. Agents and humans share the same JSON shapes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from dazzle.representation import (
    classify_project,
    decide_representation,
    gin_index_sql,
    json_extension_checklist,
    list_patterns,
)

representation_app = typer.Typer(
    help=(
        "Data-representation judgement (#1617): named hatch patterns, "
        "decide ladder, project classify. Pair with `dazzle prove representation`."
    ),
    no_args_is_help=True,
)


def _echo_json(data: dict[str, Any], pretty: bool) -> None:
    if pretty:
        typer.echo(json.dumps(data, indent=2, default=str))
    else:
        typer.echo(json.dumps(data, default=str))


@representation_app.command("patterns")
def representation_patterns(
    pretty: bool = typer.Option(True, "--pretty/--compact"),
) -> None:
    """List stable pattern IDs (rel.exclusive_fks, rel.poly_ref, …)."""
    _echo_json({"ok": True, "patterns": list_patterns()}, pretty)


@representation_app.command("decide")
def representation_decide(
    text: str = typer.Option(
        None,
        "--text",
        "-t",
        help="Free-text domain pressure (e.g. 'company or sole trader client')",
    ),
    shared_child: bool = typer.Option(
        False,
        "--shared-child",
        help="Shared child of many parent kinds (Comment/Attachment)",
    ),
    exclusive_parents: bool = typer.Option(
        False,
        "--exclusive-parents",
        help="2–4 alternative parents on one row",
    ),
    parent_count: int = typer.Option(0, "--parent-count", help="Alternative parent count"),
    true_isa: bool = typer.Option(False, "--true-isa"),
    mixed_list: bool = typer.Option(False, "--mixed-kind-list"),
    tenant_json: bool = typer.Option(False, "--tenant-json"),
    four_questions_failed: bool = typer.Option(
        False,
        "--four-questions-failed",
        help="Poly interrogation already failed → allow poly_ref",
    ),
    host_extension: bool = typer.Option(False, "--host-extension"),
    pretty: bool = typer.Option(True, "--pretty/--compact"),
) -> None:
    """Execute the representation ladder → pattern_id + DSL sketch + reject list."""
    signals: dict[str, Any] = {}
    if shared_child:
        signals["shared_child_of_many_parents"] = True
    if exclusive_parents:
        signals["exclusive_parents"] = True
    if parent_count:
        signals["parent_count"] = parent_count
    if true_isa:
        signals["true_isa"] = True
    if mixed_list:
        signals["needs_mixed_kind_list"] = True
    if tenant_json:
        signals["tenant_variable_fields"] = True
    if four_questions_failed:
        signals["four_questions_failed"] = True
    if host_extension:
        signals["host_extension"] = True

    if not text and not signals:
        typer.echo(
            "Provide --text and/or structured flags (--exclusive-parents, --shared-child, …)",
            err=True,
        )
        raise typer.Exit(2)

    data = decide_representation(text=text, signals=signals or None)
    _echo_json(data, pretty)


@representation_app.command("classify")
def representation_classify(
    project: Path = typer.Option(Path("."), "--project", "-p"),
    pretty: bool = typer.Option(True, "--pretty/--compact"),
) -> None:
    """Classify project AppSpec: exclusive FKs, hand-rolled poly, open-via gaps."""
    root = project.resolve()
    data = classify_project(root)
    _echo_json(data, pretty)
    if not data.get("ok"):
        raise typer.Exit(1)
    if data.get("error_count"):
        raise typer.Exit(1)


@representation_app.command("gin-sql")
def representation_gin_sql(
    table: str = typer.Argument(..., help="Table / entity name"),
    column: str = typer.Option(
        "extensions",
        "--column",
        "-c",
        help="json/JSONB column (default: extensions)",
    ),
) -> None:
    """Print recommended Postgres GIN index SQL for a JSONB extension bag (#1619)."""
    typer.echo(gin_index_sql(table, column))
    typer.echo("")
    typer.echo("# Checklist:")
    for line in json_extension_checklist():
        typer.echo(f"# - {line}")
