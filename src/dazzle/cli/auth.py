"""
Authentication management commands for DAZZLE CLI.

Manage users and sessions directly against the auth database
(PostgreSQL) without requiring a running server.
"""

from __future__ import annotations

import json
import os
import secrets
import string
from datetime import UTC, datetime
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
    global _database_url_override
    _database_url_override = database_url


def _get_auth_store(database_url: str | None = None) -> Any:
    """Get an AuthStore instance. Requires PostgreSQL via DATABASE_URL."""
    from dazzle_back.runtime.auth import AuthStore

    url = database_url or _database_url_override or os.environ.get("DATABASE_URL")
    if not url:
        url = "postgresql://localhost:5432/dazzle"
    return AuthStore(database_url=url)


def _generate_temp_password(length: int = 16) -> str:
    """Generate a secure temporary password."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


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

    # Build query
    conditions: list[str] = []
    params: list[Any] = []

    if user_id_filter:
        conditions.append("user_id = ?")
        params.append(user_id_filter)

    if not include_expired:
        conditions.append("expires_at > ?")
        params.append(datetime.now(UTC).isoformat())

    where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"SELECT * FROM sessions{where_clause} ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    rows = store._execute(query, tuple(params))

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


@auth_app.command(name="config")
def config(
    output_json: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Show authentication system configuration and status."""
    store = _get_auth_store()

    # Counts
    user_rows = store._execute("SELECT COUNT(*) as count FROM users")
    total_users = user_rows[0]["count"] if user_rows else 0

    active_rows = store._execute(
        f"SELECT COUNT(*) as count FROM users WHERE is_active = {store._bool_to_db(True)}"
    )
    active_users = active_rows[0]["count"] if active_rows else 0

    session_rows = store._execute(
        "SELECT COUNT(*) as count FROM sessions WHERE expires_at > ?",
        (datetime.now(UTC).isoformat(),),
    )
    active_sessions = session_rows[0]["count"] if session_rows else 0

    # Roles in use
    roles_result = store._execute("SELECT DISTINCT roles FROM users")
    all_roles: set[str] = set()
    for row in roles_result:
        parsed = json.loads(row["roles"]) if row["roles"] else []
        all_roles.update(parsed)

    db_type = "postgresql" if store._use_postgres else "sqlite"
    db_path = "[PostgreSQL]" if store._use_postgres else str(store.db_path)

    if output_json:
        console.print_json(
            json.dumps(
                {
                    "database_type": db_type,
                    "database_path": db_path,
                    "total_users": total_users,
                    "active_users": active_users,
                    "active_sessions": active_sessions,
                    "roles_in_use": sorted(all_roles),
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
        roles_str = ", ".join(sorted(all_roles)) if all_roles else "[dim]none[/dim]"
        console.print(f"  Roles in use:     {roles_str}")
