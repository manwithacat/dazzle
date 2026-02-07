"""
Knowledge graph management CLI commands.

Commands for exporting and importing the project knowledge graph.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from dazzle.mcp.knowledge_graph.store import KnowledgeGraph

kg_app = typer.Typer(help="Knowledge graph management.", no_args_is_help=True)


def _init_graph(project_dir: Path) -> KnowledgeGraph:
    """Initialize a KG for the given project directory."""
    from dazzle.mcp.knowledge_graph.store import KnowledgeGraph

    db_path = project_dir / ".dazzle" / "knowledge_graph.db"
    if not db_path.exists():
        typer.echo(f"Error: No knowledge graph database found at {db_path}", err=True)
        raise typer.Exit(code=1)
    return KnowledgeGraph(db_path)


@kg_app.command("export")
def export_kg(
    output: Path = typer.Option("kg_export.json", "--output", "-o", help="Output file path"),
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
) -> None:
    """Export project knowledge graph to JSON."""
    graph = _init_graph(project_dir)
    data = graph.export_project_data()

    data["project_path"] = str(project_dir.resolve())

    output.write_text(json.dumps(data, indent=2))
    entity_count = len(data["entities"])
    relation_count = len(data["relations"])
    typer.echo(f"Exported {entity_count} entities and {relation_count} relations to {output}")


@kg_app.command("import")
def import_kg(
    input_file: Path = typer.Argument(..., help="Path to JSON export file"),
    mode: str = typer.Option("merge", "--mode", "-m", help="Import mode: merge or replace"),
    project_dir: Path = typer.Option(".", "--project-dir", "-p", help="Project directory"),
) -> None:
    """Import knowledge graph from JSON file."""
    if not input_file.exists():
        typer.echo(f"Error: File not found: {input_file}", err=True)
        raise typer.Exit(code=1)

    try:
        data = json.loads(input_file.read_text())
    except json.JSONDecodeError as e:
        typer.echo(f"Error: Invalid JSON: {e}", err=True)
        raise typer.Exit(code=1)

    if mode == "replace":
        typer.confirm(
            "Replace mode will delete all existing project data. Continue?",
            abort=True,
        )

    graph = _init_graph(project_dir)

    try:
        stats = graph.import_project_data(data, mode=mode)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo(
        f"Import complete ({mode} mode): "
        f"{stats['entities_imported']} entities, "
        f"{stats['relations_imported']} relations imported"
    )
    if stats["relations_skipped"]:
        typer.echo(f"  Skipped {stats['relations_skipped']} duplicate relations")
