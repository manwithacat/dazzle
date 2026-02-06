"""
MCP handlers for user management.

Provides tools for LLM agents to create, list, update, and manage users
in Dazzle applications. Supports both SQLite and PostgreSQL backends.

User data is stored in:
- .dazzle/auth.db (SQLite, default for local development)
- DATABASE_URL (PostgreSQL, for production deployments)
"""

from __future__ import annotations

import os
import secrets
import string
from pathlib import Path
from typing import Any
from uuid import UUID

from ..state import get_project_path


def _generate_temp_password(length: int = 16) -> str:
    """Generate a secure temporary password."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _get_auth_store(project_path: Path | None = None) -> Any:
    """
    Get an AuthStore instance for the project.

    Checks for DATABASE_URL environment variable first (PostgreSQL),
    falls back to .dazzle/auth.db (SQLite).
    """
    from dazzle_back.runtime.auth import AuthStore

    if project_path is None:
        project_path = get_project_path()
        if not project_path:
            raise ValueError("No active project. Select a project first.")

    # Check for PostgreSQL URL in environment
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        return AuthStore(database_url=database_url)

    # Fall back to SQLite
    db_path = project_path / ".dazzle" / "auth.db"
    return AuthStore(db_path=db_path)


def _user_to_dict(user: Any, include_hash: bool = False) -> dict[str, Any]:
    """Convert UserRecord to dict for JSON serialization."""
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


def _session_to_dict(session: Any) -> dict[str, Any]:
    """Convert SessionRecord to dict for JSON serialization."""
    return {
        "id": session.id,
        "user_id": str(session.user_id),
        "created_at": session.created_at.isoformat(),
        "expires_at": session.expires_at.isoformat(),
        "ip_address": session.ip_address,
        "user_agent": session.user_agent,
    }


async def list_users_handler(
    role: str | None = None,
    active_only: bool = True,
    limit: int = 50,
    offset: int = 0,
    project_path: str | None = None,
) -> dict[str, Any]:
    """
    List users in the auth database.

    Args:
        role: Filter by role (e.g., "admin", "manager")
        active_only: Only return active users (default: True)
        limit: Maximum users to return (default: 50)
        offset: Number of users to skip for pagination
        project_path: Optional project path override

    Returns:
        List of users with id, email, username, roles, is_active, created_at
    """
    path = Path(project_path) if project_path else None
    auth_store = _get_auth_store(path)

    users = auth_store.list_users(active_only=active_only, role=role, limit=limit, offset=offset)

    return {
        "count": len(users),
        "users": [_user_to_dict(u) for u in users],
        "filters": {
            "role": role,
            "active_only": active_only,
            "limit": limit,
            "offset": offset,
        },
    }


async def create_user_handler(
    email: str,
    name: str | None = None,
    roles: list[str] | None = None,
    is_superuser: bool = False,
    project_path: str | None = None,
) -> dict[str, Any]:
    """
    Create a new user with a generated temporary password.

    The password is randomly generated and returned only once.
    Share it securely with the user and instruct them to change it.

    Args:
        email: User's email address (must be unique)
        name: User's display name (optional)
        roles: List of roles to assign (e.g., ["admin"], ["manager", "agent"])
        is_superuser: Whether user has superuser privileges
        project_path: Optional project path override

    Returns:
        Created user details including the temporary password (shown only once)
    """
    path = Path(project_path) if project_path else None
    auth_store = _get_auth_store(path)

    # Check if user already exists
    existing = auth_store.get_user_by_email(email)
    if existing:
        return {
            "success": False,
            "error": f"User with email '{email}' already exists",
            "existing_user_id": str(existing.id),
        }

    # Generate temporary password
    temp_password = _generate_temp_password()

    # Create user
    user = auth_store.create_user(
        email=email,
        password=temp_password,
        username=name,
        is_superuser=is_superuser,
        roles=roles or [],
    )

    return {
        "success": True,
        "user": _user_to_dict(user),
        "temporary_password": temp_password,
        "message": "User created. Share the temporary password securely and instruct them to change it on first login.",
    }


async def get_user_handler(
    user_id: str | None = None,
    email: str | None = None,
    project_path: str | None = None,
) -> dict[str, Any]:
    """
    Get a user by ID or email.

    Args:
        user_id: User's UUID (provide either this or email)
        email: User's email address (provide either this or user_id)
        project_path: Optional project path override

    Returns:
        User details including active sessions count
    """
    if not user_id and not email:
        return {"error": "Must provide either user_id or email"}

    path = Path(project_path) if project_path else None
    auth_store = _get_auth_store(path)

    user = None
    if user_id:
        user = auth_store.get_user_by_id(UUID(user_id))
    elif email:
        user = auth_store.get_user_by_email(email)

    if not user:
        return {
            "found": False,
            "error": f"User not found: {user_id or email}",
        }

    # Count active sessions
    session_count = auth_store.count_active_sessions(user.id)

    return {
        "found": True,
        "user": _user_to_dict(user),
        "active_sessions": session_count,
    }


async def update_user_handler(
    user_id: str,
    username: str | None = None,
    roles: list[str] | None = None,
    is_active: bool | None = None,
    is_superuser: bool | None = None,
    project_path: str | None = None,
) -> dict[str, Any]:
    """
    Update a user's properties.

    Args:
        user_id: User's UUID
        username: New display name (optional)
        roles: New roles list - replaces existing roles (optional)
        is_active: Set active status (optional)
        is_superuser: Set superuser status (optional)
        project_path: Optional project path override

    Returns:
        Updated user details
    """
    path = Path(project_path) if project_path else None
    auth_store = _get_auth_store(path)

    user = auth_store.get_user_by_id(UUID(user_id))
    if not user:
        return {
            "success": False,
            "error": f"User not found: {user_id}",
        }

    updated_user = auth_store.update_user(
        user_id=UUID(user_id),
        username=username,
        roles=roles,
        is_active=is_active,
        is_superuser=is_superuser,
    )

    if not updated_user:
        return {
            "success": False,
            "error": "No updates provided",
        }

    return {
        "success": True,
        "user": _user_to_dict(updated_user),
        "changes": {
            "username": username,
            "roles": roles,
            "is_active": is_active,
            "is_superuser": is_superuser,
        },
    }


async def reset_password_handler(
    user_id: str,
    project_path: str | None = None,
) -> dict[str, Any]:
    """
    Reset a user's password to a new temporary password.

    Generates a new random password and invalidates all existing sessions.

    Args:
        user_id: User's UUID
        project_path: Optional project path override

    Returns:
        New temporary password (shown only once) and session revocation count
    """
    path = Path(project_path) if project_path else None
    auth_store = _get_auth_store(path)

    user = auth_store.get_user_by_id(UUID(user_id))
    if not user:
        return {
            "success": False,
            "error": f"User not found: {user_id}",
        }

    # Generate new password
    new_password = _generate_temp_password()

    # Update password
    auth_store.update_password(UUID(user_id), new_password)

    # Revoke all sessions for security
    revoked_count = auth_store.delete_user_sessions(UUID(user_id))

    return {
        "success": True,
        "user_id": user_id,
        "email": user.email,
        "temporary_password": new_password,
        "sessions_revoked": revoked_count,
        "message": "Password reset. Share the new password securely. All existing sessions have been revoked.",
    }


async def deactivate_user_handler(
    user_id: str,
    project_path: str | None = None,
) -> dict[str, Any]:
    """
    Deactivate a user (soft delete).

    Sets is_active=False and revokes all sessions. The user record is preserved
    but they cannot log in.

    Args:
        user_id: User's UUID
        project_path: Optional project path override

    Returns:
        Deactivation confirmation and session revocation count
    """
    path = Path(project_path) if project_path else None
    auth_store = _get_auth_store(path)

    user = auth_store.get_user_by_id(UUID(user_id))
    if not user:
        return {
            "success": False,
            "error": f"User not found: {user_id}",
        }

    if not user.is_active:
        return {
            "success": False,
            "error": f"User is already deactivated: {user.email}",
        }

    # Deactivate
    auth_store.update_user(user_id=UUID(user_id), is_active=False)

    # Revoke all sessions
    revoked_count = auth_store.delete_user_sessions(UUID(user_id))

    return {
        "success": True,
        "user_id": user_id,
        "email": user.email,
        "sessions_revoked": revoked_count,
        "message": f"User '{user.email}' has been deactivated. They can no longer log in.",
    }


async def list_sessions_handler(
    user_id: str | None = None,
    active_only: bool = True,
    limit: int = 50,
    project_path: str | None = None,
) -> dict[str, Any]:
    """
    List sessions, optionally filtered by user.

    Args:
        user_id: Filter to sessions for this user (optional)
        active_only: Only return non-expired sessions (default: True)
        limit: Maximum sessions to return
        project_path: Optional project path override

    Returns:
        List of sessions with user info
    """
    path = Path(project_path) if project_path else None
    auth_store = _get_auth_store(path)

    conditions = []
    params: list[Any] = []

    if user_id:
        conditions.append("user_id = ?")
        params.append(user_id)

    if active_only:
        conditions.append("expires_at > datetime('now')")

    where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"SELECT * FROM sessions{where_clause} ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    rows = auth_store._execute(query, tuple(params))

    sessions = []
    for row in rows:
        session = {
            "id": row["id"],
            "user_id": row["user_id"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
            "ip_address": row["ip_address"],
            "user_agent": row["user_agent"],
        }
        sessions.append(session)

    return {
        "count": len(sessions),
        "sessions": sessions,
        "filters": {
            "user_id": user_id,
            "active_only": active_only,
            "limit": limit,
        },
    }


async def revoke_session_handler(
    session_id: str,
    project_path: str | None = None,
) -> dict[str, Any]:
    """
    Revoke a specific session (logout).

    Args:
        session_id: Session ID to revoke
        project_path: Optional project path override

    Returns:
        Revocation confirmation
    """
    path = Path(project_path) if project_path else None
    auth_store = _get_auth_store(path)

    # Check if session exists
    session = auth_store.get_session(session_id)
    if not session:
        return {
            "success": False,
            "error": f"Session not found: {session_id}",
        }

    # Delete session
    auth_store.delete_session(session_id)

    return {
        "success": True,
        "session_id": session_id,
        "user_id": str(session.user_id),
        "message": "Session has been revoked.",
    }


async def get_auth_config_handler(
    project_path: str | None = None,
) -> dict[str, Any]:
    """
    Get authentication system configuration and status.

    Args:
        project_path: Optional project path override

    Returns:
        Auth configuration including database type, user count, session count
    """
    path = Path(project_path) if project_path else None
    auth_store = _get_auth_store(path)

    # Get counts
    user_count = auth_store._execute("SELECT COUNT(*) as count FROM users")
    active_user_count = auth_store._execute(
        f"SELECT COUNT(*) as count FROM users WHERE is_active = {auth_store._bool_to_db(True)}"
    )
    session_count = auth_store._execute(
        "SELECT COUNT(*) as count FROM sessions WHERE expires_at > datetime('now')"
    )

    # Get roles in use
    roles_result = auth_store._execute("SELECT DISTINCT roles FROM users")
    import json

    all_roles: set[str] = set()
    for row in roles_result:
        roles = json.loads(row["roles"]) if row["roles"] else []
        all_roles.update(roles)

    return {
        "database_type": "postgresql" if auth_store._use_postgres else "sqlite",
        "database_path": ("[PostgreSQL]" if auth_store._use_postgres else str(auth_store.db_path)),
        "total_users": user_count[0]["count"] if user_count else 0,
        "active_users": active_user_count[0]["count"] if active_user_count else 0,
        "active_sessions": session_count[0]["count"] if session_count else 0,
        "roles_in_use": sorted(all_roles),
    }
