"""Authentication store (PostgreSQL) — user CRUD, sessions, and 2FA state."""

import logging
import secrets
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from dazzle.http.runtime.auth.connections import (
        ConnectionRecord,
        ConnectionSecretEvent,
        RewrapResult,
    )
    from dazzle.http.runtime.auth.membership_events import (
        EventChainResult,
        MembershipEvent,
    )
    from dazzle.http.runtime.auth.models import ScimGroupRecord

try:
    import psycopg
    from psycopg.rows import dict_row

    PSYCOPG_AVAILABLE = True
except ImportError:
    psycopg = None  # type: ignore[assignment]
    dict_row = None  # type: ignore[assignment]
    PSYCOPG_AVAILABLE = False

from dazzle.core.db_url import normalise_postgres_scheme

from .crypto import hash_password, verify_password
from .models import (
    AlreadyDecidedError,
    AuthContext,
    JoinRequestRecord,
    MembershipRecord,
    OrganizationRecord,
    SessionRecord,
    UserRecord,
)

logger = logging.getLogger(__name__)

# #1363: serializes auth-store boot DDL across uvicorn workers. Postgres's
# `CREATE INDEX IF NOT EXISTS` existence-check and the pg_class catalog
# insert are not atomic across sessions, so concurrently cold-booting
# workers can both pass the check and the loser dies with
# `UniqueViolation: pg_class_relname_nsp_index`. Same hex-named
# advisory-lock convention as MEMBERSHIP_EVENTS_LOCK_KEY /
# CONNECTION_DOMAIN_LOCK_KEY. ("dzdl" = dazzle DDL.)
AUTH_DDL_LOCK_KEY = 0x647A646C


def _normalize_email(email: str) -> str:
    """Canonical form for an auth identity email: trimmed + lowercased (#1342 M2).

    The store is the single normalization chokepoint so the case-insensitive identity
    invariant holds regardless of whether a caller remembered to lowercase. The
    ``users_email_lower_key`` functional index is the structural backstop for raw-SQL
    paths that bypass these methods."""
    return (email or "").strip().lower()


def _appspec_has_tenant_root(appspec: Any) -> bool:
    """True iff the appspec declares an ``is_tenant_root`` / archetype:tenant
    entity (auth Plan 1d — selects the 1:1 org<->root mirror provisioning)."""
    for e in getattr(getattr(appspec, "domain", None), "entities", []) or []:
        if getattr(e, "is_tenant_root", False):
            return True
        if getattr(getattr(e, "archetype_kind", None), "name", "") == "TENANT":
            return True
    return False


class UserStoreMixin:
    """User CRUD, password management, and password reset tokens."""

    # These methods are provided by AuthStore.__init__ via mixin composition.
    _execute: Any
    _execute_one: Any
    _execute_modify: Any
    # ADR-0039 (#778/#1398): optional domain-`User` provisioning hook, set by the server
    # at build time when the app declares an `auth_identity:` bridge. None = no mirror.
    _on_user_created: "Callable[[UserRecord], None] | None" = None

    def create_user(
        self,
        email: str,
        password: str,
        username: str | None = None,
        is_superuser: bool = False,
        roles: list[str] | None = None,
    ) -> UserRecord:
        """
        Create a new user.

        Args:
            email: User email
            password: Plain text password
            username: Optional username
            is_superuser: Is superuser flag
            roles: List of role names

        Returns:
            Created user record
        """
        import json

        user = UserRecord(
            email=_normalize_email(email),  # canonical-lowercase storage (#1342 M2)
            password_hash=hash_password(password),
            username=username,
            is_superuser=is_superuser,
            roles=roles or [],
        )

        self._execute(
            """
            INSERT INTO users (id, email, password_hash, username, is_active,
                               is_superuser, roles, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(user.id),
                user.email,
                user.password_hash,
                user.username,
                user.is_active,
                user.is_superuser,
                json.dumps(user.roles),
                user.created_at.isoformat(),
                user.updated_at.isoformat(),
            ),
        )

        # ADR-0039 (#778/#1398): provision the DSL `User` domain row for this principal
        # when the app declares an `auth_identity:` bridge. The hook is set by the server
        # at build time; absent (or no binding) ⇒ no-op. This is the single production
        # choke point all auth-user creation funnels through (magic-link signup, SSO JIT,
        # password signup, SCIM …). Best-effort — never break auth-user creation (D1).
        hook = getattr(self, "_on_user_created", None)
        if hook is not None:
            try:
                hook(user)
            except Exception:
                logger.warning(
                    "domain-User provisioning hook failed for %s", user.id, exc_info=True
                )

        return user

    def _row_to_user(self, row: dict[str, Any]) -> UserRecord:
        """Convert a database row to UserRecord."""
        import json

        return UserRecord(
            id=UUID(row["id"]),
            email=row["email"],
            password_hash=row["password_hash"],
            username=row["username"],
            is_active=bool(row["is_active"]),
            is_superuser=bool(row["is_superuser"]),
            roles=json.loads(row["roles"]),
            totp_secret=row.get("totp_secret"),
            totp_enabled=bool(row.get("totp_enabled", False)),
            email_otp_enabled=bool(row.get("email_otp_enabled", False)),
            recovery_codes_generated=bool(row.get("recovery_codes_generated", False)),
            email_verified=bool(row.get("email_verified", False)),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def get_user_by_email(self, email: str) -> UserRecord | None:
        """Get user by email. Case-insensitive: the argument is normalized to the canonical
        (trimmed + lowercased) form so any-case input resolves the same identity (#1342 M2)."""
        row = self._execute_one("SELECT * FROM users WHERE email = %s", (_normalize_email(email),))
        return self._row_to_user(row) if row else None

    def get_user_by_id(self, user_id: UUID) -> UserRecord | None:
        """Get user by ID."""
        row = self._execute_one("SELECT * FROM users WHERE id = %s", (str(user_id),))
        return self._row_to_user(row) if row else None

    def authenticate(self, email: str, password: str) -> UserRecord | None:
        """
        Authenticate user by email and password.

        Returns user if credentials are valid, None otherwise.
        """
        user = self.get_user_by_email(email)

        if user and user.is_active and verify_password(password, user.password_hash):
            return user

        return None

    def mark_email_verified(self, user_id: str | UUID) -> bool:
        """Flip ``email_verified=true`` for ``user_id``.

        Idempotent — if the row is already verified, the UPDATE is a
        no-op (PostgreSQL still reports 1 affected row because the
        WHERE matched). Returns True iff a row was touched (i.e. the
        user exists). Bookkeeping for the audit trail lives at the
        route layer via ``emit_user_email_verified``.
        """
        rowcount: int = self._execute_modify(
            "UPDATE users SET email_verified = TRUE, updated_at = %s WHERE id = %s",
            (datetime.now(UTC).isoformat(), str(user_id)),
        )
        return rowcount > 0

    def update_password(self, user_id: UUID, new_password: str) -> bool:
        """Update user password."""
        rowcount = self._execute_modify(
            """
            UPDATE users
            SET password_hash = %s, updated_at = %s
            WHERE id = %s
            """,
            (hash_password(new_password), datetime.now(UTC).isoformat(), str(user_id)),
        )
        return bool(rowcount > 0)

    def create_password_reset_token(
        self,
        user_id: UUID,
        expires_in: timedelta | None = None,
    ) -> str:
        """Create a password reset token for the given user.

        Args:
            user_id: User to create reset token for.
            expires_in: Token lifetime (default 1 hour).

        Returns:
            The generated token string.
        """
        if expires_in is None:
            expires_in = timedelta(hours=1)

        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        expires_at = now + expires_in

        # Invalidate any existing unused tokens for this user
        self._execute_modify(
            "UPDATE password_reset_tokens SET used = TRUE WHERE user_id = %s AND used = FALSE",
            (str(user_id),),
        )

        self._execute_modify(
            """
            INSERT INTO password_reset_tokens (token, user_id, created_at, expires_at, used)
            VALUES (%s, %s, %s, %s, FALSE)
            """,
            (token, str(user_id), now.isoformat(), expires_at.isoformat()),
        )

        return token

    def validate_password_reset_token(self, token: str) -> UserRecord | None:
        """Validate a password reset token and return the associated user.

        Returns None if the token is invalid, expired, or already used.
        """
        rows = self._execute(
            "SELECT * FROM password_reset_tokens WHERE token = %s",
            (token,),
        )

        if not rows:
            return None

        row = rows[0]
        if row.get("used") is True:
            return None

        expires_at = datetime.fromisoformat(row["expires_at"])
        if datetime.now(UTC) > expires_at:
            return None

        user_id = UUID(row["user_id"])
        return self.get_user_by_id(user_id)

    def consume_password_reset_token(self, token: str) -> bool:
        """Mark a password reset token as used.

        Returns True if the token was successfully consumed.
        """
        rowcount = self._execute_modify(
            "UPDATE password_reset_tokens SET used = TRUE WHERE token = %s AND used = FALSE",
            (token,),
        )
        return bool(rowcount > 0)

    def list_users(
        self,
        active_only: bool = True,
        role: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[UserRecord]:
        """
        List users with optional filters.

        Args:
            active_only: Only return active users
            role: Filter by role (Python-side, checks JSON roles array)
            limit: Maximum users to return
            offset: Number of users to skip for pagination

        Returns:
            List of matching UserRecord objects
        """
        conditions: list[str] = []
        params: list[object] = []

        if active_only:
            conditions.append("is_active = TRUE")

        where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT * FROM users{where_clause} ORDER BY created_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        rows = self._execute(query, tuple(params))

        users = []
        for row in rows:
            user = self._row_to_user(row)
            if role and role not in user.roles:
                continue
            users.append(user)

        return users

    def update_user(
        self,
        user_id: UUID,
        username: str | None = None,
        roles: list[str] | None = None,
        is_active: bool | None = None,
        is_superuser: bool | None = None,
    ) -> UserRecord | None:
        """
        Update a user's properties.

        Args:
            user_id: User UUID
            username: New display name
            roles: New roles list (replaces existing)
            is_active: Set active status
            is_superuser: Set superuser status

        Returns:
            Updated UserRecord, or None if user not found or no updates provided
        """
        import json

        updates: list[str] = []
        params: list[object] = []

        if username is not None:
            updates.append("username = %s")
            params.append(username)

        if roles is not None:
            updates.append("roles = %s")
            params.append(json.dumps(roles))

        if is_active is not None:
            updates.append("is_active = %s")
            params.append(is_active)

        if is_superuser is not None:
            updates.append("is_superuser = %s")
            params.append(is_superuser)

        if not updates:
            return None

        updates.append("updated_at = %s")
        params.append(datetime.now(UTC).isoformat())
        params.append(str(user_id))

        query = f"UPDATE users SET {', '.join(updates)} WHERE id = %s"
        rowcount = self._execute_modify(query, tuple(params))

        if rowcount == 0:
            return None

        return self.get_user_by_id(user_id)


class TwoFactorMixin:
    """Two-factor authentication state management."""

    _execute: Any
    _execute_one: Any
    _execute_modify: Any
    get_user_by_id: Any

    def enable_totp(self, user_id: UUID, secret: str) -> None:
        """Enable TOTP for a user and store the encrypted secret.

        Args:
            user_id: User UUID
            secret: Base32-encoded TOTP secret
        """
        self._execute_modify(
            "UPDATE users SET totp_secret = %s, totp_enabled = TRUE, updated_at = %s WHERE id = %s",
            (secret, datetime.now(UTC).isoformat(), str(user_id)),
        )

    def disable_totp(self, user_id: UUID) -> None:
        """Disable TOTP for a user and clear the secret."""
        self._execute_modify(
            "UPDATE users SET totp_secret = NULL, totp_enabled = FALSE, updated_at = %s "
            "WHERE id = %s",
            (datetime.now(UTC).isoformat(), str(user_id)),
        )

    def enable_email_otp(self, user_id: UUID) -> None:
        """Enable email OTP for a user."""
        self._execute_modify(
            "UPDATE users SET email_otp_enabled = TRUE, updated_at = %s WHERE id = %s",
            (datetime.now(UTC).isoformat(), str(user_id)),
        )

    def disable_email_otp(self, user_id: UUID) -> None:
        """Disable email OTP for a user."""
        self._execute_modify(
            "UPDATE users SET email_otp_enabled = FALSE, updated_at = %s WHERE id = %s",
            (datetime.now(UTC).isoformat(), str(user_id)),
        )

    def set_recovery_codes_generated(self, user_id: UUID, generated: bool = True) -> None:
        """Mark whether recovery codes have been generated for a user."""
        self._execute_modify(
            "UPDATE users SET recovery_codes_generated = %s, updated_at = %s WHERE id = %s",
            (generated, datetime.now(UTC).isoformat(), str(user_id)),
        )

    def get_totp_secret(self, user_id: UUID) -> str | None:
        """Get the TOTP secret for a user.

        Args:
            user_id: User UUID

        Returns:
            Base32-encoded TOTP secret or None
        """
        row = self._execute_one("SELECT totp_secret FROM users WHERE id = %s", (str(user_id),))
        return row["totp_secret"] if row else None


class SessionStoreMixin:
    """Session lifecycle, validation, and cleanup."""

    # These methods are provided by AuthStore.__init__ via mixin composition.
    _execute: Any
    _execute_one: Any
    _execute_modify: Any
    _get_connection: Any  # auth Plan 2a — used by _transaction / chain verify
    _transaction: Any  # auth Plan 2a — atomic mutation + lifecycle event
    _user_entity_table: str  # Set by AuthStore.__init__

    # Cross-cutting method provided by UserStoreMixin via AuthStore.
    get_user_by_id: Any

    def _load_domain_user_attributes(self, email: str) -> dict[str, str]:
        """Look up the DSL User entity record by email and return scalar fields.

        Returns a dict of field_name -> string value for all non-null scalar
        columns. These are merged into preferences so scope rules referencing
        ``current_user.<attr>`` can resolve domain attributes like ``school``,
        ``department``, ``trust`` that live on the DSL entity, not the auth
        UserRecord (#532).
        """
        if not self._user_entity_table:
            return {}
        try:
            from dazzle.http.runtime.query_builder import quote_identifier

            table = quote_identifier(self._user_entity_table)
            rows = self._execute(
                f"SELECT * FROM {table} WHERE email = %s LIMIT 1",  # nosemgrep
                (email,),
            )
        except Exception:
            logger.warning("user_attributes lookup failed", exc_info=True)
            return {}
        if not rows:
            return {}
        row = rows[0]
        _SKIP = {"id", "email", "password", "password_hash", "hashed_password"}
        result: dict[str, str] = {}
        for k, v in row.items():
            if k in _SKIP or v is None:
                continue
            from uuid import UUID as _UUID

            if isinstance(v, str | int | float | bool | _UUID):
                result[k] = str(v)
        # Store the domain entity ID as "entity_id" so via clauses can
        # resolve current_user to the DSL User entity PK (#534).
        domain_id = row.get("id")
        if domain_id is not None:
            result["entity_id"] = str(domain_id)
        return result

    def create_session(
        self,
        user: UserRecord,
        expires_in: timedelta = timedelta(days=7),
        ip_address: str | None = None,
        user_agent: str | None = None,
        active_membership_id: str | None = None,  # auth Plan 1a
    ) -> SessionRecord:
        """
        Create a new session for a user.

        Args:
            user: User record
            expires_in: Session expiration time
            ip_address: Client IP address
            user_agent: Client user agent

        Returns:
            Created session record
        """
        session = SessionRecord(
            user_id=user.id,
            expires_at=datetime.now(UTC) + expires_in,
            ip_address=ip_address,
            user_agent=user_agent,
            active_membership_id=active_membership_id,
        )

        self._execute(
            """
            INSERT INTO sessions
                (id, user_id, created_at, expires_at, ip_address, user_agent,
                 csrf_secret, active_membership_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                session.id,
                str(session.user_id),
                session.created_at.isoformat(),
                session.expires_at.isoformat(),
                session.ip_address,
                session.user_agent,
                session.csrf_secret,
                session.active_membership_id,
            ),
        )

        return session

    def get_session(self, session_id: str) -> SessionRecord | None:
        """Get session by ID."""
        row = self._execute_one("SELECT * FROM sessions WHERE id = %s", (session_id,))

        if row:
            # Pass the stored secret through verbatim so the model's
            # default_factory does NOT silently mint a fresh one on every load
            # (which would break double-submit validation). Migration 0005
            # backfills every existing row, so a NULL/empty value here is an
            # unexpected invariant violation — surface it loudly rather than
            # silently fabricating a (non-functional) secret, per the
            # silent-failure counter-prior. We still mint a transient secret so
            # the load doesn't crash on a legacy row.
            stored_csrf = row.get("csrf_secret")
            if not stored_csrf:
                logger.warning(
                    "Session %s has no csrf_secret (migration backfill gap?) — "
                    "minting a transient secret; this session's CSRF token will "
                    "not be stable until re-login.",
                    row["id"],
                )
                stored_csrf = secrets.token_urlsafe(32)
            return SessionRecord(
                id=row["id"],
                user_id=UUID(row["user_id"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                expires_at=datetime.fromisoformat(row["expires_at"]),
                ip_address=row["ip_address"],
                user_agent=row["user_agent"],
                csrf_secret=stored_csrf,
                active_membership_id=row.get("active_membership_id"),  # auth Plan 1a
            )

        return None

    def regenerate_session_csrf(self, session_id: str) -> str:
        """Mint a fresh CSRF secret for an existing session and return it.

        Rotates the token within a session's lifetime without forcing re-login
        (the privilege-change-rotation primitive). Raises if no session matches —
        rotating a non-existent session is a programming error, surfaced loudly
        rather than returning an un-persisted secret (anti-silent-failure).
        """
        new_secret = secrets.token_urlsafe(32)
        rowcount = self._execute_modify(
            "UPDATE sessions SET csrf_secret = %s WHERE id = %s",
            (new_secret, session_id),
        )
        if rowcount == 0:
            raise LookupError(f"cannot regenerate CSRF secret: no session {session_id!r}")
        return new_secret

    def set_session_active_membership(
        self, session_id: str, membership_id: str, *, identity_id: str
    ) -> bool:
        """Pin (or rotate) a session's active org membership — ownership-checked.

        The membership must belong to ``identity_id`` (the session's user) and be
        ``status="active"``; otherwise this is a no-op returning False (a user
        must not activate another identity's org, nor a suspended membership — the
        Phase-2 IDOR guard). The ``AND user_id = %s`` on the UPDATE is
        defence-in-depth so a stale/foreign ``session_id`` cannot be repointed.
        Returns True iff exactly one row moved. The RLS GUC re-binds on the next
        request via ``validate_session`` → ``_bind_rls_tenant_id`` (Plan 1a).
        """
        membership = self.get_membership(membership_id)
        if (
            membership is None
            or membership.identity_id != identity_id
            or membership.status != "active"
        ):
            return False
        rowcount = self._execute_modify(
            "UPDATE sessions SET active_membership_id = %s WHERE id = %s AND user_id = %s",
            (membership_id, session_id, identity_id),
        )
        return bool(rowcount == 1)

    def validate_session(self, session_id: str) -> AuthContext:
        """
        Validate a session and return auth context.

        Returns AuthContext with is_authenticated=True if session is valid.
        """
        session = self.get_session(session_id)

        if not session:
            return AuthContext()

        # Check expiration
        if session.expires_at < datetime.now(UTC):
            self.delete_session(session_id)
            return AuthContext()

        # Get user
        user = self.get_user_by_id(session.user_id)

        if not user or not user.is_active:
            self.delete_session(session_id)
            return AuthContext()

        # Load user preferences (methods defined on AuthStore, accessed via _execute)
        prefs: dict[str, str] = {}
        try:
            rows = self._execute(
                "SELECT key, value FROM user_preferences WHERE user_id = %s",
                (str(user.id),),
            )
            prefs = {r["key"]: r["value"] for r in rows}
        except Exception:
            logger.warning("Could not load user preferences", exc_info=True)

        # Merge domain attributes from DSL User entity (e.g. school, department)
        # so scope rules like `current_user.school` resolve correctly (#532).
        domain_attrs = self._load_domain_user_attributes(user.email)
        for k, v in domain_attrs.items():
            prefs.setdefault(k, v)  # Explicit preferences take priority

        # auth Plan 1a: resolve the session's active membership (if any). When
        # present it sources the RLS tenant id + effective roles (see
        # AuthContext.effective_roles / _bind_rls_tenant_id).
        active_membership = None
        if session.active_membership_id:
            active_membership = self.get_membership(session.active_membership_id)
            # Only an ACTIVE membership sources the fence + roles. A suspended or
            # still-invited membership must not keep scoping the session to the
            # org — fail-safe: drop to None → tenant GUC stays unbound → the RLS
            # fence denies (a suspended user sees nothing until re-auth).
            if active_membership is not None and active_membership.status != "active":
                active_membership = None

        return AuthContext(
            user=user,
            session=session,
            is_authenticated=True,
            roles=user.roles,
            preferences=prefs,
            active_membership=active_membership,
        )

    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        rowcount = self._execute_modify("DELETE FROM sessions WHERE id = %s", (session_id,))
        return bool(rowcount > 0)

    def delete_user_sessions(self, user_id: UUID) -> int:
        """Delete all sessions for a user."""
        return int(self._execute_modify("DELETE FROM sessions WHERE user_id = %s", (str(user_id),)))

    def delete_sessions_for_membership(self, membership_id: str) -> int:
        """Delete sessions currently acting as ``membership_id`` (auth Plan 4c).

        Used by SCIM deactivate/deprovision: suspending one org's membership must
        kill the identity's *sessions in that org* — sessions where they're acting as
        a different org's membership survive (multi-org-correct revocation).
        """
        return int(
            self._execute_modify(
                "DELETE FROM sessions WHERE active_membership_id = %s", (membership_id,)
            )
        )

    def count_active_sessions(self, user_id: UUID | None = None) -> int:
        """
        Count active (non-expired) sessions.

        Args:
            user_id: If provided, count only sessions for this user.
                     If None, count all active sessions across all users.

        Returns:
            Number of active sessions
        """
        now = datetime.now(UTC).isoformat()
        if user_id is not None:
            rows = self._execute(
                "SELECT COUNT(*) as count FROM sessions WHERE user_id = %s AND expires_at > %s",
                (str(user_id), now),
            )
        else:
            rows = self._execute(
                "SELECT COUNT(*) as count FROM sessions WHERE expires_at > %s",
                (now,),
            )
        return int(rows[0]["count"]) if rows else 0

    def cleanup_expired_sessions(self) -> int:
        """Delete all expired sessions."""
        return int(
            self._execute_modify(
                "DELETE FROM sessions WHERE expires_at < %s",
                (datetime.now(UTC).isoformat(),),
            )
        )

    def delete_all_sessions(self) -> int:
        """Delete all sessions for all users. Returns count deleted."""
        return int(self._execute_modify("DELETE FROM sessions"))

    # -- Memberships (auth Plan 1a) -------------------------------------------
    # Kept on this mixin (not AuthStore) so validate_session above can resolve
    # self.get_membership; membership is session-adjacent (a session pins one).

    def _row_to_membership(self, row: dict[str, Any]) -> MembershipRecord:
        import json

        return MembershipRecord(
            id=row["id"],
            tenant_id=row["tenant_id"],
            identity_id=row["identity_id"],
            roles=json.loads(row["roles"]) if row.get("roles") else [],
            status=row["status"],
            invited_by=row.get("invited_by"),
            external_id=row.get("external_id"),
            joined_at=datetime.fromisoformat(row["joined_at"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def create_membership(
        self,
        *,
        tenant_id: str,
        identity_id: str,
        roles: list[str] | None = None,
        status: str = "active",
        invited_by: str | None = None,
        external_id: str | None = None,
        actor_id: str | None = None,
        reason: str | None = None,
    ) -> MembershipRecord:
        """Create a membership (identity x org x roles) + emit a PROVISIONED event.

        Raises ``ValueError`` if ``identity_id`` does not name an existing user —
        there is no DB foreign key (the auth tables are not in the Alembic chain;
        see migration 0007), so this is the integrity guard against orphan
        memberships / a mistyped identity. The membership row and its lifecycle
        event are written in ONE transaction (auth Plan 2a — durable evidence).
        """
        import json

        from dazzle.http.runtime.auth.membership_events import (
            MEMBERSHIP_EVENTS_LOCK_KEY,
            MembershipEventType,
            record_membership_event,
        )

        if self.get_user_by_id(UUID(identity_id)) is None:
            raise ValueError(f"cannot create membership: no user with id {identity_id!r}")

        membership = MembershipRecord(
            id=secrets.token_urlsafe(24),
            tenant_id=tenant_id,
            identity_id=identity_id,
            roles=roles or [],
            status=status,
            invited_by=invited_by,
            external_id=external_id,
        )
        with self._transaction() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (MEMBERSHIP_EVENTS_LOCK_KEY,))
            cur.execute(
                """
                INSERT INTO memberships
                    (id, tenant_id, identity_id, roles, status, invited_by, external_id,
                     joined_at, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    membership.id,
                    membership.tenant_id,
                    membership.identity_id,
                    json.dumps(membership.roles),
                    membership.status,
                    membership.invited_by,
                    membership.external_id,
                    membership.joined_at.isoformat(),
                    membership.created_at.isoformat(),
                    membership.updated_at.isoformat(),
                ),
            )
            record_membership_event(
                cur,
                event_type=MembershipEventType.PROVISIONED,
                membership_id=membership.id,
                tenant_id=membership.tenant_id,
                identity_id=membership.identity_id,
                actor_id=actor_id,
                roles_after=membership.roles,
                status_after=membership.status,
                reason=reason,
            )
        return membership

    def update_membership_roles(
        self,
        membership_id: str,
        roles: list[str],
        *,
        actor_id: str | None = None,
        reason: str | None = None,
    ) -> MembershipRecord | None:
        """Grant/revoke roles on a membership (mover) + emit a ROLE_CHANGED event.

        Returns the updated record, or ``None`` if no such membership.
        """
        import json

        from dazzle.http.runtime.auth.membership_events import (
            MEMBERSHIP_EVENTS_LOCK_KEY,
            MembershipEventType,
            record_membership_event,
        )

        now = datetime.now(UTC).isoformat()
        with self._transaction() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (MEMBERSHIP_EVENTS_LOCK_KEY,))
            cur.execute("SELECT * FROM memberships WHERE id = %s", (membership_id,))
            row = cur.fetchone()
            if row is None:
                return None
            roles_before = json.loads(row["roles"]) if row.get("roles") else []
            cur.execute(
                "UPDATE memberships SET roles = %s, updated_at = %s WHERE id = %s",
                (json.dumps(roles), now, membership_id),
            )
            record_membership_event(
                cur,
                event_type=MembershipEventType.ROLE_CHANGED,
                membership_id=membership_id,
                tenant_id=row["tenant_id"],
                identity_id=row["identity_id"],
                actor_id=actor_id,
                roles_before=roles_before,
                roles_after=roles,
                reason=reason,
            )
        return self.get_membership(membership_id)

    def _transition_membership_status(
        self,
        membership_id: str,
        *,
        from_status: str,
        to_status: str,
        event_type: str,
        actor_id: str | None,
        reason: str | None,
    ) -> MembershipRecord | None:
        """Shared suspend/reactivate body: status transition + lifecycle event.

        No-op (no event) when the membership is not in ``from_status`` — keeps the
        evidence stream free of duplicate/contradictory transitions.
        """
        from dazzle.http.runtime.auth.membership_events import (
            MEMBERSHIP_EVENTS_LOCK_KEY,
            record_membership_event,
        )

        now = datetime.now(UTC).isoformat()
        with self._transaction() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (MEMBERSHIP_EVENTS_LOCK_KEY,))
            cur.execute("SELECT * FROM memberships WHERE id = %s", (membership_id,))
            row = cur.fetchone()
            if row is None or row["status"] != from_status:
                return None  # not found, or no transition → no event
            cur.execute(
                "UPDATE memberships SET status = %s, updated_at = %s WHERE id = %s",
                (to_status, now, membership_id),
            )
            record_membership_event(
                cur,
                event_type=event_type,
                membership_id=membership_id,
                tenant_id=row["tenant_id"],
                identity_id=row["identity_id"],
                actor_id=actor_id,
                status_before=from_status,
                status_after=to_status,
                reason=reason,
            )
        return self.get_membership(membership_id)

    def suspend_membership(
        self, membership_id: str, *, actor_id: str | None = None, reason: str | None = None
    ) -> MembershipRecord | None:
        """Suspend an active membership (leaver-ish) + emit a SUSPENDED event."""
        from dazzle.http.runtime.auth.membership_events import MembershipEventType

        return self._transition_membership_status(
            membership_id,
            from_status="active",
            to_status="suspended",
            event_type=MembershipEventType.SUSPENDED,
            actor_id=actor_id,
            reason=reason,
        )

    def reactivate_membership(
        self, membership_id: str, *, actor_id: str | None = None, reason: str | None = None
    ) -> MembershipRecord | None:
        """Reactivate a suspended membership (mover) + emit a REACTIVATED event."""
        from dazzle.http.runtime.auth.membership_events import MembershipEventType

        return self._transition_membership_status(
            membership_id,
            from_status="suspended",
            to_status="active",
            event_type=MembershipEventType.REACTIVATED,
            actor_id=actor_id,
            reason=reason,
        )

    def remove_membership(
        self, membership_id: str, *, actor_id: str | None = None, reason: str | None = None
    ) -> bool:
        """Delete a membership (leaver) + emit a REMOVED event.

        The ``memberships`` row is deleted (current-state), but the REMOVED event
        persists in ``membership_events`` — the leaver evidence survives. Returns
        ``True`` if a membership was deleted, ``False`` if it did not exist.
        """
        from dazzle.http.runtime.auth.membership_events import (
            MEMBERSHIP_EVENTS_LOCK_KEY,
            MembershipEventType,
            record_membership_event,
        )

        with self._transaction() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (MEMBERSHIP_EVENTS_LOCK_KEY,))
            cur.execute("SELECT * FROM memberships WHERE id = %s", (membership_id,))
            row = cur.fetchone()
            if row is None:
                return False
            cur.execute("DELETE FROM memberships WHERE id = %s", (membership_id,))
            # scim_group_members has no FK to memberships (see _init_db) — clear
            # the deleted membership's group rows here so no orphans survive.
            cur.execute("DELETE FROM scim_group_members WHERE membership_id = %s", (membership_id,))
            record_membership_event(
                cur,
                event_type=MembershipEventType.REMOVED,
                membership_id=membership_id,
                tenant_id=row["tenant_id"],
                identity_id=row["identity_id"],
                actor_id=actor_id,
                status_before=row["status"],
                status_after="removed",
                reason=reason,
            )
        return True

    def get_membership(self, membership_id: str) -> MembershipRecord | None:
        row = self._execute_one("SELECT * FROM memberships WHERE id = %s", (membership_id,))
        return self._row_to_membership(row) if row else None

    def get_memberships_for_identity(self, identity_id: str) -> list[MembershipRecord]:
        rows = self._execute(
            "SELECT * FROM memberships WHERE identity_id = %s ORDER BY created_at",
            (identity_id,),
        )
        return [self._row_to_membership(r) for r in rows]

    def get_memberships_for_tenant(self, tenant_id: str) -> list[MembershipRecord]:
        """Current roster: all memberships in an org (auth Plan 2b — access review)."""
        rows = self._execute(
            "SELECT * FROM memberships WHERE tenant_id = %s ORDER BY created_at",
            (tenant_id,),
        )
        return [self._row_to_membership(r) for r in rows]

    def get_membership_by_external_id(
        self, tenant_id: str, external_id: str
    ) -> MembershipRecord | None:
        """Resolve the membership an IdP `externalId` (Entra user GUID) names in an org.

        The dedup chokepoint for SCIM provisioning (#1342 gap 1): lets a re-push under a
        changed email find the existing membership instead of forking a duplicate. Scoped
        to ``tenant_id`` (one org's SCIM connection is authoritative only for its own org).
        """
        row = self._execute_one(
            "SELECT * FROM memberships WHERE tenant_id = %s AND external_id = %s",
            (tenant_id, external_id),
        )
        return self._row_to_membership(row) if row else None

    def update_membership_external_id(
        self, membership_id: str, external_id: str | None
    ) -> MembershipRecord | None:
        """Persist (or backfill) the IdP `externalId` on a membership. Returns the updated
        record, or ``None`` if no such membership. No lifecycle event — externalId is an
        IdP correlation key, not an access change."""
        with self._transaction() as cur:
            cur.execute(
                "UPDATE memberships SET external_id = %s, updated_at = %s WHERE id = %s",
                (external_id, datetime.now(UTC).isoformat(), membership_id),
            )
            updated = cur.rowcount
            cur.execute("SELECT * FROM memberships WHERE id = %s", (membership_id,))
            row = cur.fetchone()
        if not updated or row is None:
            return None
        return self._row_to_membership(row)

    # -- Membership lifecycle events (auth Plan 2a — compliance evidence) -----

    def _row_to_event(self, row: dict[str, Any]) -> "MembershipEvent":  # noqa: F821
        import json

        from dazzle.http.runtime.auth.membership_events import MembershipEvent

        return MembershipEvent(
            id=row["id"],
            event_type=row["event_type"],
            membership_id=row["membership_id"],
            tenant_id=row["tenant_id"],
            identity_id=row["identity_id"],
            actor_id=row.get("actor_id"),
            roles_before=json.loads(row["roles_before"]) if row.get("roles_before") else None,
            roles_after=json.loads(row["roles_after"]) if row.get("roles_after") else None,
            status_before=row.get("status_before"),
            status_after=row.get("status_after"),
            reason=row.get("reason"),
            created_at=datetime.fromisoformat(row["created_at"]),
            seq=row.get("seq"),
            row_hash=row.get("row_hash"),
        )

    def get_membership_events(
        self,
        *,
        tenant_id: str | None = None,
        identity_id: str | None = None,
        membership_id: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> list["MembershipEvent"]:  # noqa: F821
        """Return the JML event stream, ordered by seq, optionally filtered.

        ``since``/``until`` are ISO-8601 strings compared against ``created_at``
        (TEXT, ISO-8601 sorts lexically). All filters AND together.
        """
        clauses: list[str] = []
        params: list[object] = []
        if tenant_id is not None:
            clauses.append("tenant_id = %s")
            params.append(tenant_id)
        if identity_id is not None:
            clauses.append("identity_id = %s")
            params.append(identity_id)
        if membership_id is not None:
            clauses.append("membership_id = %s")
            params.append(membership_id)
        if since is not None:
            clauses.append("created_at >= %s")
            params.append(since)
        if until is not None:
            clauses.append("created_at <= %s")
            params.append(until)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        # Filters are %s-parameterised; the only interpolation is the fixed
        # clause fragments above (no user-controlled identifiers).
        rows = self._execute(
            f"SELECT * FROM membership_events{where} ORDER BY seq ASC",  # nosemgrep: parameterised filters
            tuple(params),
        )
        return [self._row_to_event(r) for r in rows]

    def verify_membership_event_chain(self) -> "EventChainResult":  # noqa: F821
        """Verify the append-only membership_events hash-chain (tamper-evidence)."""
        from dazzle.http.runtime.auth.membership_events import (
            verify_membership_event_chain as _verify,
        )

        conn = self._get_connection()
        try:
            return _verify(conn)
        finally:
            conn.close()

    # -- Organizations (auth Plan 1c — framework tenant root) ----------------

    DEFAULT_ORG_SLUG = "default"

    def _row_to_organization(self, row: dict[str, Any]) -> OrganizationRecord:
        import json

        return OrganizationRecord(
            id=row["id"],
            slug=row["slug"],
            name=row["name"],
            status=row["status"],
            is_test=bool(row["is_test"]),
            settings=json.loads(row["settings"] or "{}") if row.get("settings") is not None else {},
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def create_organization(
        self, *, slug: str, name: str, is_test: bool = False
    ) -> OrganizationRecord:
        """Create an organization (raises on duplicate slug)."""
        import json

        org = OrganizationRecord(
            id=secrets.token_urlsafe(24), slug=slug, name=name, is_test=is_test
        )
        self._execute(
            """
            INSERT INTO organizations
                (id, slug, name, status, is_test, settings, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                org.id,
                org.slug,
                org.name,
                org.status,
                org.is_test,
                json.dumps(org.settings),
                org.created_at.isoformat(),
                org.updated_at.isoformat(),
            ),
        )
        return org

    def get_organization_by_slug(self, slug: str) -> OrganizationRecord | None:
        row = self._execute_one("SELECT * FROM organizations WHERE slug = %s", (slug,))
        return self._row_to_organization(row) if row else None

    def get_organization(self, org_id: str) -> OrganizationRecord | None:
        row = self._execute_one("SELECT * FROM organizations WHERE id = %s", (org_id,))
        return self._row_to_organization(row) if row else None

    def get_org_settings(self, tenant_id: str) -> dict[str, Any]:
        """Return the settings dict for *tenant_id*, or {} if the org doesn't exist."""
        org = self.get_organization(tenant_id)
        return dict(org.settings) if org else {}

    def set_org_settings(self, tenant_id: str, settings: dict[str, Any]) -> None:
        """Persist *settings* for *tenant_id* (full replace)."""
        import json

        self._execute_modify(
            "UPDATE organizations SET settings = %s, updated_at = %s WHERE id = %s",
            (json.dumps(settings), datetime.now(UTC).isoformat(), tenant_id),
        )

    # -- Join requests (verified-domain self-service join, #1424) ---------------

    def _row_to_join_request(self, row: dict[str, Any]) -> JoinRequestRecord:
        return JoinRequestRecord(
            id=row["id"],
            tenant_id=row["tenant_id"],
            identity_id=row["identity_id"],
            email=row["email"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            decided_at=datetime.fromisoformat(row["decided_at"]) if row.get("decided_at") else None,
            decided_by=row.get("decided_by"),
        )

    def create_join_request(
        self,
        *,
        tenant_id: str,
        identity_id: str,
        email: str,
    ) -> JoinRequestRecord:
        """Create a pending join request for (tenant_id, identity_id).

        Idempotent: if a pending row already exists for this (tenant, identity)
        pair the existing record is returned unchanged (mirrors the
        ``create_membership`` UniqueViolation re-read pattern).
        """
        jr = JoinRequestRecord(
            id=secrets.token_urlsafe(24),
            tenant_id=tenant_id,
            identity_id=identity_id,
            email=email,
        )
        try:
            self._execute_modify(
                """
                INSERT INTO join_requests
                    (id, tenant_id, identity_id, email, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    jr.id,
                    jr.tenant_id,
                    jr.identity_id,
                    jr.email,
                    jr.status,
                    jr.created_at.isoformat(),
                ),
            )
        except psycopg.errors.UniqueViolation:
            # Concurrent create: another request inserted the pending row first.
            # Re-read the winner; any other DB error must propagate.
            existing = self._execute_one(
                "SELECT * FROM join_requests "
                "WHERE tenant_id = %s AND identity_id = %s AND status = 'pending'",
                (tenant_id, identity_id),
            )
            if existing is None:
                raise LookupError(
                    "join_request create hit a unique-violation but no pending row "
                    f"found for identity={identity_id!r} tenant={tenant_id!r}"
                ) from None
            return self._row_to_join_request(existing)
        return jr

    def get_pending_join_requests(self, tenant_id: str) -> list[JoinRequestRecord]:
        """Return all pending join requests for a tenant, oldest first."""
        rows = self._execute(
            "SELECT * FROM join_requests WHERE tenant_id = %s AND status = 'pending' "
            "ORDER BY created_at",
            (tenant_id,),
        )
        return [self._row_to_join_request(r) for r in rows]

    def get_join_request(self, request_id: str) -> JoinRequestRecord | None:
        """Fetch a join request by id, or None if not found."""
        row = self._execute_one("SELECT * FROM join_requests WHERE id = %s", (request_id,))
        return self._row_to_join_request(row) if row else None

    def decide_join_request(
        self,
        request_id: str,
        *,
        status: str,
        decided_by: str,
    ) -> JoinRequestRecord:
        """Atomically transition a *pending* join request to ``approved``/``denied``.

        Pending-only guard (double-decide defence, Task 1.5 review): the UPDATE
        filters ``status = 'pending'``, so a second approve/deny of an
        already-decided request matches zero rows. A double-approve therefore
        cannot overwrite the decision nor create a second membership (the approve
        helper creates the membership only when this transition succeeds).

        Raises ``AlreadyDecidedError`` when the row is missing or no longer
        pending (rowcount 0).
        """
        now = datetime.now(UTC).isoformat()
        rowcount = self._execute_modify(
            "UPDATE join_requests SET status = %s, decided_at = %s, decided_by = %s "
            "WHERE id = %s AND status = 'pending'",
            (status, now, decided_by, request_id),
        )
        if rowcount == 0:
            raise AlreadyDecidedError(request_id)
        row = self._execute_one("SELECT * FROM join_requests WHERE id = %s", (request_id,))
        assert row is not None  # just updated
        return self._row_to_join_request(row)

    def approve_join_request_atomic(
        self,
        request_id: str,
        *,
        decided_by: str,
        roles: list[str] | None = None,
        reason: str = "verified-domain join approved",
    ) -> JoinRequestRecord:
        """Approve a *pending* join request in ONE transaction, lock-serialized (#1430).

        ``SELECT … FOR UPDATE`` on the join_requests row serializes concurrent
        approvers: the first locks the row, creates the membership and flips the
        status to ``approved`` under that lock; a concurrent second approver blocks
        on the lock, then sees the row already non-pending and raises
        ``AlreadyDecidedError`` — so the membership INSERT never runs twice. This
        replaces the prior load→create→decide sequence (four independent
        auto-committed statements) whose double-approve defence rested on the
        ``memberships (tenant_id, identity_id)`` unique constraint catching the
        duplicate after the fact.

        The membership INSERT, its PROVISIONED ``membership_events`` row, and the
        status UPDATE all share this transaction's commit (mirrors
        ``create_membership``'s Plan-2a atomicity). The membership logic is inlined
        rather than calling ``create_membership`` — that opens its own separate
        connection/transaction and would defeat the row lock held here.

        Raises ``AlreadyDecidedError`` when the row is missing or no longer pending,
        and ``ValueError`` when ``identity_id`` names no existing user (orphan guard,
        since the auth tables carry no FK — see migration 0007).
        """
        import json

        from dazzle.http.runtime.auth.membership_events import (
            MEMBERSHIP_EVENTS_LOCK_KEY,
            MembershipEventType,
            record_membership_event,
        )

        now = datetime.now(UTC).isoformat()
        with self._transaction() as cur:
            cur.execute("SELECT * FROM join_requests WHERE id = %s FOR UPDATE", (request_id,))
            row = cur.fetchone()
            if row is None or dict(row).get("status") != "pending":
                raise AlreadyDecidedError(request_id)
            jr_row = dict(row)
            tenant_id = jr_row["tenant_id"]
            identity_id = jr_row["identity_id"]

            if self.get_user_by_id(UUID(identity_id)) is None:
                raise ValueError(f"cannot create membership: no user with id {identity_id!r}")

            # Same advisory lock create_membership uses to serialize event sequencing.
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (MEMBERSHIP_EVENTS_LOCK_KEY,))
            membership = MembershipRecord(
                id=secrets.token_urlsafe(24),
                tenant_id=tenant_id,
                identity_id=identity_id,
                roles=roles or [],
            )
            cur.execute(
                """
                INSERT INTO memberships
                    (id, tenant_id, identity_id, roles, status, invited_by, external_id,
                     joined_at, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    membership.id,
                    membership.tenant_id,
                    membership.identity_id,
                    json.dumps(membership.roles),
                    membership.status,
                    membership.invited_by,
                    membership.external_id,
                    membership.joined_at.isoformat(),
                    membership.created_at.isoformat(),
                    membership.updated_at.isoformat(),
                ),
            )
            record_membership_event(
                cur,
                event_type=MembershipEventType.PROVISIONED,
                membership_id=membership.id,
                tenant_id=membership.tenant_id,
                identity_id=membership.identity_id,
                actor_id=decided_by,
                roles_after=membership.roles,
                status_after=membership.status,
                reason=reason,
            )
            # Flip the (locked, confirmed-pending) request to approved in the same tx.
            cur.execute(
                "UPDATE join_requests SET status = %s, decided_at = %s, decided_by = %s "
                "WHERE id = %s",
                ("approved", now, decided_by, request_id),
            )
            jr_row.update({"status": "approved", "decided_at": now, "decided_by": decided_by})
            return self._row_to_join_request(jr_row)

    # -- Enterprise connections (auth Plan 4a — per-org OIDC/SAML/SCIM) -------

    def _row_to_connection(self, row: dict[str, Any]) -> "ConnectionRecord":  # noqa: F821
        import json

        from dazzle.http.runtime.auth.connection_crypto import decrypt_secret
        from dazzle.http.runtime.auth.connections import ConnectionRecord

        enc = row.get("encrypted_secret")
        secrets_dict = json.loads(decrypt_secret(enc)) if enc else {}
        return ConnectionRecord(
            id=row["id"],
            tenant_id=row["tenant_id"],
            type=row["type"],
            provider=row["provider"],
            domains=json.loads(row["domains"]) if row.get("domains") else [],
            verified_domains=(
                json.loads(row["verified_domains"]) if row.get("verified_domains") else []
            ),
            config=json.loads(row["config"]) if row.get("config") else {},
            secrets=secrets_dict,
            group_mapping=json.loads(row["group_mapping"]) if row.get("group_mapping") else {},
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def create_connection(
        self,
        *,
        tenant_id: str,
        type: str,
        config: dict[str, Any],
        secrets: dict[str, Any],
        domains: list[str],
        provider: str = "native",
        group_mapping: dict[str, str] | None = None,
        status: str = "active",
    ) -> "ConnectionRecord":  # noqa: F821
        """Create a per-org connection; secret material is AES-GCM-encrypted at rest."""
        import json
        import secrets as _secrets  # the `secrets` param shadows the stdlib module here

        from dazzle.http.runtime.auth.connection_crypto import encrypt_secret

        conn_id = _secrets.token_urlsafe(24)
        now = datetime.now(UTC).isoformat()
        encrypted = encrypt_secret(json.dumps(secrets)) if secrets else None
        self._execute_modify(
            """
            INSERT INTO connections
                (id, tenant_id, type, provider, domains, verified_domains, config,
                 encrypted_secret, group_mapping, status, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                conn_id,
                tenant_id,
                type,
                provider,
                json.dumps(domains),
                json.dumps([]),
                json.dumps(config),
                encrypted,
                json.dumps(group_mapping or {}),
                status,
                now,
                now,
            ),
        )
        created = self.get_connection(conn_id)
        assert created is not None  # just inserted
        return created

    def get_connection(
        self, connection_id: str, *, tenant_id: str | None = None
    ) -> "ConnectionRecord | None":  # noqa: F821
        """Fetch a connection (decrypting its secrets).

        Pass ``tenant_id`` to fence the read to one org — a route serving a
        connection by id MUST pass the caller's active org so an id from another
        org can't leak its config + decrypted secrets (defense-in-depth; the id is
        unguessable but the decrypt-bearing read should require tenant context).
        """
        if tenant_id is not None:
            row = self._execute_one(
                "SELECT * FROM connections WHERE id = %s AND tenant_id = %s",
                (connection_id, tenant_id),
            )
        else:
            row = self._execute_one("SELECT * FROM connections WHERE id = %s", (connection_id,))
        return self._row_to_connection(row) if row else None

    def get_connections_for_tenant(self, tenant_id: str) -> list["ConnectionRecord"]:  # noqa: F821
        rows = self._execute(
            "SELECT * FROM connections WHERE tenant_id = %s ORDER BY created_at", (tenant_id,)
        )
        return [self._row_to_connection(r) for r in rows]

    def connection_type_counts(self) -> dict[str, int]:
        """``{connection.type: count}`` for the capability boot guard (#1344). Defensive:
        returns ``{}`` on ANY failure (missing ``connections`` table on a fresh/unmigrated
        DB, query error) — a boot guard must never break boot."""
        try:
            rows = self._execute("SELECT type, COUNT(*) AS n FROM connections GROUP BY type")
        except Exception:  # noqa: BLE001 — advisory guard; a read failure must not abort boot
            logger.debug("connection_type_counts: read failed (benign at boot)", exc_info=True)
            return {}
        return {str(r["type"]): int(r["n"]) for r in rows}

    def get_connection_by_verified_domain(  # noqa: F821
        self,
        domain: str,
        *,
        types: "tuple[str, ...] | None" = None,
    ) -> "ConnectionRecord | None":
        """Route an email domain to its org's connection — VERIFIED domains only.

        Matches against ``verified_domains`` (never the unverified ``domains``
        claim) so org A cannot hijack org B's SSO by claiming its domain (spec §5).
        Returns the first active match; verified-domain uniqueness is owned by the
        domain-verification flow (a later slice).

        When ``types`` is given, only connections whose ``type`` is in that set
        are considered.  SSO callers pass ``types=("oidc", "saml")`` to prevent a
        ``type="domain"`` connection (which has no SSO provider) from being handed
        to the SSO resolver and crashing the login flow.  Callers that need the
        unfiltered view (e.g. ``domain_verification.verify_domain``) omit the
        argument.
        """
        import json

        d = domain.strip().lower()
        for row in self._execute(
            "SELECT * FROM connections WHERE status = 'active' ORDER BY created_at"
        ):
            if types is not None and row.get("type") not in types:
                continue
            verified = [x.strip().lower() for x in json.loads(row.get("verified_domains") or "[]")]
            if d in verified:
                return self._row_to_connection(row)
        return None

    def get_scim_connection_by_bearer(self, token: str) -> "ConnectionRecord | None":  # noqa: F821
        """Authenticate a SCIM request: the active SCIM connection whose stored bearer
        matches ``token`` (auth Plan 4c), or ``None``.

        Constant-time comparison (``hmac.compare_digest``) against each candidate's
        decrypted ``secrets['scim_bearer']`` so a timing side-channel can't reveal the
        token byte-by-byte. Fail-closed: an empty token, or a connection with no stored
        bearer, never matches. The bearer is high-entropy, so the small per-connection
        timing signal (how many candidates were compared) can't help forge it.

        Grace window (#1342): a non-expired ``previous_encrypted_secret`` bearer also
        authenticates, so a ``rotate-secret --grace`` overlap lets the IdP migrate without
        a provisioning outage. An expired or absent previous secret is ignored; the read
        path stays read-only (no lazy cleanup — that's ``revoke-previous-secret``).
        """
        import hmac
        import json

        if not token:
            return None
        now = datetime.now(UTC)
        match: ConnectionRecord | None = None
        for row in self._execute(
            "SELECT * FROM connections WHERE status = 'active' AND type = 'scim'"
        ):
            conn = self._row_to_connection(row)
            stored = (conn.secrets or {}).get("scim_bearer") or ""
            # Compare as bytes so a non-ASCII presented token fails closed (no match)
            # instead of raising in compare_digest.
            # Don't break — compare all candidates (uniform work); record only the
            # FIRST match (the compares still all run, so timing stays uniform).
            if (
                stored
                and hmac.compare_digest(str(stored).encode("utf-8"), token.encode("utf-8"))
                and match is None
            ):
                match = conn
            # Grace: a non-expired PREVIOUS bearer also authenticates.
            prev_blob = row.get("previous_encrypted_secret")
            prev_exp = row.get("previous_secret_expires_at")
            if prev_blob and prev_exp:
                from dazzle.http.runtime.auth.connection_crypto import (
                    ConnectionSecretError,
                    decrypt_secret,
                )

                try:
                    if datetime.fromisoformat(prev_exp) > now:
                        prev_bearer = (json.loads(decrypt_secret(prev_blob)) or {}).get(
                            "scim_bearer"
                        ) or ""
                        if (
                            prev_bearer
                            and hmac.compare_digest(
                                str(prev_bearer).encode("utf-8"), token.encode("utf-8")
                            )
                            and match is None
                        ):
                            match = conn
                except (ConnectionSecretError, ValueError):
                    # Undecryptable/malformed previous → ignore (fail-closed). Narrow,
                    # not a bare `except: pass`; the current bearer still governs. WARNING
                    # (not debug) so a stranded grace blob — which silently fails the old
                    # bearer mid-window — is visible to the operator.
                    logger.warning("ignoring an unreadable grace blob for connection %s", conn.id)
        return match

    def set_connection_domains(self, connection_id: str, domains: list[str]) -> None:
        """Set the *claimed* domain list (advisory — never routes until verified)."""
        import json

        self._execute_modify(
            "UPDATE connections SET domains = %s, updated_at = %s WHERE id = %s",
            (json.dumps(domains), datetime.now(UTC).isoformat(), connection_id),
        )

    def rewrap_all_connection_secrets(self) -> "RewrapResult":  # noqa: F821
        """Re-encrypt every connection secret onto the PRIMARY key (encryption-key rotation).

        Decrypts each connection's secret (trying the primary key then the optional
        ``DAZZLE_CONNECTION_SECRET_OLD`` rotation key) and re-encrypts with the primary,
        so after the operator sets the new key as primary + the old key as the rotation
        key, this moves all ciphertext onto the new key. **Idempotent:** a secret already
        on the primary key is left untouched (counted as ``already_current``); a re-run
        after a full rotation rewraps nothing. A secret that no configured key can decrypt
        is collected in ``failed`` (the operator must set the right ``..._OLD`` key) — it
        is skipped, never dropped, and the rotation continues.

        Covers BOTH the live ``encrypted_secret`` and the ``previous_encrypted_secret``
        grace blob (#1342) — a grace blob left on the old key would silently stop the
        in-window old bearer from authenticating after a master-key rotation. A connection
        that is actually rewrapped also gets an ``encryption_key_rewrapped`` audit event.
        """
        from dazzle.http.runtime.auth.connection_crypto import (
            ConnectionSecretError,
            decrypt_secret_with_key_index,
            encrypt_secret,
        )
        from dazzle.http.runtime.auth.connections import RewrapResult
        from dazzle.http.runtime.auth.secret_rotation import SECRET_EVENT_KEY_REWRAPPED

        rewrapped = 0
        already_current = 0
        failed: list[str] = []
        now = datetime.now(UTC).isoformat()
        for row in self._execute(
            "SELECT id, tenant_id, encrypted_secret, previous_encrypted_secret "
            "FROM connections "
            "WHERE encrypted_secret IS NOT NULL OR previous_encrypted_secret IS NOT NULL"
        ):
            updates: dict[str, str] = {}
            had_failure = False
            for col in ("encrypted_secret", "previous_encrypted_secret"):
                enc = row.get(col)
                if not enc:
                    continue
                try:
                    plaintext, key_index = decrypt_secret_with_key_index(enc)
                except ConnectionSecretError:
                    # This blob can't be moved — report it, but DON'T abandon a
                    # sibling blob that CAN move. Breaking here would strand the
                    # live secret when only the grace blob is undecryptable.
                    had_failure = True
                    continue
                if key_index != 0:  # on the rotation key — move it onto the primary
                    updates[col] = encrypt_secret(plaintext)
            if had_failure:
                failed.append(row["id"])
            if not updates:
                if not had_failure:
                    already_current += 1  # all present blobs already on the primary key
                continue
            # Only the two fixed column names are ever set here (never user input);
            # values are bound via %s — so this stays parameterised/injection-safe.
            if "encrypted_secret" in updates and "previous_encrypted_secret" in updates:
                update_sql = (
                    "UPDATE connections SET encrypted_secret = %s, "
                    "previous_encrypted_secret = %s, updated_at = %s WHERE id = %s"
                )
                params: tuple[Any, ...] = (
                    updates["encrypted_secret"],
                    updates["previous_encrypted_secret"],
                    now,
                    row["id"],
                )
            elif "encrypted_secret" in updates:
                update_sql = (
                    "UPDATE connections SET encrypted_secret = %s, updated_at = %s WHERE id = %s"
                )
                params = (updates["encrypted_secret"], now, row["id"])
            else:
                update_sql = (
                    "UPDATE connections SET previous_encrypted_secret = %s, "
                    "updated_at = %s WHERE id = %s"
                )
                params = (updates["previous_encrypted_secret"], now, row["id"])
            with self._transaction() as cur:
                cur.execute(update_sql, params)
                self._write_secret_event(
                    cur,
                    connection_id=row["id"],
                    tenant_id=row["tenant_id"],
                    event=SECRET_EVENT_KEY_REWRAPPED,
                    actor="system",
                    detail={"from_key": "old"},
                    at=now,
                )
            rewrapped += 1
        return RewrapResult(rewrapped=rewrapped, already_current=already_current, failed=failed)

    def update_connection_secrets(
        self, connection_id: str, secrets: dict[str, Any], *, tenant_id: str | None = None
    ) -> bool:
        """Replace a connection's secret material (rotation), re-encrypting at rest.

        ``secrets`` REPLACES the stored blob (an empty dict clears it). Bumps
        ``updated_at`` — load-bearing: the OIDC provider's per-connection client cache is
        keyed on ``updated_at``, so a rotated ``client_secret`` rebuilds the client (the
        old secret stops working for new logins) without a process restart. Pass
        ``tenant_id`` to fence the write to one org. Returns ``True`` if a row changed.
        """
        import json

        from dazzle.http.runtime.auth.connection_crypto import encrypt_secret

        encrypted = encrypt_secret(json.dumps(secrets)) if secrets else None
        now = datetime.now(UTC).isoformat()
        if tenant_id is not None:
            rowcount = self._execute_modify(
                "UPDATE connections SET encrypted_secret = %s, updated_at = %s "
                "WHERE id = %s AND tenant_id = %s",
                (encrypted, now, connection_id, tenant_id),
            )
        else:
            rowcount = self._execute_modify(
                "UPDATE connections SET encrypted_secret = %s, updated_at = %s WHERE id = %s",
                (encrypted, now, connection_id),
            )
        return bool(rowcount > 0)

    def _load_config_secrets(
        self, cur: Any, connection_id: str, tenant_id: str | None
    ) -> tuple[dict[str, Any] | None, dict[str, Any], str | None, str | None]:
        """(config, secrets, tenant_id, type) for a connection inside a tx, or
        (None, {}, None, None) if absent (tenant-fenced when tenant_id given)."""
        import json

        from dazzle.http.runtime.auth.connection_crypto import decrypt_secret

        if tenant_id is not None:
            cur.execute(
                "SELECT config, encrypted_secret, tenant_id, type FROM connections "
                "WHERE id = %s AND tenant_id = %s",
                (connection_id, tenant_id),
            )
        else:
            cur.execute(
                "SELECT config, encrypted_secret, tenant_id, type FROM connections WHERE id = %s",
                (connection_id,),
            )
        row = cur.fetchone()
        if row is None:
            return None, {}, None, None
        config = json.loads(row["config"]) if row["config"] else {}
        enc = row["encrypted_secret"]
        secrets = json.loads(decrypt_secret(enc)) if enc else {}
        return config, secrets, row["tenant_id"], row["type"]

    def _write_connection_config_and_secrets(
        self, cur: Any, connection_id: str, config: dict[str, Any], secrets: dict[str, Any]
    ) -> None:
        import json

        from dazzle.http.runtime.auth.connection_crypto import encrypt_secret

        encrypted = encrypt_secret(json.dumps(secrets)) if secrets else None
        cur.execute(
            "UPDATE connections SET config = %s, encrypted_secret = %s, updated_at = %s "
            "WHERE id = %s",
            (json.dumps(config), encrypted, datetime.now(UTC).isoformat(), connection_id),
        )

    def enable_connection_request_signing(
        self,
        connection_id: str,
        *,
        sp_cert: str,
        sp_private_key: str,
        tenant_id: str | None = None,
    ) -> bool:
        """Persist SAML SP request-signing material in one transaction (#1342): merge
        ``sp_cert`` + ``sign_requests='true'`` into config and ``sp_private_key`` into the
        encrypted secrets blob. Returns True if a row changed. Tenant-fenced when given."""
        from dazzle.http.runtime.auth.secret_rotation import SECRET_EVENT_SIGNING_ENABLED

        with self._transaction() as cur:
            config, secrets, ten, conn_type = self._load_config_secrets(
                cur, connection_id, tenant_id
            )
            if config is None:
                return False
            # SAML-only at the store layer too (the CLI guards, but a future caller
            # mustn't write an SP key onto an OIDC/SCIM connection — a later rotate-secret
            # would silently destroy it).
            if conn_type != "saml":
                raise ValueError(
                    f"request signing is SAML-only (connection {connection_id!r} is {conn_type!r})"
                )
            config["sign_requests"] = "true"
            self._ensure_sp_keypair(config, secrets, sp_cert=sp_cert, sp_private_key=sp_private_key)
            self._write_connection_config_and_secrets(cur, connection_id, config, secrets)
            self._write_secret_event(
                cur,
                connection_id=connection_id,
                tenant_id=ten or "",
                event=SECRET_EVENT_SIGNING_ENABLED,
                actor="cli",
                detail={"type": conn_type},
                at=datetime.now(UTC).isoformat(),
            )
        return True

    def disable_connection_request_signing(
        self, connection_id: str, *, tenant_id: str | None = None
    ) -> bool:
        """Remove ``sp_cert`` + ``sign_requests`` from config and ``sp_private_key`` from
        secrets (one transaction). Returns True iff signing was on."""
        from dazzle.http.runtime.auth.secret_rotation import SECRET_EVENT_SIGNING_DISABLED

        with self._transaction() as cur:
            config, secrets, ten, conn_type = self._load_config_secrets(
                cur, connection_id, tenant_id
            )
            if config is None or not config.get("sign_requests"):
                return False
            config.pop("sign_requests", None)
            self._maybe_remove_sp_keypair(config, secrets)
            self._write_connection_config_and_secrets(cur, connection_id, config, secrets)
            self._write_secret_event(
                cur,
                connection_id=connection_id,
                tenant_id=ten or "",
                event=SECRET_EVENT_SIGNING_DISABLED,
                actor="cli",
                detail={"type": conn_type},
                at=datetime.now(UTC).isoformat(),
            )
        return True

    def set_connection_idp_initiated(
        self, connection_id: str, allowed: bool, *, tenant_id: str | None = None
    ) -> bool:
        """Toggle the per-connection ``allow_idp_initiated`` flag (SAML #1342). When on, the ACS
        accepts unsolicited (IdP-initiated) Responses — replay-protected by one-time assertion
        consumption (``record_consumed_assertion``). SAML-only; raises on another type so a flag
        can't be written onto an OIDC/SCIM connection. Returns True if a row changed."""
        import json

        with self._transaction() as cur:
            config, secrets, _ten, conn_type = self._load_config_secrets(
                cur, connection_id, tenant_id
            )
            if config is None:
                return False
            if conn_type != "saml":
                raise ValueError(
                    f"IdP-initiated is SAML-only (connection {connection_id!r} is {conn_type!r})"
                )
            if allowed:
                config["allow_idp_initiated"] = "true"
            else:
                config.pop("allow_idp_initiated", None)
            cur.execute(
                "UPDATE connections SET config = %s, updated_at = %s WHERE id = %s",
                (json.dumps(config), datetime.now(UTC).isoformat(), connection_id),
            )
        return True

    def record_consumed_assertion(
        self,
        assertion_id: str,
        *,
        connection_id: str,
        tenant_id: str | None,
        expires_at: str,
    ) -> bool:
        """One-time-use guard for an IdP-initiated SAML assertion (#1342 replay defense).

        Returns True if ``assertion_id`` was newly recorded (fresh — proceed), False if it was
        already consumed (replay — refuse). The ``INSERT ... ON CONFLICT DO NOTHING`` is the
        atomic, race-safe check (two concurrent replays can't both win). Expired rows (past their
        assertion ``NotOnOrAfter``) are purged first to bound growth."""
        now = datetime.now(UTC).isoformat()
        with self._transaction() as cur:
            cur.execute("DELETE FROM saml_consumed_assertions WHERE expires_at < %s", (now,))
            cur.execute(
                "INSERT INTO saml_consumed_assertions "
                "(assertion_id, connection_id, tenant_id, expires_at, created_at) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (assertion_id) DO NOTHING",
                (assertion_id, connection_id, tenant_id, expires_at, now),
            )
            inserted = cur.rowcount
        return bool(inserted)

    @staticmethod
    def _ensure_sp_keypair(
        config: dict[str, Any],
        secrets: dict[str, Any],
        *,
        sp_cert: str,
        sp_private_key: str,
    ) -> None:
        """Write the shared SP keypair only if absent — never clobber an existing key, so
        enabling the second feature (sign/encrypt) keeps the first feature's key. Rotation
        stays explicit (disable both features, then re-enable)."""
        config.setdefault("sp_cert", sp_cert)
        secrets.setdefault("sp_private_key", sp_private_key)

    @staticmethod
    def _maybe_remove_sp_keypair(config: dict[str, Any], secrets: dict[str, Any]) -> None:
        """Drop the shared SP keypair iff NEITHER request-signing nor assertion-encryption
        uses it any more."""
        if not config.get("sign_requests") and not config.get("encrypt_assertions"):
            config.pop("sp_cert", None)
            secrets.pop("sp_private_key", None)

    def enable_connection_assertion_encryption(
        self,
        connection_id: str,
        *,
        sp_cert: str,
        sp_private_key: str,
        tenant_id: str | None = None,
    ) -> bool:
        """Persist SAML assertion-encryption material (#1342 feature B): set
        ``encrypt_assertions='true'`` and ensure the shared SP keypair. Returns True if a
        row changed. SAML-only at the store layer; tenant-fenced when given."""
        from dazzle.http.runtime.auth.secret_rotation import SECRET_EVENT_ENCRYPTION_ENABLED

        with self._transaction() as cur:
            config, secrets, ten, conn_type = self._load_config_secrets(
                cur, connection_id, tenant_id
            )
            if config is None:
                return False
            if conn_type != "saml":
                raise ValueError(
                    f"assertion encryption is SAML-only (connection {connection_id!r} "
                    f"is {conn_type!r})"
                )
            config["encrypt_assertions"] = "true"
            self._ensure_sp_keypair(config, secrets, sp_cert=sp_cert, sp_private_key=sp_private_key)
            self._write_connection_config_and_secrets(cur, connection_id, config, secrets)
            self._write_secret_event(
                cur,
                connection_id=connection_id,
                tenant_id=ten or "",
                event=SECRET_EVENT_ENCRYPTION_ENABLED,
                actor="cli",
                detail={"type": conn_type},
                at=datetime.now(UTC).isoformat(),
            )
        return True

    def disable_connection_assertion_encryption(
        self, connection_id: str, *, tenant_id: str | None = None
    ) -> bool:
        """Remove ``encrypt_assertions`` and drop the shared SP keypair iff request-signing
        is also off (one transaction). Returns True iff encryption was on."""
        from dazzle.http.runtime.auth.secret_rotation import SECRET_EVENT_ENCRYPTION_DISABLED

        with self._transaction() as cur:
            config, secrets, ten, conn_type = self._load_config_secrets(
                cur, connection_id, tenant_id
            )
            if config is None or not config.get("encrypt_assertions"):
                return False
            config.pop("encrypt_assertions", None)
            self._maybe_remove_sp_keypair(config, secrets)
            self._write_connection_config_and_secrets(cur, connection_id, config, secrets)
            self._write_secret_event(
                cur,
                connection_id=connection_id,
                tenant_id=ten or "",
                event=SECRET_EVENT_ENCRYPTION_DISABLED,
                actor="cli",
                detail={"type": conn_type},
                at=datetime.now(UTC).isoformat(),
            )
        return True

    def _write_secret_event(
        self,
        cur: Any,
        *,
        connection_id: str,
        tenant_id: str,
        event: str,
        actor: str | None,
        detail: dict[str, Any],
        at: str,
    ) -> None:
        """Append one connection_secret_events row (#1342). ``detail`` is non-secret JSON."""
        import json
        import uuid

        cur.execute(
            "INSERT INTO connection_secret_events "
            "(id, connection_id, tenant_id, event, actor, detail, at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (uuid.uuid4().hex, connection_id, tenant_id, event, actor, json.dumps(detail), at),
        )

    def rotate_connection_secret(
        self,
        connection_id: str,
        new_secrets: dict[str, Any],
        *,
        grace: "timedelta | None" = None,  # noqa: F821
        actor: str | None = None,
        tenant_id: str | None = None,
    ) -> bool:
        """Rotate a connection's secret, optionally keeping the OLD one valid for ``grace``.

        One transaction: writes the new ``encrypted_secret``, sets-or-clears the grace
        columns (``previous_encrypted_secret`` / ``previous_secret_expires_at``), bumps
        ``updated_at`` (the OIDC client-cache key), and appends a ``rotated`` audit event
        with non-secret detail. With ``grace`` the old blob stays valid until
        ``now + grace`` (SCIM-bearer overlap; see ``get_scim_connection_by_bearer``);
        without it the rotation is a hard swap that clears any prior grace secret. Returns
        ``True`` if a row changed. ``tenant_id`` fences the write to one org.
        """
        import json

        from dazzle.http.runtime.auth.connection_crypto import encrypt_secret
        from dazzle.http.runtime.auth.secret_rotation import SECRET_EVENT_ROTATED

        now_dt = datetime.now(UTC)
        now = now_dt.isoformat()
        encrypted_new = encrypt_secret(json.dumps(new_secrets)) if new_secrets else None
        with self._transaction() as cur:
            if tenant_id is not None:
                cur.execute(
                    "SELECT encrypted_secret, tenant_id, type FROM connections "
                    "WHERE id = %s AND tenant_id = %s",
                    (connection_id, tenant_id),
                )
            else:
                cur.execute(
                    "SELECT encrypted_secret, tenant_id, type FROM connections WHERE id = %s",
                    (connection_id,),
                )
            row = cur.fetchone()
            if row is None:
                return False
            ten = row["tenant_id"]
            # Grace is SCIM-bearer-ONLY (an OIDC client_secret is arbitrated by the IdP,
            # so an overlap window is meaningless). Enforce here too, not just in the CLI,
            # so a future route / MCP / programmatic caller can't store a useless grace
            # blob + a misleading grace=True audit event on a non-SCIM connection.
            if grace is not None and row["type"] != "scim":
                raise ValueError(
                    f"grace window is SCIM-only (connection {connection_id!r} is {row['type']!r})"
                )
            if grace is not None:
                expires = (now_dt + grace).isoformat()
                cur.execute(
                    "UPDATE connections SET encrypted_secret = %s, "
                    "previous_encrypted_secret = %s, previous_secret_expires_at = %s, "
                    "updated_at = %s WHERE id = %s",
                    (encrypted_new, row["encrypted_secret"], expires, now, connection_id),
                )
                detail: dict[str, Any] = {
                    "type": row["type"],
                    "grace": True,
                    "grace_until": expires,
                }
            else:
                cur.execute(
                    "UPDATE connections SET encrypted_secret = %s, "
                    "previous_encrypted_secret = NULL, previous_secret_expires_at = NULL, "
                    "updated_at = %s WHERE id = %s",
                    (encrypted_new, now, connection_id),
                )
                detail = {"type": row["type"], "grace": False}
            self._write_secret_event(
                cur,
                connection_id=connection_id,
                tenant_id=ten,
                event=SECRET_EVENT_ROTATED,
                actor=actor,
                detail=detail,
                at=now,
            )
        return True

    def revoke_previous_connection_secret(
        self, connection_id: str, *, actor: str | None = None, tenant_id: str | None = None
    ) -> bool:
        """Clear the grace (previous) secret immediately + audit. Returns ``True`` iff a
        previous secret was present (idempotent: ``False`` when there's nothing to revoke)."""
        from dazzle.http.runtime.auth.secret_rotation import SECRET_EVENT_REVOKED_PREVIOUS

        now = datetime.now(UTC).isoformat()
        with self._transaction() as cur:
            if tenant_id is not None:
                cur.execute(
                    "SELECT tenant_id, previous_encrypted_secret FROM connections "
                    "WHERE id = %s AND tenant_id = %s",
                    (connection_id, tenant_id),
                )
            else:
                cur.execute(
                    "SELECT tenant_id, previous_encrypted_secret FROM connections WHERE id = %s",
                    (connection_id,),
                )
            row = cur.fetchone()
            if row is None or not row["previous_encrypted_secret"]:
                return False
            cur.execute(
                "UPDATE connections SET previous_encrypted_secret = NULL, "
                "previous_secret_expires_at = NULL, updated_at = %s WHERE id = %s",
                (now, connection_id),
            )
            self._write_secret_event(
                cur,
                connection_id=connection_id,
                tenant_id=row["tenant_id"],
                event=SECRET_EVENT_REVOKED_PREVIOUS,
                actor=actor,
                detail={},
                at=now,
            )
        return True

    def get_connection_secret_events(
        self, connection_id: str, *, tenant_id: str | None = None
    ) -> "list[ConnectionSecretEvent]":  # noqa: F821
        """The append-only rotation history for one connection, newest first.

        Pass ``tenant_id`` to fence the read to one org (mirrors ``get_connection``'s fenced
        getter) — a cross-org ``connection_id`` then returns ``[]`` instead of leaking the
        other org's history. The events table carries ``tenant_id`` for exactly this."""
        import json

        from dazzle.http.runtime.auth.connections import ConnectionSecretEvent

        if tenant_id is not None:
            rows = self._execute(
                "SELECT * FROM connection_secret_events "
                "WHERE connection_id = %s AND tenant_id = %s ORDER BY seq DESC",
                (connection_id, tenant_id),
            )
        else:
            rows = self._execute(
                "SELECT * FROM connection_secret_events WHERE connection_id = %s ORDER BY seq DESC",
                (connection_id,),
            )
        return [
            ConnectionSecretEvent(
                id=r["id"],
                connection_id=r["connection_id"],
                tenant_id=r["tenant_id"],
                event=r["event"],
                actor=r["actor"],
                detail=json.loads(r["detail"]),
                at=datetime.fromisoformat(r["at"]),
            )
            for r in rows
        ]

    def get_connection_grace_status(
        self, connection_id: str, *, tenant_id: str | None = None
    ) -> tuple[bool, str | None]:
        """(grace_active, expires_at_iso) for a connection's SCIM-bearer overlap window
        (#1342). A timestamp, not a secret — safe for the secret-free org-admin surface.
        (False, None) when there's no grace secret or the window has lapsed. Pass
        ``tenant_id`` to fence to one org (cross-org → (False, None)). Read-only —
        revoking stays in the CLI."""
        if tenant_id is not None:
            row = self._execute_one(
                "SELECT previous_secret_expires_at FROM connections "
                "WHERE id = %s AND tenant_id = %s",
                (connection_id, tenant_id),
            )
        else:
            row = self._execute_one(
                "SELECT previous_secret_expires_at FROM connections WHERE id = %s",
                (connection_id,),
            )
        exp = row["previous_secret_expires_at"] if row else None
        if not exp:
            return (False, None)
        try:
            return (datetime.fromisoformat(exp) > datetime.now(UTC), exp)
        except ValueError:
            return (False, None)

    def set_connection_verified_domains(self, connection_id: str, verified: list[str]) -> None:
        """Set the verified-domain list — the output of a domain-ownership check.

        Low-level blind overwrite. For domain *verification* prefer
        :meth:`claim_verified_domain`, which enforces one-owner-per-domain atomically.
        """
        import json

        self._execute_modify(
            "UPDATE connections SET verified_domains = %s, updated_at = %s WHERE id = %s",
            (json.dumps(verified), datetime.now(UTC).isoformat(), connection_id),
        )

    def claim_verified_domain(self, connection_id: str, domain: str) -> bool:
        """Atomically claim ``domain`` as verified for ``connection_id``.

        Returns ``True`` when this connection owns the domain after the call (newly
        claimed OR already its own — idempotent), ``False`` when a *different* active
        connection already verified it (one verified owner per domain).

        Serialized via a single advisory lock (mirrors the ``membership_events``
        pattern) so concurrent verifications can neither both claim the same domain
        (the cross-connection TOCTOU) nor lost-update a connection's domain list when
        two domains are verified for it at once — the connection's current list is
        re-read fresh inside the locked transaction, never trusting a caller snapshot.
        """
        import json

        from dazzle.http.runtime.auth.domain_verification import CONNECTION_DOMAIN_LOCK_KEY

        norm = domain.strip().lower().rstrip(".")
        with self._transaction() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (CONNECTION_DOMAIN_LOCK_KEY,))
            # Authoritative owner scan (active connections only).
            cur.execute("SELECT id, verified_domains FROM connections WHERE status = 'active'")
            for row in cur.fetchall():
                verified = [
                    x.strip().lower() for x in json.loads(row.get("verified_domains") or "[]")
                ]
                if norm in verified:
                    return bool(row["id"] == connection_id)  # ours → True (idempotent); else False
            # Unowned — append to THIS connection's fresh list (re-read inside the txn).
            cur.execute("SELECT verified_domains FROM connections WHERE id = %s", (connection_id,))
            row = cur.fetchone()
            if row is None:
                return False  # no such connection
            current = {x.strip().lower() for x in json.loads(row.get("verified_domains") or "[]")}
            cur.execute(
                "UPDATE connections SET verified_domains = %s, updated_at = %s WHERE id = %s",
                (
                    json.dumps(sorted(current | {norm})),
                    datetime.now(UTC).isoformat(),
                    connection_id,
                ),
            )
            return True

    def delete_connection(self, connection_id: str) -> bool:
        return bool(
            self._execute_modify("DELETE FROM connections WHERE id = %s", (connection_id,)) > 0
        )

    def get_or_create_default_organization(self, *, name: str = "Default") -> OrganizationRecord:
        """Return the single default org, creating it race-safely if absent.

        Concurrent first-signups converge on one row: the INSERT is a no-op on
        slug conflict, then we SELECT the winner. The fixed ``DEFAULT_ORG_SLUG``
        + its UNIQUE constraint is the idempotency key.
        """
        now = datetime.now(UTC).isoformat()
        self._execute(
            """
            INSERT INTO organizations
                (id, slug, name, status, is_test, created_at, updated_at)
            VALUES (%s, %s, %s, 'active', false, %s, %s)
            ON CONFLICT (slug) DO NOTHING
            """,
            (secrets.token_urlsafe(24), self.DEFAULT_ORG_SLUG, name, now, now),
        )
        existing = self.get_organization_by_slug(self.DEFAULT_ORG_SLUG)
        if existing is None:
            # The INSERT either created the row or was a no-op against an existing
            # one — a missing row here means a real failure (committed-INSERT not
            # visible / DDL drift), not a benign race. Raise loudly rather than
            # assert (asserts are stripped under -O and would 'return None' into
            # the login path) — anti-silent-failure.
            raise LookupError(
                f"default organization (slug={self.DEFAULT_ORG_SLUG!r}) absent after "
                "get-or-create INSERT"
            )
        return existing

    def ensure_single_org_membership(
        self, user: UserRecord, *, name: str = "Default", appspec: Any = None
    ) -> MembershipRecord:
        """Ensure ``user`` has a membership in the single default org (Plan 1c/1d).

        Race-safe: get-or-create the default org, then return the user's existing
        membership in it (the 1a ``(tenant_id, identity_id)`` unique makes the
        create idempotent — on a lost race we re-read). The membership's roles
        mirror the user's signup roles (``user.roles``) so ``effective_roles``
        equals what the user had before the membership model.

        Plan 1d: when ``appspec`` is given and declares an ``is_tenant_root``
        entity, the org is provisioned with a matching tenant-root row at the
        SAME id (the 1:1 mirror) so the membership fences the canonical RLS
        domain rows. Otherwise the framework org IS the tenant (1c behaviour).
        """
        if appspec is not None and _appspec_has_tenant_root(appspec):
            from dazzle.db.provision import provision_single_org

            with self._get_connection() as conn:  # concrete AuthStore provides it
                org_id = provision_single_org(appspec, name, conn=conn)
            org = self.get_organization(org_id)
            if org is None:
                raise LookupError(f"provisioned org {org_id!r} not found after mirror")
        else:
            org = self.get_or_create_default_organization(name=name)

        def _existing() -> MembershipRecord | None:
            for m in self.get_memberships_for_identity(str(user.id)):
                if m.tenant_id == org.id:
                    return m
            return None

        found = _existing()
        if found is not None:
            return found
        try:
            return self.create_membership(
                tenant_id=org.id,
                identity_id=str(user.id),
                roles=list(user.roles or []),
            )
        except psycopg.errors.UniqueViolation:
            # ONLY the concurrent-create race: another request inserted the same
            # (tenant_id, identity_id) first. Re-read the winner. Any OTHER error
            # (orphan-user ValueError from create_membership, DB outage, malformed
            # id) must propagate — swallowing it would mask a real failure as a
            # benign "no orgs" outcome (anti-silent-failure).
            again = _existing()
            if again is None:
                raise LookupError(
                    "membership create hit a unique-violation but no existing row "
                    f"found for identity={user.id!r} org={org.id!r}"
                ) from None
            return again


def ensure_auth_core_tables(cur: Any) -> None:
    """Create all auth tables and indexes (idempotent).

    Single source of DDL for the auth schema — called by both
    ``AuthStore._init_db`` (under its advisory lock, after which
    ``_ensure_email_ci_uniqueness`` runs in its own tx) and
    ``ensure_framework_schema`` (under the framework-schema advisory lock;
    the CI uniqueness check is skipped there because fresh installs never
    have duplicate-email rows).

    The caller is responsible for committing (or rolling back) the
    transaction; this function never commits.

    Args:
        cur: An open psycopg cursor.
    """
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            username TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            is_superuser BOOLEAN DEFAULT FALSE,
            roles TEXT DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    # Add 2FA + email-verification columns if they don't exist (idempotent migration).
    for _col, _col_type, _default in [
        ("totp_secret", "TEXT", None),
        ("totp_enabled", "BOOLEAN", "FALSE"),
        ("email_otp_enabled", "BOOLEAN", "FALSE"),
        ("recovery_codes_generated", "BOOLEAN", "FALSE"),
        ("email_verified", "BOOLEAN", "FALSE"),
    ]:
        _default_clause = f" DEFAULT {_default}" if _default else ""
        cur.execute(
            f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {_col} {_col_type}{_default_clause}"
        )

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            csrf_secret TEXT
        )
    """)
    cur.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS csrf_secret TEXT")
    cur.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS active_membership_id TEXT")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS memberships (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            identity_id TEXT NOT NULL,
            roles TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'active',
            invited_by TEXT,
            joined_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CONSTRAINT uq_memberships_tenant_identity UNIQUE (tenant_id, identity_id)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_memberships_identity_id ON memberships(identity_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_memberships_tenant_id ON memberships(tenant_id)")
    cur.execute("ALTER TABLE memberships ADD COLUMN IF NOT EXISTS external_id TEXT")
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_memberships_tenant_external "
        "ON memberships(tenant_id, external_id) WHERE external_id IS NOT NULL"
    )

    cur.execute("""
        CREATE TABLE IF NOT EXISTS organizations (
            id TEXT PRIMARY KEY,
            slug TEXT NOT NULL,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            is_test BOOLEAN NOT NULL DEFAULT false,
            settings TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CONSTRAINT uq_organizations_slug UNIQUE (slug)
        )
    """)

    from dazzle.http.runtime.auth.membership_events import (
        MEMBERSHIP_EVENTS_DDL,
        MEMBERSHIP_EVENTS_INDEXES,
    )

    cur.execute(MEMBERSHIP_EVENTS_DDL)
    for _ix in MEMBERSHIP_EVENTS_INDEXES:
        cur.execute(_ix)

    from dazzle.http.runtime.auth.invitations import INVITATIONS_DDL, INVITATIONS_INDEXES

    cur.execute(INVITATIONS_DDL)
    for _ix in INVITATIONS_INDEXES:
        cur.execute(_ix)

    from dazzle.http.runtime.auth.connections import CONNECTIONS_DDL, CONNECTIONS_INDEXES

    cur.execute(CONNECTIONS_DDL)
    for _ix in CONNECTIONS_INDEXES:
        cur.execute(_ix)

    cur.execute("ALTER TABLE connections ADD COLUMN IF NOT EXISTS previous_encrypted_secret TEXT")
    cur.execute("ALTER TABLE connections ADD COLUMN IF NOT EXISTS previous_secret_expires_at TEXT")

    from dazzle.http.runtime.auth.secret_rotation import (
        CONNECTION_SECRET_EVENTS_DDL,
        CONNECTION_SECRET_EVENTS_INDEXES,
    )

    cur.execute(CONNECTION_SECRET_EVENTS_DDL)
    for _ix in CONNECTION_SECRET_EVENTS_INDEXES:
        cur.execute(_ix)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS scim_groups (
            id            TEXT PRIMARY KEY,
            connection_id TEXT NOT NULL,
            display_name  TEXT NOT NULL,
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL,
            UNIQUE (connection_id, display_name)
        )
    """)
    cur.execute("ALTER TABLE scim_groups ADD COLUMN IF NOT EXISTS external_id TEXT")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_scim_groups_conn ON scim_groups(connection_id)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS scim_group_members (
            group_id      TEXT NOT NULL REFERENCES scim_groups(id) ON DELETE CASCADE,
            membership_id TEXT NOT NULL,
            PRIMARY KEY (group_id, membership_id)
        )
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS ix_scim_group_members_member "
        "ON scim_group_members(membership_id)"
    )

    cur.execute("""
        CREATE TABLE IF NOT EXISTS saml_consumed_assertions (
            assertion_id  TEXT PRIMARY KEY,
            connection_id TEXT NOT NULL,
            tenant_id     TEXT,
            expires_at    TEXT NOT NULL,
            created_at    TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used BOOLEAN DEFAULT FALSE
        )
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_reset_tokens_user ON password_reset_tokens(user_id)"
    )

    from dazzle.http.runtime.auth.magic_link import MAGIC_LINKS_DDL

    cur.execute(MAGIC_LINKS_DDL)

    from dazzle.http.runtime.auth.email_verification import EMAIL_VERIFICATION_TOKENS_DDL

    cur.execute(EMAIL_VERIFICATION_TOKENS_DDL)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_email_verify_user ON email_verification_tokens(user_id)"
    )

    cur.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            user_id TEXT NOT NULL REFERENCES users(id),
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, key)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_prefs_user ON user_preferences(user_id)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS join_requests (
            id          TEXT PRIMARY KEY,
            tenant_id   TEXT NOT NULL,
            identity_id TEXT NOT NULL,
            email       TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'pending',
            created_at  TEXT NOT NULL,
            decided_at  TEXT,
            decided_by  TEXT
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_join_requests_tenant ON join_requests(tenant_id)")
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_join_requests_pending "
        "ON join_requests(tenant_id, identity_id) WHERE status = 'pending'"
    )


class AuthStore(UserStoreMixin, SessionStoreMixin, TwoFactorMixin):
    """
    Authentication store using PostgreSQL.

    Manages users and sessions in a separate auth database.
    Combines UserStoreMixin (user CRUD, passwords) and
    SessionStoreMixin (session lifecycle, validation).
    """

    def __init__(
        self,
        database_url: str,
        user_entity_table: str = "",
    ):
        """
        Initialize the auth store.

        Args:
            database_url: PostgreSQL connection URL
            user_entity_table: DSL User entity table name (e.g. "User").
                When set, domain attributes from this table are merged
                into auth_context.preferences during session validation,
                so scope rules like ``current_user.school`` resolve.
        """
        # Normalize Heroku's postgres:// to postgresql://
        self._database_url = normalise_postgres_scheme(database_url)
        self._user_entity_table = user_entity_table

        self._init_db()

    # ------------------------------------------------------------------ #
    # SCIM Groups (#1342) — connection-scoped; members link to memberships.
    # ------------------------------------------------------------------ #

    def create_scim_group(
        self, connection_id: str, display_name: str, external_id: str | None = None
    ) -> "ScimGroupRecord":  # noqa: F821
        from uuid import uuid4

        from dazzle.http.runtime.auth.models import ScimGroupRecord

        now = datetime.now(UTC).isoformat()
        gid = str(uuid4())
        self._execute(
            "INSERT INTO scim_groups (id, connection_id, display_name, external_id, "
            "created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s)",
            (gid, connection_id, display_name, external_id, now, now),
        )
        return ScimGroupRecord(
            id=gid,
            connection_id=connection_id,
            display_name=display_name,
            external_id=external_id,
            created_at=now,
            updated_at=now,
        )

    def update_scim_group_external_id(
        self, group_id: str, connection_id: str, external_id: str | None
    ) -> None:
        """Set/refresh a SCIM group's IdP stable id (#1342) — e.g. a PUT replace carrying it."""
        self._execute(
            "UPDATE scim_groups SET external_id = %s, updated_at = %s "
            "WHERE id = %s AND connection_id = %s",
            (external_id, datetime.now(UTC).isoformat(), group_id, connection_id),
        )

    def get_member_group_keys(self, membership_id: str, connection_id: str) -> list[str]:
        """Role-mapping candidate keys for a member's SCIM groups: each group's display_name
        AND its external_id (GUID) when set, so a ``group_mapping`` keyed by EITHER (Entra GUID
        / Google name) matches (#1342 schools gap 2). Connection-scoped (org containment)."""
        rows = self._execute(
            "SELECT g.display_name AS display_name, g.external_id AS external_id "
            "FROM scim_group_members m JOIN scim_groups g ON g.id = m.group_id "
            "WHERE m.membership_id = %s AND g.connection_id = %s",
            (membership_id, connection_id),
        )
        keys: list[str] = []
        for r in rows:
            keys.append(r["display_name"])
            if r.get("external_id"):
                keys.append(r["external_id"])
        return keys

    def _row_to_scim_group(self, row: dict[str, Any]) -> "ScimGroupRecord":  # noqa: F821
        from dazzle.http.runtime.auth.models import ScimGroupRecord

        return ScimGroupRecord(
            id=row["id"],
            connection_id=row["connection_id"],
            display_name=row["display_name"],
            external_id=row.get("external_id"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def get_scim_group(self, group_id: str, connection_id: str) -> "ScimGroupRecord | None":  # noqa: F821
        row = self._execute_one(
            "SELECT * FROM scim_groups WHERE id = %s AND connection_id = %s",
            (group_id, connection_id),
        )
        return self._row_to_scim_group(row) if row else None

    def list_scim_groups(
        self, connection_id: str, display_name: str | None = None
    ) -> "list[ScimGroupRecord]":  # noqa: F821
        if display_name is not None:
            rows = self._execute(
                "SELECT * FROM scim_groups WHERE connection_id = %s AND display_name = %s "
                "ORDER BY created_at",
                (connection_id, display_name),
            )
        else:
            rows = self._execute(
                "SELECT * FROM scim_groups WHERE connection_id = %s ORDER BY created_at",
                (connection_id,),
            )
        return [self._row_to_scim_group(r) for r in rows]

    def rename_scim_group(self, group_id: str, connection_id: str, display_name: str) -> None:
        self._execute_modify(
            "UPDATE scim_groups SET display_name = %s, updated_at = %s "
            "WHERE id = %s AND connection_id = %s",
            (display_name, datetime.now(UTC).isoformat(), group_id, connection_id),
        )

    def delete_scim_group(self, group_id: str, connection_id: str) -> bool:
        n = self._execute_modify(
            "DELETE FROM scim_groups WHERE id = %s AND connection_id = %s",
            (group_id, connection_id),
        )
        return n > 0

    def get_group_member_ids(self, group_id: str) -> list[str]:
        rows = self._execute(
            "SELECT membership_id FROM scim_group_members WHERE group_id = %s "
            "ORDER BY membership_id",
            (group_id,),
        )
        return [r["membership_id"] for r in rows]

    def add_group_member(self, group_id: str, membership_id: str) -> None:
        self._execute_modify(
            "INSERT INTO scim_group_members (group_id, membership_id) VALUES (%s, %s) "
            "ON CONFLICT DO NOTHING",
            (group_id, membership_id),
        )

    def remove_group_member(self, group_id: str, membership_id: str) -> None:
        self._execute_modify(
            "DELETE FROM scim_group_members WHERE group_id = %s AND membership_id = %s",
            (group_id, membership_id),
        )

    def replace_group_members(self, group_id: str, membership_ids: list[str]) -> None:
        # Atomic: the DELETE + re-INSERTs share one commit so the group never
        # observes an empty member set mid-replace (a concurrent recompute would
        # otherwise read the gap and transiently zero roles).
        with self._transaction() as cur:
            cur.execute("DELETE FROM scim_group_members WHERE group_id = %s", (group_id,))
            for mid in membership_ids:
                cur.execute(
                    "INSERT INTO scim_group_members (group_id, membership_id) "
                    "VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (group_id, mid),
                )

    def get_member_group_names(self, membership_id: str, connection_id: str) -> list[str]:
        rows = self._execute(
            "SELECT g.display_name AS display_name FROM scim_group_members m "
            "JOIN scim_groups g ON g.id = m.group_id "
            "WHERE m.membership_id = %s AND g.connection_id = %s",
            (membership_id, connection_id),
        )
        return [r["display_name"] for r in rows]

    def _ensure_email_ci_uniqueness(self) -> None:
        """Enforce case-insensitive email uniqueness on `users` (#1342, M2).

        A plain `email TEXT UNIQUE` is case-SENSITIVE, so "Foo@x.com" and
        "foo@x.com" could coexist — a *split identity* an out-of-convention
        create-path could mint. A functional unique index on LOWER(email) closes
        that structurally (no CITEXT extension needed).

        Runs in its OWN transaction, *after* `_init_db` has committed the base
        schema — so if pre-existing case-duplicate rows block the index, the
        failure is isolated (the rest of the schema is already in place) and we
        raise a clear, actionable error rather than an opaque duplicate-key that
        also tore down the other table creation. Fails loud by design: you cannot
        silently boot with the split-identity hole open.
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            # #1363: serialize across workers — released at commit/close.
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", (AUTH_DDL_LOCK_KEY,))
            cursor.execute(
                "SELECT LOWER(email) AS k, COUNT(*) AS n FROM users "
                "GROUP BY LOWER(email) HAVING COUNT(*) > 1 LIMIT 5"
            )
            collisions = cursor.fetchall()
            if collisions:
                examples = ", ".join(f"{r['k']} (x{r['n']})" for r in collisions)
                raise RuntimeError(
                    "Cannot enforce case-insensitive email uniqueness (#1342): "
                    f"the users table has rows that collide on LOWER(email): {examples}. "
                    "Merge the duplicate user rows (one identity per lowercased email), "
                    "then restart."
                )
            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_key ON users (LOWER(email))"
            )
            conn.commit()
        finally:
            conn.close()

    def _get_connection(self) -> psycopg.Connection[dict[str, Any]]:
        """Get a PostgreSQL database connection."""
        return psycopg.connect(self._database_url, row_factory=dict_row)

    def _init_db(self) -> None:
        """Initialize database tables.

        #1363: the whole DDL transaction runs under an advisory lock —
        every uvicorn worker executes this at boot, and Postgres's
        ``IF NOT EXISTS`` checks are not concurrency-safe at the catalog
        level. The lock releases at commit.

        Delegates to ``ensure_auth_core_tables`` for the table/index DDL
        (shared with ``ensure_framework_schema``); retains the advisory
        lock and the post-commit ``_ensure_email_ci_uniqueness`` call here
        since those are store-specific concerns.
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", (AUTH_DDL_LOCK_KEY,))
            ensure_auth_core_tables(cursor)
            conn.commit()
        finally:
            conn.close()

        # Case-insensitive email uniqueness (#1342, M2) runs AFTER the base schema
        # is committed and its connection closed — in its own transaction (see the
        # method docstring) so a pre-existing case-dup failure can't tear down the
        # rest of schema init. Folded into _init_db (not __init__) so a test that
        # patches _init_db skips this DB work too.
        self._ensure_email_ci_uniqueness()

    def _execute(self, query: str, params: tuple[object, ...] = ()) -> list[dict[str, Any]]:
        """Execute a query and return results as list of dicts."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            if cursor.description:
                return [dict(row) for row in cursor.fetchall()]
            conn.commit()
            return []
        finally:
            conn.close()

    def _execute_one(self, query: str, params: tuple[object, ...] = ()) -> dict[str, Any] | None:
        """Execute a query and return single result."""
        results = self._execute(query, params)
        return results[0] if results else None

    def _execute_modify(self, query: str, params: tuple[object, ...] = ()) -> int:
        """Execute a modification query and return rowcount."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rowcount: int = cursor.rowcount
            conn.commit()
            return rowcount
        finally:
            conn.close()

    @contextmanager
    def _transaction(self) -> Any:
        """Yield a cursor in a single transaction; commit on success, rollback on error.

        Used for mutations that must be atomic with their ``membership_events``
        row (auth Plan 2a) — the mutation and the event INSERT share one commit.
        """
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # =========================================================================
    # User Preferences (v0.38.0)
    # =========================================================================

    def get_preferences(self, user_id: UUID) -> dict[str, str]:
        """Get all preferences for a user as {key: value} dict."""
        rows = self._execute(
            "SELECT key, value FROM user_preferences WHERE user_id = %s",
            (str(user_id),),
        )
        return {r["key"]: r["value"] for r in rows}

    def get_preference(self, user_id: UUID, key: str) -> str | None:
        """Get a single preference value, or None."""
        row = self._execute_one(
            "SELECT value FROM user_preferences WHERE user_id = %s AND key = %s",
            (str(user_id), key),
        )
        return row["value"] if row else None

    def set_preference(self, user_id: UUID, key: str, value: str) -> None:
        """Set a user preference (upsert)."""
        now = datetime.now(UTC).isoformat()
        self._execute_modify(
            """
            INSERT INTO user_preferences (user_id, key, value, updated_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id, key) DO UPDATE SET value = %s, updated_at = %s
            """,
            (str(user_id), key, value, now, value, now),
        )

    def set_preferences(self, user_id: UUID, prefs: dict[str, str]) -> None:
        """Bulk set preferences (upsert each)."""
        if not prefs:
            return
        now = datetime.now(UTC).isoformat()
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            for key, value in prefs.items():
                cursor.execute(
                    """
                    INSERT INTO user_preferences (user_id, key, value, updated_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (user_id, key) DO UPDATE SET value = %s, updated_at = %s
                    """,
                    (str(user_id), key, value, now, value, now),
                )
            conn.commit()
        finally:
            conn.close()

    def delete_preference(self, user_id: UUID, key: str) -> bool:
        """Delete a single preference. Returns True if deleted."""
        return bool(
            self._execute_modify(
                "DELETE FROM user_preferences WHERE user_id = %s AND key = %s",
                (str(user_id), key),
            )
        )

    def delete_preferences(self, user_id: UUID) -> int:
        """Delete all preferences for a user. Returns count deleted."""
        return int(
            self._execute_modify(
                "DELETE FROM user_preferences WHERE user_id = %s",
                (str(user_id),),
            )
        )

    # =========================================================================
    # Aggregate / Query helpers (v0.48.x)
    # =========================================================================

    def count_users(self, active_only: bool = False) -> int:
        """Return the total number of users.

        Args:
            active_only: When True, count only active (is_active = TRUE) users.

        Returns:
            User count.
        """
        if active_only:
            rows = self._execute("SELECT COUNT(*) as count FROM users WHERE is_active = TRUE")
        else:
            rows = self._execute("SELECT COUNT(*) as count FROM users")
        return int(rows[0]["count"]) if rows else 0

    def list_distinct_roles(self) -> list[str]:
        """Return a sorted list of all distinct role names currently assigned to users.

        Roles are stored as a JSON array per row; this method unnests and
        deduplicates them across all users.

        Returns:
            Sorted list of unique role name strings.
        """
        import json

        rows = self._execute("SELECT DISTINCT roles FROM users")
        all_roles: set[str] = set()
        for row in rows:
            roles = json.loads(row["roles"]) if row["roles"] else []
            all_roles.update(roles)
        return sorted(all_roles)

    def search_users(
        self,
        query: str | None = None,
        user_id: str | None = None,
        active_only: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Search / list raw session rows for display purposes.

        Returns raw dicts (not UserRecord objects) so callers can render them
        without additional conversion.  Intended for admin tools that need
        flexible filtering beyond what :meth:`list_users` provides.

        Args:
            query:      Filter by user_id equality (kept for backwards compat
                        with callers that pass a dynamic WHERE fragment; pass
                        ``None`` to skip).
            user_id:    Explicit user_id filter applied as ``user_id = %s``.
            active_only: When True, add ``is_active = TRUE`` to the WHERE clause.
            limit:      Maximum rows to return.
            offset:     Number of rows to skip.

        Returns:
            List of raw row dicts ordered by ``created_at DESC``.
        """
        conditions: list[str] = []
        params: list[object] = []

        if user_id is not None:
            conditions.append("user_id = %s")
            params.append(user_id)

        if active_only:
            conditions.append("is_active = TRUE")

        where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"SELECT * FROM users{where_clause} ORDER BY created_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        return self._execute(sql, tuple(params))

    def list_sessions(
        self,
        user_id: str | None = None,
        active_only: bool = True,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return raw session rows, optionally filtered.

        Args:
            user_id:    If provided, restrict to sessions for this user.
            active_only: When True, exclude expired sessions.
            limit:      Maximum rows to return.

        Returns:
            List of raw row dicts ordered by ``created_at DESC``.
        """
        conditions: list[str] = []
        params: list[object] = []

        if user_id is not None:
            conditions.append("user_id = %s")
            params.append(user_id)

        if active_only:
            conditions.append("expires_at > %s")
            params.append(datetime.now(UTC).isoformat())

        where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"SELECT * FROM sessions{where_clause} ORDER BY created_at DESC LIMIT %s"
        params.append(limit)

        return self._execute(sql, tuple(params))

    def store_totp_secret_pending(self, user_id: UUID, secret: str) -> None:
        """Store a TOTP secret without enabling TOTP (pending confirmation).

        Use this during TOTP setup to persist the secret before the user
        has verified their first code.  Call :meth:`enable_totp` once the
        verification succeeds.

        Args:
            user_id: User UUID.
            secret:  Base32-encoded TOTP secret to store.
        """
        self._execute_modify(
            "UPDATE users SET totp_secret = %s, totp_enabled = FALSE, updated_at = %s "
            "WHERE id = %s",
            (secret, datetime.now(UTC).isoformat(), str(user_id)),
        )
