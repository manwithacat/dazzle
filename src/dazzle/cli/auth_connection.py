"""`dazzle auth connection` — manage per-org enterprise SSO connections (auth Plan 4b.iv).

Operator/agent CLI for the runtime ``Connection`` records that drive enterprise OIDC and
SCIM (create / list / delete, claim + DNS-TXT-verify domains). DB access is the authz, the
same model as the rest of `dazzle auth` — this is meant to be driven by devops or an
agent, not exposed as an in-app surface.

Domain verification is the anti-hijack gate: a domain only routes / lets an IdP assert
identities once its DNS TXT record proves ownership (``verify-domain``).
"""

import json
import secrets as _secrets
from typing import Annotated, Any

import click
import typer
from rich.console import Console
from rich.table import Table

from dazzle.cli.services.auth_service import AuthService
from dazzle.http.runtime.auth.connection_crypto import ConnectionSecretError
from dazzle.http.runtime.auth.connection_doctor import diagnose_connection, environment_flags
from dazzle.http.runtime.auth.connection_probe import probe_connection
from dazzle.http.runtime.auth.domain_verification import (
    DomainVerificationError,
    txt_record,
    verify_domain,
)
from dazzle.http.runtime.auth.secret_rotation import parse_grace_duration
from dazzle.http.runtime.tenant.aliases import DnspythonResolver

connection_app = typer.Typer(
    help="Manage per-org enterprise SSO connections (OIDC, SCIM) and verify their domains",
    no_args_is_help=True,
)

console = Console()


def _database_url_from_context() -> str | None:
    """The ``--database-url`` given to the parent ``dazzle auth`` callback, if any.

    Read from the click context chain so this module does not import ``dazzle.cli.auth``
    (which mounts it — an import cycle)."""
    ctx = click.get_current_context(silent=True)
    while ctx is not None:
        value = ctx.params.get("database_url")
        if value:
            return str(value)
        ctx = ctx.parent
    return None


def _store() -> Any:
    """The raw AuthStore — connection ops are store-level (the AuthService facade
    deliberately doesn't expose them). Resolves the DB URL via the auth CLI callback."""
    return AuthService.from_manifest(database_url_override=_database_url_from_context())._store


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


@connection_app.command("create-scim")
def create_scim(
    tenant: Annotated[str, typer.Option("--tenant", help="Organization (tenant) id")],
    group_map: Annotated[
        list[str] | None,
        typer.Option("--group-map", help="IdP group→role, e.g. --group-map eng=engineer"),
    ] = None,
) -> None:
    """Create a SCIM connection, mint its bearer token, and print it ONCE.

    The bearer is stored encrypted at rest; it is shown here only at creation — save
    it and configure it in the IdP. The IdP must also be given the SCIM base URL.
    """
    bearer = _secrets.token_urlsafe(32)
    store = _store()
    conn = store.create_connection(
        tenant_id=tenant,
        type="scim",
        config={},
        secrets={"scim_bearer": bearer},
        domains=[],
        group_mapping=_parse_group_map(group_map or []),
    )
    console.print(f"[green]Created SCIM connection[/green] [bold]{conn.id}[/bold] for org {tenant}")
    console.print("\n[bold]Configure these in the IdP (the bearer is shown only once):[/bold]")
    console.print("  SCIM base URL:  [cyan]<base_url>/scim/v2[/cyan]")
    console.print(f"  Bearer token:   [cyan]{bearer}[/cyan]")
    console.print(
        "\nThen verify a domain ([cyan]add-domain[/cyan] → publish TXT → [cyan]verify-domain"
        "[/cyan]) — SCIM only provisions users in this connection's verified domains."
    )


@connection_app.command("rotate-secret")
def rotate_secret(
    connection_id: Annotated[str, typer.Argument(help="Connection id")],
    client_secret: Annotated[
        str,
        typer.Option(
            "--client-secret",
            envvar="DAZZLE_OIDC_CLIENT_SECRET",
            help="New OIDC client secret (OIDC only; prefer the env var)",
        ),
    ] = "",
    grace: Annotated[
        str,
        typer.Option(
            "--grace",
            help="Keep the OLD SCIM bearer valid this long (e.g. 24h, 7d). SCIM only.",
        ),
    ] = "",
) -> None:
    """Rotate a connection's secret (after a leak / scheduled rotation).

    OIDC: replaces the ``client_secret`` (pass ``--client-secret``; the IdP must already
    have the new one). SCIM: mints a NEW bearer and prints it once. A ``domain``
    connection has no secret to rotate.

    By default the old secret stops working immediately (right for a leak). Pass
    ``--grace 24h`` (SCIM only) to keep the OLD bearer valid for an overlap window so the
    IdP can migrate without a provisioning outage; end it early with
    ``revoke-previous-secret``. Existing user sessions are unaffected.
    """
    store = _store()
    conn = store.get_connection(connection_id)
    if conn is None:
        console.print(f"[red]No connection {connection_id!r}[/red]")
        raise typer.Exit(code=1)

    new_bearer: str | None = None
    if conn.type == "oidc":
        if not client_secret:
            console.print(
                "[red]--client-secret is required for an OIDC connection "
                "(or set DAZZLE_OIDC_CLIENT_SECRET)[/red]"
            )
            raise typer.Exit(code=1)
        new_secrets: dict[str, str] = {"client_secret": client_secret}
    elif conn.type == "scim":
        new_bearer = _secrets.token_urlsafe(32)
        new_secrets = {"scim_bearer": new_bearer}
    else:
        console.print(
            f"[red]Connection {connection_id!r} is type {conn.type!r} — no rotatable secret.[/red]"
        )
        raise typer.Exit(code=1)

    grace_td = None
    if grace:
        if conn.type != "scim":
            console.print(
                "[red]--grace applies only to a SCIM bearer (an OIDC client_secret is "
                "arbitrated by the IdP, so an overlap window can't help).[/red]"
            )
            raise typer.Exit(code=1)
        try:
            grace_td = parse_grace_duration(grace)
        except ValueError as exc:
            console.print(f"[red]Invalid --grace: {exc}[/red]")
            raise typer.Exit(code=1) from exc

    if not store.rotate_connection_secret(connection_id, new_secrets, grace=grace_td, actor="cli"):
        console.print(f"[red]Rotation failed — connection {connection_id!r} not updated[/red]")
        raise typer.Exit(code=1)

    console.print(f"[green]Rotated[/green] the secret for connection {connection_id}.")
    if new_bearer is not None:
        console.print("\n[bold]New SCIM bearer (shown once — update the IdP):[/bold]")
        console.print(f"  [cyan]{new_bearer}[/cyan]")
        if grace_td is not None:
            console.print(
                f"The previous bearer stays [bold]valid[/bold] for ~{grace} — run "
                "`revoke-previous-secret` to end the window early."
            )
        else:
            console.print("The previous bearer is now [bold]invalid[/bold].")
    else:
        console.print(
            "Ensure the IdP has the new client secret — the previous one no longer works "
            "for new logins. Existing user sessions are unaffected."
        )


@connection_app.command("revoke-previous-secret")
def revoke_previous_secret(
    connection_id: Annotated[str, typer.Argument(help="Connection id")],
) -> None:
    """Immediately invalidate the OLD (grace) SCIM bearer left by `rotate-secret --grace`."""
    store = _store()
    # Distinguish "no such connection" from "nothing to revoke" — a mistyped id
    # must not look like a benign no-op for a security operation.
    if store.get_connection(connection_id) is None:
        console.print(f"[red]No connection {connection_id!r}[/red]")
        raise typer.Exit(code=1)
    if store.revoke_previous_connection_secret(connection_id, actor="cli"):
        console.print(f"[green]Revoked[/green] the previous (grace) secret for {connection_id}.")
    else:
        console.print(
            f"[yellow]No active grace secret[/yellow] for {connection_id} — nothing to revoke."
        )


@connection_app.command("secret-history")
def secret_history(
    connection_id: Annotated[str, typer.Argument(help="Connection id")],
) -> None:
    """Show the append-only secret-rotation audit trail for a connection."""
    store = _store()
    events = store.get_connection_secret_events(connection_id)
    if not events:
        console.print(f"No secret-rotation events for {connection_id}.")
        return
    for e in events:
        detail = e.detail if isinstance(e.detail, dict) else json.loads(e.detail or "{}")
        console.print(f"[cyan]{e.at}[/cyan]  {e.event}  (actor={e.actor or '-'})  {detail}")


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
    norm = domain.strip().lower().rstrip(".")
    console.print(f'{norm}  IN TXT  "{txt_record(connection_id, norm)}"')


@connection_app.command("verify-domain")
def verify_domain_cmd(
    connection_id: Annotated[str, typer.Argument(help="Connection id")],
    domain: Annotated[str, typer.Argument(help="Domain to verify")],
) -> None:
    """Verify domain ownership via DNS TXT; on success the domain starts routing."""
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


@connection_app.command("set-require-sso")
def set_require_sso(
    connection_id: Annotated[str, typer.Argument(help="OIDC connection id")],
    on: Annotated[
        bool,
        typer.Option(
            "--on/--off",
            help="Refuse local sign-in for the connection's verified domains (--on) or allow it",
        ),
    ],
    tenant: Annotated[
        str | None,
        typer.Option("--tenant", help="Fence the change to this organization (tenant) id"),
    ] = None,
) -> None:
    """Turn `require_sso` on or off for an OIDC connection (DD-013).

    On: password login, signup, magic links and password reset for the connection's
    VERIFIED domains are refused and sent to the IdP. OIDC connections only.
    """
    try:
        changed = _store().set_connection_require_sso(connection_id, on, tenant_id=tenant)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    if not changed:
        console.print(f"[red]No connection {connection_id!r}[/red]")
        raise typer.Exit(code=1)
    state = "on" if on else "off"
    console.print(f"[green]require_sso {state}[/green] for connection {connection_id}.")


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


_SYMBOL = {"ok": "[green]✓[/green]", "warn": "[yellow]●[/yellow]", "fail": "[red]✗[/red]"}


def _blocked(connection_id: str, blocked: str, remedy: str, json_out: bool, text: str) -> None:
    """Report a doctor run that cannot proceed (``blocked`` is a stable machine code)."""
    if json_out:
        console.print_json(
            data={
                "connection_id": connection_id,
                "ready": False,
                "blocked": blocked,
                "remedy": remedy,
            }
        )
    else:
        console.print(text)


def _doctor_payload(diag: Any, probe_checks: tuple[Any, ...] | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "connection_id": diag.connection_id,
        "connection_type": diag.connection_type,
        "ready": diag.ready,
        "checks": [
            {
                "name": c.name,
                "level": c.level,
                "status": c.status,
                "detail": c.detail,
                "remedy": c.remedy,
            }
            for c in diag.checks
        ],
        "runbook": list(diag.runbook),
    }
    if probe_checks is not None:
        payload["probe"] = [
            {"name": c.name, "level": c.level, "status": c.status, "detail": c.detail}
            for c in probe_checks
        ]
    return payload


def _render_doctor(diag: Any, probe_checks: tuple[Any, ...] | None) -> None:
    table = Table(title=f"Connection {diag.connection_id} ({diag.connection_type})")
    for col in ("", "check", "level", "detail"):
        table.add_column(col)
    for c in diag.checks:
        table.add_row(_SYMBOL.get(c.status, "?"), c.name, c.level, c.detail)
    console.print(table)

    if diag.ready:
        console.print("[green]Activation-ready.[/green]")
    else:
        console.print("[red]Not activation-ready.[/red]")
    console.print("\n[bold]Activation runbook:[/bold]")
    for i, step in enumerate(diag.runbook, 1):
        console.print(f"  {i}. {step}")

    if probe_checks is not None:
        probe_table = Table(title="Live probe (network)")
        for col in ("", "check", "detail"):
            probe_table.add_column(col)
        for c in probe_checks:
            probe_table.add_row(_SYMBOL.get(c.status, "?"), c.name, c.detail)
        console.print()
        console.print(probe_table)


@connection_app.command("doctor")
def doctor(
    connection_id: Annotated[str, typer.Argument(help="Connection id")],
    json_out: Annotated[
        bool, typer.Option("--json", help="Emit the diagnosis as JSON (for agents)")
    ] = False,
    probe: Annotated[
        bool,
        typer.Option(
            "--probe",
            help="Also run a live reachability probe of the OIDC discovery document (network "
            "I/O, SSRF-guarded). Opt-in; does not affect the exit code.",
        ),
    ] = False,
) -> None:
    """Report what a connection still needs to go live + an activation runbook.

    Exit code is 0 only when the connection is activation-ready (config completeness), so
    CI/agents can gate on it. ``--probe`` adds an opt-in live reachability check of the OIDC
    discovery document on top of the network-free audit — informational only (a transient IdP
    outage must not flip the gate), so it never changes the exit code. Never prints the
    client secret value (only whether one is present).
    """
    secret_key_ok, sso_extra_ok, dns_extra_ok = environment_flags()

    # The key gates everything: without it the stored secret can't be decrypted, so
    # there's nothing further to introspect. Report just that and stop.
    if not secret_key_ok:
        msg = (
            "DAZZLE_CONNECTION_SECRET is missing/invalid — set a 32-byte base64 key and "
            "re-run doctor for the full report. Generate one with: "
            'python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"'
        )
        _blocked(connection_id, "secret_key", msg, json_out, f"[red]{msg}[/red]")
        raise typer.Exit(code=1)

    try:
        conn = _store().get_connection(connection_id)
    except ConnectionSecretError as exc:
        # Key is present but the stored secret won't decrypt (rotated/wrong key).
        detail = (
            "Cannot decrypt the stored secret with the current key "
            "(rotated/wrong DAZZLE_CONNECTION_SECRET?)"
        )
        _blocked(connection_id, "secret_decrypt", detail, json_out, f"[red]{detail}: {exc}[/red]")
        raise typer.Exit(code=1) from exc
    if conn is None:
        console.print(f"[red]No connection {connection_id!r}[/red]")
        raise typer.Exit(code=1)

    diag = diagnose_connection(
        conn, secret_key_ok=secret_key_ok, sso_extra_ok=sso_extra_ok, dns_extra_ok=dns_extra_ok
    )

    # Opt-in live reachability probe (network I/O, SSRF-guarded). Informational only — never
    # affects the exit code, which stays bound to config-readiness (diag.ready).
    probe_checks = probe_connection(conn) if probe else None

    if json_out:
        # Plain stdout, not the rich console: rich wraps long lines and eats `[sso]` as markup.
        typer.echo(json.dumps(_doctor_payload(diag, probe_checks), indent=2))
    else:
        _render_doctor(diag, probe_checks)
    if not diag.ready:
        raise typer.Exit(code=1)


@connection_app.command("scaffold")
def scaffold() -> None:
    """Print the end-to-end command sequence to stand up a new OIDC connection."""
    console.print("[bold]Stand up an enterprise OIDC connection:[/bold]\n")
    steps = [
        (
            "Generate the at-rest key (once per deployment)",
            "export DAZZLE_CONNECTION_SECRET=\"$(python -c 'import os,base64;"
            "print(base64.b64encode(os.urandom(32)).decode())')\"",
        ),
        (
            "Create the connection (secret via env, not argv)",
            "export DAZZLE_OIDC_CLIENT_SECRET=<idp-client-secret>\n"
            "     dazzle auth connection create --tenant <org-id> "
            "--issuer https://<idp> --client-id <client-id> "
            "--group-map <idp-group>=<role>",
        ),
        (
            "Claim a domain (prints the DNS TXT record to publish)",
            "dazzle auth connection add-domain <connection-id> <domain>",
        ),
        (
            "Publish that TXT record in the domain's DNS, then verify",
            "dazzle auth connection verify-domain <connection-id> <domain>",
        ),
        ("Register the redirect URI with the IdP", "<base_url>/auth/enterprise/callback"),
        ("Check readiness (exit 0 when live)", "dazzle auth connection doctor <connection-id>"),
    ]
    for i, (title, cmd) in enumerate(steps, 1):
        console.print(f"[bold]{i}. {title}[/bold]")
        console.print(f"   [cyan]{cmd}[/cyan]\n")
