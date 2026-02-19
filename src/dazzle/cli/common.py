"""Shared CLI helpers to reduce boilerplate across CLI command modules."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import typer


def resolve_project(manifest: str) -> Path:
    """Resolve a manifest path to the project root directory.

    Validates that ``dazzle.toml`` exists in the resolved directory.
    Exits with code 1 if not found.
    """
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent
    if not (root / "dazzle.toml").exists():
        typer.echo(f"No dazzle.toml found in {root}", err=True)
        raise typer.Exit(code=1)
    return root


def run_mcp_handler(
    root: Path,
    tool: str,
    operation: str,
    handler: Callable[..., str],
    args: dict[str, Any],
    *,
    error_label: str | None = None,
    setup: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Wrap an MCP handler call with CLI activity tracking.

    Opens a :func:`~dazzle.cli.activity.cli_activity` context, injects
    the ``_progress`` key into *args*, calls *handler(root, args)*,
    and returns the parsed JSON result.

    Args:
        root: Project root directory.
        tool: Consolidated tool name (e.g. ``"pipeline"``).
        operation: Operation within the tool (e.g. ``"run"``).
        handler: MCP handler function ``(Path, dict) -> str``.
        args: Arguments dict — ``_progress`` is injected automatically.
        error_label: Human-readable label for error messages.
        setup: Optional callback invoked inside the activity context
            before the handler runs. Receives *args* so it can inject
            extra keys (e.g. ``_activity_store``).

    Returns:
        Parsed JSON response as a dict.

    Raises:
        typer.Exit: On handler failure (code 1).
    """
    label = error_label or f"{tool} {operation}"
    try:
        from dazzle.cli.activity import cli_activity

        with cli_activity(root, tool, operation) as progress:
            args["_progress"] = progress
            if setup is not None:
                setup(args)
            raw = handler(root, args)
        result: dict[str, Any] = json.loads(raw)
        return result
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"{label} error: {e}", err=True)
        raise typer.Exit(code=1)
