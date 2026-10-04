"""
DAZZLE CLI Utilities.

Shared utility functions used across CLI modules.
"""

import platform
from pathlib import Path

import typer

from dazzle._version import get_version
from dazzle.core.appspec_loader import load_project_appspec as load_project_appspec


def print_version_info(full: bool = False) -> None:
    """Print the full version + environment + features report.

    Shared between the top-level ``--version`` flag and the ``version``
    subcommand. When ``full`` is True, append machine-readable feature
    flags (``python_available: true``, etc.) for automation consumers
    such as the homebrew-tap validate-formula workflow.
    """
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
        llm_status = "✗ Not available (install with: pip install dazzle-dsl[llm])"
    typer.echo(f"  LLM Support:   {llm_status}")

    if full:
        # Machine-readable feature flags. Consumed by e.g. the
        # homebrew-tap validate-formula workflow, which greps the
        # output for `python_available`.
        typer.echo("")
        typer.echo("Flags:")
        typer.echo("  python_available: true")
        typer.echo(f"  lsp_available: {'true' if lsp_available else 'false'}")
        typer.echo(f"  llm_available: {'true' if llm_available else 'false'}")


def version_callback(value: bool) -> None:
    """Display version and environment information (``--version`` flag)."""
    if value:
        print_version_info(full=False)
        raise typer.Exit()


def project_root_from_manifest(manifest: str | Path) -> Path:
    """Resolve project root from a ``dazzle.toml`` path or directory.

    Raises ``typer.Exit(1)`` when no dazzle.toml is found.
    """
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent if manifest_path.is_file() else manifest_path
    if not (root / "dazzle.toml").exists():
        typer.echo(f"No dazzle.toml found in {root}", err=True)
        raise typer.Exit(code=1)
    return root
