"""CLI-facing auth service wrapping AuthStore."""

from __future__ import annotations  # required: forward reference

from pathlib import Path
from typing import Any
from uuid import UUID


class AuthService:
    """Thin wrapper around AuthStore for CLI usage.

    Centralizes database URL resolution and provides a clean
    interface for CLI auth commands.
    """

    def __init__(self, db_url: str) -> None:
        from dazzle_back import AuthStore

        self._store = AuthStore(database_url=db_url)

    @classmethod
    def from_manifest(
        cls, database_url_override: str | None = None, manifest_path: Path | None = None
    ) -> AuthService:
        """Create an AuthService resolving the database URL from manifest/env.

        Resolution order: explicit override -> dazzle.toml -> env -> default.
        """
        from dazzle.core.manifest import load_manifest, resolve_database_url

        explicit = database_url_override or ""
        manifest = None
        mpath = manifest_path or Path("dazzle.toml").resolve()
        if mpath.exists():
            manifest = load_manifest(mpath)

        from dazzle.cli.env import get_active_env

        url = resolve_database_url(manifest, explicit_url=explicit, env_name=get_active_env())
        return cls(url)

    # ----- User CRUD -----

    def create_user(
        self,
        email: str,
        password: str,
        username: str | None = None,
        is_superuser: bool = False,
        roles: list[str] | None = None,
    ) -> Any:
        """Create a new user. Returns UserRecord."""
        return self._store.create_user(
            email=email,
            password=password,
            username=username,
            is_superuser=is_superuser,
            roles=roles,
        )

    def get_user_by_email(self, email: str) -> Any | None:
        """Get a user by email. Returns UserRecord or None."""
        return self._store.get_user_by_email(email)

    def get_user_by_id(self, user_id: UUID) -> Any | None:
        """Get a user by UUID. Returns UserRecord or None."""
        return self._store.get_user_by_id(user_id)

    def list_users(
        self,
        active_only: bool = True,
        role: str | None = None,
        limit: int = 50,
    ) -> list[Any]:
        """List users with optional filters."""
        result: list[Any] = self._store.list_users(active_only=active_only, role=role, limit=limit)
        return result

    def update_user(
        self,
        user_id: UUID,
        username: str | None = None,
        roles: list[str] | None = None,
        is_active: bool | None = None,
        is_superuser: bool | None = None,
    ) -> Any | None:
        """Update user properties. Returns updated UserRecord or None."""
        return self._store.update_user(
            user_id=user_id,
            username=username,
            roles=roles,
            is_active=is_active,
            is_superuser=is_superuser,
        )

    # ----- Password -----

    def update_password(self, user_id: UUID, new_password: str) -> bool:
        """Update a user's password."""
        result: bool = self._store.update_password(user_id, new_password)
        return result

    # ----- Sessions -----

    def count_active_sessions(self, user_id: UUID | None = None) -> int:
        """Count active (non-expired) sessions.

        If *user_id* is provided, count only that user's sessions.
        If omitted, count all active sessions across all users.
        """
        result: int = self._store.count_active_sessions(user_id)
        return result

    def delete_user_sessions(self, user_id: UUID) -> int:
        """Delete all sessions for a user. Returns count of deleted sessions."""
        result: int = self._store.delete_user_sessions(user_id)
        return result

    def cleanup_expired_sessions(self) -> int:
        """Delete all expired sessions. Returns count removed."""
        result: int = self._store.cleanup_expired_sessions()
        return result

    # ----- Aggregate / stats -----

    def count_users(self, active_only: bool = False) -> int:
        """Return total (or active-only) user count."""
        return self._store.count_users(active_only=active_only)

    def list_distinct_roles(self) -> list[str]:
        """Return sorted list of all distinct role names in use."""
        return self._store.list_distinct_roles()

    # ----- Session listing -----

    def list_sessions(
        self,
        user_id: str | None = None,
        active_only: bool = True,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return raw session rows, optionally filtered by user."""
        return self._store.list_sessions(user_id=user_id, active_only=active_only, limit=limit)
