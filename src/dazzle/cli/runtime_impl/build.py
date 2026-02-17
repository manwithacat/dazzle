"""
Dazzle build commands.

Commands for generating UI artifacts, API specs, and production bundles.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from dazzle.cli.utils import load_project_appspec
from dazzle.core.errors import DazzleError, ParseError
from dazzle.core.lint import lint_appspec

from .docker import (
    generate_docker_compose,
    generate_dockerfile,
    generate_env_template,
    generate_local_compose,
    generate_local_run_script,
    generate_production_main,
    generate_requirements,
)


def build_ui_command(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    out: str = typer.Option("./dnr-ui", "--out", "-o", help="Output directory"),
    format: str = typer.Option(
        "html",
        "--format",
        "-f",
        help="Output format: 'html' (default, static preview files)",
    ),
) -> None:
    """
    Generate UI artifacts from AppSpec.

    Generates server-rendered HTML preview files from AppSpec.
    Each surface produces HTML files (e.g., task-list.html, task-create.html).

    Examples:
        dazzle build-ui                         # Preview files in ./dnr-ui
        dazzle build-ui -o out                   # Output to ./out
    """
    try:
        # Import Dazzle UI components
        from dazzle_ui.runtime.static_preview import generate_preview_files
    except ImportError as e:
        typer.echo(f"Dazzle UI not available: {e}", err=True)
        typer.echo("Install with: pip install dazzle-app-ui", err=True)
        raise typer.Exit(code=1)

    # Load and build AppSpec
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    try:
        appspec = load_project_appspec(root)

        # Validate
        errors, warnings = lint_appspec(appspec)
        if errors:
            typer.echo("Cannot generate UI; spec has validation errors:", err=True)
            for err in errors:
                typer.echo(f"  ERROR: {err}", err=True)
            raise typer.Exit(code=1)

        for warn in warnings:
            typer.echo(f"WARNING: {warn}")

    except (ParseError, DazzleError) as e:
        typer.echo(f"Error loading spec: {e}", err=True)
        raise typer.Exit(code=1)

    # Generate preview files
    output_dir = Path(out).resolve()

    typer.echo(f"\nGenerating static preview HTML → {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    files = generate_preview_files(appspec, str(output_dir))
    typer.echo(f"  ✓ Generated {len(files)} files")
    typer.echo("\nTo preview:")
    if files:
        typer.echo(f"  Open in browser: file://{files[0]}")


def build_api_command(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    out: str = typer.Option("./dazzle-api", "--out", "-o", help="Output directory"),
    format: str = typer.Option(
        "json",
        "--format",
        "-f",
        help="Output format: 'json' (spec file) or 'python' (stub module)",
    ),
) -> None:
    """
    Generate API spec from AppSpec.

    Converts AppSpec to BackendSpec suitable for FastAPI runtime.

    Examples:
        dazzle build-api                        # JSON spec in ./dazzle-api
        dazzle build-api --format python        # Python module stub
    """
    try:
        from dazzle_back.converters import convert_appspec_to_backend
        from dazzle_back.specs import BackendSpec as _BackendSpec  # noqa: F401
    except ImportError as e:
        typer.echo(f"Dazzle Backend not available: {e}", err=True)
        typer.echo("Install with: pip install dazzle-app-back", err=True)
        raise typer.Exit(code=1)
    del _BackendSpec  # Used only to verify import availability

    # Load and build AppSpec
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    try:
        appspec = load_project_appspec(root)

        errors, warnings = lint_appspec(appspec)
        if errors:
            typer.echo("Cannot generate API; spec has validation errors:", err=True)
            for err in errors:
                typer.echo(f"  ERROR: {err}", err=True)
            raise typer.Exit(code=1)

        for warn in warnings:
            typer.echo(f"WARNING: {warn}")

    except (ParseError, DazzleError) as e:
        typer.echo(f"Error loading spec: {e}", err=True)
        raise typer.Exit(code=1)

    # Convert to BackendSpec
    typer.echo(f"Converting AppSpec '{appspec.name}' to BackendSpec...")
    backend_spec = convert_appspec_to_backend(appspec)
    typer.echo(f"  • {len(backend_spec.entities)} entities")
    typer.echo(f"  • {len(backend_spec.services)} services")
    typer.echo(f"  • {len(backend_spec.endpoints)} endpoints")

    # Output
    output_dir = Path(out).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if format == "json":
        spec_file = output_dir / "backend-spec.json"
        typer.echo(f"\nWriting BackendSpec → {spec_file}")
        spec_file.write_text(backend_spec.model_dump_json(indent=2))
        typer.echo(f"  ✓ Written {spec_file.stat().st_size} bytes")

    elif format == "python":
        stub_file = output_dir / "api_stub.py"
        typer.echo(f"\nWriting Python stub → {stub_file}")

        stub_content = f'''"""
Auto-generated API stub for {backend_spec.name}.

Usage:
    from dazzle_back.runtime import create_app_from_json
    app = create_app_from_json('backend-spec.json')

Or run directly:
    uvicorn api_stub:app --reload
"""

from pathlib import Path

try:
    from dazzle_back.runtime import create_app_from_json, FASTAPI_AVAILABLE
    if not FASTAPI_AVAILABLE:
        raise ImportError("FastAPI not installed")

    spec_path = Path(__file__).parent / "backend-spec.json"
    app = create_app_from_json(str(spec_path))

except ImportError as e:
    print(f"Dazzle runtime not available: {{e}}")
    print("Install with: pip install fastapi uvicorn")
    app = None
'''
        stub_file.write_text(stub_content)

        # Also write the JSON spec
        spec_file = output_dir / "backend-spec.json"
        spec_file.write_text(backend_spec.model_dump_json(indent=2))

        typer.echo("  ✓ Generated stub and spec")
        typer.echo("\nTo run:")
        typer.echo(f"  cd {output_dir}")
        typer.echo("  pip install fastapi uvicorn")
        typer.echo("  uvicorn api_stub:app --reload")

    else:
        typer.echo(f"Unknown format: {format}", err=True)
        typer.echo("Use one of: json, python", err=True)
        raise typer.Exit(code=1)


def migrate_command(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show planned changes without applying"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Apply even if destructive changes detected"
    ),
    database_url: str = typer.Option(
        "",
        "--database-url",
        help="PostgreSQL URL. Also reads DATABASE_URL env var.",
    ),
) -> None:
    """
    Run database migrations for production.

    Detects schema changes between entity definitions and the database,
    then applies safe migrations automatically. Requires DATABASE_URL.

    Examples:
        # Preview migrations
        dazzle migrate --dry-run

        # Apply migrations
        dazzle migrate

        # Force apply (including destructive changes)
        dazzle migrate --force
    """
    import os

    try:
        from dazzle_back.converters import convert_appspec_to_backend
        from dazzle_back.runtime.migrations import (
            MigrationAction,
            auto_migrate,
            plan_migrations,
        )
        from dazzle_back.runtime.pg_backend import PostgresBackend
    except ImportError as e:
        typer.echo(f"Dazzle packages not available: {e}", err=True)
        typer.echo("Install with: pip install dazzle-app-back", err=True)
        raise typer.Exit(code=1)

    # Load and build AppSpec
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    try:
        appspec = load_project_appspec(root)

        errors, warnings = lint_appspec(appspec)
        if errors:
            typer.echo("Cannot migrate; spec has validation errors:", err=True)
            for err in errors:
                typer.echo(f"  ERROR: {err}", err=True)
            raise typer.Exit(code=1)

    except FileNotFoundError:
        typer.echo(f"Manifest not found: {manifest}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"Failed to load spec: {e}", err=True)
        raise typer.Exit(code=1)

    # Convert to backend spec
    backend_spec = convert_appspec_to_backend(appspec)

    # Resolve database URL: CLI flag → env → dazzle.toml → default
    from dazzle.core.manifest import _DEFAULT_DATABASE_URL, load_manifest, resolve_database_url

    mf = load_manifest(manifest_path)
    had_explicit_source = bool(
        database_url or os.environ.get("DATABASE_URL") or mf.database.url != _DEFAULT_DATABASE_URL
    )
    database_url = resolve_database_url(mf, explicit_url=database_url)
    if not had_explicit_source:
        typer.echo("DATABASE_URL is required for migrations.", err=True)
        typer.echo(
            "Set it in .env, dazzle.toml [database], or export before running:",
            err=True,
        )
        typer.echo("  export DATABASE_URL=postgresql://localhost:5432/dazzle_dev", err=True)
        raise typer.Exit(code=1)

    # Create database backend
    db_manager = PostgresBackend(database_url)

    if dry_run:
        # Plan only, don't apply
        typer.echo(f"Analyzing database: {database_url}")
        typer.echo(f"Entities: {len(backend_spec.entities)}")
        typer.echo()

        plan = plan_migrations(db_manager, backend_spec.entities)

        if plan.is_empty:
            typer.echo("No migrations needed. Database is up to date.")
            return

        typer.echo("Planned migrations:")
        typer.echo()

        for step in plan.steps:
            icon = "⚠️ " if step.is_destructive else "  "
            if step.action == MigrationAction.CREATE_TABLE:
                typer.echo(f"{icon}CREATE TABLE {step.table}")
            elif step.action == MigrationAction.ADD_COLUMN:
                typer.echo(f"{icon}ADD COLUMN {step.table}.{step.column}")
            elif step.action == MigrationAction.ADD_INDEX:
                typer.echo(f"{icon}ADD INDEX on {step.table}.{step.column}")
            elif step.action == MigrationAction.DROP_COLUMN:
                typer.echo(f"{icon}DROP COLUMN {step.table}.{step.column} (destructive)")
            elif step.action == MigrationAction.CHANGE_TYPE:
                typer.echo(f"{icon}CHANGE TYPE {step.table}.{step.column} (destructive)")

        if plan.warnings:
            typer.echo()
            typer.echo("Warnings:")
            for warning in plan.warnings:
                typer.echo(f"  ⚠️  {warning}")

        if plan.has_destructive:
            typer.echo()
            typer.echo("⚠️  Destructive changes detected!")
            typer.echo("   Use --force to apply, or handle manually.")

        typer.echo()
        typer.echo(f"Total: {len(plan.steps)} migration steps")
        if plan.safe_steps:
            typer.echo(f"  Safe: {len(plan.safe_steps)}")
        if plan.has_destructive:
            typer.echo(
                f"  Destructive: {len(plan.steps) - len(plan.safe_steps)} (requires --force)"
            )

    else:
        # Apply migrations
        typer.echo(f"Migrating database: {database_url}")
        typer.echo()

        # Note: auto_migrate only applies safe migrations by default
        # Force mode would require extending the migrations API
        if force:
            typer.echo("Warning: --force is noted but destructive migrations", err=True)
            typer.echo("  require manual SQL execution for safety.", err=True)
            typer.echo()

        plan = auto_migrate(
            db_manager,
            backend_spec.entities,
            record_history=True,
        )

        if plan.is_empty:
            typer.echo("✓ No migrations needed. Database is up to date.")
            return

        applied = len(plan.safe_steps)
        skipped = len(plan.steps) - len(plan.safe_steps) if not force else 0

        typer.echo(f"✓ Applied {applied} migration(s)")

        if plan.warnings:
            typer.echo()
            for warning in plan.warnings:
                typer.echo(f"  ⚠️  {warning}")

        if skipped > 0:
            typer.echo()
            typer.echo(f"⚠️  {skipped} destructive change(s) skipped")
            typer.echo("   Use --force to apply, or handle manually.")


def build_command(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    out: str = typer.Option("./dist", "--out", "-o", help="Output directory"),
    target: str = typer.Option(
        "bundle",
        "--target",
        "-t",
        help="Build target: bundle (default), sql, openapi, asyncapi, all",
    ),
    check: bool = typer.Option(False, "--check", help="Validate only, do not write files"),
    docker: bool = typer.Option(True, "--docker/--no-docker", help="Generate Dockerfile"),
    env_template: bool = typer.Option(True, "--env/--no-env", help="Generate environment template"),
    frontend: bool = typer.Option(True, "--frontend/--no-frontend", help="Include frontend"),
    _minify: bool = typer.Option(True, "--minify/--no-minify", help="Minify frontend assets"),
) -> None:
    """
    Build production artifacts from DSL specifications.

    Targets:
        bundle  — Full deployment package (Docker, main.py, requirements)
        sql     — SQL schema DDL (CREATE TABLE statements)
        openapi — OpenAPI 3.1 specification
        asyncapi — AsyncAPI 3.0 specification
        all     — Generate all codegen targets

    Examples:
        dazzle build                        # Full bundle in ./dist
        dazzle build --target sql           # SQL schema only
        dazzle build --target openapi       # OpenAPI spec
        dazzle build --target all           # All codegen targets
        dazzle build --check                # Validate without writing
        dazzle build -o deploy              # Output to ./deploy
        dazzle build --no-frontend          # Backend bundle only
        dazzle build --no-docker            # Skip Dockerfile

    To deploy:
        cd dist && docker build -t myapp . && docker run -p 8000:8000 myapp
        # Or without Docker:
        cd dist && pip install -r requirements.txt && python main.py
    """
    try:
        from dazzle_back.converters import convert_appspec_to_backend
        from dazzle_ui.runtime.static_preview import generate_preview_files
    except ImportError as e:
        typer.echo(f"Dazzle packages not available: {e}", err=True)
        typer.echo("Install with: pip install dazzle-app-back dazzle-app-ui", err=True)
        raise typer.Exit(code=1)

    # Load and build AppSpec
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    try:
        appspec = load_project_appspec(root)

        errors, warnings = lint_appspec(appspec)
        if errors:
            typer.echo("Cannot build; spec has validation errors:", err=True)
            for err in errors:
                typer.echo(f"  ERROR: {err}", err=True)
            raise typer.Exit(code=1)

        for warn in warnings:
            typer.echo(f"WARNING: {warn}")

    except (ParseError, DazzleError) as e:
        typer.echo(f"Error loading spec: {e}", err=True)
        raise typer.Exit(code=1)

    # --check mode: validate without generating
    if check:
        typer.echo(f"Validation passed for '{appspec.name}'")
        typer.echo(f"  {len(appspec.domain.entities)} entities")
        typer.echo(f"  {len(appspec.surfaces)} surfaces")
        typer.echo(f"  {len(appspec.workspaces)} workspaces")
        raise typer.Exit(code=0)

    # Dispatch codegen targets
    valid_targets = {"bundle", "sql", "openapi", "asyncapi", "all"}
    if target not in valid_targets:
        typer.echo(
            f"Unknown target '{target}'. Valid: {', '.join(sorted(valid_targets))}", err=True
        )
        raise typer.Exit(code=1)

    if target != "bundle":
        output_dir = Path(out).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        _run_codegen_targets(appspec, output_dir, target)
        raise typer.Exit(code=0)

    typer.echo(f"Building production bundle for '{appspec.name}'...")

    # Create output directory
    output_dir = Path(out).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Generate BackendSpec
    typer.echo("\n[1/5] Generating backend...")
    backend_spec = convert_appspec_to_backend(appspec)
    typer.echo(f"  • {len(backend_spec.entities)} entities")
    typer.echo(f"  • {len(backend_spec.endpoints)} endpoints")

    backend_dir = output_dir / "backend"
    backend_dir.mkdir(exist_ok=True)
    spec_file = backend_dir / "backend-spec.json"
    spec_file.write_text(backend_spec.model_dump_json(indent=2))

    # 2. Generate Frontend (optional)
    if frontend:
        typer.echo("\n[2/5] Generating frontend...")
        frontend_dir = output_dir / "frontend"
        files = generate_preview_files(appspec, str(frontend_dir))
        typer.echo(f"  • {len(files)} preview files generated")
    else:
        typer.echo("\n[2/5] Skipping frontend (--no-frontend)")

    # 3. Generate main.py entry point
    typer.echo("\n[3/5] Generating entry point...")
    main_content = generate_production_main(appspec.name, frontend)
    main_file = output_dir / "main.py"
    main_file.write_text(main_content)
    typer.echo(f"  ✓ {main_file.name}")

    # 4. Generate requirements.txt
    requirements = generate_requirements()
    req_file = output_dir / "requirements.txt"
    req_file.write_text(requirements)
    typer.echo(f"  ✓ {req_file.name}")

    # 5. Generate Dockerfile (optional)
    if docker:
        typer.echo("\n[4/5] Generating Dockerfile...")
        dockerfile = generate_dockerfile(appspec.name, frontend)
        (output_dir / "Dockerfile").write_text(dockerfile)
        typer.echo("  ✓ Dockerfile")

        # Docker-compose for development/local deployment
        compose = generate_docker_compose(appspec.name)
        (output_dir / "docker-compose.yml").write_text(compose)
        typer.echo("  ✓ docker-compose.yml")

        # Local backing services (Postgres + Redis)
        local_compose = generate_local_compose(appspec.name)
        (output_dir / "docker-compose.local.yml").write_text(local_compose)
        typer.echo("  ✓ docker-compose.local.yml (Postgres + Redis)")

        # Local dev run script
        scripts_dir = output_dir / "scripts"
        scripts_dir.mkdir(exist_ok=True)
        run_script = generate_local_run_script(appspec.name)
        run_script_path = scripts_dir / "run_local.sh"
        run_script_path.write_text(run_script)
        run_script_path.chmod(0o755)
        typer.echo("  ✓ scripts/run_local.sh")
    else:
        typer.echo("\n[4/5] Skipping Dockerfile (--no-docker)")

    # 6. Generate environment template
    if env_template:
        typer.echo("\n[5/5] Generating environment template...")
        env = generate_env_template(appspec.name)
        (output_dir / ".env.example").write_text(env)
        typer.echo("  ✓ .env.example")
    else:
        typer.echo("\n[5/5] Skipping environment template (--no-env)")

    # Summary
    typer.echo("\n" + "=" * 50)
    typer.echo(f"Production bundle ready: {output_dir}")
    typer.echo("=" * 50)
    if docker:
        typer.echo("\nLocal development (production-grade):")
        typer.echo(f"  cd {output_dir}")
        typer.echo("  cp .env.example .env  # Edit configuration")
        typer.echo("  docker compose -f docker-compose.local.yml up -d  # Start Postgres + Redis")
        typer.echo("  ./scripts/run_local.sh --reload  # Start dev server")
        typer.echo("\nTo deploy with Docker:")
        typer.echo(f"  cd {output_dir}")
        typer.echo("  docker compose up --build")
    typer.echo("\nTo deploy without Docker:")
    typer.echo(f"  cd {output_dir}")
    typer.echo("  pip install -r requirements.txt")
    if frontend:
        typer.echo("  cd frontend && npm install && npm run build && cd ..")
    typer.echo("  python main.py")


# =============================================================================
# Codegen target pipeline
# =============================================================================


def _run_codegen_targets(appspec: Any, output_dir: Path, target: str) -> None:
    """Run codegen targets: sql, openapi, asyncapi, or all."""

    targets = ["sql", "openapi", "asyncapi"] if target == "all" else [target]

    typer.echo(f"Generating codegen artifacts for '{appspec.name}'...")

    for t in targets:
        if t == "sql":
            _generate_sql_target(appspec, output_dir)
        elif t == "openapi":
            _generate_openapi_target(appspec, output_dir)
        elif t == "asyncapi":
            _generate_asyncapi_target(appspec, output_dir)

    typer.echo(f"\nArtifacts written to: {output_dir}")


def _generate_sql_target(appspec: Any, output_dir: Path) -> None:
    """Generate SQL DDL schema from AppSpec."""
    try:
        from dazzle_back.converters import convert_appspec_to_backend
        from dazzle_back.runtime.sa_schema import build_metadata
    except ImportError as e:
        typer.echo(f"  SQL target requires dazzle-app-back: {e}", err=True)
        return

    backend_spec = convert_appspec_to_backend(appspec)
    metadata = build_metadata(backend_spec.entities)

    lines: list[str] = []
    lines.append(f"-- SQL schema for {appspec.name}")
    lines.append("-- Generated by dazzle build --target sql")
    lines.append(f"-- {len(backend_spec.entities)} tables\n")

    for table in metadata.sorted_tables:
        lines.append(f'CREATE TABLE IF NOT EXISTS "{table.name}" (')
        col_defs: list[str] = []
        for col in table.columns:
            parts = [f'  "{col.name}"']
            # Map SQLAlchemy type to SQL type string
            sa_type = type(col.type).__name__.upper()
            type_map = {
                "TEXT": "TEXT",
                "INTEGER": "INTEGER",
                "FLOAT": "REAL",
                "BOOLEAN": "BOOLEAN",
            }
            parts.append(type_map.get(sa_type, "TEXT"))
            if col.primary_key:
                parts.append("PRIMARY KEY")
            if not col.nullable and not col.primary_key:
                parts.append("NOT NULL")
            if col.default is not None and hasattr(col.default, "arg"):
                parts.append(f"DEFAULT {col.default.arg!r}")
            col_defs.append(" ".join(parts))
        lines.append(",\n".join(col_defs))
        lines.append(");\n")

    sql_content = "\n".join(lines)
    sql_file = output_dir / "schema.sql"
    sql_file.write_text(sql_content)
    typer.echo(f"  SQL schema -> {sql_file} ({len(backend_spec.entities)} tables)")


def _generate_openapi_target(appspec: Any, output_dir: Path) -> None:
    """Generate OpenAPI 3.1 spec from AppSpec."""
    try:
        from dazzle.specs import generate_openapi, openapi_to_json, openapi_to_yaml
    except ImportError as e:
        typer.echo(f"  OpenAPI target requires dazzle specs: {e}", err=True)
        return

    openapi = generate_openapi(appspec)

    yaml_file = output_dir / "openapi.yaml"
    yaml_file.write_text(openapi_to_yaml(openapi))

    json_file = output_dir / "openapi.json"
    json_file.write_text(openapi_to_json(openapi))

    typer.echo(f"  OpenAPI -> {yaml_file}, {json_file}")


def _generate_asyncapi_target(appspec: Any, output_dir: Path) -> None:
    """Generate AsyncAPI 3.0 spec from AppSpec."""
    try:
        from dazzle.specs import asyncapi_to_json, asyncapi_to_yaml, generate_asyncapi
    except ImportError as e:
        typer.echo(f"  AsyncAPI target requires dazzle specs: {e}", err=True)
        return

    asyncapi = generate_asyncapi(appspec)

    yaml_file = output_dir / "asyncapi.yaml"
    yaml_file.write_text(asyncapi_to_yaml(asyncapi))

    json_file = output_dir / "asyncapi.json"
    json_file.write_text(asyncapi_to_json(asyncapi))

    typer.echo(f"  AsyncAPI -> {yaml_file}, {json_file}")
