"""CLI-facing auth service wrapping AuthStore."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID


class AuthService:
    """Thin wrapper around AuthStore for CLI usage.

    Centralizes database URL resolution and provides a clean
    interface for CLI auth commands.
    """

    def __init__(self, db_url: str) -> None:
        from dazzle_back.runtime.auth import AuthStore

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

        url = resolve_database_url(manifest, explicit_url=explicit)
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
        return self._store.list_users(active_only=active_only, role=role, limit=limit)

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
        return self._store.update_password(user_id, new_password)

    # ----- Sessions -----

    def count_active_sessions(self, user_id: UUID) -> int:
        """Count active (non-expired) sessions for a user."""
        return self._store.count_active_sessions(user_id)

    def delete_user_sessions(self, user_id: UUID) -> int:
        """Delete all sessions for a user. Returns count of deleted sessions."""
        return self._store.delete_user_sessions(user_id)

    def cleanup_expired_sessions(self) -> int:
        """Delete all expired sessions. Returns count removed."""
        return self._store.cleanup_expired_sessions()

    # ----- Raw SQL (for queries not covered by AuthStore API) -----

    def execute_raw(self, query: str, params: tuple[object, ...] = ()) -> list[dict[str, Any]]:
        """Execute a raw SQL query against the auth database.

        Used by CLI commands that need direct DB access (e.g. session listing,
        config/stats queries) where AuthStore doesn't expose a dedicated method.
        """
        return self._store._execute(query, params)
