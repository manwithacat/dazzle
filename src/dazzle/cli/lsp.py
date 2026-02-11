"""
LSP (Language Server Protocol) CLI commands.

Commands for running the DAZZLE LSP server and querying LSP resources.
"""

from pathlib import Path

import typer

lsp_app = typer.Typer(
    help="Language Server Protocol (LSP) commands.",
    no_args_is_help=True,
)


@lsp_app.command("run")
def lsp_run(
    stdio: bool = typer.Option(
        True,
        "--stdio/--no-stdio",
        help="Use stdio transport (default, for editor piping)",
    ),
    tcp: bool = typer.Option(
        False,
        "--tcp",
        help="Use TCP transport (for debugging)",
    ),
    port: int = typer.Option(
        2087,
        "--port",
        help="TCP port (only used with --tcp)",
    ),
) -> None:
    """
    Start the DAZZLE LSP server.

    By default uses stdio transport for editor integration.
    Use --tcp --port for debugging with a TCP connection.
    """
    if tcp:
        typer.echo(f"Starting DAZZLE LSP server on TCP port {port}...")
        try:
            from dazzle.lsp.server import server

            server.start_tcp("127.0.0.1", port)
        except ImportError as e:
            typer.echo(
                f"Error: LSP dependencies not installed: {e}\n"
                "Install with: pip install dazzle[lsp]",
                err=True,
            )
            raise typer.Exit(code=1)
        except Exception as e:
            typer.echo(f"Error starting LSP server: {e}", err=True)
            raise typer.Exit(code=1)
    else:
        try:
            from dazzle.lsp import start_server

            start_server()
        except ImportError as e:
            typer.echo(
                f"Error: LSP dependencies not installed: {e}\n"
                "Install with: pip install dazzle[lsp]",
                err=True,
            )
            raise typer.Exit(code=1)
        except KeyboardInterrupt:
            typer.echo("\nLSP server stopped.")
        except Exception as e:
            typer.echo(f"Error starting LSP server: {e}", err=True)
            raise typer.Exit(code=1)


@lsp_app.command("check")
def lsp_check() -> None:
    """
    Verify LSP dependencies are installed and show version info.
    """
    errors = []

    try:
        import pygls

        pygls_version = getattr(pygls, "__version__", "unknown")
        typer.echo(f"pygls:        {pygls_version}")
    except ImportError:
        errors.append("pygls")

    try:
        import lsprotocol

        lsprotocol_version = getattr(lsprotocol, "__version__", "unknown")
        typer.echo(f"lsprotocol:   {lsprotocol_version}")
    except ImportError:
        errors.append("lsprotocol")

    if errors:
        typer.echo(
            f"\nMissing dependencies: {', '.join(errors)}\nInstall with: pip install dazzle[lsp]",
            err=True,
        )
        raise typer.Exit(code=1)

    typer.echo("\nAll LSP dependencies installed.")


@lsp_app.command("grammar-path")
def lsp_grammar_path() -> None:
    """
    Print the absolute path to the bundled TextMate grammar JSON.

    Use this path to configure syntax highlighting in editors
    like Sublime Text, Neovim, or other TextMate-compatible editors.
    """
    grammar_file = Path(__file__).parent.parent / "lsp" / "grammars" / "dazzle.tmLanguage.json"
    if not grammar_file.exists():
        typer.echo("Error: Grammar file not found. Package may be incomplete.", err=True)
        raise typer.Exit(code=1)
    typer.echo(str(grammar_file.resolve()))
