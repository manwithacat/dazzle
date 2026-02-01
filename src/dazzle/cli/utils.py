"""
DAZZLE CLI Utilities.

Shared utility functions used across CLI modules.
"""

import platform
from pathlib import Path

import typer

from dazzle.core.errors import ParseError

__version__ = "0.5.0"


def get_version() -> str:
    """Get DAZZLE version from package metadata."""
    try:
        from importlib.metadata import version

        return version("dazzle")
    except Exception:
        return __version__


def version_callback(value: bool) -> None:
    """Display version and environment information."""
    if value:
        # Get DAZZLE version
        dazzle_version = get_version()

        # Get Python version
        python_version = platform.python_version()
        python_impl = platform.python_implementation()

        # Get installation location
        try:
            import dazzle

            install_location = Path(dazzle.__file__).parent.parent.parent
        except Exception:
            install_location = Path.cwd()

        # Check if installed via pip (editable or not)
        install_method = "unknown"
        try:
            from importlib.metadata import distribution

            dist = distribution("dazzle")
            if dist.read_text("direct_url.json"):
                install_method = "pip (editable)"
            else:
                install_method = "pip"
        except Exception:
            # Check if we're in development directory
            if (install_location / "pyproject.toml").exists():
                install_method = "development"

        # Check LSP server availability
        lsp_available = False
        try:
            # Suppress verbose pygls logging during import check
            # MUST set logging level BEFORE importing pygls/dazzle.lsp.server
            import logging

            logging.getLogger("pygls.feature_manager").setLevel(logging.ERROR)
            logging.getLogger("pygls").setLevel(logging.ERROR)

            import dazzle.lsp.server

            lsp_available = True
        except ImportError:
            pass

        # Check LLM support
        llm_available = False
        llm_providers = []
        try:
            import anthropic  # noqa: F401 - intentional import for availability check

            llm_providers.append("anthropic")
            llm_available = True
        except ImportError:
            pass
        try:
            import openai  # noqa: F401 - intentional import for availability check

            llm_providers.append("openai")
            llm_available = True
        except ImportError:
            pass

        # Output version information
        typer.echo(f"DAZZLE version {dazzle_version}")
        typer.echo("")
        typer.echo("Environment:")
        typer.echo(f"  Python:        {python_impl} {python_version}")
        typer.echo(f"  Platform:      {platform.system()} {platform.release()}")
        typer.echo(f"  Architecture:  {platform.machine()}")
        typer.echo("")
        typer.echo("Installation:")
        typer.echo(f"  Method:        {install_method}")
        typer.echo(f"  Location:      {install_location}")
        typer.echo("")
        typer.echo("Features:")
        if lsp_available:
            lsp_status = "✓ Available"
        else:
            lsp_status = "✗ Not available (install with: pip install dazzle)"
        typer.echo(f"  LSP Server:    {lsp_status}")
        if llm_available:
            llm_status = "✓ Available (" + ", ".join(llm_providers) + ")"
        else:
            llm_status = "✗ Not available (install with: pip install dazzle[llm])"
        typer.echo(f"  LLM Support:   {llm_status}")

        raise typer.Exit()


def print_human_diagnostics(errors: list[str], warnings: list[str]) -> None:
    """Print diagnostics in human-readable format."""
    if errors:
        typer.echo("Validation failed:\n", err=True)
        for err in errors:
            typer.echo(f"ERROR: {err}", err=True)

    if warnings:
        typer.echo("Validation warnings:\n", err=False)
        for warn in warnings:
            typer.echo(f"WARNING: {warn}", err=False)

    if not errors and not warnings:
        typer.echo("OK: spec is valid.")


def print_vscode_diagnostics(errors: list[str], warnings: list[str], root: Path) -> None:
    """
    Print diagnostics in VS Code format: file:line:col: severity: message

    Since most validation errors don't have location info yet, we output
    them with a generic location. Parse errors will have specific locations.
    """
    for err in errors:
        # Try to extract file info from error message if present
        # Format: "filename.dsl:line:col: error: message"
        # For now, output generic location
        typer.echo(f"dazzle.toml:1:1: error: {err}", err=True)

    for warn in warnings:
        typer.echo(f"dazzle.toml:1:1: warning: {warn}", err=True)

    # If no errors or warnings, output success (for CLI feedback)
    if not errors and not warnings:
        typer.echo("::notice: Validation successful")


def print_vscode_parse_error(error: ParseError, root: Path) -> None:
    """Print parse error in VS Code format with location info."""
    if error.context:
        # ParseError has file, line, column information
        file_path = error.context.file
        if file_path:
            # Make path relative to root
            try:
                rel_path = Path(file_path).relative_to(root)
            except ValueError:
                rel_path = Path(file_path)

            line = error.context.line or 1
            col = error.context.column or 1
            typer.echo(f"{rel_path}:{line}:{col}: error: {error.message}", err=True)
        else:
            typer.echo(f"::error: {error.message}", err=True)
    else:
        typer.echo(f"::error: {error.message}", err=True)


def is_directory_empty(directory: Path) -> bool:
    """
    Check if directory is empty (or has only files we commonly allow).

    A directory is considered "empty" for init purposes if it contains:
    - No files at all, OR
    - Only .git directory, OR
    - Only .git and common files (.gitignore, README.md, LICENSE, .DS_Store)

    Args:
        directory: Path to check

    Returns:
        True if directory is empty or only has allowed files
    """
    if not directory.exists():
        return True

    contents = list(directory.iterdir())

    if len(contents) == 0:
        return True

    # Allow some common files that might be pre-created
    allowed_files = {".git", ".gitignore", "README.md", "LICENSE", ".DS_Store"}
    actual_files = {item.name for item in contents}

    # If all files are in allowed list, consider it empty
    if actual_files.issubset(allowed_files):
        return True

    return False


# Aliases for backward compatibility (functions were previously underscore-prefixed)
_print_human_diagnostics = print_human_diagnostics
_print_vscode_diagnostics = print_vscode_diagnostics
_print_vscode_parse_error = print_vscode_parse_error
_is_directory_empty = is_directory_empty
