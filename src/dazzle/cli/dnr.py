"""
DNR (Dazzle Native Runtime) CLI commands.

Commands for generating and serving runtime apps using DNR.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import typer

from dazzle.core.errors import DazzleError, ParseError

if TYPE_CHECKING:
    from dazzle.core import ir
    from dazzle_dnr_back.specs import BackendSpec
    from dazzle_dnr_ui.specs import UISpec
from dazzle.core.fileset import discover_dsl_files
from dazzle.core.linker import build_appspec
from dazzle.core.lint import lint_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules

dnr_app = typer.Typer(
    help="Dazzle Native Runtime (DNR) commands for generating and serving runtime apps.",
    no_args_is_help=True,
)


@dnr_app.command("build-ui")
def dnr_build_ui(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    out: str = typer.Option("./dnr-ui", "--out", "-o", help="Output directory"),
    format: str = typer.Option(
        "vite",
        "--format",
        "-f",
        help="Output format: 'vite' (default), 'js' (split files), or 'html' (single file)",
    ),
) -> None:
    """
    Generate DNR UI artifacts from AppSpec.

    Converts AppSpec to UISpec and generates:
    - vite: Full Vite project with ES modules (production-ready)
    - js: Split HTML/JS files for development
    - html: Single HTML file with embedded runtime (quick preview)

    Examples:
        dazzle dnr build-ui                         # Vite project in ./dnr-ui
        dazzle dnr build-ui --format html -o out    # Single HTML file
        dazzle dnr build-ui --format js             # Split JS files
    """
    try:
        # Import DNR UI components
        from dazzle_dnr_ui.converters import convert_appspec_to_ui
        from dazzle_dnr_ui.runtime import (
            generate_js_app,
            generate_single_html,
            generate_vite_app,
        )
    except ImportError as e:
        typer.echo(f"DNR UI not available: {e}", err=True)
        typer.echo("Install with: pip install dazzle-dnr-ui", err=True)
        raise typer.Exit(code=1)

    # Load and build AppSpec
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    try:
        mf = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(root, mf)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, mf.project_root)

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

    # Convert to UISpec (pass shell config from manifest)
    typer.echo(f"Converting AppSpec '{appspec.name}' to UISpec...")
    ui_spec = convert_appspec_to_ui(appspec, shell_config=mf.shell)
    typer.echo(f"  • {len(ui_spec.workspaces)} workspace(s)")
    typer.echo(f"  • {len(ui_spec.components)} component(s)")
    typer.echo(f"  • {len(ui_spec.themes)} theme(s)")

    # Generate based on format
    output_dir = Path(out).resolve()

    if format == "vite":
        typer.echo(f"\nGenerating Vite project → {output_dir}")
        output_dir.mkdir(parents=True, exist_ok=True)
        files = generate_vite_app(ui_spec, str(output_dir))
        typer.echo(f"  ✓ Generated {len(files)} files")
        typer.echo("\nTo run:")
        typer.echo(f"  cd {output_dir}")
        typer.echo("  npm install")
        typer.echo("  npm run dev")

    elif format == "js":
        typer.echo(f"\nGenerating JS app → {output_dir}")
        output_dir.mkdir(parents=True, exist_ok=True)
        files = generate_js_app(ui_spec, str(output_dir))
        typer.echo(f"  ✓ Generated {len(files)} files")
        typer.echo("\nTo run:")
        typer.echo(f"  cd {output_dir}")
        typer.echo("  python -m http.server 8000")

    elif format == "html":
        output_file = output_dir / "index.html" if output_dir.suffix != ".html" else output_dir
        output_file.parent.mkdir(parents=True, exist_ok=True)
        typer.echo(f"\nGenerating single HTML → {output_file}")
        html = generate_single_html(ui_spec)
        output_file.write_text(html)
        typer.echo(f"  ✓ Generated {len(html)} bytes")
        typer.echo(f"\nOpen in browser: file://{output_file}")

    else:
        typer.echo(f"Unknown format: {format}", err=True)
        typer.echo("Use one of: vite, js, html", err=True)
        raise typer.Exit(code=1)


@dnr_app.command("build-api")
def dnr_build_api(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    out: str = typer.Option("./dnr-api", "--out", "-o", help="Output directory"),
    format: str = typer.Option(
        "json",
        "--format",
        "-f",
        help="Output format: 'json' (spec file) or 'python' (stub module)",
    ),
) -> None:
    """
    Generate DNR API spec from AppSpec.

    Converts AppSpec to BackendSpec suitable for FastAPI runtime.

    Examples:
        dazzle dnr build-api                        # JSON spec in ./dnr-api
        dazzle dnr build-api --format python        # Python module stub
    """
    try:
        from dazzle_dnr_back.converters import convert_appspec_to_backend
        from dazzle_dnr_back.specs import BackendSpec as _BackendSpec  # noqa: F401
    except ImportError as e:
        typer.echo(f"DNR Backend not available: {e}", err=True)
        typer.echo("Install with: pip install dazzle-dnr-back", err=True)
        raise typer.Exit(code=1)
    del _BackendSpec  # Used only to verify import availability

    # Load and build AppSpec
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    try:
        mf = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(root, mf)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, mf.project_root)

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
Auto-generated DNR API stub for {backend_spec.name}.

Usage:
    from dazzle_dnr_back.runtime import create_app_from_json
    app = create_app_from_json('backend-spec.json')

Or run directly:
    uvicorn api_stub:app --reload
"""

from pathlib import Path

try:
    from dazzle_dnr_back.runtime import create_app_from_json, FASTAPI_AVAILABLE
    if not FASTAPI_AVAILABLE:
        raise ImportError("FastAPI not installed")

    spec_path = Path(__file__).parent / "backend-spec.json"
    app = create_app_from_json(str(spec_path))

except ImportError as e:
    print(f"DNR runtime not available: {{e}}")
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


@dnr_app.command("migrate")
def dnr_migrate(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    db: str = typer.Option(".dazzle/data.db", "--db", "-d", help="Path to SQLite database"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show planned changes without applying"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Apply even if destructive changes detected"
    ),
) -> None:
    """
    Run database migrations for production.

    Detects schema changes between entity definitions and the database,
    then applies safe migrations automatically.

    Examples:
        # Preview migrations
        dazzle dnr migrate --dry-run

        # Apply migrations
        dazzle dnr migrate

        # Use a different database
        dazzle dnr migrate --db /path/to/prod.db

        # Force apply (including destructive changes)
        dazzle dnr migrate --force
    """
    try:
        from dazzle_dnr_back.converters import convert_appspec_to_backend
        from dazzle_dnr_back.runtime.migrations import (
            MigrationAction,
            auto_migrate,
            plan_migrations,
        )
        from dazzle_dnr_back.runtime.repository import DatabaseManager
    except ImportError as e:
        typer.echo(f"DNR packages not available: {e}", err=True)
        typer.echo("Install with: pip install dazzle-dnr-back", err=True)
        raise typer.Exit(code=1)

    # Load and build AppSpec
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    try:
        mf = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(root, mf)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, mf.project_root)

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

    # Resolve database path
    db_path = Path(db).resolve()

    # Create database manager
    db_manager = DatabaseManager(db_path)

    if dry_run:
        # Plan only, don't apply
        typer.echo(f"Analyzing database: {db_path}")
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
        typer.echo(f"Migrating database: {db_path}")
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


@dnr_app.command("build")
def dnr_build(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    out: str = typer.Option("./dist", "--out", "-o", help="Output directory"),
    docker: bool = typer.Option(True, "--docker/--no-docker", help="Generate Dockerfile"),
    env_template: bool = typer.Option(True, "--env/--no-env", help="Generate environment template"),
    frontend: bool = typer.Option(True, "--frontend/--no-frontend", help="Include frontend"),
    minify: bool = typer.Option(True, "--minify/--no-minify", help="Minify frontend assets"),
) -> None:
    """
    Build a production-ready DNR deployment bundle.

    Creates a complete deployment package with:
    - Backend: FastAPI server with production settings
    - Frontend: Built static assets (optional)
    - Dockerfile: Multi-stage Docker build
    - Environment: Template for configuration
    - Entry point: Production-ready main.py

    Examples:
        dazzle dnr build                    # Full bundle in ./dist
        dazzle dnr build -o deploy          # Output to ./deploy
        dazzle dnr build --no-frontend      # Backend only
        dazzle dnr build --no-docker        # Skip Dockerfile

    To deploy:
        cd dist && docker build -t myapp . && docker run -p 8000:8000 myapp
        # Or without Docker:
        cd dist && pip install -r requirements.txt && python main.py
    """
    try:
        from dazzle_dnr_back.converters import convert_appspec_to_backend
        from dazzle_dnr_ui.converters import convert_appspec_to_ui
        from dazzle_dnr_ui.runtime import generate_vite_app
    except ImportError as e:
        typer.echo(f"DNR packages not available: {e}", err=True)
        typer.echo("Install with: pip install dazzle-dnr-back dazzle-dnr-ui", err=True)
        raise typer.Exit(code=1)

    # Load and build AppSpec
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    try:
        mf = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(root, mf)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, mf.project_root)

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
        ui_spec = convert_appspec_to_ui(appspec, shell_config=mf.shell)
        typer.echo(f"  • {len(ui_spec.workspaces)} workspaces")
        typer.echo(f"  • {len(ui_spec.components)} components")

        frontend_dir = output_dir / "frontend"
        files = generate_vite_app(ui_spec, str(frontend_dir))
        typer.echo(f"  • {len(files)} files generated")

        # Note: In production, you'd run npm build here
        # For now, we generate the Vite project structure
    else:
        typer.echo("\n[2/5] Skipping frontend (--no-frontend)")

    # 3. Generate main.py entry point
    typer.echo("\n[3/5] Generating entry point...")
    main_content = _generate_production_main(appspec.name, frontend)
    main_file = output_dir / "main.py"
    main_file.write_text(main_content)
    typer.echo(f"  ✓ {main_file.name}")

    # 4. Generate requirements.txt
    requirements = _generate_requirements()
    req_file = output_dir / "requirements.txt"
    req_file.write_text(requirements)
    typer.echo(f"  ✓ {req_file.name}")

    # 5. Generate Dockerfile (optional)
    if docker:
        typer.echo("\n[4/5] Generating Dockerfile...")
        dockerfile = _generate_dockerfile(appspec.name, frontend)
        (output_dir / "Dockerfile").write_text(dockerfile)
        typer.echo("  ✓ Dockerfile")

        # Docker-compose for development/local deployment
        compose = _generate_docker_compose(appspec.name)
        (output_dir / "docker-compose.yml").write_text(compose)
        typer.echo("  ✓ docker-compose.yml")
    else:
        typer.echo("\n[4/5] Skipping Dockerfile (--no-docker)")

    # 6. Generate environment template
    if env_template:
        typer.echo("\n[5/5] Generating environment template...")
        env = _generate_env_template(appspec.name)
        (output_dir / ".env.example").write_text(env)
        typer.echo("  ✓ .env.example")
    else:
        typer.echo("\n[5/5] Skipping environment template (--no-env)")

    # Summary
    typer.echo("\n" + "=" * 50)
    typer.echo(f"Production bundle ready: {output_dir}")
    typer.echo("=" * 50)
    typer.echo("\nTo deploy with Docker:")
    typer.echo(f"  cd {output_dir}")
    typer.echo("  cp .env.example .env  # Edit configuration")
    typer.echo("  docker compose up --build")
    typer.echo("\nTo deploy without Docker:")
    typer.echo(f"  cd {output_dir}")
    typer.echo("  pip install -r requirements.txt")
    if frontend:
        typer.echo("  cd frontend && npm install && npm run build && cd ..")
    typer.echo("  python main.py")


def _generate_production_main(app_name: str, include_frontend: bool) -> str:
    """Generate production-ready main.py entry point."""
    return f'''"""
Production entry point for {app_name}.

Auto-generated by Dazzle DNR build.

Usage:
    python main.py                    # Run with defaults
    python main.py --port 8080        # Custom port
    python main.py --host 0.0.0.0     # Bind to all interfaces

Environment variables:
    PORT          - Server port (default: 8000)
    HOST          - Server host (default: 0.0.0.0)
    DATABASE_URL  - SQLite database path (default: ./data/app.db)
    LOG_LEVEL     - Logging level (default: INFO)
"""

import argparse
import logging
import os
from pathlib import Path

# Configure logging
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="{app_name} - DNR Production Server")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    parser.add_argument("--host", type=str, default=os.getenv("HOST", "0.0.0.0"))
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (dev only)")
    args = parser.parse_args()

    # Database setup
    db_path = os.getenv("DATABASE_URL", "./data/app.db")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Starting {app_name}")
    logger.info(f"  Host: {{args.host}}:{{args.port}}")
    logger.info(f"  Database: {{db_path}}")

    try:
        import uvicorn
        from dazzle_dnr_back.runtime import create_app_from_json

        spec_path = Path(__file__).parent / "backend" / "backend-spec.json"
        if not spec_path.exists():
            logger.error(f"Backend spec not found: {{spec_path}}")
            return 1

        app = create_app_from_json(str(spec_path), db_path=db_path)

        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            reload=args.reload,
            log_level=log_level.lower(),
        )

    except ImportError as e:
        logger.error(f"Missing dependencies: {{e}}")
        logger.error("Install with: pip install -r requirements.txt")
        return 1
    except Exception as e:
        logger.error(f"Failed to start: {{e}}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
'''


def _generate_requirements() -> str:
    """Generate requirements.txt for production."""
    return """# DNR Production Dependencies
# Generated by: dazzle dnr build

# Core runtime
dazzle-dnr-back>=0.4.0
fastapi>=0.100.0
uvicorn[standard]>=0.22.0
pydantic>=2.0.0

# Database
aiosqlite>=0.19.0

# Optional: Production server
gunicorn>=21.0.0

# Optional: Monitoring
prometheus-fastapi-instrumentator>=6.0.0
"""


def _generate_dockerfile(app_name: str, include_frontend: bool) -> str:
    """Generate multi-stage Dockerfile."""
    frontend_stage = ""
    copy_frontend = ""
    if include_frontend:
        frontend_stage = """
# Frontend build stage
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
"""
        copy_frontend = """
# Copy frontend build
COPY --from=frontend-builder /app/frontend/dist /app/static
ENV STATIC_FILES_DIR=/app/static
"""

    return f"""# Dockerfile for {app_name}
# Generated by: dazzle dnr build
{frontend_stage}
# Backend build stage
FROM python:3.11-slim AS backend

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
{copy_frontend}
# Copy backend
COPY backend/ ./backend/
COPY main.py .

# Create data directory
RUN mkdir -p /app/data

# Environment
ENV PORT=8000
ENV HOST=0.0.0.0
ENV DATABASE_URL=/app/data/app.db
ENV LOG_LEVEL=INFO

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \\
    CMD curl -f http://localhost:${{PORT}}/health || exit 1

EXPOSE ${{PORT}}

CMD ["python", "main.py"]
"""


def _generate_docker_compose(app_name: str) -> str:
    """Generate docker-compose.yml for local deployment."""
    return f"""# Docker Compose for {app_name}
# Generated by: dazzle dnr build

version: "3.8"

services:
  app:
    build: .
    ports:
      - "${{PORT:-8000}}:8000"
    environment:
      - PORT=8000
      - HOST=0.0.0.0
      - DATABASE_URL=/app/data/app.db
      - LOG_LEVEL=${{LOG_LEVEL:-INFO}}
    volumes:
      - app-data:/app/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 3s
      retries: 3
      start_period: 10s

volumes:
  app-data:
    driver: local
"""


def _generate_env_template(app_name: str) -> str:
    """Generate environment template."""
    return f"""# Environment configuration for {app_name}
# Generated by: dazzle dnr build
#
# Copy this file to .env and customize:
#   cp .env.example .env

# Server configuration
PORT=8000
HOST=0.0.0.0

# Database
DATABASE_URL=./data/app.db

# Logging
LOG_LEVEL=INFO

# Security (generate your own secret key!)
# SECRET_KEY=your-secret-key-here

# CORS (comma-separated origins)
# CORS_ORIGINS=http://localhost:3000,https://myapp.com

# Optional: Auth settings
# AUTH_ENABLED=true
# JWT_SECRET=your-jwt-secret

# Optional: File uploads
# FILES_ENABLED=true
# FILES_PATH=./uploads
# MAX_FILE_SIZE=10485760

# Production settings
# WORKERS=4
# TIMEOUT=30
"""


@dnr_app.command("serve")
def dnr_serve(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    port: int = typer.Option(3000, "--port", "-p", help="Frontend port"),
    api_port: int = typer.Option(8000, "--api-port", help="Backend API port"),
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to"),
    ui_only: bool = typer.Option(False, "--ui-only", help="Serve UI only (static files)"),
    backend_only: bool = typer.Option(
        False,
        "--backend-only",
        help="Serve backend API only (no frontend UI)",
    ),
    db_path: str = typer.Option(".dazzle/data.db", "--db", help="SQLite database path"),
    test_mode: bool = typer.Option(
        False,
        "--test-mode",
        help="Enable test endpoints (/__test__/seed, /__test__/reset, etc.)",
    ),
    watch: bool = typer.Option(
        False,
        "--watch",
        "-w",
        help="Enable hot reload: watch DSL files and auto-refresh browser on changes",
    ),
    local: bool = typer.Option(
        False,
        "--local",
        help="Run locally without Docker (default is docker-first)",
    ),
    rebuild: bool = typer.Option(
        False,
        "--rebuild",
        help="Force rebuild of Docker image",
    ),
    attach: bool = typer.Option(
        False,
        "--attach",
        "-a",
        help="Run Docker container attached (stream logs to terminal)",
    ),
    single_container: bool = typer.Option(
        False,
        "--single-container",
        help="Use legacy single-container mode (combined frontend + backend)",
    ),
    graphql: bool = typer.Option(
        False,
        "--graphql",
        help="Enable GraphQL endpoint at /graphql (requires strawberry-graphql)",
    ),
) -> None:
    """
    Serve DNR app (backend API + UI with live data).

    By default, runs frontend and backend in separate Docker containers.
    Use --single-container for legacy combined mode, --local to run without Docker.

    Runs:
    - FastAPI backend on api-port (default 8000) with SQLite persistence
    - Vite frontend dev server on port (default 3000)
    - Auto-migration for schema changes
    - Interactive API docs at http://host:api-port/docs

    Examples:
        dazzle dnr serve                    # Split containers (default)
        dazzle dnr serve --local --watch    # Local mode with hot reload
        dazzle dnr serve --attach           # Run Docker with log streaming
        dazzle dnr serve --local            # Run locally without Docker
        dazzle dnr serve --single-container # Legacy single-container mode
        dazzle dnr serve --backend-only     # API server only (for separate frontend)
        dazzle dnr serve --rebuild          # Force Docker image rebuild
        dazzle dnr serve --port 4000        # Frontend on 4000
        dazzle dnr serve --api-port 9000    # API on 9000
        dazzle dnr serve --ui-only          # Static UI only (no API)
        dazzle dnr serve --db ./my.db       # Custom database path
        dazzle dnr serve --test-mode        # Enable E2E test endpoints
        dazzle dnr serve --graphql          # Enable GraphQL at /graphql

    Hot reload (--watch):
        Watch DSL files for changes and auto-refresh browser.
        Currently only works in --local mode.

    Related commands:
        dazzle dnr stop                     # Stop the running container
        dazzle dnr rebuild                  # Rebuild and restart container
        dazzle dnr logs                     # View container logs
    """
    # Resolve project path from manifest
    manifest_path = Path(manifest).resolve()
    project_root = manifest_path.parent

    # Load manifest to get auth config and project name
    try:
        mf = load_manifest(manifest_path)
        auth_enabled = mf.auth.enabled
        project_name = mf.name
    except Exception:
        auth_enabled = False
        project_name = None

    # Warn if --watch is used without --local
    if watch and not local:
        typer.echo(
            "Note: --watch requires --local mode. Enabling local mode automatically.",
            err=True,
        )
        local = True

    # Docker-first: unless --local is specified, try Docker first
    if not local and not ui_only and not backend_only:
        try:
            from dazzle_dnr_ui.runtime import is_docker_available, run_in_docker

            if is_docker_available():
                detach = not attach  # Default to detached (no logs), --attach streams logs
                mode_desc = "single-container" if single_container else "split containers"
                auth_desc = " with auth" if auth_enabled else ""
                typer.echo(
                    f"Running in Docker mode ({mode_desc}{auth_desc}, use --local to run without Docker)"
                    if attach
                    else f"Starting Docker containers in background ({mode_desc}{auth_desc})..."
                )
                exit_code = run_in_docker(
                    project_path=project_root,
                    frontend_port=port,
                    api_port=api_port,
                    test_mode=test_mode,
                    auth_enabled=auth_enabled,
                    rebuild=rebuild,
                    detach=detach,
                    single_container=single_container,
                    project_name=project_name,
                )
                raise typer.Exit(code=exit_code)
            else:
                typer.echo("Docker not available, falling back to local mode")
                typer.echo("Install Docker for the recommended development experience")
                typer.echo()
        except ImportError:
            pass  # Docker runner not available, fall back to local

    # Local mode execution
    try:
        from dazzle_dnr_back.converters import convert_appspec_to_backend
        from dazzle_dnr_back.runtime import FASTAPI_AVAILABLE
        from dazzle_dnr_ui.converters import convert_appspec_to_ui
        from dazzle_dnr_ui.runtime import generate_single_html, run_combined_server
    except ImportError as e:
        typer.echo(f"DNR runtime not available: {e}", err=True)
        typer.echo("Install with: pip install dazzle-dnr-back dazzle-dnr-ui", err=True)
        raise typer.Exit(code=1)

    if not FASTAPI_AVAILABLE and not ui_only:
        typer.echo("FastAPI not installed. Use --ui-only or install:", err=True)
        typer.echo("  pip install fastapi uvicorn", err=True)
        raise typer.Exit(code=1)

    # Load AppSpec
    root = project_root

    try:
        mf = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(root, mf)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, mf.project_root)

        errors, _ = lint_appspec(appspec)
        if errors:
            typer.echo("Cannot serve; spec has validation errors:", err=True)
            for err in errors:
                typer.echo(f"  ERROR: {err}", err=True)
            raise typer.Exit(code=1)

    except (ParseError, DazzleError) as e:
        typer.echo(f"Error loading spec: {e}", err=True)
        raise typer.Exit(code=1)

    if ui_only:
        # Serve UI only with simple HTTP server
        import http.server
        import socketserver
        import tempfile

        ui_spec = convert_appspec_to_ui(appspec, shell_config=mf.shell)
        html = generate_single_html(ui_spec)

        with tempfile.TemporaryDirectory() as tmpdir:
            html_path = Path(tmpdir) / "index.html"
            html_path.write_text(html)

            os.chdir(tmpdir)
            handler = http.server.SimpleHTTPRequestHandler
            typer.echo(f"\nServing DNR UI at http://{host}:{port}")
            typer.echo("Press Ctrl+C to stop\n")

            with socketserver.TCPServer((host, port), handler) as httpd:
                try:
                    httpd.serve_forever()
                except KeyboardInterrupt:
                    typer.echo("\nStopped.")
        return

    if backend_only:
        # Serve backend API only (no frontend UI)
        from dazzle_dnr_ui.runtime import run_backend_only

        backend_spec = convert_appspec_to_backend(appspec)

        typer.echo(f"Starting DNR backend for '{appspec.name}'...")
        typer.echo(f"  • {len(backend_spec.entities)} entities")
        typer.echo(f"  • {len(backend_spec.endpoints)} endpoints")
        typer.echo(f"  • Database: {db_path}")
        if test_mode:
            typer.echo("  • Test mode: ENABLED (/__test__/* endpoints available)")
        if graphql:
            typer.echo("  • GraphQL: ENABLED (/graphql endpoint)")
        typer.echo()
        typer.echo(f"API: http://{host}:{api_port}")
        typer.echo(f"Docs: http://{host}:{api_port}/docs")
        if graphql:
            typer.echo(f"GraphQL: http://{host}:{api_port}/graphql")
        typer.echo()

        db_file = Path(db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        run_backend_only(
            backend_spec=backend_spec,
            port=api_port,
            db_path=db_file,
            enable_test_mode=test_mode,
            enable_graphql=graphql,
            host=host,
        )
        return

    # Full combined server with API + UI
    typer.echo(f"Starting DNR server for '{appspec.name}'...")

    # Convert specs (pass shell config from manifest)
    backend_spec = convert_appspec_to_backend(appspec)
    ui_spec = convert_appspec_to_ui(appspec, shell_config=mf.shell)

    typer.echo(f"  • {len(backend_spec.entities)} entities")
    typer.echo(f"  • {len(backend_spec.endpoints)} endpoints")
    typer.echo(f"  • {len(ui_spec.workspaces)} workspaces")
    typer.echo(f"  • Database: {db_path}")
    typer.echo()

    # Ensure database directory exists
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    # Run combined server
    # Show test mode status
    if test_mode:
        typer.echo("  • Test mode: ENABLED (/__test__/* endpoints available)")

    # Show hot reload status
    if watch:
        typer.echo("  • Hot reload: ENABLED (watching DSL files)")

    run_combined_server(
        backend_spec=backend_spec,
        ui_spec=ui_spec,
        backend_port=api_port,
        frontend_port=port,
        db_path=db_file,
        enable_test_mode=test_mode,
        enable_auth=auth_enabled,
        host=host,
        enable_watch=watch,
        project_root=project_root,
    )


@dnr_app.command("info")
def dnr_info() -> None:
    """
    Show DNR installation status and available features.
    """
    typer.echo("Dazzle Native Runtime (DNR) Status")
    typer.echo("=" * 50)

    # Check DNR Backend
    dnr_back_available = False
    fastapi_available = False
    try:
        import dazzle_dnr_back  # noqa: F401

        dnr_back_available = True
        from dazzle_dnr_back.runtime import FASTAPI_AVAILABLE

        fastapi_available = FASTAPI_AVAILABLE
    except ImportError:
        pass

    # Check DNR UI
    dnr_ui_available = False
    try:
        import dazzle_dnr_ui  # noqa: F401

        dnr_ui_available = True
    except ImportError:
        pass

    # Check uvicorn
    uvicorn_available = False
    try:
        import uvicorn  # noqa: F401

        uvicorn_available = True
    except ImportError:
        pass

    typer.echo(
        f"DNR Backend:   {'✓' if dnr_back_available else '✗'} {'installed' if dnr_back_available else 'not installed'}"
    )
    typer.echo(
        f"DNR UI:        {'✓' if dnr_ui_available else '✗'} {'installed' if dnr_ui_available else 'not installed'}"
    )
    typer.echo(
        f"FastAPI:       {'✓' if fastapi_available else '✗'} {'installed' if fastapi_available else 'not installed'}"
    )
    typer.echo(
        f"Uvicorn:       {'✓' if uvicorn_available else '✗'} {'installed' if uvicorn_available else 'not installed'}"
    )

    typer.echo("\nAvailable Commands:")
    if dnr_ui_available:
        typer.echo("  dazzle dnr build-ui   Generate UI (Vite/JS/HTML)")
    if dnr_back_available:
        typer.echo("  dazzle dnr build-api  Generate API spec")
    if dnr_back_available and fastapi_available and uvicorn_available:
        typer.echo("  dazzle dnr serve      Run development server")
    elif dnr_ui_available:
        typer.echo("  dazzle dnr serve --ui-only  Serve UI only")

    if not (dnr_back_available and dnr_ui_available):
        typer.echo("\nTo install DNR packages:")
        if not dnr_back_available:
            typer.echo("  pip install dazzle-dnr-back")
        if not dnr_ui_available:
            typer.echo("  pip install dazzle-dnr-ui")
        if not fastapi_available:
            typer.echo("  pip install fastapi")
        if not uvicorn_available:
            typer.echo("  pip install uvicorn")


def _get_container_name(project_root: Path, project_name: str | None = None) -> str:
    """Get the Docker container name for a project.

    Uses project_name from manifest if provided, otherwise falls back to directory name.
    """
    base_name = project_name or project_root.resolve().name
    return f"dazzle-{base_name}"


def _is_container_running(container_name: str) -> bool:
    """Check if a Docker container is running."""
    import subprocess

    try:
        result = subprocess.run(
            ["docker", "ps", "-q", "-f", f"name={container_name}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return bool(result.stdout.strip())
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


@dnr_app.command("stop")
def dnr_stop(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    remove: bool = typer.Option(
        True,
        "--remove/--no-remove",
        help="Remove the container after stopping",
    ),
) -> None:
    """
    Stop the running DNR Docker container.

    Stops and optionally removes the Docker container for this project.

    Examples:
        dazzle dnr stop              # Stop and remove container
        dazzle dnr stop --no-remove  # Stop but keep container
    """
    import subprocess

    manifest_path = Path(manifest).resolve()
    project_root = manifest_path.parent

    # Load manifest to get project name
    try:
        mf = load_manifest(manifest_path)
        project_name = mf.name
    except Exception:
        project_name = None

    container_name = _get_container_name(project_root, project_name)

    # Check if container is running
    if not _is_container_running(container_name):
        typer.echo(f"Container '{container_name}' is not running")
        raise typer.Exit(code=0)

    typer.echo(f"Stopping container: {container_name}")

    try:
        # Stop the container
        result = subprocess.run(
            ["docker", "stop", container_name],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            typer.echo(f"Failed to stop container: {result.stderr}", err=True)
            raise typer.Exit(code=1)

        typer.echo("Container stopped")

        # Remove if requested
        if remove:
            result = subprocess.run(
                ["docker", "rm", container_name],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                typer.echo("Container removed")

    except subprocess.TimeoutExpired:
        typer.echo("Timeout stopping container", err=True)
        raise typer.Exit(code=1)
    except FileNotFoundError:
        typer.echo("Docker not found", err=True)
        raise typer.Exit(code=1)


@dnr_app.command("rebuild")
def dnr_rebuild(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    port: int = typer.Option(3000, "--port", "-p", help="Frontend port"),
    api_port: int = typer.Option(8000, "--api-port", help="Backend API port"),
    test_mode: bool = typer.Option(
        False,
        "--test-mode",
        help="Enable test endpoints (/__test__/seed, /__test__/reset, etc.)",
    ),
    attach: bool = typer.Option(
        False,
        "--attach",
        "-a",
        help="Run Docker container attached (stream logs to terminal)",
    ),
) -> None:
    """
    Rebuild the Docker image and restart the container.

    Stops any running container, rebuilds the Docker image from the current
    DSL files, and starts a fresh container.

    Examples:
        dazzle dnr rebuild              # Rebuild and restart (detached)
        dazzle dnr rebuild --attach     # Rebuild and restart with logs
        dazzle dnr rebuild --test-mode  # Rebuild with test endpoints
    """
    import subprocess

    manifest_path = Path(manifest).resolve()
    project_root = manifest_path.parent

    # Load manifest to get project name
    try:
        mf = load_manifest(manifest_path)
        project_name = mf.name
    except Exception:
        project_name = None

    container_name = _get_container_name(project_root, project_name)

    # Stop existing container if running
    if _is_container_running(container_name):
        typer.echo(f"Stopping existing container: {container_name}")
        subprocess.run(
            ["docker", "stop", container_name],
            capture_output=True,
            timeout=30,
        )
        subprocess.run(
            ["docker", "rm", container_name],
            capture_output=True,
            timeout=10,
        )
        typer.echo("Stopped existing container")

    # Now start with rebuild flag
    typer.echo("Rebuilding Docker image from DSL...")

    try:
        from dazzle_dnr_ui.runtime import is_docker_available, run_in_docker

        if not is_docker_available():
            typer.echo("Docker is not available", err=True)
            raise typer.Exit(code=1)

        detach = not attach
        exit_code = run_in_docker(
            project_path=project_root,
            frontend_port=port,
            api_port=api_port,
            test_mode=test_mode,
            rebuild=True,  # Force rebuild
            detach=detach,
        )
        raise typer.Exit(code=exit_code)

    except ImportError as e:
        typer.echo(f"DNR runtime not available: {e}", err=True)
        raise typer.Exit(code=1)


@dnr_app.command("logs")
def dnr_logs(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    follow: bool = typer.Option(
        False,
        "--follow",
        "-f",
        help="Follow log output (stream new logs)",
    ),
    tail: int = typer.Option(
        100,
        "--tail",
        "-n",
        help="Number of lines to show from end of logs",
    ),
) -> None:
    """
    View logs from the running DNR Docker container.

    Shows the most recent logs from the container. Use --follow to stream
    new logs as they are generated.

    Examples:
        dazzle dnr logs              # Show last 100 lines
        dazzle dnr logs -f           # Follow/stream logs
        dazzle dnr logs -n 50        # Show last 50 lines
        dazzle dnr logs -f -n 10     # Follow starting from last 10 lines
    """
    import subprocess

    manifest_path = Path(manifest).resolve()
    project_root = manifest_path.parent

    # Load manifest to get project name
    try:
        mf = load_manifest(manifest_path)
        project_name = mf.name
    except Exception:
        project_name = None

    container_name = _get_container_name(project_root, project_name)

    # Check if container exists
    if not _is_container_running(container_name):
        typer.echo(f"Container '{container_name}' is not running")
        typer.echo("Start it with: dazzle dnr serve")
        raise typer.Exit(code=1)

    # Build docker logs command
    cmd = ["docker", "logs"]

    if follow:
        cmd.append("-f")

    cmd.extend(["--tail", str(tail)])
    cmd.append(container_name)

    typer.echo(f"Logs from container: {container_name}")
    typer.echo("-" * 50)

    try:
        # Run docker logs, passing output directly to terminal
        subprocess.run(cmd)
    except KeyboardInterrupt:
        typer.echo("\nStopped following logs")
    except FileNotFoundError:
        typer.echo("Docker not found", err=True)
        raise typer.Exit(code=1)


@dnr_app.command("status")
def dnr_status(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
) -> None:
    """
    Show the status of the DNR Docker container.

    Displays whether the container is running, its ports, and resource usage.

    Examples:
        dazzle dnr status
    """
    import subprocess

    manifest_path = Path(manifest).resolve()
    project_root = manifest_path.parent

    # Load manifest to get project name
    try:
        mf = load_manifest(manifest_path)
        project_name = mf.name
    except Exception:
        project_name = None

    container_name = _get_container_name(project_root, project_name)

    typer.echo(f"DNR Container Status: {container_name}")
    typer.echo("=" * 50)

    # Check if container is running
    if not _is_container_running(container_name):
        typer.echo("Status: NOT RUNNING")
        typer.echo("\nStart with: dazzle dnr serve")
        return

    typer.echo("Status: RUNNING")

    # Get container details
    try:
        result = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                "{{range .NetworkSettings.Ports}}{{.}}{{end}}",
                container_name,
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            typer.echo(f"Ports: {result.stdout.strip()}")

        # Get container stats (CPU, memory)
        result = subprocess.run(
            [
                "docker",
                "stats",
                "--no-stream",
                "--format",
                "CPU: {{.CPUPerc}}, Memory: {{.MemUsage}}",
                container_name,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            typer.echo(result.stdout.strip())

        # Health check
        result = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                "{{.State.Health.Status}}",
                container_name,
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            health = result.stdout.strip()
            typer.echo(f"Health: {health}")

    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    typer.echo("\nCommands:")
    typer.echo("  dazzle dnr logs     - View container logs")
    typer.echo("  dazzle dnr stop     - Stop the container")
    typer.echo("  dazzle dnr rebuild  - Rebuild and restart")


@dnr_app.command("inspect")
def dnr_inspect(
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
        help="Query a running DNR server for runtime state (entity counts, uptime, etc.)",
    ),
    api_url: str = typer.Option(
        "http://localhost:8000",
        "--api-url",
        help="URL of running DNR API server (for --live mode)",
    ),
    schema: bool = typer.Option(
        False,
        "--schema",
        help="Generate and display GraphQL schema SDL (requires strawberry-graphql)",
    ),
) -> None:
    """
    Inspect the DNR app structure and generated artifacts.

    Shows detailed information about entities, surfaces, workspaces,
    API endpoints, and UI components generated from the DSL.

    Use --live to query a running server for runtime statistics like
    entity counts, uptime, and database state.

    Examples:
        dazzle dnr inspect                    # Full tree view
        dazzle dnr inspect --format json      # JSON output
        dazzle dnr inspect --format summary   # Brief summary
        dazzle dnr inspect --entity Task      # Inspect Task entity
        dazzle dnr inspect --surface task_list  # Inspect surface
        dazzle dnr inspect --endpoints        # Show API endpoints
        dazzle dnr inspect --components       # Show UI components
        dazzle dnr inspect --live             # Query running server
        dazzle dnr inspect --live --entity Task  # Live entity details
        dazzle dnr inspect --schema           # Show GraphQL schema SDL
    """
    import json as json_module

    # Handle live mode - query running server
    if live:
        _inspect_live(api_url, format_output, entity)
        return

    manifest_path = Path(manifest).resolve()
    project_root = manifest_path.parent

    # Load and parse the project
    try:
        mf = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(project_root, mf)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, mf.project_root)
    except Exception as e:
        typer.echo(f"Error loading project: {e}", err=True)
        raise typer.Exit(code=1)

    # Import converters
    try:
        from dazzle_dnr_back.converters import convert_appspec_to_backend
        from dazzle_dnr_ui.converters import convert_appspec_to_ui

        backend_spec = convert_appspec_to_backend(appspec)
        ui_spec = convert_appspec_to_ui(appspec, shell_config=mf.shell)
    except ImportError as e:
        typer.echo(f"DNR runtime not available: {e}", err=True)
        raise typer.Exit(code=1)

    # Handle specific item inspection
    if entity:
        _inspect_entity(appspec, backend_spec, entity, format_output)
        return

    if surface:
        _inspect_surface(appspec, ui_spec, surface, format_output)
        return

    if workspace:
        _inspect_workspace(appspec, ui_spec, workspace, format_output)
        return

    if endpoints:
        _inspect_endpoints(backend_spec, format_output)
        return

    if schema:
        _inspect_schema(backend_spec, format_output)
        return

    if components:
        _inspect_components(ui_spec, format_output)
        return

    # Get entities from domain
    entities = appspec.domain.entities

    # Full inspection
    if format_output == "json":
        output = {
            "app": appspec.name,
            "entities": [e.name for e in entities],
            "surfaces": [s.name for s in appspec.surfaces],
            "workspaces": [w.name for w in appspec.workspaces],
            "endpoints": len(backend_spec.endpoints),
            "components": len(ui_spec.components),
        }
        typer.echo(json_module.dumps(output, indent=2))
    elif format_output == "summary":
        typer.echo(f"App: {appspec.name}")
        typer.echo(f"  Entities:   {len(entities)}")
        typer.echo(f"  Surfaces:   {len(appspec.surfaces)}")
        typer.echo(f"  Workspaces: {len(appspec.workspaces)}")
        typer.echo(f"  Endpoints:  {len(backend_spec.endpoints)}")
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

        # Backend summary
        typer.echo("│")
        typer.echo(f"├── 🔧 Backend: {len(backend_spec.endpoints)} endpoints")

        # UI summary
        typer.echo("│")
        typer.echo(f"└── 🎨 UI: {len(ui_spec.components)} components")


def _inspect_entity(
    appspec: ir.AppSpec,
    backend_spec: BackendSpec,
    entity_name: str,
    format_output: str,
) -> None:
    """Inspect a specific entity."""
    import json as json_module

    entities = appspec.domain.entities

    # Find entity
    entity = next((e for e in entities if e.name == entity_name), None)
    if not entity:
        typer.echo(f"Entity '{entity_name}' not found", err=True)
        typer.echo(f"Available: {', '.join(e.name for e in entities)}")
        raise typer.Exit(code=1)

    # Find related endpoints
    related_endpoints = [
        ep for ep in backend_spec.endpoints if entity_name.lower() in ep.path.lower()
    ]

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
            "endpoints": [{"method": str(ep.method), "path": ep.path} for ep in related_endpoints],
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

        if related_endpoints:
            typer.echo()
            typer.echo("   Endpoints:")
            for ep in related_endpoints:
                typer.echo(f"   • {ep.method:6} {ep.path}")


def _inspect_surface(
    appspec: ir.AppSpec,
    ui_spec: UISpec,
    surface_name: str,
    format_output: str,
) -> None:
    """Inspect a specific surface."""
    import json as json_module

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
    import json as json_module

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


def _inspect_endpoints(backend_spec: BackendSpec, format_output: str) -> None:
    """Inspect API endpoints."""
    import json as json_module

    if format_output == "json":
        output = [
            {"method": str(ep.method), "path": ep.path, "name": ep.name}
            for ep in backend_spec.endpoints
        ]
        typer.echo(json_module.dumps(output, indent=2))
    else:
        typer.echo("🔧 API Endpoints")
        typer.echo()
        # Group by entity/path prefix
        for ep in sorted(backend_spec.endpoints, key=lambda e: (e.path, str(e.method))):
            typer.echo(f"   {str(ep.method):6} {ep.path}")


def _inspect_components(ui_spec: UISpec, format_output: str) -> None:
    """Inspect UI components."""
    import json as json_module

    if format_output == "json":
        output = [{"name": c.name, "category": c.category} for c in ui_spec.components]
        typer.echo(json_module.dumps(output, indent=2))
    else:
        typer.echo("🎨 UI Components")
        typer.echo()
        for c in ui_spec.components:
            typer.echo(f"   • {c.name} ({c.category})")


def _inspect_schema(backend_spec: BackendSpec, format_output: str) -> None:
    """Inspect GraphQL schema."""
    import json as json_module

    try:
        from dazzle_dnr_back.graphql.integration import inspect_schema, print_schema
    except ImportError:
        typer.echo(
            "GraphQL support not available. Install with: pip install strawberry-graphql",
            err=True,
        )
        raise typer.Exit(code=1)

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
    """Query running DNR server for runtime state."""
    import json as json_module
    import urllib.error
    import urllib.request

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
        data = fetch_json(f"/_dnr/entity/{entity_name}")
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
    stats = fetch_json("/_dnr/stats")
    health = fetch_json("/_dnr/health")
    spec = fetch_json("/_dnr/spec")

    if not stats:
        typer.echo("Could not connect to DNR server", err=True)
        typer.echo(f"Tried: {api_url}/_dnr/stats")
        typer.echo()
        typer.echo("Make sure the server is running:")
        typer.echo("  dazzle dnr serve")
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


@dnr_app.command("test")
def dnr_test(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    api_only: bool = typer.Option(
        False,
        "--api-only",
        help="Run only API contract tests (no UI tests)",
    ),
    e2e: bool = typer.Option(
        False,
        "--e2e",
        help="Run E2E tests with Playwright (requires app running or --start-server)",
    ),
    benchmark: bool = typer.Option(
        False,
        "--benchmark",
        help="Run performance benchmarks",
    ),
    a11y: bool = typer.Option(
        False,
        "--a11y",
        help="Run accessibility checks (requires Playwright)",
    ),
    a11y_level: str = typer.Option(
        "AA",
        "--a11y-level",
        help="WCAG level to check: A, AA, or AAA (default: AA)",
    ),
    start_server: bool = typer.Option(
        True,
        "--start-server/--no-start-server",
        help="Automatically start server for testing (default: true)",
    ),
    port: int = typer.Option(
        8000,
        "--port",
        "-p",
        help="API server port",
    ),
    ui_port: int = typer.Option(
        3000,
        "--ui-port",
        help="UI server port (for E2E tests)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Verbose output",
    ),
    output: str = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file for test results JSON",
    ),
) -> None:
    """
    Run tests for a DNR application.

    This command provides comprehensive testing for DNR apps:
    - API contract tests: Validates all endpoints against the spec
    - E2E tests: Runs Playwright-based UI tests (with --e2e)
    - Benchmarks: Performance testing with latency/throughput metrics (with --benchmark)
    - Accessibility: WCAG compliance checks using axe-core (with --a11y)

    The server is automatically started in test mode for the duration of tests.

    Examples:
        dazzle dnr test                       # Run API tests (starts server)
        dazzle dnr test --api-only            # Run only API contract tests
        dazzle dnr test --e2e                 # Include E2E UI tests
        dazzle dnr test --benchmark           # Run performance benchmarks
        dazzle dnr test --a11y                # Run WCAG AA accessibility checks
        dazzle dnr test --a11y --a11y-level A # Run WCAG Level A checks only
        dazzle dnr test --no-start-server     # Use already-running server
        dazzle dnr test -o results.json       # Save results to file
    """
    import json as json_module
    import subprocess
    import sys
    import time

    # Load and build AppSpec
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    try:
        mf = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(root, mf)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, mf.project_root)

        # Validate
        errors, warnings = lint_appspec(appspec)
        if errors:
            typer.echo("Cannot run tests; spec has validation errors:", err=True)
            for err in errors:
                typer.echo(f"  ERROR: {err}", err=True)
            raise typer.Exit(code=1)

        for warn in warnings:
            if verbose:
                typer.echo(f"WARNING: {warn}")

    except (ParseError, DazzleError) as e:
        typer.echo(f"Error loading spec: {e}", err=True)
        raise typer.Exit(code=1)

    # Convert to BackendSpec for API testing
    try:
        from dazzle_dnr_back.converters import convert_appspec_to_backend
    except ImportError as e:
        typer.echo(f"DNR backend not available: {e}", err=True)
        raise typer.Exit(code=1)

    backend_spec = convert_appspec_to_backend(appspec)

    typer.echo(f"Testing DNR application: {appspec.name}")
    typer.echo(f"  • {len(backend_spec.entities)} entities")
    typer.echo(f"  • {len(backend_spec.endpoints)} endpoints")
    typer.echo()

    # Start server if requested
    server_process = None
    api_url = f"http://localhost:{port}"
    temp_db_path: str | None = None

    if start_server:
        # Create a temporary database for test isolation
        import tempfile

        fd, temp_db_path = tempfile.mkstemp(suffix=".db", prefix="dazzle_test_")
        os.close(fd)  # Close the file descriptor, we just need the path

        # Determine if we need the UI (for E2E or a11y tests)
        need_ui = e2e or a11y
        if need_ui:
            typer.echo("Starting DNR server with UI in test mode...")
        else:
            typer.echo("Starting DNR server in test mode...")

        # Use subprocess to start the server
        # Note: serve uses --port for frontend (3000) and --api-port for API (8000)
        if need_ui:
            # Full server with UI
            cmd = [
                sys.executable,
                "-m",
                "dazzle.cli",
                "dnr",
                "serve",
                "--local",
                "--port",
                str(ui_port),  # Frontend port
                "--api-port",
                str(port),  # API port
                "--test-mode",
                "--db",
                temp_db_path,  # Use ephemeral database for test isolation
                "-m",
                str(manifest_path),
            ]
        else:
            # Backend only
            cmd = [
                sys.executable,
                "-m",
                "dazzle.cli",
                "dnr",
                "serve",
                "--local",
                "--backend-only",
                "--port",
                str(port),  # API port (used as main port in backend-only mode)
                "--test-mode",
                "--db",
                temp_db_path,  # Use ephemeral database for test isolation
                "-m",
                str(manifest_path),
            ]

        server_process = subprocess.Popen(
            cmd,
            cwd=root,
            stdout=subprocess.PIPE if not verbose else None,
            stderr=subprocess.PIPE if not verbose else None,
        )

        # Wait for server to be ready
        max_wait = 30.0
        waited = 0.0
        while waited < max_wait:
            try:
                import urllib.request

                with urllib.request.urlopen(f"{api_url}/health", timeout=1) as resp:
                    if resp.status == 200:
                        break
            except Exception:
                pass
            time.sleep(0.5)
            waited += 0.5

        if waited >= max_wait:
            typer.echo("Server failed to start within timeout", err=True)
            if server_process:
                server_process.terminate()
            raise typer.Exit(code=1)

        typer.echo(f"  API ready at {api_url}")

        # Wait for UI to be ready if needed
        if need_ui:
            ui_url = f"http://localhost:{ui_port}"
            ui_waited = 0.0
            while ui_waited < max_wait:
                try:
                    with urllib.request.urlopen(ui_url, timeout=1) as resp:
                        if resp.status == 200:
                            break
                except Exception:
                    pass
                time.sleep(0.5)
                ui_waited += 0.5

            if ui_waited >= max_wait:
                typer.secho(
                    f"  Warning: UI at {ui_url} not responding",
                    fg=typer.colors.YELLOW,
                )
            else:
                typer.echo(f"  UI ready at {ui_url}")

        typer.echo()

    results: dict[str, Any] = {
        "app_name": appspec.name,
        "api_tests": [],
        "e2e_tests": [],
        "a11y_results": None,
        "summary": {
            "api_passed": 0,
            "api_failed": 0,
            "e2e_passed": 0,
            "e2e_failed": 0,
            "a11y_violations": 0,
            "a11y_passed": True,
        },
    }

    try:
        # Import test runners from separate module
        from dazzle.cli.dnr_testing import (
            run_accessibility_checks,
            run_api_contract_tests,
            run_benchmarks,
            run_e2e_tests,
        )

        # Run API contract tests
        typer.echo("Running API contract tests...")
        api_results = run_api_contract_tests(backend_spec, api_url, verbose)
        results["api_tests"] = api_results["tests"]
        results["summary"]["api_passed"] = api_results["passed"]
        results["summary"]["api_failed"] = api_results["failed"]

        typer.echo(f"  API tests: {api_results['passed']} passed, {api_results['failed']} failed")

        # Run E2E tests if requested
        if e2e and not api_only:
            typer.echo()
            typer.echo("Running E2E tests...")
            e2e_results = run_e2e_tests(
                manifest_path, api_url, f"http://localhost:{ui_port}", verbose
            )
            results["e2e_tests"] = e2e_results["tests"]
            results["summary"]["e2e_passed"] = e2e_results["passed"]
            results["summary"]["e2e_failed"] = e2e_results["failed"]

            typer.echo(
                f"  E2E tests: {e2e_results['passed']} passed, {e2e_results['failed']} failed"
            )

        # Run benchmarks if requested
        if benchmark:
            typer.echo()
            typer.echo("Running performance benchmarks...")
            bench_results = run_benchmarks(backend_spec, api_url, verbose)
            results["benchmarks"] = bench_results

            # Display benchmark summary
            typer.echo(f"  Cold start:    {bench_results['cold_start_ms']:.0f}ms")
            typer.echo(f"  Latency p50:   {bench_results['latency_p50_ms']:.1f}ms")
            typer.echo(f"  Latency p95:   {bench_results['latency_p95_ms']:.1f}ms")
            typer.echo(f"  Latency p99:   {bench_results['latency_p99_ms']:.1f}ms")
            typer.echo(f"  Throughput:    {bench_results['throughput_rps']:.0f} req/s")

        # Run accessibility checks if requested
        if a11y and not api_only:
            typer.echo()
            typer.echo(f"Running WCAG {a11y_level.upper()} accessibility checks...")
            a11y_results = run_accessibility_checks(
                f"http://localhost:{ui_port}",
                a11y_level.upper(),
                appspec,
                verbose,
            )
            results["a11y_results"] = a11y_results
            results["summary"]["a11y_violations"] = a11y_results["violation_count"]
            results["summary"]["a11y_passed"] = a11y_results["passed"]

            # Display a11y summary
            if a11y_results["passed"]:
                typer.secho(
                    f"  No WCAG {a11y_level.upper()} violations found!",
                    fg=typer.colors.GREEN,
                )
            else:
                typer.secho(
                    f"  {a11y_results['violation_count']} WCAG {a11y_level.upper()} violation(s) found",
                    fg=typer.colors.YELLOW,
                )
                if verbose and a11y_results.get("violations"):
                    for v in a11y_results["violations"][:5]:  # Show first 5
                        typer.echo(f"    - {v['id']}: {v['impact']} - {v['help']}")

    finally:
        # Stop server if we started it
        if server_process:
            server_process.terminate()
            try:
                server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_process.kill()

        # Clean up temporary database
        if temp_db_path and os.path.exists(temp_db_path):
            try:
                os.unlink(temp_db_path)
            except OSError:
                pass  # Best effort cleanup

    # Summary
    typer.echo()
    total_passed = results["summary"]["api_passed"] + results["summary"]["e2e_passed"]
    total_failed = results["summary"]["api_failed"] + results["summary"]["e2e_failed"]
    a11y_violations = results["summary"]["a11y_violations"]
    a11y_passed = results["summary"]["a11y_passed"]

    if total_failed == 0 and a11y_passed:
        typer.secho(f"✓ All {total_passed} tests passed!", fg=typer.colors.GREEN)
    elif total_failed == 0 and not a11y_passed:
        typer.secho(
            f"✓ All {total_passed} tests passed, but {a11y_violations} a11y violation(s)",
            fg=typer.colors.YELLOW,
        )
    else:
        msg = f"✗ {total_passed} passed, {total_failed} failed"
        if a11y_violations > 0:
            msg += f", {a11y_violations} a11y violation(s)"
        typer.secho(msg, fg=typer.colors.RED)

    # Output results to file
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json_module.dumps(results, indent=2))
        typer.echo(f"Results saved to {output_path}")

    if total_failed > 0:
        raise typer.Exit(code=1)

