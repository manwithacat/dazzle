# Production Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the vestigial container runtime with `--production` flag on `dazzle serve` and a new `dazzle deploy dockerfile|heroku|compose` command group for generating deployment artifacts.

**Architecture:** The real runtime (`dazzle serve`) becomes the universal entry point. Production mode adds `--production` flag that binds `0.0.0.0`, reads `PORT` env var, requires `DATABASE_URL`, disables dev features, and enables structured JSON logging. The `dazzle deploy` subcommands generate static deployment files (Dockerfile, Procfile, docker-compose.yml) without executing them. The container runtime (~1500 lines) and DockerRunner are deleted.

**Tech Stack:** Python 3.12, Typer CLI, FastAPI/Uvicorn

**Spec:** `docs/superpowers/specs/2026-03-22-production-deployment-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/dazzle/cli/runtime_impl/serve.py` | Modify | Add `--production` flag with validation |
| `src/dazzle/cli/runtime_impl/production.py` | Create | Production mode helpers (validate env, configure logging) |
| `src/dazzle/cli/deploy.py` | Modify | Add `dockerfile\|heroku\|compose` commands alongside existing AWS CDK commands |
| `src/dazzle/cli/runtime_impl/lifecycle.py` | Modify | Replace `rebuild_command` with deprecation message |
| `src/dazzle_ui/runtime/docker/runner.py` | Delete | Retired DockerRunner |
| `src/dazzle_ui/runtime/docker/templates.py` | Delete | Retired templates |
| `src/dazzle_ui/runtime/docker/__init__.py` | Modify | Remove runner/templates exports |
| `src/dazzle_ui/runtime/__init__.py` | Modify | Remove Docker runner exports |
| `src/dazzle_ui/runtime/container/` | Delete | Entire retired container runtime (11 files) |
| `tests/unit/test_production_mode.py` | Create | Tests for `--production` flag behavior |
| `tests/unit/test_deploy_commands.py` | Create | Tests for `dazzle deploy dockerfile\|heroku\|compose` |
| `tests/unit/test_container_auth.py` | Delete | Tests for retired container runtime |
| `examples/*/build/Dockerfile` | Modify | Update to new `dazzle serve --production` pattern |
| `CHANGELOG.md` | Modify | Document changes |

---

### Task 1: Create production mode helpers

**Files:**
- Create: `src/dazzle/cli/runtime_impl/production.py`
- Create: `tests/unit/test_production_mode.py`

- [ ] **Step 1: Write failing tests for production validation**

```python
"""Tests for production mode helpers."""

from __future__ import annotations

import json
import logging
import os
from unittest.mock import patch

import pytest

from dazzle.cli.runtime_impl.production import (
    configure_production_logging,
    validate_production_env,
)


class TestValidateProductionEnv:
    """Tests for production environment validation."""

    def test_returns_database_url_when_set(self) -> None:
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://localhost/db"}):
            db_url, redis_url = validate_production_env()
            assert db_url == "postgresql://localhost/db"
            assert redis_url is None

    def test_normalizes_postgres_to_postgresql(self) -> None:
        with patch.dict(os.environ, {"DATABASE_URL": "postgres://localhost/db"}):
            db_url, _ = validate_production_env()
            assert db_url == "postgresql://localhost/db"

    def test_raises_when_database_url_missing(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(SystemExit):
                validate_production_env()

    def test_returns_redis_url_when_set(self) -> None:
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://localhost/db", "REDIS_URL": "redis://localhost"},
        ):
            _, redis_url = validate_production_env()
            assert redis_url == "redis://localhost"

    def test_redis_url_is_none_when_unset(self) -> None:
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://localhost/db"}, clear=True):
            _, redis_url = validate_production_env()
            assert redis_url is None

    def test_reads_port_env_var(self) -> None:
        with patch.dict(
            os.environ, {"DATABASE_URL": "postgresql://localhost/db", "PORT": "9000"}
        ):
            db_url, _ = validate_production_env()
            assert os.environ["PORT"] == "9000"


class TestConfigureProductionLogging:
    """Tests for structured JSON logging setup."""

    def test_sets_json_format_on_root_logger(self) -> None:
        configure_production_logging()
        root = logging.getLogger()
        # Should have at least one handler with JSON-style formatter
        assert any(
            hasattr(h.formatter, '_fmt') and 'message' in (h.formatter._fmt or '')
            for h in root.handlers
        ) or len(root.handlers) > 0
        # Clean up
        root.handlers.clear()

    def test_produces_json_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        configure_production_logging()
        logger = logging.getLogger("test.production")
        logger.setLevel(logging.INFO)
        logger.info("test message")
        # Clean up
        logging.getLogger().handlers.clear()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_production_mode.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dazzle.cli.runtime_impl.production'`

- [ ] **Step 3: Implement production.py**

```python
"""
Production mode helpers for dazzle serve --production.

Validates environment, configures structured logging, and provides
the production-specific settings that differ from dev/local modes.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone

import typer


def validate_production_env() -> tuple[str, str | None]:
    """Validate required environment variables for production mode.

    Returns:
        (database_url, redis_url) — redis_url is None if REDIS_URL not set.

    Raises:
        SystemExit: If DATABASE_URL is missing.
    """
    database_url = os.environ.get("DATABASE_URL", "")

    if not database_url:
        typer.echo(
            "--production requires DATABASE_URL environment variable. "
            "Set it to your PostgreSQL connection string.",
            err=True,
        )
        raise typer.Exit(code=1)

    # Normalize postgres:// → postgresql:// (Heroku convention)
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
        os.environ["DATABASE_URL"] = database_url

    redis_url = os.environ.get("REDIS_URL") or None

    return database_url, redis_url


class _JsonFormatter(logging.Formatter):
    """Structured JSON log formatter for production."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


def configure_production_logging() -> None:
    """Configure structured JSON logging for production.

    Replaces default handlers on the root logger with a single
    StreamHandler that emits JSON lines to stderr.
    """
    root = logging.getLogger()
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_JsonFormatter())
    root.addHandler(handler)
    root.setLevel(logging.INFO)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_production_mode.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/cli/runtime_impl/production.py tests/unit/test_production_mode.py
git commit -m "feat: add production mode helpers (validate env, JSON logging)"
```

---

### Task 2: Add --production flag to dazzle serve

**Files:**
- Modify: `src/dazzle/cli/runtime_impl/serve.py`
- Modify: `tests/unit/test_production_mode.py` (add integration-level tests)

- [ ] **Step 1: Write failing tests for --production flag behavior**

Add to `tests/unit/test_production_mode.py`:

```python
import inspect
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

runner = CliRunner()


class TestProductionFlagOnServe:
    """Tests for --production flag integration in serve_command."""

    def test_production_parameter_exists(self) -> None:
        """serve_command should accept --production."""
        from dazzle.cli.runtime_impl.serve import serve_command

        sig = inspect.signature(serve_command)
        assert "production" in sig.parameters

    def test_production_fails_without_database_url(self) -> None:
        """--production without DATABASE_URL should exit 1."""
        from dazzle.cli import app

        with patch.dict(os.environ, {}, clear=True):
            result = runner.invoke(app, ["serve", "--production"])
            assert result.exit_code != 0
            assert "DATABASE_URL" in result.output or "DATABASE_URL" in (result.stderr or "")

    def test_production_fails_without_dsl_files(self, tmp_path: Path) -> None:
        """--production with DATABASE_URL but no DSL files should exit 1."""
        from dazzle.cli import app

        # Create minimal dazzle.toml but no .dsl files
        (tmp_path / "dazzle.toml").write_text('[project]\nname = "test"\n')
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://localhost/db"},
            clear=True,
        ):
            result = runner.invoke(
                app, ["serve", "--production", "--manifest", str(tmp_path / "dazzle.toml")]
            )
            assert result.exit_code != 0
            assert "No DSL files" in result.output or "No DSL files" in (result.stderr or "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_production_mode.py::TestProductionFlagOnServe -v`
Expected: FAIL — `production` not in parameters

- [ ] **Step 3: Add --production flag to serve_command**

In `src/dazzle/cli/runtime_impl/serve.py`, add the `production` parameter to `serve_command` and the import:

After the existing `from .ports import ...` block, add:

```python
from .production import configure_production_logging, validate_production_env
```

Add this parameter to `serve_command` after the `workers` parameter:

```python
    production: bool = typer.Option(
        False,
        "--production",
        help="Production mode: bind 0.0.0.0, require DATABASE_URL, JSON logging, no dev features.",
    ),
```

Then at the start of `serve_command` body (after `manifest_path` and `project_root` are set, before manifest loading), add production mode handling:

```python
    # Production mode: override settings for deployment
    if production:
        configure_production_logging()
        database_url_prod, redis_url_prod = validate_production_env()

        # Check for DSL files
        from dazzle.core.fileset import discover_dsl_files as _discover

        try:
            mf_check = load_manifest(manifest_path)
            dsl_files = _discover(project_root, mf_check)
        except Exception:
            dsl_files = []
        if not dsl_files:
            typer.echo(
                "No DSL files found in current directory. "
                "Run dazzle serve --production from your project root.",
                err=True,
            )
            raise typer.Exit(code=1)

        # Override settings
        host = "0.0.0.0"
        port_env = os.environ.get("PORT")
        if port_env:
            try:
                port = int(port_env)
            except ValueError:
                pass
        database_url = database_url_prod
        redis_url = redis_url_prod or ""
        os.environ["DATABASE_URL"] = database_url
        if redis_url:
            os.environ["REDIS_URL"] = redis_url

        # Disable dev features
        local = True  # Skip Docker infrastructure management
        watch = False
        watch_source = False
        enable_dev_mode = False
        enable_test_mode = False
        auto_mock = False
```

Also move the `env` / `enable_dev_mode` / `enable_test_mode` resolution block so it only runs when `not production` — wrap the existing env resolution in an `if not production:` guard, and declare the variables before the block. The cleanest approach: move the existing env block under `else` of the production check, and set the variables for production in the `if production:` block above.

**Important:** The `if not local and not ui_only and not backend_only:` Docker infrastructure block must also be skipped in production mode. Since we set `local = True` in production mode, this happens automatically.

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_production_mode.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite on related files**

Run: `pytest tests/unit/test_production_mode.py tests/unit/test_docker_generation.py -v`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/cli/runtime_impl/serve.py tests/unit/test_production_mode.py
git commit -m "feat: add --production flag to dazzle serve"
```

---

### Task 3: Add deploy dockerfile|heroku|compose commands

The existing `deploy.py` has AWS CDK commands (`generate`, `plan`, `status`, `validate`, `preflight`). These are kept. The new commands are added alongside them.

**Files:**
- Modify: `src/dazzle/cli/deploy.py`
- Create: `tests/unit/test_deploy_commands.py`

- [ ] **Step 1: Write failing tests for deploy dockerfile**

```python
"""Tests for dazzle deploy dockerfile|heroku|compose commands."""

from __future__ import annotations

from dazzle.cli.deploy import (
    generate_compose_yaml,
    generate_production_dockerfile,
    generate_heroku_files,
)


class TestGenerateProductionDockerfile:
    """Tests for Dockerfile generation."""

    def test_uses_python_312_slim(self) -> None:
        result = generate_production_dockerfile()
        assert "FROM python:3.12-slim" in result

    def test_includes_healthcheck(self) -> None:
        result = generate_production_dockerfile()
        assert "HEALTHCHECK" in result

    def test_cmd_is_dazzle_serve_production(self) -> None:
        result = generate_production_dockerfile()
        assert 'dazzle", "serve", "--production"' in result

    def test_exposes_port_8000(self) -> None:
        result = generate_production_dockerfile()
        assert "EXPOSE 8000" in result

    def test_copies_requirements(self) -> None:
        result = generate_production_dockerfile()
        assert "COPY requirements.txt" in result


class TestGenerateHerokuFiles:
    """Tests for Heroku file generation."""

    def test_procfile_uses_production_flag(self) -> None:
        procfile, runtime, requirements = generate_heroku_files("0.46.2")
        assert "dazzle serve --production" in procfile

    def test_runtime_is_python_312(self) -> None:
        _, runtime, _ = generate_heroku_files("0.46.2")
        assert "python-3.12" in runtime

    def test_requirements_pins_dazzle_version(self) -> None:
        _, _, requirements = generate_heroku_files("0.46.2")
        assert "dazzle-dsl==0.46.2" in requirements

    def test_requirements_includes_psycopg(self) -> None:
        _, _, requirements = generate_heroku_files("0.46.2")
        assert "psycopg[binary]" in requirements


class TestGenerateComposeYaml:
    """Tests for docker-compose.yml generation."""

    def test_has_app_service(self) -> None:
        result = generate_compose_yaml()
        assert "app:" in result

    def test_has_postgres_service(self) -> None:
        result = generate_compose_yaml()
        assert "postgres:" in result

    def test_has_redis_service(self) -> None:
        result = generate_compose_yaml()
        assert "redis:" in result

    def test_app_depends_on_postgres(self) -> None:
        result = generate_compose_yaml()
        assert "depends_on:" in result
        assert "postgres:" in result

    def test_postgres_has_healthcheck(self) -> None:
        result = generate_compose_yaml()
        assert "pg_isready" in result

    def test_has_pgdata_volume(self) -> None:
        result = generate_compose_yaml()
        assert "pgdata:" in result

    def test_app_port_maps_3000_to_8000(self) -> None:
        result = generate_compose_yaml()
        assert '"3000:8000"' in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_deploy_commands.py -v`
Expected: FAIL — `ImportError` on the new functions

- [ ] **Step 3: Add new functions and commands to deploy.py**

Add the following to the **end** of `src/dazzle/cli/deploy.py`, after the existing `deploy_preflight` command. The existing AWS CDK commands (`generate`, `plan`, `status`, `validate`, `preflight`) remain untouched.

```python
# ---------------------------------------------------------------------------
# Production deployment artifact generators (v0.47)
# ---------------------------------------------------------------------------


def generate_production_dockerfile() -> str:
    """Generate a production Dockerfile using dazzle serve --production."""
    return """FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \\
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"
CMD ["dazzle", "serve", "--production"]
"""


def generate_deploy_requirements(version: str) -> str:
    """Generate requirements.txt pinned to the current dazzle-dsl version."""
    return f"""dazzle-dsl=={version}
psycopg[binary]>=3.1
redis>=5.0
httpx>=0.24
"""


def generate_heroku_files(version: str) -> tuple[str, str, str]:
    """Generate Heroku deployment files.

    Returns:
        (procfile, runtime_txt, requirements_txt)
    """
    procfile = "web: dazzle serve --production\n"
    runtime = "python-3.12\n"
    requirements = generate_deploy_requirements(version)
    return procfile, runtime, requirements


def generate_compose_yaml() -> str:
    """Generate a production docker-compose.yml."""
    return """services:
  app:
    build: .
    ports:
      - "3000:8000"
    environment:
      - DATABASE_URL=postgresql://dazzle:dazzle@postgres:5432/dazzle
      - REDIS_URL=redis://redis:6379
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: dazzle
      POSTGRES_PASSWORD: dazzle
      POSTGRES_DB: dazzle
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U dazzle"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine

volumes:
  pgdata:
"""


def _get_dazzle_version() -> str:
    """Get the installed dazzle-dsl version."""
    try:
        from importlib.metadata import version

        return version("dazzle-dsl")
    except Exception:
        return "0.0.0"


@deploy_app.command(name="dockerfile")
def deploy_dockerfile_cmd(
    output_dir: Annotated[
        Path,
        typer.Option("--output", "-o", help="Directory to write Dockerfile and requirements.txt"),
    ] = Path("."),
) -> None:
    """Generate a production Dockerfile and requirements.txt.

    Example:
        dazzle deploy dockerfile
        docker build -t myapp .
        docker run -e DATABASE_URL=... myapp
    """
    version = _get_dazzle_version()
    output_path = Path(output_dir).resolve()

    (output_path / "Dockerfile").write_text(generate_production_dockerfile())
    (output_path / "requirements.txt").write_text(generate_deploy_requirements(version))

    console.print(f"Generated {output_path / 'Dockerfile'}")
    console.print(f"Generated {output_path / 'requirements.txt'}")
    console.print()
    console.print("[bold]Next steps:[/bold]")
    console.print("  docker build -t myapp .")
    console.print("  docker run -e DATABASE_URL=... -p 8000:8000 myapp")


@deploy_app.command(name="heroku")
def deploy_heroku_cmd(
    output_dir: Annotated[
        Path,
        typer.Option("--output", "-o", help="Directory to write Heroku files"),
    ] = Path("."),
) -> None:
    """Generate Heroku deployment files (Procfile, runtime.txt, requirements.txt).

    Example:
        dazzle deploy heroku
        git push heroku main
    """
    version = _get_dazzle_version()
    output_path = Path(output_dir).resolve()

    procfile, runtime, requirements = generate_heroku_files(version)

    (output_path / "Procfile").write_text(procfile)
    (output_path / "runtime.txt").write_text(runtime)
    (output_path / "requirements.txt").write_text(requirements)

    console.print(f"Generated {output_path / 'Procfile'}")
    console.print(f"Generated {output_path / 'runtime.txt'}")
    console.print(f"Generated {output_path / 'requirements.txt'}")
    console.print()
    console.print("[bold]Next steps:[/bold]")
    console.print("  heroku create myapp")
    console.print("  heroku addons:create heroku-postgresql")
    console.print("  heroku addons:create heroku-redis")
    console.print("  git push heroku main")


@deploy_app.command(name="compose")
def deploy_compose_cmd(
    output_dir: Annotated[
        Path,
        typer.Option("--output", "-o", help="Directory to write docker-compose.yml"),
    ] = Path("."),
) -> None:
    """Generate a production docker-compose.yml.

    Requires a Dockerfile (run 'dazzle deploy dockerfile' first).

    Example:
        dazzle deploy dockerfile
        dazzle deploy compose
        docker compose up
    """
    output_path = Path(output_dir).resolve()
    compose_path = output_path / "docker-compose.yml"

    if not (output_path / "Dockerfile").exists():
        console.print(
            "[yellow]Warning: No Dockerfile found. "
            "Run 'dazzle deploy dockerfile' first.[/yellow]"
        )

    compose_path.write_text(generate_compose_yaml())

    console.print(f"Generated {compose_path}")
    console.print()
    console.print("[bold]Next steps:[/bold]")
    console.print("  docker compose up")
```

Note: The existing file already imports `Annotated`, `Path`, `typer`, `Console`, and defines `console = Console()`, so no new imports are needed.

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_deploy_commands.py -v`
Expected: PASS

- [ ] **Step 5: Run existing deploy tests to check for breakage**

Run: `pytest tests/unit/test_deploy_runner.py tests/unit/test_deploy_tigerbeetle.py -v 2>&1 | head -20`

These tests import from `dazzle.deploy` (the AWS CDK module), not `dazzle.cli.deploy`, so they should still pass.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/cli/deploy.py tests/unit/test_deploy_commands.py
git commit -m "feat: add dazzle deploy dockerfile|heroku|compose commands"
```

---

### Task 4: Deprecate rebuild command

**Files:**
- Modify: `src/dazzle/cli/runtime_impl/lifecycle.py`
- Modify: `tests/unit/test_production_mode.py` (add deprecation test)

- [ ] **Step 1: Replace rebuild_command body with deprecation message**

In `src/dazzle/cli/runtime_impl/lifecycle.py`, replace the entire `rebuild_command` function (lines 88–165) with:

```python
def rebuild_command() -> None:
    """Deprecated: container mode has been removed."""
    typer.echo(
        "--rebuild has been removed. "
        "Run 'dazzle deploy dockerfile' to generate deployment files.",
        err=True,
    )
    raise typer.Exit(code=1)
```

Remove the unused imports that were only needed by the old `rebuild_command`: the function no longer uses `subprocess`, the docker helpers, or `load_manifest`. However, `stop_command`, `logs_command`, and `status_command` still use those imports — only remove imports that become fully unused.

Check: `subprocess` is used by `stop_command`, `logs_command`, `status_command` — keep it.
Check: `load_manifest` is used by all four commands — keep it.
Check: `get_container_name`, `is_container_running` from `.docker` — used by `stop_command`, `logs_command`, `status_command` — keep them.

So only the function body changes, no import changes needed.

- [ ] **Step 2: Write deprecation test**

Add to `tests/unit/test_production_mode.py`:

```python
class TestRebuildDeprecation:
    """Tests for rebuild command deprecation."""

    def test_rebuild_prints_deprecation_and_exits(self) -> None:
        from dazzle.cli import app

        result = runner.invoke(app, ["rebuild"])
        assert result.exit_code != 0
        assert "dazzle deploy dockerfile" in (result.output + (result.stderr or ""))
```

Run: `pytest tests/unit/test_production_mode.py::TestRebuildDeprecation -v`
Expected: FAIL (rebuild still has old behavior)

Keep `rebuild_command` registered in `cli/__init__.py` and exported from `runtime_impl/__init__.py` so users get the deprecation message instead of "unknown command". Only the function body changes.

- [ ] **Step 3: Run deprecation test**

Run: `pytest tests/unit/test_production_mode.py::TestRebuildDeprecation -v`
Expected: PASS

- [ ] **Step 4: Verify deprecation message manually**

Run: `cd /Volumes/SSD/Dazzle && python -m dazzle.cli rebuild 2>&1`
Expected output: `--rebuild has been removed. Run 'dazzle deploy dockerfile' to generate deployment files.`

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/cli/runtime_impl/lifecycle.py
git commit -m "feat: deprecate rebuild command with migration message"
```

---

### Task 5: Delete container runtime and DockerRunner

**Files:**
- Delete: `src/dazzle_ui/runtime/container/` (entire directory)
- Delete: `src/dazzle_ui/runtime/docker/runner.py`
- Delete: `src/dazzle_ui/runtime/docker/templates.py`
- Modify: `src/dazzle_ui/runtime/docker/__init__.py`
- Modify: `src/dazzle_ui/runtime/__init__.py`
- Delete: `tests/unit/test_container_auth.py`
- Modify: `src/dazzle/cli/runtime_impl/lifecycle.py` (remove `run_in_docker` import)

- [ ] **Step 1: Delete the container runtime directory**

```bash
rm -rf src/dazzle_ui/runtime/container/
```

- [ ] **Step 2: Delete runner.py and templates.py**

```bash
rm src/dazzle_ui/runtime/docker/runner.py
rm src/dazzle_ui/runtime/docker/templates.py
```

- [ ] **Step 3: Update docker/__init__.py**

Replace `src/dazzle_ui/runtime/docker/__init__.py` with:

```python
"""
Docker subpackage for Dazzle runtime.

Provides Docker availability checks for dev infrastructure.
"""

from __future__ import annotations

from .utils import get_docker_version, is_docker_available

__all__ = [
    "is_docker_available",
    "get_docker_version",
]
```

- [ ] **Step 4: Update runtime/__init__.py**

In `src/dazzle_ui/runtime/__init__.py`, remove the Docker runner imports and exports.

Remove lines 35–41 (the `from dazzle_ui.runtime.docker import ...` block).

Remove from `__all__`: `"DockerRunner"`, `"DockerRunConfig"`, `"is_docker_available"`, `"run_in_docker"`, `"stop_docker_container"`.

Keep the `is_docker_available` import if needed elsewhere — but `serve.py` imports it directly from `dazzle_ui.runtime.docker.utils`, so the re-export can be removed.

- [ ] **Step 5: Remove run_in_docker import from lifecycle.py**

In `src/dazzle/cli/runtime_impl/lifecycle.py`, the `rebuild_command` function body was already replaced in Task 4. The old lazy import `from dazzle_ui.runtime import is_docker_available, run_in_docker` inside that function is gone. No change needed.

- [ ] **Step 6: Delete container auth tests**

```bash
rm tests/unit/test_container_auth.py
```

- [ ] **Step 7: Run tests to check for breakage**

Run: `pytest tests/unit/test_docker_generation.py -v`

This file imports from `dazzle.cli.runtime_impl.docker` which still exists (it has the dev infrastructure code). Should pass.

Run: `pytest tests/ -m "not e2e" -x --timeout=60 -q 2>&1 | tail -20`

Check for any import errors related to the deleted modules.

- [ ] **Step 8: Commit**

```bash
git add src/dazzle_ui/runtime/ tests/unit/test_container_auth.py
git commit -m "refactor: retire container runtime and DockerRunner (~1500 lines removed)"
```

---

### Task 6: Update example Dockerfiles

**Files:**
- Modify: `examples/simple_task/build/Dockerfile`
- Modify: `examples/contact_manager/build/Dockerfile`
- Modify: `examples/ops_dashboard/build/Dockerfile`
- Modify: `examples/support_tickets/build/Dockerfile`
- Modify: `examples/fieldtest_hub/build/Dockerfile`
- Delete: `examples/simple_task/build/simple_task/Dockerfile` (nested duplicate)
- Delete: `examples/support_tickets/build/support_tickets/Dockerfile` (nested duplicate)

- [ ] **Step 1: Update all example Dockerfiles to the new pattern**

Replace each `examples/*/build/Dockerfile` with:

```dockerfile
FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"
CMD ["dazzle", "serve", "--production"]
```

The only difference between examples is the leading comment, but per the spec these are now generated by `dazzle deploy dockerfile` and should be uniform.

- [ ] **Step 2: Delete nested duplicate Dockerfiles**

```bash
rm -rf examples/simple_task/build/simple_task/
rm -rf examples/support_tickets/build/support_tickets/
```

- [ ] **Step 3: Commit**

```bash
git add examples/
git commit -m "chore: update example Dockerfiles to use dazzle serve --production"
```

---

### Task 7: CHANGELOG and cleanup

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add CHANGELOG entry**

Add under `## [Unreleased]`:

```markdown
### Added
- `--production` flag on `dazzle serve` — binds 0.0.0.0, reads PORT env var, requires DATABASE_URL, structured JSON logging, disables dev features
- `dazzle deploy dockerfile` — generates production Dockerfile + requirements.txt
- `dazzle deploy heroku` — generates Procfile, runtime.txt, requirements.txt
- `dazzle deploy compose` — generates production docker-compose.yml

### Removed
- Container runtime (`dazzle_ui.runtime.container`) — replaced by `dazzle serve --production`
- `DockerRunner` and Docker template generation — replaced by `dazzle deploy`
- `dazzle rebuild` command — prints migration message directing to `dazzle deploy dockerfile`
```

- [ ] **Step 2: Run lint**

Run: `ruff check src/dazzle/cli/runtime_impl/production.py src/dazzle/cli/deploy.py src/dazzle/cli/runtime_impl/serve.py --fix`

- [ ] **Step 3: Run mypy**

Run: `mypy src/dazzle/cli/runtime_impl/production.py src/dazzle/cli/deploy.py`

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -m "not e2e" -x --timeout=120 -q 2>&1 | tail -30`

Expected: All tests pass (count may drop slightly due to deleted container tests).

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: CHANGELOG entry for production deployment"
```
