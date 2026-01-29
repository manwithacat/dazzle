"""
DAZZLE CLI Package.

This package contains modularized CLI components:

- dnr.py: DNR (Dazzle Native Runtime) commands
- project.py: Project commands (init, validate, lint, build, etc.)
- vocab.py: Vocabulary management commands
- testing.py: E2E testing commands
- e2e.py: Docker-based E2E testing
- mcp.py: MCP server commands
- utils.py: Shared utilities

The main CLI entry point is main() which delegates to cli_legacy during migration.
After full migration, it will be fully contained here.

IMPORTANT: Sub-apps are imported at module level, but cli_legacy is imported
lazily in main() to avoid circular imports.
"""

import typer

# Sub-apps - each is self-contained with no cli_legacy dependency
from dazzle.cli.dnr_impl import dnr_app
from dazzle.cli.e2e import e2e_app
from dazzle.cli.events import dlq_app, events_app, outbox_app
from dazzle.cli.mcp import mcp_app
from dazzle.cli.migrate import migrate_app
from dazzle.cli.pitch import pitch_app
from dazzle.cli.story import story_app
from dazzle.cli.testing import test_app

# Re-export utilities (no dazzle imports, safe)
from dazzle.cli.utils import get_version, version_callback
from dazzle.cli.vocab import vocab_app


def main(argv: list[str] | None = None) -> None:
    """
    Main CLI entry point.

    Delegates to cli_legacy during migration. After full migration,
    this will contain the main app directly.
    """
    # Lazy import to avoid circular dependency
    from dazzle.cli_legacy import main as _legacy_main

    _legacy_main(argv)


# Lazy-loaded app singleton for testing
_app = None


def __getattr__(name: str) -> typer.Typer:
    """
    Lazy attribute access for 'app'.

    This allows `from dazzle.cli import app` to work without importing
    cli_legacy at module load time, avoiding circular imports.
    """
    if name == "app":
        global _app
        if _app is None:
            from dazzle.cli_legacy import app as _legacy_app

            _app = _legacy_app
        return _app
    raise AttributeError(f"module 'dazzle.cli' has no attribute {name!r}")


__all__ = [
    # Entry point and main app
    "main",
    "app",
    # Sub-apps (Typer instances)
    "dnr_app",
    "vocab_app",
    "story_app",
    "test_app",
    "e2e_app",
    "mcp_app",
    "migrate_app",
    "events_app",
    "dlq_app",
    "outbox_app",
    "pitch_app",
    # Utilities
    "get_version",
    "version_callback",
]
