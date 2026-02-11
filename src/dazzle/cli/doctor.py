"""
DAZZLE Doctor — environment health check.

Validates that the local environment has everything needed to run Dazzle.
"""

from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from pathlib import Path

import typer


def doctor_command() -> None:
    """Run environment health checks for DAZZLE."""
    ok_count = 0
    warn_count = 0
    fail_count = 0

    def _ok(msg: str) -> None:
        nonlocal ok_count
        ok_count += 1
        typer.echo(f"  [ok] {msg}")

    def _warn(msg: str) -> None:
        nonlocal warn_count
        warn_count += 1
        typer.echo(f"  [warn] {msg}")

    def _fail(msg: str) -> None:
        nonlocal fail_count
        fail_count += 1
        typer.echo(f"  [FAIL] {msg}")

    typer.echo("DAZZLE Doctor\n")

    # 1. Python version
    typer.echo("Python:")
    v = sys.version_info
    if v >= (3, 12):
        _ok(f"Python {v.major}.{v.minor}.{v.micro}")
    elif v >= (3, 11):
        _warn(f"Python {v.major}.{v.minor}.{v.micro} (3.12+ recommended)")
    else:
        _fail(f"Python {v.major}.{v.minor}.{v.micro} (3.12+ required)")

    # 2. Core packages
    typer.echo("\nCore packages:")
    for pkg in ("pydantic", "typer", "jinja2", "sqlalchemy", "yaml"):
        import_name = pkg
        try:
            mod = importlib.import_module(import_name)
            version = getattr(mod, "__version__", getattr(mod, "VERSION", "?"))
            _ok(f"{pkg} {version}")
        except ImportError:
            _fail(f"{pkg} not importable")

    # 3. Optional dependencies
    typer.echo("\nOptional packages:")
    optional = [
        ("mcp", "MCP server"),
        ("anthropic", "LLM support"),
        ("pygls", "LSP server"),
    ]
    for pkg, purpose in optional:
        try:
            mod = importlib.import_module(pkg)
            version = getattr(mod, "__version__", "?")
            _ok(f"{pkg} {version} ({purpose})")
        except ImportError:
            _warn(f"{pkg} not installed ({purpose}) — install with extras")

    # 4. Docker
    typer.echo("\nTools:")
    if shutil.which("docker"):
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0:
                _ok("Docker available and running")
            else:
                _warn("Docker installed but not running")
        except (subprocess.TimeoutExpired, OSError):
            _warn("Docker installed but not responding")
    else:
        _warn("Docker not found (needed for `dazzle serve` without --local)")

    # 5. Git
    if shutil.which("git"):
        try:
            git_result = subprocess.run(
                ["git", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            version_str = git_result.stdout.strip() if git_result.returncode == 0 else "unknown"
            _ok(f"Git: {version_str}")
        except (subprocess.TimeoutExpired, OSError):
            _warn("Git found but not responding")
    else:
        _warn("Git not found")

    # 6. Project validation (if in a dazzle project)
    typer.echo("\nProject:")
    dazzle_toml = Path.cwd() / "dazzle.toml"
    if dazzle_toml.exists():
        try:
            from dazzle.core import load_project

            load_project(Path.cwd())
            _ok(f"Project valid ({dazzle_toml})")
        except Exception as e:
            _fail(f"Project invalid: {e}")
    else:
        _warn("Not in a DAZZLE project (no dazzle.toml)")

    # 7. MCP registration
    typer.echo("\nMCP:")
    try:
        from dazzle.mcp.setup import check_mcp_server

        status = check_mcp_server()
        if status.get("registered"):
            _ok("MCP server registered with Claude Code")
        else:
            _warn("MCP server not registered (run: dazzle mcp setup)")
    except ImportError:
        _warn("MCP not installed — cannot check registration")
    except Exception:
        _warn("Could not check MCP registration")

    # Summary
    typer.echo(f"\n{'=' * 40}")
    typer.echo(f"  {ok_count} ok, {warn_count} warnings, {fail_count} failures")

    if fail_count > 0:
        typer.echo("\nSome checks failed. Fix the issues above.")
        raise typer.Exit(code=1)
    elif warn_count > 0:
        typer.echo("\nEnvironment is usable but has warnings.")
    else:
        typer.echo("\nEnvironment is healthy!")
