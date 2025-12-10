"""
CLI Bridge for DAZZLE Bun CLI.

Provides JSON-serializable functions for the TypeScript CLI to call.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


def _to_dict(obj: Any) -> Any:
    """Convert object to JSON-serializable dict."""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (list, tuple)):
        return [_to_dict(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    if is_dataclass(obj) and not isinstance(obj, type):
        return _to_dict(asdict(obj))
    if hasattr(obj, "model_dump"):
        return _to_dict(obj.model_dump())
    if hasattr(obj, "__dict__"):
        return _to_dict(obj.__dict__)
    return str(obj)


def validate_project_json(
    path: str | None = None,
    strict: bool = False,
) -> dict[str, Any]:
    """
    Validate a DAZZLE project and return JSON-serializable result.

    Args:
        path: Project path (default: current directory)
        strict: Treat warnings as errors

    Returns:
        Dict with validation results
    """
    from dazzle.core import DazzleError, load_project
    from dazzle.core.lint import lint_appspec

    project_path = Path(path) if path else Path.cwd()

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    modules: list[dict[str, Any]] = []
    entities: list[str] = []
    surfaces: list[str] = []

    try:
        # Load and validate project
        app_spec = load_project(project_path)

        # Get entities from domain
        domain_entities = app_spec.domain.entities if app_spec.domain else []

        # Get module info from app_spec
        modules.append(
            {
                "name": app_spec.name,
                "path": str(project_path),
                "entities": len(domain_entities),
                "surfaces": len(app_spec.surfaces),
            }
        )

        # Run lint checks
        lint_results = lint_appspec(app_spec)

        for result in lint_results:
            item = {
                "file": str(result.file) if hasattr(result, "file") and result.file else "",
                "line": result.line if hasattr(result, "line") and result.line else 0,
                "message": result.message if hasattr(result, "message") else str(result),
                "code": result.code if hasattr(result, "code") else "LINT",
            }
            if hasattr(result, "severity") and result.severity == "warning":
                warnings.append(item)
            else:
                # Treat everything else as warnings for now
                warnings.append(item)

        # Collect names
        entities = [e.name for e in domain_entities]
        surfaces = [s.name for s in app_spec.surfaces]

    except DazzleError as e:
        errors.append(
            {
                "file": str(e.file) if hasattr(e, "file") and e.file else "",
                "line": e.line if hasattr(e, "line") and e.line else 0,
                "message": str(e),
                "code": type(e).__name__,
            }
        )
    except Exception as e:
        errors.append(
            {
                "file": "",
                "line": 0,
                "message": str(e),
                "code": "UNKNOWN_ERROR",
            }
        )

    valid = len(errors) == 0 and (not strict or len(warnings) == 0)

    return {
        "valid": valid,
        "modules": modules,
        "entities": entities,
        "surfaces": surfaces,
        "errors": errors,
        "warnings": warnings,
    }


def get_project_info_json(
    path: str | None = None,
    include_details: bool = False,
) -> dict[str, Any]:
    """
    Get project information as JSON.

    Args:
        path: Project path (default: current directory)
        include_details: Include detailed field/section info

    Returns:
        Dict with project information
    """
    from dazzle.core import load_project_with_manifest

    project_path = Path(path) if path else Path.cwd()

    # Load project with manifest
    try:
        app_spec, manifest = load_project_with_manifest(project_path)
        name = manifest.name if manifest else app_spec.name
        version = manifest.version if manifest else "0.0.0"
    except Exception:
        return {
            "name": "unnamed",
            "version": "0.0.0",
            "entities": [],
            "surfaces": [],
            "workspaces": [],
            "services": [],
        }

    # Build entity info
    domain_entities = app_spec.domain.entities if app_spec.domain else []
    entities = []
    for entity in domain_entities:
        entity_info: dict[str, Any] = {
            "name": entity.name,
            "description": entity.title or entity.intent or "",
        }
        if include_details:
            entity_info["fields"] = [
                {
                    "name": f.name,
                    "type": str(f.type),
                    "required": f.required,
                }
                for f in entity.fields
            ]
            entity_info["relationships"] = [
                {
                    "name": r.field_name,
                    "target": r.target_entity,
                    "kind": r.relationship_type.value
                    if hasattr(r.relationship_type, "value")
                    else str(r.relationship_type),
                }
                for r in getattr(entity, "relationships", [])
            ]
        entities.append(entity_info)

    # Build surface info
    surfaces = []
    for surface in app_spec.surfaces:
        surface_info: dict[str, Any] = {
            "name": surface.name,
            "description": surface.title or "",
            "entity": surface.entity_ref or "",
            "mode": surface.mode.value if hasattr(surface.mode, "value") else str(surface.mode),
        }
        if include_details:
            surface_info["sections"] = [s.name for s in surface.sections]
        surfaces.append(surface_info)

    # Workspaces and services
    workspaces = [w.name for w in app_spec.workspaces]
    # Combine apis and domain_services
    services = [s.name for s in app_spec.apis] + [s.name for s in app_spec.domain_services]

    return {
        "name": name,
        "version": version,
        "entities": entities,
        "surfaces": surfaces,
        "workspaces": workspaces,
        "services": services,
    }


def init_project_json(
    name: str,
    template: str = "simple_task",
    path: str | None = None,
) -> dict[str, Any]:
    """
    Initialize a new DAZZLE project.

    Args:
        name: Project name
        template: Template to use
        path: Target path

    Returns:
        Dict with project info
    """
    from dazzle.core import init_project

    target_path = Path(path) if path else Path.cwd() / name

    try:
        init_project(
            name=name,
            target_dir=target_path,
            template=template,
        )
        return {
            "name": name,
            "path": str(target_path),
            "template": template,
        }
    except Exception as e:
        raise RuntimeError(f"Failed to create project: {e}") from e


def build_project_json(
    path: str | None = None,
    output: str = "./dist",
    docker: bool = True,
    graphql: bool = False,
) -> dict[str, Any]:
    """
    Build project for production.

    Args:
        path: Project path
        output: Output directory
        docker: Generate Dockerfile
        graphql: Include GraphQL

    Returns:
        Dict with build results
    """
    # Import the build functionality
    from dazzle.cli.dnr_impl.build import build_production

    project_path = Path(path) if path else Path.cwd()
    output_path = Path(output)

    try:
        result = build_production(
            project_path=project_path,
            output_path=output_path,
            include_docker=docker,
            include_graphql=graphql,
        )
        return {
            "output_path": str(output_path),
            "files": result.get("files", []),
            "docker": docker,
        }
    except Exception as e:
        raise RuntimeError(f"Build failed: {e}") from e


def eject_project_json(
    path: str | None = None,
    output: str = "./ejected",
    backend: str = "fastapi",
    frontend: str = "react",
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Eject project to standalone code.

    Args:
        path: Project path
        output: Output directory
        backend: Backend framework
        frontend: Frontend framework
        dry_run: Preview only

    Returns:
        Dict with ejection results
    """
    from dazzle.eject.runner import run_ejection

    project_path = Path(path) if path else Path.cwd()
    output_path = Path(output)

    try:
        result = run_ejection(
            project_path=project_path,
            output_path=output_path,
            backend=backend if backend != "none" else None,
            frontend=frontend if frontend != "none" else None,
            dry_run=dry_run,
        )
        return {
            "output_path": str(output_path),
            "backend_files": result.get("backend_files", []),
            "frontend_files": result.get("frontend_files", []),
            "total_files": result.get("total_files", 0),
        }
    except Exception as e:
        raise RuntimeError(f"Ejection failed: {e}") from e
