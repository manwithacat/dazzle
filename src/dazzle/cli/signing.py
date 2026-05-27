"""`dazzle signing` CLI commands (#1283 phase 4).

Provisioning surface for the native document signing primitive. The
single ``init`` subcommand mints a project-level CA + signing cert
chain (ECDSA P-256, 10y / 1y validity) and emits the PKCS#12 bundle to
stdout base64-encoded, ready to capture into ``SIGNING_CERT_PFX_B64``
+ ``SIGNING_CERT_PASSWORD`` config vars.

Usage::

    dazzle signing init                  # uses manifest name (e.g. "Acme Ltd")
    dazzle signing init --project-name "Acme Ltd"
    dazzle signing init --country GB
    dazzle signing init --heroku-app my-app   # emits `heroku config:set` hints
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import typer

from dazzle.core.manifest import load_manifest

logger = logging.getLogger(__name__)

signing_app = typer.Typer(help="Provision the native document signing primitive (#1283).")


@signing_app.callback()
def _signing_main() -> None:
    """Group callback — keeps typer in multi-command mode.

    Without this, a Typer app with a single subcommand collapses so that
    ``dazzle signing --project-name X`` would work instead of
    ``dazzle signing init --project-name X``. The issue spec requires
    the ``init`` subcommand name; the callback preserves it.
    """


def _resolve_project_name(manifest_path: Path) -> str:
    """Resolve the project name for the signing cert subject.

    Priority:
        1. ``--project-name`` flag (handled at the caller)
        2. ``[project] name`` in ``dazzle.toml``
        3. Repository root directory name (last-ditch fallback)
    """
    if manifest_path.exists():
        try:
            manifest = load_manifest(manifest_path)
            if manifest.name:
                return manifest.name
        except Exception as exc:
            logger.warning("Could not read project name from manifest: %s", exc)
    return manifest_path.parent.name or "Dazzle App"


@signing_app.command("init")
def init(
    project_name: str = typer.Option(
        "",
        "--project-name",
        help=(
            "Organisation name on the cert (e.g. 'Acme Ltd'). Defaults to "
            "the project's `name` from dazzle.toml, then the directory name."
        ),
    ),
    country: str = typer.Option(
        "GB",
        "--country",
        help="Two-letter ISO 3166-1 alpha-2 country code on the cert subject.",
    ),
    heroku_app: str = typer.Option(
        "",
        "--heroku-app",
        help="If set, emits `heroku config:set` invocation hints alongside the PKCS#12.",
    ),
    refuse_if_set: bool = typer.Option(
        True,
        "--refuse-if-set/--force",
        help=(
            "Refuse to re-mint when SIGNING_CERT_PFX_B64 is already set in "
            "the current shell. `--force` overrides — useful for cert rotation."
        ),
    ),
) -> None:
    """Mint a project-level CA + signing cert chain.

    Outputs a single base64-encoded PKCS#12 bundle to stdout, plus the
    one-time encryption password. Copy these into the production
    environment's config vars (see ``--heroku-app`` for one-line
    invocation hints).

    Re-running rotates the CA — every previously issued cert and every
    signed document chain becomes unverifiable against the new CA.
    Phase 1 deliberately ships a single CA per project; per-tenant CAs
    and rotation-with-history land in a later cycle.
    """
    if refuse_if_set and os.environ.get("SIGNING_CERT_PFX_B64"):
        typer.echo(
            "SIGNING_CERT_PFX_B64 is already set in the current environment. "
            "Pass --force to mint a new cert chain anyway (this rotates the "
            "CA — previously signed documents will not verify against the new "
            "chain).",
            err=True,
        )
        raise typer.Exit(code=1)

    # Resolve project name. Default lookup uses dazzle.toml in the CWD.
    resolved_name = project_name or _resolve_project_name(Path.cwd() / "dazzle.toml")

    try:
        from dazzle.signing.cert import generate_cert_chain_b64
    except ImportError as exc:
        typer.echo(
            f"`cryptography` is not installed: {exc}. "
            "Install the signing extra with `pip install dazzle-dsl[signing]`.",
            err=True,
        )
        raise typer.Exit(code=2) from exc

    b64, password = generate_cert_chain_b64(resolved_name, country=country)

    typer.echo(f"# Dazzle signing cert for {resolved_name} ({country})")
    typer.echo("# Capture these into your runtime environment:")
    typer.echo("")
    typer.echo(f'SIGNING_CERT_PASSWORD="{password}"')
    typer.echo(f'SIGNING_CERT_PFX_B64="{b64}"')

    # Token secret is a third env var the runtime needs; mint a sane
    # random default and surface it alongside the cert so callers don't
    # have to remember the third piece. Project may override.
    import secrets

    token_secret = secrets.token_urlsafe(32)
    typer.echo(f'SIGNING_TOKEN_SECRET="{token_secret}"')

    if heroku_app:
        typer.echo("")
        typer.echo(f"# Or as Heroku config (target: {heroku_app}):")
        typer.echo(f'heroku config:set SIGNING_CERT_PFX_B64="{b64}" -a {heroku_app}')
        typer.echo(f'heroku config:set SIGNING_CERT_PASSWORD="{password}" -a {heroku_app}')
        typer.echo(f'heroku config:set SIGNING_TOKEN_SECRET="{token_secret}" -a {heroku_app}')
