"""
Authentication management commands for DAZZLE CLI.

Manage users and sessions directly against the auth database
(PostgreSQL) without requiring a running server.
"""

from __future__ import annotations

import json
import secrets
import string
from typing import Annotated, Any
from uuid import UUID

import typer
from rich.console import Console
from rich.table import Table

auth_app = typer.Typer(
    help="Manage authentication users and sessions",
    no_args_is_help=True,
)

console = Console()

# Module-level database URL set by the callback
_database_url_override: str | None = None


@auth_app.callback()
def auth_callback(
    database_url: Annotated[
        str | None,
        typer.Option(
            "--database-url",
            envvar="DATABASE_URL",
            help="PostgreSQL database URL. Defaults to postgresql://localhost:5432/dazzle",
        ),
    ] = None,
) -> None:
    """Manage authentication users and sessions."""
    global _database_url_override  # noqa: PLW0603  # CLI callback storage, per-invocation
    _database_url_override = database_url


def _get_auth_store(database_url: str | None = None) -> Any:
    """Get an AuthService instance.

    Resolves URL via: explicit arg → CLI callback → dazzle.toml → env → default.
    """
    from dazzle.cli.services.auth_service import AuthService

    explicit = database_url or _database_url_override or ""
    return AuthService.from_manifest(database_url_override=explicit or None)


def _generate_temp_password(length: int = 16) -> str:
    """Generate a secure temporary password."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _parse_ttl(ttl_str: str) -> int:
    """Parse a TTL string like '5m', '1h', '30s' into seconds."""
    units = {"s": 1, "m": 60, "h": 3600}
    if ttl_str[-1] in units:
        return int(ttl_str[:-1]) * units[ttl_str[-1]]
    return int(ttl_str)


def _resolve_user(store: Any, identifier: str) -> Any:
    """Resolve a user by UUID or email. Returns UserRecord or None."""
    try:
        user_id = UUID(identifier)
        return store.get_user_by_id(user_id)
    except ValueError:
        return store.get_user_by_email(identifier)


def _user_to_dict(user: Any, include_hash: bool = False) -> dict[str, Any]:
    """Convert UserRecord to dict for JSON output."""
    result = {
        "id": str(user.id),
        "email": user.email,
        "username": user.username,
        "is_active": user.is_active,
        "is_superuser": user.is_superuser,
        "roles": user.roles,
        "created_at": user.created_at.isoformat(),
        "updated_at": user.updated_at.isoformat(),
    }
    if include_hash:
        result["password_hash"] = user.password_hash
    return result


# =============================================================================
# Commands
# =============================================================================


_MIN_PASSWORD_LENGTH = 8


@auth_app.command(name="create-user")
def create_user(
    email: Annotated[str, typer.Argument(help="User email address")],
    name: Annotated[str | None, typer.Option("--name", "-n", help="Display name")] = None,
    roles: Annotated[
        str | None, typer.Option("--roles", "-r", help="Comma-separated roles")
    ] = None,
    superuser: Annotated[
        bool, typer.Option("--superuser", help="Grant superuser privileges")
    ] = False,
    password: Annotated[
        str | None,
        typer.Option("--password", "-p", help="Set an explicit password instead of generating one"),
    ] = None,
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Create a new user with a generated or explicit password."""
    store = _get_auth_store()

    existing = store.get_user_by_email(email)
    if existing:
        console.print(f"[red]User with email '{email}' already exists[/red]")
        raise typer.Exit(1)

    if password is not None:
        if len(password) < _MIN_PASSWORD_LENGTH:
            console.print(f"[red]Password must be at least {_MIN_PASSWORD_LENGTH} characters[/red]")
            raise typer.Exit(1)
        chosen_password = password
        is_explicit = True
    else:
        chosen_password = _generate_temp_password()
        is_explicit = False

    role_list = [r.strip() for r in roles.split(",")] if roles else []

    user = store.create_user(
        email=email,
        password=chosen_password,
        username=name,
        is_superuser=superuser,
        roles=role_list,
    )

    if output_json:
        data = _user_to_dict(user)
        if not is_explicit:
            data["temporary_password"] = chosen_password
        console.print_json(json.dumps(data))
    else:
        console.print(f"[green]User created:[/green] {user.email} (ID: {user.id})")
        if name:
            console.print(f"  Name: {name}")
        if role_list:
            console.print(f"  Roles: {', '.join(role_list)}")
        if superuser:
            console.print("  Superuser: yes")
        if is_explicit:
            console.print("  Password: set to provided value")
        else:
            console.print(f"  [yellow]Temporary password: {chosen_password}[/yellow]")
            console.print(
                "  Share this password securely. The user should change it on first login."
            )


@auth_app.command(name="list-users")
def list_users(
    role: Annotated[str | None, typer.Option("--role", "-r", help="Filter by role")] = None,
    include_inactive: Annotated[
        bool, typer.Option("--include-inactive", help="Include deactivated users")
    ] = False,
    limit: Annotated[int, typer.Option("--limit", "-l", help="Maximum users to return")] = 50,
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """List users in the auth database."""
    store = _get_auth_store()
    users = store.list_users(active_only=not include_inactive, role=role, limit=limit)

    if output_json:
        console.print_json(json.dumps([_user_to_dict(u) for u in users]))
        return

    if not users:
        console.print("[dim]No users found.[/dim]")
        return

    table = Table(title="Users")
    table.add_column("ID", style="dim", max_width=36)
    table.add_column("Email")
    table.add_column("Name")
    table.add_column("Roles")
    table.add_column("Active")
    table.add_column("Superuser")

    for user in users:
        table.add_row(
            str(user.id),
            user.email,
            user.username or "",
            ", ".join(user.roles) if user.roles else "",
            "[green]yes[/green]" if user.is_active else "[red]no[/red]",
            "yes" if user.is_superuser else "",
        )

    console.print(table)
    console.print(f"\n[dim]{len(users)} user(s) shown[/dim]")


@auth_app.command(name="get-user")
def get_user(
    identifier: Annotated[str, typer.Argument(help="User email or UUID")],
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Get detailed information about a user."""
    store = _get_auth_store()
    user = _resolve_user(store, identifier)

    if not user:
        console.print(f"[red]User not found: {identifier}[/red]")
        raise typer.Exit(1)

    session_count = store.count_active_sessions(user.id)

    if output_json:
        data = _user_to_dict(user)
        data["active_sessions"] = session_count
        console.print_json(json.dumps(data))
        return

    console.print("[bold]User Details[/bold]")
    console.print(f"  ID:              {user.id}")
    console.print(f"  Email:           {user.email}")
    console.print(f"  Name:            {user.username or '[dim]not set[/dim]'}")
    console.print(
        f"  Roles:           {', '.join(user.roles) if user.roles else '[dim]none[/dim]'}"
    )
    active_str = "[green]yes[/green]" if user.is_active else "[red]no[/red]"
    console.print(f"  Active:          {active_str}")
    console.print(f"  Superuser:       {'yes' if user.is_superuser else 'no'}")
    console.print(f"  Active sessions: {session_count}")
    console.print(f"  Created:         {user.created_at.isoformat()}")
    console.print(f"  Updated:         {user.updated_at.isoformat()}")


@auth_app.command(name="update-user")
def update_user(
    identifier: Annotated[str, typer.Argument(help="User email or UUID")],
    name: Annotated[str | None, typer.Option("--name", "-n", help="New display name")] = None,
    roles: Annotated[
        str | None,
        typer.Option("--roles", "-r", help="New comma-separated roles (replaces existing)"),
    ] = None,
    superuser: Annotated[
        bool | None, typer.Option("--superuser/--no-superuser", help="Set superuser status")
    ] = None,
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Update a user's properties."""
    store = _get_auth_store()
    user = _resolve_user(store, identifier)

    if not user:
        console.print(f"[red]User not found: {identifier}[/red]")
        raise typer.Exit(1)

    role_list = [r.strip() for r in roles.split(",")] if roles is not None else None

    updated = store.update_user(
        user_id=user.id,
        username=name,
        roles=role_list,
        is_superuser=superuser,
    )

    if not updated:
        console.print("[yellow]No updates provided.[/yellow]")
        raise typer.Exit(1)

    if output_json:
        console.print_json(json.dumps(_user_to_dict(updated)))
    else:
        console.print(f"[green]User updated:[/green] {updated.email}")
        if name is not None:
            console.print(f"  Name: {updated.username}")
        if role_list is not None:
            console.print(f"  Roles: {', '.join(updated.roles)}")
        if superuser is not None:
            console.print(f"  Superuser: {'yes' if updated.is_superuser else 'no'}")


@auth_app.command(name="reset-password")
def reset_password(
    identifier: Annotated[str, typer.Argument(help="User email or UUID")],
    password: Annotated[
        str | None,
        typer.Option("--password", "-p", help="Set an explicit password instead of generating one"),
    ] = None,
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Reset a user's password to a new generated or explicit password."""
    store = _get_auth_store()
    user = _resolve_user(store, identifier)

    if not user:
        console.print(f"[red]User not found: {identifier}[/red]")
        raise typer.Exit(1)

    if password is not None:
        if len(password) < _MIN_PASSWORD_LENGTH:
            console.print(f"[red]Password must be at least {_MIN_PASSWORD_LENGTH} characters[/red]")
            raise typer.Exit(1)
        new_password = password
        is_explicit = True
    else:
        new_password = _generate_temp_password()
        is_explicit = False

    store.update_password(user.id, new_password)
    revoked = store.delete_user_sessions(user.id)

    if output_json:
        result: dict[str, Any] = {
            "user_id": str(user.id),
            "email": user.email,
            "sessions_revoked": revoked,
        }
        if not is_explicit:
            result["temporary_password"] = new_password
        console.print_json(json.dumps(result))
    else:
        console.print(f"[green]Password reset for:[/green] {user.email}")
        if is_explicit:
            console.print("  Password: set to provided value")
        else:
            console.print(f"  [yellow]New temporary password: {new_password}[/yellow]")
        console.print(f"  Sessions revoked: {revoked}")
        if not is_explicit:
            console.print(
                "  Share this password securely. The user should change it on first login."
            )


@auth_app.command(name="deactivate")
def deactivate(
    identifier: Annotated[str, typer.Argument(help="User email or UUID")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Deactivate a user (soft delete)."""
    store = _get_auth_store()
    user = _resolve_user(store, identifier)

    if not user:
        console.print(f"[red]User not found: {identifier}[/red]")
        raise typer.Exit(1)

    if not user.is_active:
        console.print(f"[yellow]User '{user.email}' is already deactivated.[/yellow]")
        raise typer.Exit(1)

    if not yes:
        confirm = typer.confirm(f"Deactivate user '{user.email}'? This will revoke all sessions.")
        if not confirm:
            raise typer.Abort()

    store.update_user(user_id=user.id, is_active=False)
    revoked = store.delete_user_sessions(user.id)

    if output_json:
        console.print_json(
            json.dumps(
                {
                    "user_id": str(user.id),
                    "email": user.email,
                    "deactivated": True,
                    "sessions_revoked": revoked,
                }
            )
        )
    else:
        console.print(f"[green]User deactivated:[/green] {user.email}")
        console.print(f"  Sessions revoked: {revoked}")


@auth_app.command(name="list-sessions")
def list_sessions(
    user: Annotated[
        str | None, typer.Option("--user", "-u", help="Filter by user email or UUID")
    ] = None,
    include_expired: Annotated[
        bool, typer.Option("--include-expired", help="Include expired sessions")
    ] = False,
    limit: Annotated[int, typer.Option("--limit", "-l", help="Maximum sessions to return")] = 50,
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """List sessions in the auth database."""
    store = _get_auth_store()

    # Resolve user filter
    user_id_filter: str | None = None
    if user:
        resolved = _resolve_user(store, user)
        if not resolved:
            console.print(f"[red]User not found: {user}[/red]")
            raise typer.Exit(1)
        user_id_filter = str(resolved.id)

    rows = store.list_sessions(
        user_id=user_id_filter,
        active_only=not include_expired,
        limit=limit,
    )

    if output_json:
        console.print_json(json.dumps(rows))
        return

    if not rows:
        console.print("[dim]No sessions found.[/dim]")
        return

    table = Table(title="Sessions")
    table.add_column("ID", style="dim", max_width=20)
    table.add_column("User ID", style="dim", max_width=36)
    table.add_column("Created")
    table.add_column("Expires")
    table.add_column("IP Address")

    for row in rows:
        table.add_row(
            row["id"][:20] + "..." if len(row["id"]) > 20 else row["id"],
            row["user_id"],
            row["created_at"],
            row["expires_at"],
            row["ip_address"] or "",
        )

    console.print(table)
    console.print(f"\n[dim]{len(rows)} session(s) shown[/dim]")


@auth_app.command(name="cleanup-sessions")
def cleanup_sessions(
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Remove all expired sessions."""
    store = _get_auth_store()
    removed = store.cleanup_expired_sessions()

    if output_json:
        console.print_json(json.dumps({"removed": removed}))
    else:
        console.print(f"[green]Removed {removed} expired session(s).[/green]")


@auth_app.command(name="flush-sessions")
def flush_sessions(
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
    expired: Annotated[
        bool, typer.Option("--expired", help="Only remove expired sessions")
    ] = False,
    user: Annotated[
        str | None,
        typer.Option("--user", "-u", help="Flush sessions for specific user (email or UUID)"),
    ] = None,
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Flush sessions — all, expired only, or for a specific user."""
    store = _get_auth_store()

    if expired:
        deleted = store.cleanup_expired_sessions()
    elif user:
        resolved = _resolve_user(store, user)
        if not resolved:
            console.print(f"[red]User not found: {user}[/red]")
            raise typer.Exit(1)
        deleted = store.delete_user_sessions(resolved.id)
    else:
        if not yes:
            confirm = typer.confirm("Delete ALL sessions? Every user will be logged out.")
            if not confirm:
                raise typer.Abort()
        deleted = store.delete_all_sessions()

    if output_json:
        console.print_json(json.dumps({"deleted": deleted}))
    else:
        console.print(f"[green]Deleted {deleted} session(s).[/green]")


@auth_app.command(name="impersonate")
def impersonate(
    identifier: Annotated[str, typer.Argument(help="User email or UUID")],
    url: Annotated[
        bool, typer.Option("--url", help="Generate a one-time login URL instead of cookie")
    ] = False,
    ttl: Annotated[str, typer.Option("--ttl", help="Session/token TTL (e.g. 5m, 1h, 30s)")] = "30m",
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Generate a session or one-time login URL for any user."""
    import socket
    from datetime import timedelta

    from dazzle_back.runtime.auth.magic_link import create_magic_link

    store = _get_auth_store()
    user = _resolve_user(store, identifier)

    if not user:
        console.print(f"[red]User not found: {identifier}[/red]")
        raise typer.Exit(1)

    ttl_seconds = _parse_ttl(ttl)
    created_by = f"cli@{socket.gethostname()}"

    if url:
        token = create_magic_link(
            store, user_id=str(user.id), ttl_seconds=ttl_seconds, created_by=created_by
        )
        link = f"http://localhost:8000/_auth/magic/{token}"
        if output_json:
            console.print_json(
                json.dumps({"email": user.email, "magic_link": link, "ttl_seconds": ttl_seconds})
            )
        else:
            console.print(f"[green]Magic link for:[/green] {user.email}")
            console.print(f"  [yellow]{link}[/yellow]")
            console.print(f"  Expires in: {ttl}")
            console.print("  [dim]Single use — link is consumed on first visit.[/dim]")
    else:
        session = store.create_session(user, expires_in=timedelta(seconds=ttl_seconds))
        if output_json:
            console.print_json(
                json.dumps(
                    {
                        "email": user.email,
                        "session_id": session.id,
                        "cookie": f"dazzle_session={session.id}; Path=/; HttpOnly",
                        "ttl_seconds": ttl_seconds,
                    }
                )
            )
        else:
            console.print(f"[green]Session created for:[/green] {user.email}")
            console.print(f"  [yellow]Cookie: dazzle_session={session.id}[/yellow]")
            console.print(f"  Expires in: {ttl}")
            console.print(
                "  [dim]Paste in browser devtools or use: curl -b 'dazzle_session=...'[/dim]"
            )


@auth_app.command(name="rotate-passwords")
def rotate_passwords(
    all_users: Annotated[bool, typer.Option("--all", help="Rotate for all users")] = False,
    role: Annotated[
        str | None, typer.Option("--role", "-r", help="Rotate only for users with this role")
    ] = None,
    generate: Annotated[
        bool, typer.Option("--generate", "-g", help="Generate random passwords")
    ] = False,
    password: Annotated[
        str | None, typer.Option("--password", "-p", help="Set explicit password for all users")
    ] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Rotate passwords for multiple users at once."""
    if not all_users and not role:
        console.print("[red]Specify --all or --role to select users.[/red]")
        raise typer.Exit(1)
    if not generate and not password:
        console.print("[red]Specify --generate or --password.[/red]")
        raise typer.Exit(1)
    if generate and password:
        console.print("[red]Use --generate or --password, not both.[/red]")
        raise typer.Exit(1)
    if password and len(password) < _MIN_PASSWORD_LENGTH:
        console.print(f"[red]Password must be at least {_MIN_PASSWORD_LENGTH} characters.[/red]")
        raise typer.Exit(1)

    store = _get_auth_store()
    if role:
        users = store.list_users(role=role)
    else:
        users = store.list_users()

    if not users:
        console.print("[yellow]No matching users found.[/yellow]")
        raise typer.Exit(0)

    if not yes:
        confirm = typer.confirm(f"Rotate passwords for {len(users)} user(s)?")
        if not confirm:
            raise typer.Abort()

    results: list[dict[str, Any]] = []
    for user in users:
        new_pw = _generate_temp_password() if generate else password
        store.update_password(user.id, new_pw)
        revoked = store.delete_user_sessions(user.id)
        entry: dict[str, Any] = {"email": user.email, "sessions_revoked": revoked}
        if generate:
            entry["password"] = new_pw
        results.append(entry)

    if output_json:
        console.print_json(json.dumps({"rotated": len(results), "users": results}))
    else:
        table = Table(title=f"Rotated {len(results)} password(s)")
        table.add_column("Email")
        if generate:
            table.add_column("New Password")
        table.add_column("Sessions Revoked")
        for r in results:
            row = [r["email"]]
            if generate:
                row.append(r["password"])
            row.append(str(r["sessions_revoked"]))
            table.add_row(*row)
        console.print(table)


@auth_app.command(name="config")
def config(
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Show authentication system configuration and status."""
    store = _get_auth_store()

    total_users = store.count_users()
    active_users = store.count_users(active_only=True)
    active_sessions = store.count_active_sessions()
    roles_in_use = store.list_distinct_roles()

    db_type = "postgresql"
    db_path = "[PostgreSQL]"

    if output_json:
        console.print_json(
            json.dumps(
                {
                    "database_type": db_type,
                    "database_path": db_path,
                    "total_users": total_users,
                    "active_users": active_users,
                    "active_sessions": active_sessions,
                    "roles_in_use": roles_in_use,
                }
            )
        )
    else:
        console.print("[bold]Auth Configuration[/bold]")
        console.print(f"  Database type:    {db_type}")
        console.print(f"  Database path:    {db_path}")
        console.print(f"  Total users:      {total_users}")
        console.print(f"  Active users:     {active_users}")
        console.print(f"  Active sessions:  {active_sessions}")
        roles_str = ", ".join(roles_in_use) if roles_in_use else "[dim]none[/dim]"
        console.print(f"  Roles in use:     {roles_str}")
