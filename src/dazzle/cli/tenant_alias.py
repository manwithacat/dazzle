"""CLI: dazzle tenant alias — custom-domain hostname aliases (ADR-0055 PR4).

New commands. Do **not** reuse ``dazzle auth connection verify-domain``
(that proves email-domain ownership for membership, not HTTP Host routing).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
from rich.console import Console

from dazzle.cli.env import get_active_env
from dazzle.cli.utils import load_project_appspec
from dazzle.core.manifest import load_manifest, resolve_database_url
from dazzle.http.runtime.tenant.aliases import (
    AliasError,
    AliasStore,
    claim,
    default_cname_resolver,
    default_txt_resolver,
    detach,
    txt_name,
    txt_value,
    verify_step,
)

alias_app = typer.Typer(
    help="Custom-domain hostname aliases (composing with tenant_host topology)",
    no_args_is_help=True,
)
console = Console()


def _alias_context() -> tuple[Any, str, str, tuple[str, ...]]:
    project_root = Path.cwd().resolve()
    if not (project_root / "dazzle.toml").exists():
        console.print("[red]No dazzle.toml found.[/red]")
        raise typer.Exit(1)
    manifest = load_manifest(project_root / "dazzle.toml")
    db_url = resolve_database_url(manifest, env_name=get_active_env())
    appspec = load_project_appspec(project_root)
    domain = ""
    canonical: list[str] = []
    for entity in appspec.domain.entities:
        th = getattr(entity, "tenant_host", None)
        if th is None:
            continue
        domain = th.domain
        canonical = list(th.canonical_hosts or [])
        break
    if not domain:
        console.print("[red]No tenant_host: block in this app — aliases compose with A/B.[/red]")
        raise typer.Exit(1)
    return appspec, db_url, domain, tuple(canonical)


def _connect(url: str) -> Any:
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(url, row_factory=dict_row)


def _txt_resolver() -> Any:
    return default_txt_resolver()


def _cname_resolver() -> Any:
    return default_cname_resolver()


@alias_app.command("claim")
def claim_command(
    tenant_id: str = typer.Argument(help="Existing tenant-root id to alias"),
    hostname: str = typer.Argument(help="Customer hostname (e.g. app.customer.com)"),
    cname_target: str = typer.Option(
        ...,
        "--cname-target",
        help="Platform hostname the customer CNAME must point at",
    ),
) -> None:
    """Claim a customer hostname. Prints the TXT challenge to publish."""
    _appspec, db_url, domain, canonical = _alias_context()
    try:
        with _connect(db_url) as conn:
            store = AliasStore(conn)
            row = claim(
                store,
                tenant_id=tenant_id,
                hostname=hostname,
                cname_target=cname_target,
                provider_domain=domain,
                canonical_hosts=canonical,
            )
            conn.commit()
    except AliasError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(f"[green]Claimed[/green] {row.hostname} → tenant {row.tenant_id}")
    console.print(f"  state:        {row.state}")
    console.print(f"  TXT name:     {txt_name(row.hostname)}")
    console.print(f"  TXT value:    {txt_value(row.txt_token)}")
    console.print(f"  CNAME target: {row.cname_target}")
    console.print("Publish the TXT, then run [cyan]dazzle tenant alias verify[/cyan].")


@alias_app.command("show-verification")
def show_verification_command(
    hostname: str = typer.Argument(help="Claimed customer hostname"),
) -> None:
    """Show the TXT + CNAME records the operator must publish."""
    _appspec, db_url, _domain, _canonical = _alias_context()
    with _connect(db_url) as conn:
        row = AliasStore(conn).get_by_hostname(hostname)
    if row is None:
        console.print(f"[red]No alias claimed for {hostname!r}.[/red]")
        raise typer.Exit(1)
    console.print(f"hostname:     {row.hostname}")
    console.print(f"tenant_id:    {row.tenant_id}")
    console.print(f"state:        {row.state}")
    console.print(f"TXT name:     {txt_name(row.hostname)}")
    console.print(f"TXT value:    {txt_value(row.txt_token)}")
    console.print(f"CNAME:        {row.hostname} → {row.cname_target}")
    console.print(
        "SNI:          provision a per-hostname cert (see docs/reference/tenant-hosts.md)"
    )


@alias_app.command("verify")
def verify_command(
    hostname: str = typer.Argument(help="Claimed customer hostname"),
) -> None:
    """Advance one attach step (TXT, then CNAME). Fail-closed if DNS mismatches."""
    _appspec, db_url, _domain, _canonical = _alias_context()
    try:
        with _connect(db_url) as conn:
            store = AliasStore(conn)
            row = verify_step(
                store,
                hostname,
                txt_resolver=_txt_resolver(),
                cname_resolver=_cname_resolver(),
            )
            conn.commit()
    except AliasError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(f"[green]Verified[/green] {row.hostname} → {row.state}")
    if row.state == "pending_cname":
        console.print(f"Next: CNAME {row.hostname} → {row.cname_target}, then verify again.")
        console.print("Then provision the SNI cert (ops runbook in tenant-hosts.md).")
    elif row.state == "active":
        console.print("Alias is active. Resolver will bind this Host to the tenant.")


@alias_app.command("detach")
def detach_command(
    hostname: str = typer.Argument(help="Customer hostname to detach"),
) -> None:
    """Detach. Keeps serving until DNS is gone, then cools ≥24h."""
    _appspec, db_url, _domain, _canonical = _alias_context()
    try:
        with _connect(db_url) as conn:
            store = AliasStore(conn)
            row = detach(
                store,
                hostname,
                txt_resolver=_txt_resolver(),
                cname_resolver=_cname_resolver(),
            )
            conn.commit()
    except AliasError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    if row is None:
        console.print(f"[green]Abandoned[/green] pending claim for {hostname}")
        return
    console.print(f"[yellow]{row.hostname}[/yellow] → {row.state}")
    if row.state == "pending_detach":
        console.print("Still serving until TXT and CNAME are gone. Re-run detach after DNS drops.")
    elif row.state == "cooling" and row.reusable_after is not None:
        console.print(f"Reusable after {row.reusable_after.isoformat()} (≥24h cooling).")
