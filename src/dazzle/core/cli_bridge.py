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
    if isinstance(obj, str | int | float | bool):
        return obj
    if isinstance(obj, list | tuple):
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

    def format_field_type(ft: Any) -> str:
        """Format a FieldType to a nice display string."""
        kind = ft.kind.value if hasattr(ft.kind, "value") else str(ft.kind)
        if kind == "str" and ft.max_length:
            return f"str({ft.max_length})"
        if kind == "decimal" and ft.precision:
            return f"decimal({ft.precision},{ft.scale or 0})"
        if kind == "enum" and ft.enum_values:
            vals = ", ".join(ft.enum_values[:3])
            if len(ft.enum_values) > 3:
                vals += ", ..."
            return f"enum[{vals}]"
        if kind == "ref" and ft.ref_entity:
            return f"ref {ft.ref_entity}"
        if kind in ("has_many", "has_one", "belongs_to", "embeds") and ft.ref_entity:
            return f"{kind} {ft.ref_entity}"
        return kind

    # Build entity info
    domain_entities = app_spec.domain.entities if app_spec.domain else []
    entities = []
    for entity in domain_entities:
        entity_info: dict[str, Any] = {
            "name": entity.name,
            "label": entity.title or entity.name,
            "description": entity.title or entity.intent or "",
        }
        if include_details:
            entity_info["fields"] = [
                {
                    "name": f.name,
                    "type": format_field_type(f.type),
                    "required": f.is_required,
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
            "label": surface.title or surface.name,
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
    template: str = "blank",
    path: str | None = None,
) -> dict[str, Any]:
    """
    Initialize a new DAZZLE project.

    Args:
        name: Project name
        template: Template to use ("blank" for empty project, or example name)
        path: Target path

    Returns:
        Dict with project info
    """
    from dazzle.core import init_project

    target_path = Path(path) if path else Path.cwd() / name

    # "blank" template uses templates/blank, not an example
    # Other templates are treated as example names
    from_example = None if template == "blank" else template

    try:
        init_project(
            project_name=name,
            target_dir=target_path,
            from_example=from_example,
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
        graphql: Include GraphQL (not yet implemented)

    Returns:
        Dict with build results
    """
    from dazzle.cli.dnr_impl.docker import (
        generate_docker_compose,
        generate_dockerfile,
        generate_env_template,
        generate_production_main,
        generate_requirements,
    )
    from dazzle.core import load_project_with_manifest

    project_path = Path(path) if path else Path.cwd()
    output_path = Path(output)

    try:
        # Load project
        app_spec, manifest = load_project_with_manifest(project_path)
        app_name = manifest.name if manifest else app_spec.name

        # Create output directory
        output_path.mkdir(parents=True, exist_ok=True)

        files_generated: list[str] = []

        # Generate backend spec
        try:
            from dazzle_dnr_back.converters import convert_appspec_to_backend

            backend_spec = convert_appspec_to_backend(app_spec)
            backend_dir = output_path / "backend"
            backend_dir.mkdir(exist_ok=True)
            spec_file = backend_dir / "backend-spec.json"
            spec_file.write_text(backend_spec.model_dump_json(indent=2))
            files_generated.append("backend/backend-spec.json")
        except ImportError:
            pass  # DNR backend not installed

        # Generate frontend
        try:
            from dazzle_dnr_ui.converters import convert_appspec_to_ui
            from dazzle_dnr_ui.runtime import generate_vite_app

            shell_config = manifest.shell if manifest else None
            ui_spec = convert_appspec_to_ui(app_spec, shell_config=shell_config)
            frontend_dir = output_path / "frontend"
            frontend_files = generate_vite_app(ui_spec, str(frontend_dir))
            files_generated.extend([f"frontend/{f}" for f in frontend_files])
        except ImportError:
            pass  # DNR UI not installed

        # Generate main.py
        main_content = generate_production_main(app_name, include_frontend=True)
        (output_path / "main.py").write_text(main_content)
        files_generated.append("main.py")

        # Generate requirements.txt
        requirements = generate_requirements()
        (output_path / "requirements.txt").write_text(requirements)
        files_generated.append("requirements.txt")

        # Generate Docker files
        if docker:
            dockerfile = generate_dockerfile(app_name, include_frontend=True)
            (output_path / "Dockerfile").write_text(dockerfile)
            files_generated.append("Dockerfile")

            compose = generate_docker_compose(app_name)
            (output_path / "docker-compose.yml").write_text(compose)
            files_generated.append("docker-compose.yml")

            env = generate_env_template(app_name)
            (output_path / ".env.example").write_text(env)
            files_generated.append(".env.example")

        return {
            "output_path": str(output_path),
            "files": files_generated,
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
    from dazzle.core import load_project
    from dazzle.eject import EjectionRunner, load_ejection_config

    project_path = Path(path) if path else Path.cwd()
    output_path = Path(output)

    try:
        # Load project
        app_spec = load_project(project_path)

        # Load ejection config (or use defaults)
        toml_path = project_path / "dazzle.toml"
        if toml_path.exists():
            config = load_ejection_config(toml_path)
        else:
            # Create minimal config
            from dazzle.eject.config import EjectionConfig

            config = EjectionConfig()

        # Override output directory
        config.output.directory = str(output_path)

        # Create runner and execute
        runner = EjectionRunner(app_spec, project_path, config)

        if dry_run:
            # Return preview info
            return {
                "output_path": str(output_path),
                "backend_files": [],
                "frontend_files": [],
                "total_files": 0,
                "dry_run": True,
            }

        # Run ejection
        result = runner.run(
            backend=backend != "none",
            frontend=frontend != "none",
            testing=False,
            ci=False,
            clean=True,
            verify=False,
        )

        # Categorize files
        backend_files = [
            str(p.relative_to(output_path))
            for p in result.files.keys()
            if any(part in str(p) for part in ["backend", "api", "models"])
        ]
        frontend_files = [
            str(p.relative_to(output_path))
            for p in result.files.keys()
            if any(part in str(p) for part in ["frontend", "src", "components"])
        ]

        return {
            "output_path": str(output_path),
            "backend_files": backend_files,
            "frontend_files": frontend_files,
            "total_files": len(result.files),
        }
    except Exception as e:
        raise RuntimeError(f"Ejection failed: {e}") from e


def db_migrate_json(
    path: str | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """
    Run database migrations.

    Args:
        path: Project path
        dry_run: Preview changes only
        force: Apply destructive changes

    Returns:
        Dict with migration results
    """
    from dazzle.core import load_project_with_manifest

    project_path = Path(path) if path else Path.cwd()

    try:
        # Load project to get backend spec
        app_spec, manifest = load_project_with_manifest(project_path)

        # Try to import DNR backend
        try:
            from dazzle_dnr_back.converters import convert_appspec_to_backend
            from dazzle_dnr_back.runtime.migrations import auto_migrate, plan_migrations
            from dazzle_dnr_back.runtime.repository import DatabaseManager
        except ImportError as e:
            raise RuntimeError(f"DNR backend not available: {e}") from e

        # Convert to backend spec
        backend_spec = convert_appspec_to_backend(app_spec)

        # Get database path
        db_path = project_path / ".dazzle" / "data.db"
        db_manager = DatabaseManager(db_path)

        if dry_run:
            # Plan only
            plan = plan_migrations(db_manager, backend_spec.entities)
            return {
                "dry_run": True,
                "steps": len(plan.steps),
                "safe_steps": len(plan.safe_steps),
                "has_destructive": plan.has_destructive,
                "warnings": plan.warnings,
            }
        else:
            # Apply migrations
            plan = auto_migrate(db_manager, backend_spec.entities, record_history=True)
            return {
                "applied": len(plan.safe_steps),
                "skipped": len(plan.steps) - len(plan.safe_steps),
                "warnings": plan.warnings,
            }
    except Exception as e:
        raise RuntimeError(f"Migration failed: {e}") from e


def db_seed_json(
    path: str | None = None,
) -> dict[str, Any]:
    """
    Seed database with demo data.

    Args:
        path: Project path

    Returns:
        Dict with seeding results
    """
    from dazzle.core import load_project_with_manifest

    project_path = Path(path) if path else Path.cwd()

    try:
        app_spec, manifest = load_project_with_manifest(project_path)

        try:
            from dazzle_dnr_back.runtime.seeder import seed_demo_data

            from dazzle_dnr_back.converters import convert_appspec_to_backend
            from dazzle_dnr_back.runtime.repository import DatabaseManager
        except ImportError as e:
            raise RuntimeError(f"DNR backend not available: {e}") from e

        backend_spec = convert_appspec_to_backend(app_spec)
        db_path = project_path / ".dazzle" / "data.db"
        db_manager = DatabaseManager(db_path)

        counts = seed_demo_data(db_manager, backend_spec.entities)
        return {
            "seeded": True,
            "counts": counts,
        }
    except Exception as e:
        raise RuntimeError(f"Seeding failed: {e}") from e


def db_reset_json(
    path: str | None = None,
) -> dict[str, Any]:
    """
    Reset database (drop and recreate).

    Args:
        path: Project path

    Returns:
        Dict with reset results
    """
    from dazzle.core import load_project_with_manifest

    project_path = Path(path) if path else Path.cwd()

    try:
        app_spec, manifest = load_project_with_manifest(project_path)

        try:
            from dazzle_dnr_back.converters import convert_appspec_to_backend
            from dazzle_dnr_back.runtime.repository import DatabaseManager
        except ImportError as e:
            raise RuntimeError(f"DNR backend not available: {e}") from e

        backend_spec = convert_appspec_to_backend(app_spec)
        db_path = project_path / ".dazzle" / "data.db"

        # Delete existing database
        if db_path.exists():
            db_path.unlink()

        # Create fresh database with schema
        db_manager = DatabaseManager(db_path)
        db_manager.initialize_schema(backend_spec.entities)  # type: ignore[attr-defined]

        return {
            "reset": True,
            "tables": len(backend_spec.entities),
        }
    except Exception as e:
        raise RuntimeError(f"Reset failed: {e}") from e


def dev_server_json(
    path: str | None = None,
    port: int = 8000,
    ui_port: int = 3000,
    host: str = "127.0.0.1",
) -> dict[str, Any]:
    """
    Start development server info (actual server runs in foreground).

    Note: This just returns server config. The actual server
    is started by the CLI using subprocess for foreground mode.

    Args:
        path: Project path
        port: API port
        ui_port: UI port
        host: Host to bind

    Returns:
        Dict with server configuration
    """
    from dazzle.core import load_project_with_manifest

    project_path = Path(path) if path else Path.cwd()

    try:
        app_spec, manifest = load_project_with_manifest(project_path)
        return {
            "name": manifest.name if manifest else app_spec.name,
            "api_url": f"http://{host}:{port}",
            "ui_url": f"http://{host}:{ui_port}",
            "api_docs": f"http://{host}:{port}/docs",
        }
    except Exception as e:
        raise RuntimeError(f"Failed to load project: {e}") from e


def run_tests_json(
    path: str | None = None,
    flow: str | None = None,
    headless: bool = True,
    coverage: bool = False,
) -> dict[str, Any]:
    """
    Run E2E tests.

    Args:
        path: Project path
        flow: Specific flow to run
        headless: Run in headless mode
        coverage: Generate coverage report

    Returns:
        Dict with test results
    """
    from dazzle.core import load_project_with_manifest

    project_path = Path(path) if path else Path.cwd()

    try:
        app_spec, manifest = load_project_with_manifest(project_path)

        # Try to import test runner
        try:
            from dazzle.testing.test_runner import run_project_tests
        except ImportError:
            # Testing module may not be available
            return {
                "error": "Testing module not available",
                "hint": "E2E testing requires playwright. Install with: pip install playwright",
            }

        # Run tests for the project
        results = run_project_tests(project_path)
        # Note: flow, headless, coverage params not currently supported

        return {
            "passed": results.passed,
            "failed": results.failed,
            "skipped": results.skipped,
            "total": results.total,
            "duration_ms": 0.0,  # Not tracked at this level
            "coverage": None,  # Not tracked at this level
        }
    except ImportError:
        # No testing module - return helpful message
        return {
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "total": 0,
            "error": "E2E testing not configured",
            "hint": "Add test flows to your DSL or install playwright",
        }
    except Exception as e:
        raise RuntimeError(f"Tests failed: {e}") from e


def list_api_packs_json() -> dict[str, Any]:
    """
    List available API packs for integration selection.

    Returns:
        Dict with list of available packs
    """
    try:
        from dazzle.api_kb.loader import list_packs

        packs = list_packs()
        return {
            "packs": [
                {
                    "name": p.name,
                    "provider": p.provider,
                    "category": p.category,
                    "description": p.description,
                }
                for p in packs
            ]
        }
    except Exception as e:
        return {"packs": [], "error": str(e)}


def generate_env_example_json(
    pack_names: list[str] | None = None,
) -> dict[str, Any]:
    """
    Generate .env.example content from selected API packs.

    Args:
        pack_names: List of pack names to include (None for all)

    Returns:
        Dict with generated content
    """
    try:
        from dazzle.api_kb.loader import generate_env_example

        content = generate_env_example(pack_names)
        return {
            "content": content,
            "pack_count": len(pack_names) if pack_names else 0,
        }
    except Exception as e:
        return {"content": "", "error": str(e)}
