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
    import secrets as _secrets

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


@connection_app.command("create-saml")
def create_saml(
    tenant: Annotated[str, typer.Option("--tenant", help="Organization (tenant) id")],
    idp_entity_id: Annotated[
        str,
        typer.Option("--idp-entity-id", help="IdP entity id (issuer); from metadata if omitted"),
    ] = "",
    idp_sso_url: Annotated[
        str,
        typer.Option("--idp-sso-url", help="IdP SSO redirect URL; from metadata if omitted"),
    ] = "",
    idp_cert_file: Annotated[
        str,
        typer.Option(
            "--idp-cert-file", help="IdP X.509 signing cert (PEM); from metadata if omitted"
        ),
    ] = "",
    idp_metadata_url: Annotated[
        str,
        typer.Option(
            "--idp-metadata-url", help="Fetch IdP metadata from this https URL (auto-fill)"
        ),
    ] = "",
    idp_metadata_file: Annotated[
        str,
        typer.Option(
            "--idp-metadata-file", help="Read IdP metadata from this local file (auto-fill)"
        ),
    ] = "",
    email_attribute: Annotated[
        str, typer.Option("--email-attribute", help="SAML attr holding email (else NameID)")
    ] = "",
    groups_attribute: Annotated[
        str, typer.Option("--groups-attribute", help="SAML attr holding groups (default 'groups')")
    ] = "",
    group_map: Annotated[
        list[str] | None,
        typer.Option("--group-map", help="IdP group→role, e.g. --group-map eng=engineer"),
    ] = None,
) -> None:
    """Create a SAML connection from the IdP's metadata (entity id, SSO URL, signing cert).

    Provide the three values explicitly, or auto-fill them from the IdP's metadata with
    ``--idp-metadata-url`` (https, SSRF-guarded fetch) or ``--idp-metadata-file`` (local).
    Explicit flags override metadata. The IdP signing cert is PUBLIC (config, not secrets).
    After creating, give the IdP the ACS URL + SP entity id below, then verify a domain —
    SAML is SP-initiated only.
    """
    from pathlib import Path

    from dazzle.back.runtime.auth.saml_metadata import (
        SamlMetadataError,
        fetch_idp_metadata,
        parse_idp_metadata_xml,
    )

    if idp_metadata_url and idp_metadata_file:
        console.print(
            "[red]--idp-metadata-url and --idp-metadata-file are mutually exclusive[/red]"
        )
        raise typer.Exit(code=1)

    parsed: dict[str, str] = {}
    if idp_metadata_url or idp_metadata_file:
        try:
            if idp_metadata_url:
                xml = fetch_idp_metadata(idp_metadata_url)
            else:
                xml = Path(idp_metadata_file).read_text(encoding="utf-8")
            parsed = parse_idp_metadata_xml(xml)
        except SamlMetadataError as exc:
            console.print(f"[red]IdP metadata import failed ({exc.reason}): {exc}[/red]")
            raise typer.Exit(code=1) from exc
        except OSError as exc:
            console.print(
                f"[red]Cannot read --idp-metadata-file {idp_metadata_file!r}: {exc}[/red]"
            )
            raise typer.Exit(code=1) from exc

    cert = ""
    if idp_cert_file:
        try:
            cert = Path(idp_cert_file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            console.print(f"[red]Cannot read --idp-cert-file {idp_cert_file!r}: {exc}[/red]")
            raise typer.Exit(code=1) from exc
    # Explicit flags override metadata.
    entity_id = idp_entity_id or parsed.get("idp_entity_id", "")
    sso_url = idp_sso_url or parsed.get("idp_sso_url", "")
    cert = cert or parsed.get("idp_x509_cert", "")

    missing = [
        name
        for name, val in (
            ("entity id", entity_id),
            ("SSO URL", sso_url),
            ("signing cert", cert),
        )
        if not val
    ]
    if missing:
        console.print(
            f"[red]Missing IdP {', '.join(missing)}. Provide --idp-metadata-url/"
            "--idp-metadata-file, or pass --idp-entity-id/--idp-sso-url/--idp-cert-file.[/red]"
        )
        raise typer.Exit(code=1)

    config: dict[str, str] = {
        "idp_entity_id": entity_id,
        "idp_sso_url": sso_url,
        "idp_x509_cert": cert,
    }
    if parsed.get("idp_slo_url"):
        config["idp_slo_url"] = parsed["idp_slo_url"]
    if email_attribute:
        config["email_attribute"] = email_attribute
    if groups_attribute:
        config["groups_attribute"] = groups_attribute

    conn = _store().create_connection(
        tenant_id=tenant,
        type="saml",
        config=config,
        secrets={},
        domains=[],
        group_mapping=_parse_group_map(group_map or []),
    )
    console.print(f"[green]Created SAML connection[/green] [bold]{conn.id}[/bold] for org {tenant}")
    console.print("\n[bold]Configure these in the IdP:[/bold]")
    console.print("  ACS (Reply) URL:  [cyan]<base_url>/auth/saml/acs[/cyan]")
    console.print("  SP Entity ID:     [cyan]<base_url>/auth/saml/acs[/cyan] (default)")
    console.print("  NameID format:    [cyan]emailAddress[/cyan]")
    console.print(
        "\nSAML is [bold]SP-initiated only[/bold] (IdP-initiated is refused). Then verify a "
        "domain ([cyan]add-domain[/cyan] → publish TXT → [cyan]verify-domain[/cyan])."
    )


@connection_app.command("enable-request-signing")
def enable_request_signing(
    connection_id: Annotated[str, typer.Argument(help="SAML connection id")],
) -> None:
    """Generate an SP keypair and sign this connection's AuthnRequests (SAML only).

    Re-import the connection's metadata at the IdP afterwards (printed URL) so it trusts the
    SP signing cert. The Response signature is still the trust anchor. Rotate the key by
    running disable-request-signing then this again.
    """
    from dazzle.back.runtime.auth.saml_sp_keys import generate_sp_keypair

    store = _store()
    conn = store.get_connection(connection_id)
    if conn is None:
        console.print(f"[red]No connection {connection_id!r}[/red]")
        raise typer.Exit(code=1)
    if conn.type != "saml":
        console.print(
            f"[red]Connection {connection_id!r} is {conn.type!r} — request signing is SAML-only[/red]"
        )
        raise typer.Exit(code=1)
    if (conn.config or {}).get("sign_requests"):
        console.print(
            f"[yellow]Request signing already enabled[/yellow] for {connection_id} "
            "(disable-request-signing then enable to rotate the key)."
        )
        raise typer.Exit(code=0)
    common_name = (conn.config or {}).get("sp_entity_id") or connection_id
    key_pem, cert_pem = generate_sp_keypair(common_name)
    if not store.enable_connection_request_signing(
        connection_id, sp_cert=cert_pem, sp_private_key=key_pem
    ):
        console.print(f"[red]Failed to enable request signing for {connection_id!r}[/red]")
        raise typer.Exit(code=1)
    console.print(f"[green]Request signing enabled[/green] for connection {connection_id}.")
    console.print(
        "Re-import this connection's SP metadata at the IdP so it trusts the signing cert:"
    )
    console.print(f"  [cyan]<base_url>/auth/saml/metadata?connection={connection_id}[/cyan]")


@connection_app.command("disable-request-signing")
def disable_request_signing(
    connection_id: Annotated[str, typer.Argument(help="SAML connection id")],
) -> None:
    """Stop signing this connection's AuthnRequests and drop its SP keypair."""
    store = _store()
    if store.disable_connection_request_signing(connection_id):
        console.print(f"[green]Request signing disabled[/green] for connection {connection_id}.")
    else:
        console.print(f"[yellow]Request signing was not enabled[/yellow] for {connection_id}.")


@connection_app.command("enable-assertion-encryption")
def enable_assertion_encryption(
    connection_id: Annotated[str, typer.Argument(help="SAML connection id")],
) -> None:
    """Require + decrypt encrypted SAML assertions on this connection (SAML only).

    Reuses the SP keypair if request-signing already created one, else generates it. After
    enabling, configure the IdP to ENCRYPT assertions and re-import this connection's SP
    metadata (printed URL) so it has the SP encryption cert. WARNING: once on, a response
    carrying a plaintext (unencrypted) assertion is rejected — enable the IdP side first.
    """
    from dazzle.back.runtime.auth.saml_sp_keys import generate_sp_keypair

    store = _store()
    conn = store.get_connection(connection_id)
    if conn is None:
        console.print(f"[red]No connection {connection_id!r}[/red]")
        raise typer.Exit(code=1)
    if conn.type != "saml":
        console.print(
            f"[red]Connection {connection_id!r} is {conn.type!r} — assertion encryption is "
            "SAML-only[/red]"
        )
        raise typer.Exit(code=1)
    if (conn.config or {}).get("encrypt_assertions"):
        console.print(f"[yellow]Assertion encryption already enabled[/yellow] for {connection_id}.")
        raise typer.Exit(code=0)
    cfg = conn.config or {}
    sp_cert = cfg.get("sp_cert")
    sp_key = (conn.secrets or {}).get("sp_private_key")
    if not (sp_cert and sp_key):
        common_name = cfg.get("sp_entity_id") or connection_id
        sp_key, sp_cert = generate_sp_keypair(common_name)
    if not store.enable_connection_assertion_encryption(
        connection_id, sp_cert=sp_cert, sp_private_key=sp_key
    ):
        console.print(f"[red]Failed to enable assertion encryption for {connection_id!r}[/red]")
        raise typer.Exit(code=1)
    console.print(f"[green]Assertion encryption enabled[/green] for connection {connection_id}.")
    console.print(
        "[yellow]Configure the IdP to encrypt assertions, then re-import this connection's "
        "SP metadata[/yellow] (a plaintext assertion is now rejected):"
    )
    console.print(f"  [cyan]<base_url>/auth/saml/metadata?connection={connection_id}[/cyan]")


@connection_app.command("disable-assertion-encryption")
def disable_assertion_encryption(
    connection_id: Annotated[str, typer.Argument(help="SAML connection id")],
) -> None:
    """Stop requiring encrypted assertions (drops the SP keypair iff signing is also off)."""
    store = _store()
    if store.disable_connection_assertion_encryption(connection_id):
        console.print(
            f"[green]Assertion encryption disabled[/green] for connection {connection_id}."
        )
    else:
        console.print(f"[yellow]Assertion encryption was not enabled[/yellow] for {connection_id}.")


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
    have the new one). SCIM: mints a NEW bearer and prints it once. SAML has no rotatable
    secret (the IdP cert is public config; use ``create-saml`` to replace it).

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
        import secrets as _secrets

        new_bearer = _secrets.token_urlsafe(32)
        new_secrets = {"scim_bearer": new_bearer}
    else:
        console.print(
            f"[red]Connection {connection_id!r} is type {conn.type!r} — no rotatable secret. "
            "A SAML IdP cert is public config; recreate the connection to change it.[/red]"
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
        from dazzle.back.runtime.auth.secret_rotation import parse_grace_duration

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
    import json

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


def _env_flags() -> tuple[bool, bool, bool]:
    """(secret_key_ok, sso_extra_ok, dns_extra_ok) for the doctor — shared with the
    org-admin readiness panel via the runtime helper (single source of truth)."""
    from dazzle.back.runtime.auth.connection_doctor import environment_flags

    return environment_flags()


@connection_app.command("doctor")
def doctor(
    connection_id: Annotated[str, typer.Argument(help="Connection id")],
    json_out: Annotated[
        bool, typer.Option("--json", help="Emit the diagnosis as JSON (for agents)")
    ] = False,
) -> None:
    """Report what a connection still needs to go live + an activation runbook.

    Exit code is 0 only when the connection is activation-ready, so CI/agents can gate
    on it. Never prints the client secret value (only whether one is present).
    """
    import json as _json

    from dazzle.back.runtime.auth.connection_crypto import ConnectionSecretError
    from dazzle.back.runtime.auth.connection_doctor import diagnose_connection

    secret_key_ok, sso_extra_ok, dns_extra_ok = _env_flags()

    # The key gates everything: without it the stored secret can't be decrypted, so
    # there's nothing further to introspect. Report just that and stop.
    if not secret_key_ok:
        msg = (
            "DAZZLE_CONNECTION_SECRET is missing/invalid — set a 32-byte base64 key and "
            "re-run doctor for the full report. Generate one with: "
            'python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"'
        )
        if json_out:
            console.print_json(
                data={
                    "connection_id": connection_id,
                    "ready": False,
                    "blocked": "secret_key",
                    "remedy": msg,
                }
            )
        else:
            console.print(f"[red]{msg}[/red]")
        raise typer.Exit(code=1)

    try:
        conn = _store().get_connection(connection_id)
    except ConnectionSecretError as exc:
        # Key is present but the stored secret won't decrypt (rotated/wrong key).
        detail = (
            "Cannot decrypt the stored secret with the current key "
            "(rotated/wrong DAZZLE_CONNECTION_SECRET?)"
        )
        if json_out:
            console.print_json(
                data={
                    "connection_id": connection_id,
                    "ready": False,
                    "blocked": "secret_decrypt",
                    "remedy": detail,
                }
            )
        else:
            console.print(f"[red]{detail}: {exc}[/red]")
        raise typer.Exit(code=1) from exc
    if conn is None:
        console.print(f"[red]No connection {connection_id!r}[/red]")
        raise typer.Exit(code=1)

    diag = diagnose_connection(
        conn, secret_key_ok=secret_key_ok, sso_extra_ok=sso_extra_ok, dns_extra_ok=dns_extra_ok
    )

    if json_out:
        console.print(
            _json.dumps(
                {
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
                },
                indent=2,
            )
        )
        if not diag.ready:
            raise typer.Exit(code=1)
        return

    _symbol = {"ok": "[green]✓[/green]", "warn": "[yellow]●[/yellow]", "fail": "[red]✗[/red]"}
    table = Table(title=f"Connection {diag.connection_id} ({diag.connection_type})")
    for col in ("", "check", "level", "detail"):
        table.add_column(col)
    for c in diag.checks:
        table.add_row(_symbol.get(c.status, "?"), c.name, c.level, c.detail)
    console.print(table)

    if diag.ready:
        console.print("[green]Activation-ready.[/green]")
    else:
        console.print("[red]Not activation-ready.[/red]")
    console.print("\n[bold]Activation runbook:[/bold]")
    for i, step in enumerate(diag.runbook, 1):
        console.print(f"  {i}. {step}")

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
