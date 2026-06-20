"""Per-org enterprise connections + the ConnectionProvider seam (auth Plan 4a).

A ``Connection`` is a framework-owned, org-fenced auth-store record (OIDC/SAML/
SCIM config). Non-secret ``config`` is stored plaintext; secret material is a
single AES-GCM-encrypted blob (see ``connection_crypto``). Domains route to a
connection only when VERIFIED (an unverified claimed domain can't hijack another
org's SSO — spec §5).

The ``ConnectionProvider`` Protocol is the seam: native (authlib OIDC / pysaml2
SAML / SCIM 2.0) vs delegated (a vendor), chosen per connection by ``(type,
provider)``. 4a defines the seam only — ``resolve_provider`` raises until 4b/4c
register the native implementations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


class ConnectionError(RuntimeError):
    """A connection operation cannot proceed (e.g. no provider for type/provider)."""


CONNECTIONS_DDL = """
CREATE TABLE IF NOT EXISTS connections (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    type TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'native',
    domains TEXT NOT NULL DEFAULT '[]',
    verified_domains TEXT NOT NULL DEFAULT '[]',
    config TEXT NOT NULL DEFAULT '{}',
    encrypted_secret TEXT,
    previous_encrypted_secret TEXT,
    previous_secret_expires_at TEXT,
    group_mapping TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

CONNECTIONS_INDEXES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS ix_connections_tenant ON connections(tenant_id)",
)


@dataclass(frozen=True)
class ConnectionRecord:
    """A per-org enterprise auth connection. ``secrets`` is decrypted in memory on
    read — its values are masked in ``repr`` so a logged/traced record never leaks
    secret material."""

    id: str
    tenant_id: str
    type: str  # oidc | saml | scim
    provider: str  # native | <vendor>
    domains: list[str]
    verified_domains: list[str]
    config: dict[str, Any]  # non-secret (issuer, client_id, endpoints)
    secrets: dict[str, Any]  # decrypted on read; encrypted at rest
    group_mapping: dict[str, str]  # IdP group/attr → persona (default-deny if unmapped)
    status: str
    created_at: datetime
    updated_at: datetime

    def __repr__(self) -> str:
        # Never render secret values (avoids leaking via logs / tracebacks).
        masked = dict.fromkeys(self.secrets, "***")
        return (
            f"ConnectionRecord(id={self.id!r}, tenant_id={self.tenant_id!r}, "
            f"type={self.type!r}, provider={self.provider!r}, status={self.status!r}, "
            f"secrets={masked!r})"
        )


@dataclass(frozen=True)
class RewrapResult:
    """Outcome of an encryption-key rotation rewrap (``rewrap_all_connection_secrets``).

    ``rewrapped`` = secrets moved onto the primary key; ``already_current`` = secrets that
    were already on it (idempotent skip); ``failed`` = connection ids no configured key
    could decrypt (the operator must set ``DAZZLE_CONNECTION_SECRET_OLD`` to the right key).
    """

    rewrapped: int
    already_current: int
    failed: list[str]


@dataclass(frozen=True)
class ConnectionSecretEvent:
    """One append-only rotation-audit row (#1342). ``detail`` is non-secret JSON
    context (connection type, grace flag/expiry) — a secret value never appears here."""

    id: str
    connection_id: str
    tenant_id: str
    event: str  # rotated | revoked_previous | encryption_key_rewrapped
    actor: str | None
    detail: dict[str, Any]
    at: datetime


@dataclass(frozen=True)
class AssertedIdentity:
    """What a SSO provider's ``callback`` asserts after validating the IdP response.

    ``claims_source`` records the provenance of the claims so a downstream
    identity-join can apply differential trust: ``"id_token"`` claims were
    cryptographically validated (signature/iss/aud/exp/nonce) by the provider's
    token library, whereas ``"userinfo_endpoint"`` claims were fetched from the
    UserInfo endpoint with a validated access token but are not themselves signed.
    """

    email: str
    attributes: dict[str, Any] = field(default_factory=dict)
    groups: list[str] = field(default_factory=list)
    claims_source: str = "id_token"


@runtime_checkable
class ConnectionProvider(Protocol):
    """The swappable seam — native or delegated, chosen per connection.

    Call sites never know who implements it. SSO providers implement
    ``initiate``/``callback``; SCIM providers expose REST handlers (added in 4c).

    Both methods are ``async`` — the native OIDC implementation (4b) drives
    authlib's async OAuth flow, and SAML (Plan 5) does async metadata fetches.
    """

    async def initiate(self, connection: ConnectionRecord, request: Any) -> str:
        """Return the redirect URL that starts the IdP login (SSO)."""
        ...

    async def callback(self, connection: ConnectionRecord, request: Any) -> AssertedIdentity:
        """Validate the IdP response and return the asserted identity (SSO)."""
        ...


# (type, provider) → implementation. 4b/4c register the natives; empty in 4a.
_PROVIDERS: dict[tuple[str, str], ConnectionProvider] = {}


def register_provider(conn_type: str, provider: str, impl: ConnectionProvider) -> None:
    """Register a ConnectionProvider for a (type, provider) pair (called at startup)."""
    _PROVIDERS[(conn_type, provider)] = impl


def resolve_provider(connection: Any) -> ConnectionProvider:
    """Return the provider for ``connection``'s (type, provider), or raise.

    Fail-loud: an unregistered pair raises ``ConnectionError`` — better than a
    silent no-op when a connection references a provider the build doesn't have.
    """
    if connection.type == "domain":
        raise ConnectionError("domain connections are routing-only and have no IdP provider")
    key = (connection.type, connection.provider)
    impl = _PROVIDERS.get(key)
    if impl is None:
        raise ConnectionError(
            f"no provider registered for connection type={connection.type!r} "
            f"provider={connection.provider!r}"
        )
    return impl
