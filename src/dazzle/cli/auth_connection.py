"""`dazzle auth connection` — manage per-org enterprise SSO connections (auth Plan 4b.iv).

Operator/agent CLI for the runtime ``Connection`` records that drive enterprise OIDC
(create / list / delete, claim + DNS-TXT-verify domains). DB access is the authz, the
same model as the rest of `dazzle auth` — this is meant to be driven by devops or an
agent, not exposed as an in-app surface.

Domain verification is the anti-hijack gate: a domain only routes / lets an IdP assert
identities once its DNS TXT record proves ownership (``verify-domain``).
"""

from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

connection_app = typer.Typer(
    help="Manage per-org enterprise SSO connections (OIDC) and verify their domains",
    no_args_is_help=True,
)

console = Console()


def _store() -> Any:
    """The raw AuthStore — connection ops are store-level (the AuthService facade
    deliberately doesn't expose them). Resolves the DB URL via the auth CLI callback."""
    from dazzle.cli.auth import _get_auth_store

    return _get_auth_store()._store


def _parse_group_map(pairs: list[str]) -> dict[str, str]:
    """Parse ``["eng=engineer", "ops=operator"]`` → ``{"eng": "engineer", ...}``."""
    mapping: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise typer.BadParameter(f"--group-map expects group=role, got {pair!r}")
        group, role = pair.split("=", 1)
        group, role = group.strip(), role.strip()
        if not group or not role:
            raise typer.BadParameter(f"--group-map expects non-empty group=role, got {pair!r}")
        mapping[group] = role
    return mapping


@connection_app.command("create")
def create(
    tenant: Annotated[str, typer.Option("--tenant", help="Organization (tenant) id")],
    issuer: Annotated[str, typer.Option("--issuer", help="OIDC issuer URL")],
    client_id: Annotated[str, typer.Option("--client-id", help="OIDC client id")],
    client_secret: Annotated[
        str,
        typer.Option(
            "--client-secret",
            envvar="DAZZLE_OIDC_CLIENT_SECRET",
            help="OIDC client secret (prefer the env var so it stays out of argv)",
        ),
    ],
    group_map: Annotated[
        list[str] | None,
        typer.Option("--group-map", help="IdP group→role, e.g. --group-map eng=engineer"),
    ] = None,
) -> None:
    """Create an OIDC connection for an org. Encrypts the client secret at rest."""
    store = _store()
    conn = store.create_connection(
        tenant_id=tenant,
        type="oidc",
        config={"issuer": issuer, "client_id": client_id},
        secrets={"client_secret": client_secret},
        domains=[],
        group_mapping=_parse_group_map(group_map or []),
    )
    console.print(f"[green]Created OIDC connection[/green] [bold]{conn.id}[/bold] for org {tenant}")
    console.print(
        "Next: claim a domain with "
        f"[cyan]dazzle auth connection add-domain {conn.id} <domain>[/cyan], publish its TXT "
        "record, then [cyan]verify-domain[/cyan]. Register this redirect URI with the IdP: "
        "[cyan]<base_url>/auth/enterprise/callback[/cyan]."
    )


@connection_app.command("list")
def list_connections(
    tenant: Annotated[str, typer.Option("--tenant", help="Organization (tenant) id")],
) -> None:
    """List an org's connections."""
    conns = _store().get_connections_for_tenant(tenant)
    if not conns:
        console.print(f"No connections for org {tenant}.")
        return
    table = Table(title=f"Connections for {tenant}")
    for col in ("id", "type", "status", "claimed domains", "verified domains"):
        table.add_column(col)
    for c in conns:
        table.add_row(
            c.id,
            c.type,
            c.status,
            ", ".join(c.domains) or "—",
            ", ".join(c.verified_domains) or "—",
        )
    console.print(table)


@connection_app.command("add-domain")
def add_domain(
    connection_id: Annotated[str, typer.Argument(help="Connection id")],
    domain: Annotated[str, typer.Argument(help="Domain to claim (e.g. acme.test)")],
) -> None:
    """Claim a domain for a connection and print the DNS TXT record to publish."""
    from dazzle.back.runtime.auth.domain_verification import txt_record

    store = _store()
    conn = store.get_connection(connection_id)
    if conn is None:
        console.print(f"[red]No connection {connection_id!r}[/red]")
        raise typer.Exit(code=1)
    norm = domain.strip().lower().rstrip(".")
    store.set_connection_domains(connection_id, sorted({*conn.domains, norm}))
    console.print(f"Claimed [bold]{norm}[/bold] for connection {connection_id}.")
    console.print("Publish this DNS TXT record on the domain, then run verify-domain:")
    console.print(f'  [cyan]{norm}  IN TXT  "{txt_record(connection_id, norm)}"[/cyan]')


@connection_app.command("show-verification")
def show_verification(
    connection_id: Annotated[str, typer.Argument(help="Connection id")],
    domain: Annotated[str, typer.Argument(help="Domain")],
) -> None:
    """Print the DNS TXT record a domain must publish to verify (no DNS lookup)."""
    from dazzle.back.runtime.auth.domain_verification import txt_record

    norm = domain.strip().lower().rstrip(".")
    console.print(f'{norm}  IN TXT  "{txt_record(connection_id, norm)}"')


@connection_app.command("verify-domain")
def verify_domain_cmd(
    connection_id: Annotated[str, typer.Argument(help="Connection id")],
    domain: Annotated[str, typer.Argument(help="Domain to verify")],
) -> None:
    """Verify domain ownership via DNS TXT; on success the domain starts routing."""
    from dazzle.back.runtime.auth.domain_verification import (
        DnspythonResolver,
        DomainVerificationError,
        txt_record,
        verify_domain,
    )

    store = _store()
    conn = store.get_connection(connection_id)
    if conn is None:
        console.print(f"[red]No connection {connection_id!r}[/red]")
        raise typer.Exit(code=1)
    norm = domain.strip().lower().rstrip(".")
    try:
        ok = verify_domain(store, conn, norm, resolver=DnspythonResolver())
    except DomainVerificationError as exc:
        console.print(f"[red]Cannot verify {norm}: {exc}[/red]")
        raise typer.Exit(code=1) from exc
    if ok:
        console.print(f"[green]Verified[/green] [bold]{norm}[/bold] — it now routes to this org.")
    else:
        console.print(
            f"[yellow]Not verified yet[/yellow] — DNS TXT for {norm} doesn't carry the token. "
            "Publish this record (propagation can take minutes), then retry:"
        )
        console.print(f'  [cyan]{norm}  IN TXT  "{txt_record(connection_id, norm)}"[/cyan]')
        raise typer.Exit(code=1)


@connection_app.command("delete")
def delete(
    connection_id: Annotated[str, typer.Argument(help="Connection id")],
) -> None:
    """Delete a connection."""
    if _store().delete_connection(connection_id):
        console.print(f"[green]Deleted[/green] connection {connection_id}.")
    else:
        console.print(f"[red]No connection {connection_id!r}[/red]")
        raise typer.Exit(code=1)
