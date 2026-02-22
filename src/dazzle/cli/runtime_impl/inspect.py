"""
Dazzle inspect command and helper functions.

Inspect the Dazzle app structure and generated artifacts.
"""

from __future__ import annotations

import json as json_module
import urllib.error
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any

import typer

from dazzle.cli.utils import load_project_appspec

if TYPE_CHECKING:
    from dazzle.core import ir
    from dazzle_ui.specs import UISpec


def schema_command(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    format_output: str = typer.Option(
        "tree",
        "--format",
        "-f",
        help="Output format: tree, json, summary",
    ),
    entity: str | None = typer.Option(
        None,
        "--entity",
        "-e",
        help="Inspect a specific entity by name",
    ),
    surface: str | None = typer.Option(
        None,
        "--surface",
        "-s",
        help="Inspect a specific surface by name",
    ),
    workspace: str | None = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Inspect a specific workspace by name",
    ),
    endpoints: bool = typer.Option(
        False,
        "--endpoints",
        help="Show generated API endpoints",
    ),
    components: bool = typer.Option(
        False,
        "--components",
        help="Show generated UI components",
    ),
    live: bool = typer.Option(
        False,
        "--live",
        "-l",
        help="Query a running Dazzle server for runtime state (entity counts, uptime, etc.)",
    ),
    api_url: str = typer.Option(
        "http://localhost:8000",
        "--api-url",
        help="URL of running Dazzle API server (for --live mode)",
    ),
    schema: bool = typer.Option(
        False,
        "--schema",
        help="Generate and display GraphQL schema SDL (requires strawberry-graphql)",
    ),
) -> None:
    """
    Inspect the Dazzle app structure and generated artifacts.

    Shows detailed information about entities, surfaces, workspaces,
    API endpoints, and UI components generated from the DSL.

    Use --live to query a running server for runtime statistics like
    entity counts, uptime, and database state.

    Examples:
        dazzle schema                    # Full tree view
        dazzle schema --format json      # JSON output
        dazzle schema --format summary   # Brief summary
        dazzle schema --entity Task      # Inspect Task entity
        dazzle schema --surface task_list  # Inspect surface
        dazzle schema --endpoints        # Show API endpoints
        dazzle schema --components       # Show UI components
        dazzle schema --live             # Query running server
        dazzle schema --live --entity Task  # Live entity details
        dazzle schema --schema           # Show GraphQL schema SDL
    """
    # Handle live mode - query running server
    if live:
        _inspect_live(api_url, format_output, entity)
        return

    manifest_path = Path(manifest).resolve()
    project_root = manifest_path.parent

    # Load and parse the project
    try:
        appspec = load_project_appspec(project_root)
    except Exception as e:
        typer.echo(f"Error loading project: {e}", err=True)
        raise typer.Exit(code=1)

    # Import UI converter (optional)
    ui_spec = None
    try:
        from dazzle.core.manifest import load_manifest
        from dazzle_ui.converters import convert_appspec_to_ui

        mf = load_manifest(manifest_path)
        ui_spec = convert_appspec_to_ui(appspec, shell_config=mf.shell)
    except ImportError:
        pass  # UI package not installed; non-UI inspection still works

    # Handle specific item inspection
    if entity:
        _inspect_entity(appspec, entity, format_output)
        return

    if surface:
        if ui_spec is None:
            typer.echo("Dazzle UI not available for surface inspection", err=True)
            raise typer.Exit(code=1)
        _inspect_surface(appspec, ui_spec, surface, format_output)
        return

    if workspace:
        if ui_spec is None:
            typer.echo("Dazzle UI not available for workspace inspection", err=True)
            raise typer.Exit(code=1)
        _inspect_workspace(appspec, ui_spec, workspace, format_output)
        return

    if endpoints:
        _inspect_endpoints(appspec, format_output)
        return

    if schema:
        _inspect_schema(appspec, format_output)
        return

    if components:
        if ui_spec is None:
            typer.echo("Dazzle UI not available for component inspection", err=True)
            raise typer.Exit(code=1)
        _inspect_components(ui_spec, format_output)
        return

    # Get entities from domain
    entities = appspec.domain.entities

    # Full inspection
    if format_output == "json":
        output: dict[str, Any] = {
            "app": appspec.name,
            "entities": [e.name for e in entities],
            "surfaces": [s.name for s in appspec.surfaces],
            "workspaces": [w.name for w in appspec.workspaces],
        }
        if ui_spec is not None:
            output["components"] = len(ui_spec.components)
        typer.echo(json_module.dumps(output, indent=2))
    elif format_output == "summary":
        typer.echo(f"App: {appspec.name}")
        typer.echo(f"  Entities:   {len(entities)}")
        typer.echo(f"  Surfaces:   {len(appspec.surfaces)}")
        typer.echo(f"  Workspaces: {len(appspec.workspaces)}")
        if ui_spec is not None:
            typer.echo(f"  Components: {len(ui_spec.components)}")
    else:  # tree format
        typer.echo(f"📦 {appspec.name}")
        typer.echo("│")

        # Entities
        if entities:
            typer.echo("├── 📊 Entities")
            for i, ent in enumerate(entities):
                prefix = "│   └──" if i == len(entities) - 1 else "│   ├──"
                field_count = len(ent.fields)
                typer.echo(f"{prefix} {ent.name} ({field_count} fields)")

        # Surfaces
        if appspec.surfaces:
            typer.echo("│")
            typer.echo("├── 🖥️  Surfaces")
            for i, s in enumerate(appspec.surfaces):
                prefix = "│   └──" if i == len(appspec.surfaces) - 1 else "│   ├──"
                entity_ref = s.entity_ref or "no entity"
                typer.echo(f"{prefix} {s.name} ({s.mode}, {entity_ref})")

        # Workspaces
        if appspec.workspaces:
            typer.echo("│")
            typer.echo("├── 📁 Workspaces")
            for i, w in enumerate(appspec.workspaces):
                prefix = "│   └──" if i == len(appspec.workspaces) - 1 else "│   ├──"
                region_count = len(w.regions)
                typer.echo(f"{prefix} {w.name} ({region_count} regions)")

        # UI summary (if available)
        if ui_spec is not None:
            typer.echo("│")
            typer.echo(f"└── 🎨 UI: {len(ui_spec.components)} components")
        else:
            typer.echo("│")
            typer.echo(f"└── {len(appspec.surfaces)} surfaces")


def _inspect_entity(
    appspec: ir.AppSpec,
    entity_name: str,
    format_output: str,
) -> None:
    """Inspect a specific entity."""
    entities = appspec.domain.entities

    # Find entity
    entity = next((e for e in entities if e.name == entity_name), None)
    if not entity:
        typer.echo(f"Entity '{entity_name}' not found", err=True)
        typer.echo(f"Available: {', '.join(e.name for e in entities)}")
        raise typer.Exit(code=1)

    # Find surfaces that reference this entity
    related_surfaces = [s for s in appspec.surfaces if s.entity_ref and s.entity_ref == entity_name]

    if format_output == "json":
        output = {
            "name": entity.name,
            "title": entity.title,
            "fields": [
                {
                    "name": f.name,
                    "type": str(f.type),
                    "required": f.is_required,
                    "primary_key": f.is_primary_key,
                }
                for f in entity.fields
            ],
            "surfaces": [{"name": s.name, "mode": str(s.mode)} for s in related_surfaces],
        }
        typer.echo(json_module.dumps(output, indent=2))
    else:
        typer.echo(f"📊 Entity: {entity.name}")
        if entity.title:
            typer.echo(f"   Title: {entity.title}")
        typer.echo()
        typer.echo("   Fields:")
        for f in entity.fields:
            pk = " [PK]" if f.is_primary_key else ""
            req = " (required)" if f.is_required else ""
            typer.echo(f"   • {f.name}: {f.type}{pk}{req}")

        if related_surfaces:
            typer.echo()
            typer.echo("   Surfaces:")
            for s in related_surfaces:
                typer.echo(f"   • {s.name} ({s.mode})")


def _inspect_surface(
    appspec: ir.AppSpec,
    ui_spec: UISpec,
    surface_name: str,
    format_output: str,
) -> None:
    """Inspect a specific surface."""
    # Find surface
    surface = next((s for s in appspec.surfaces if s.name == surface_name), None)
    if not surface:
        typer.echo(f"Surface '{surface_name}' not found", err=True)
        typer.echo(f"Available: {', '.join(s.name for s in appspec.surfaces)}")
        raise typer.Exit(code=1)

    if format_output == "json":
        output = {
            "name": surface.name,
            "title": surface.title,
            "mode": str(surface.mode),
            "entity_ref": surface.entity_ref,
            "sections": [
                {"name": sec.name, "elements": len(sec.elements)} for sec in surface.sections
            ],
        }
        typer.echo(json_module.dumps(output, indent=2))
    else:
        typer.echo(f"🖥️  Surface: {surface.name}")
        if surface.title:
            typer.echo(f"   Title: {surface.title}")
        typer.echo(f"   Mode: {surface.mode}")
        if surface.entity_ref:
            typer.echo(f"   Entity: {surface.entity_ref}")
        typer.echo()
        typer.echo("   Sections:")
        for sec in surface.sections:
            typer.echo(f"   • {sec.name}: {len(sec.elements)} elements")


def _inspect_workspace(
    appspec: ir.AppSpec,
    ui_spec: UISpec,
    workspace_name: str,
    format_output: str,
) -> None:
    """Inspect a specific workspace."""
    # Find workspace
    workspace = next((w for w in appspec.workspaces if w.name == workspace_name), None)
    if not workspace:
        typer.echo(f"Workspace '{workspace_name}' not found", err=True)
        typer.echo(f"Available: {', '.join(w.name for w in appspec.workspaces)}")
        raise typer.Exit(code=1)

    if format_output == "json":
        output = {
            "name": workspace.name,
            "title": workspace.title,
            "purpose": workspace.purpose,
            "regions": [{"name": r.name, "source": r.source} for r in workspace.regions],
        }
        typer.echo(json_module.dumps(output, indent=2))
    else:
        typer.echo(f"📁 Workspace: {workspace.name}")
        if workspace.title:
            typer.echo(f"   Title: {workspace.title}")
        if workspace.purpose:
            typer.echo(f"   Purpose: {workspace.purpose}")
        typer.echo()
        typer.echo("   Regions:")
        for r in workspace.regions:
            typer.echo(f"   • {r.name}: {r.source}")


def _inspect_endpoints(appspec: ir.AppSpec, format_output: str) -> None:
    """Inspect API surfaces (endpoint sources)."""
    from dazzle.core.strings import to_api_plural

    entities = appspec.domain.entities
    if format_output == "json":
        output = []
        for entity in entities:
            plural = to_api_plural(entity.name)
            for method in ("GET", "POST"):
                output.append({"method": method, "path": f"/{plural}", "entity": entity.name})
            for method in ("GET", "PATCH", "DELETE"):
                output.append(
                    {"method": method, "path": f"/{plural}/{{id}}", "entity": entity.name}
                )
        typer.echo(json_module.dumps(output, indent=2))
    else:
        typer.echo("🔧 API Endpoints (derived from entities)")
        typer.echo()
        for entity in entities:
            plural = to_api_plural(entity.name)
            typer.echo(f"   GET    /{plural}")
            typer.echo(f"   POST   /{plural}")
            typer.echo(f"   GET    /{plural}/{{id}}")
            typer.echo(f"   PATCH  /{plural}/{{id}}")
            typer.echo(f"   DELETE /{plural}/{{id}}")


def _inspect_components(ui_spec: UISpec, format_output: str) -> None:
    """Inspect UI components."""
    if format_output == "json":
        output = [{"name": c.name, "category": c.category} for c in ui_spec.components]
        typer.echo(json_module.dumps(output, indent=2))
    else:
        typer.echo("🎨 UI Components")
        typer.echo()
        for c in ui_spec.components:
            typer.echo(f"   • {c.name} ({c.category})")


def _inspect_schema(appspec: ir.AppSpec, format_output: str) -> None:
    """Inspect GraphQL schema."""
    try:
        from dazzle_back.converters import convert_appspec_to_backend
        from dazzle_back.graphql.integration import inspect_schema, print_schema
    except ImportError:
        typer.echo(
            "GraphQL support not available. Install with: pip install strawberry-graphql",
            err=True,
        )
        raise typer.Exit(code=1)

    backend_spec = convert_appspec_to_backend(appspec)

    if format_output == "json":
        info = inspect_schema(backend_spec)
        typer.echo(json_module.dumps(info, indent=2))
    else:
        # Print SDL for tree/summary formats
        typer.echo("📊 GraphQL Schema")
        typer.echo()
        sdl = print_schema(backend_spec)
        typer.echo(sdl)


def _inspect_live(api_url: str, format_output: str, entity_name: str | None = None) -> None:
    """Query running Dazzle server for runtime state."""

    def fetch_json(endpoint: str) -> dict[str, Any] | None:
        """Fetch JSON from API endpoint."""
        url = f"{api_url.rstrip('/')}{endpoint}"
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                result: dict[str, Any] = json_module.loads(response.read().decode())
                return result
        except urllib.error.URLError as e:
            typer.echo(f"Error connecting to {url}: {e}", err=True)
            return None
        except Exception as e:
            typer.echo(f"Error fetching {endpoint}: {e}", err=True)
            return None

    # If entity specified, get entity details
    if entity_name:
        data = fetch_json(f"/_dazzle/entity/{entity_name}")
        if not data:
            raise typer.Exit(code=1)

        if "error" in data:
            typer.echo(f"Error: {data['error']}", err=True)
            raise typer.Exit(code=1)

        if format_output == "json":
            typer.echo(json_module.dumps(data, indent=2, default=str))
        else:
            typer.echo(f"📊 Entity: {data['name']} (live)")
            if data.get("label"):
                typer.echo(f"   Label: {data['label']}")
            if data.get("description"):
                typer.echo(f"   Description: {data['description']}")
            typer.echo(f"   Records: {data.get('count', 0)}")
            typer.echo()
            typer.echo("   Fields:")
            for f in data.get("fields", []):
                req = " (required)" if f.get("required") else ""
                unique = " [unique]" if f.get("unique") else ""
                indexed = " [indexed]" if f.get("indexed") else ""
                typer.echo(f"   • {f['name']}: {f['type']}{req}{unique}{indexed}")

            if data.get("sample"):
                typer.echo()
                typer.echo(f"   Sample data ({len(data['sample'])} records):")
                for row in data["sample"][:3]:  # Show max 3
                    # Show a compact view of the row
                    preview = ", ".join(f"{k}={v!r}" for k, v in list(row.items())[:4])
                    if len(row) > 4:
                        preview += ", ..."
                    typer.echo(f"   • {preview}")
        return

    # Get overall stats
    stats = fetch_json("/_dazzle/stats")
    health = fetch_json("/_dazzle/health")
    spec = fetch_json("/_dazzle/spec")

    if not stats:
        typer.echo("Could not connect to Dazzle server", err=True)
        typer.echo(f"Tried: {api_url}/_dazzle/stats")
        typer.echo()
        typer.echo("Make sure the server is running:")
        typer.echo("  dazzle serve")
        raise typer.Exit(code=1)

    if format_output == "json":
        output = {
            "stats": stats,
            "health": health,
            "spec": spec,
        }
        typer.echo(json_module.dumps(output, indent=2, default=str))
    elif format_output == "summary":
        typer.echo(f"App: {stats.get('app_name', 'Unknown')}")
        typer.echo(f"  Status:       {health.get('status', 'unknown') if health else 'unknown'}")
        typer.echo(f"  Uptime:       {_format_uptime(stats.get('uptime_seconds', 0))}")
        typer.echo(f"  Total records: {stats.get('total_records', 0)}")
        typer.echo(f"  Entities:     {len(stats.get('entities', []))}")
    else:  # tree format
        status_emoji = "✅" if health and health.get("status") == "ok" else "⚠️"
        typer.echo(f"📦 {stats.get('app_name', 'Unknown')} (live)")
        typer.echo(
            f"│  {status_emoji} Status: {health.get('status', 'unknown') if health else 'unknown'}"
        )
        typer.echo(f"│  ⏱️  Uptime: {_format_uptime(stats.get('uptime_seconds', 0))}")
        typer.echo("│")

        # Show entities with record counts
        entities = stats.get("entities", [])
        if entities:
            typer.echo("├── 📊 Entities (with record counts)")
            for i, ent in enumerate(entities):
                prefix = "│   └──" if i == len(entities) - 1 else "│   ├──"
                fts_badge = " 🔍" if ent.get("has_fts") else ""
                typer.echo(f"{prefix} {ent['name']}: {ent['count']} records{fts_badge}")

        # Show database info
        typer.echo("│")
        typer.echo(f"└── 💾 Total records: {stats.get('total_records', 0)}")


def _format_uptime(seconds: float) -> str:
    """Format uptime seconds into a human-readable string."""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}m {secs}s"
    else:
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        return f"{hours}h {mins}m"
