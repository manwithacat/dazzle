"""Native enterprise OIDC ConnectionProvider (auth Plan 4b).

Implements the 4a ``ConnectionProvider`` seam for per-org enterprise OIDC by
wrapping a per-connection authlib ``StarletteOAuth2App``. The client is built
lazily from the connection's non-secret ``config`` (issuer / discovery URL /
client_id) plus the decrypted ``client_secret`` from ``connection.secrets``.

**id_token validation is delegated to authlib** — ``authorize_access_token``
verifies the token's signature/iss/aud/exp/nonce against the discovery doc's
``jwks_uri``. We never parse or trust the JWT ourselves (no hand-rolled token
crypto — the well-tested library owns the security-critical path).

This slice (4b.i) ships the provider + its registration. The enterprise routes,
org-resolution, JIT membership, and group→persona mapping that *drive* it land
in 4b.ii — the account-takeover-risk identity-join gets its own focused review.
"""

from __future__ import annotations

import logging
from typing import Any

from dazzle.http.runtime.auth.connections import (
    AssertedIdentity,
    ConnectionError,
    ConnectionRecord,
    register_provider,
)

_logger = logging.getLogger(__name__)

# One stable redirect URI per app — the admin registers exactly this with their
# IdP. The connection is carried in the OAuth ``state`` (wired in 4b.ii), so a
# single callback endpoint serves every org's enterprise OIDC connection.
_CALLBACK_PATH = "/auth/enterprise/callback"

# Default OIDC scopes — minimum-viable (matches the global-SSO default).
_DEFAULT_SCOPE = "openid email profile"

# Default claim carrying IdP group membership. Overridable per connection via
# ``config["groups_claim"]`` (Azure emits ``groups``; Okta often a custom claim).
_DEFAULT_GROUPS_CLAIM = "groups"


def _coerce_groups(value: Any) -> list[str]:
    """Normalize a group claim (list, scalar, or absent) to ``list[str]``."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(g) for g in value if g is not None and str(g) != ""]
    return [str(value)]


class NativeOIDCProvider:
    """Native enterprise OIDC via authlib.

    One instance is registered for ``(oidc, native)``; it memoizes one authlib
    client per connection id so each org's credentials stay isolated.
    """

    CALLBACK_PATH = _CALLBACK_PATH

    def __init__(self) -> None:
        # connection.id → (revision, authlib StarletteOAuth2App). Built once per
        # connection *revision*; carries that org's client_id/secret only. Keying
        # on the revision (updated_at) means a config/secret rotation rebuilds the
        # client instead of silently reusing stale credentials — critical because
        # the usual reason to rotate a client_secret is that the old one leaked.
        # (Contract: any connection mutation must bump updated_at, which the store
        # does on write.)
        self._clients: dict[str, tuple[str, Any]] = {}

    def _revision(self, connection: ConnectionRecord) -> str:
        return connection.updated_at.isoformat()

    def _client(self, connection: ConnectionRecord) -> Any:
        """Return a memoized authlib client for ``connection`` (built lazily).

        Rebuilds when the connection's revision (``updated_at``) changes so a
        rotated secret / repointed issuer takes effect without a process restart.
        Raises ``ConnectionError`` when the connection lacks the minimum config
        to drive OIDC (a fail-loud config gap, not a silent half-working client).
        """
        revision = self._revision(connection)
        cached = self._clients.get(connection.id)
        if cached is not None and cached[0] == revision:
            return cached[1]

        config = connection.config or {}
        client_id = config.get("client_id")
        client_secret = (connection.secrets or {}).get("client_secret")
        issuer = config.get("issuer")
        discovery_url = config.get("discovery_url") or (
            f"{issuer.rstrip('/')}/.well-known/openid-configuration" if issuer else None
        )
        if not client_id:
            raise ConnectionError(
                f"OIDC connection {connection.id!r}: config.client_id is required"
            )
        if not discovery_url:
            raise ConnectionError(
                f"OIDC connection {connection.id!r}: config.discovery_url or config.issuer "
                "is required (one supplies the OIDC discovery document)"
            )

        # Lazy import — keeps authlib in the optional [sso] extra.
        from authlib.integrations.starlette_client import OAuth

        oauth = OAuth()
        name = f"conn_{connection.id}"
        oauth.register(
            name=name,
            client_id=client_id,
            client_secret=client_secret,
            server_metadata_url=discovery_url,
            client_kwargs={"scope": config.get("scope") or _DEFAULT_SCOPE},
        )
        client = getattr(oauth, name)
        self._clients[connection.id] = (revision, client)
        return client

    def _callback_url(self, request: Any) -> str:
        base = str(request.base_url).rstrip("/")
        return f"{base}{self.CALLBACK_PATH}"

    async def initiate(self, connection: ConnectionRecord, request: Any) -> str:
        """Begin the IdP login — return the authorize URL to redirect to.

        authlib stashes the ``state``/``nonce`` in ``request.session`` as a side
        effect; the route persists that session and rebuilds the redirect.
        """
        client = self._client(connection)
        result = await client.authorize_redirect(request, self._callback_url(request))
        # authorize_redirect returns a RedirectResponse; the route owns the final
        # response object, so we hand back just the Location URL.
        location: str = result.headers["location"]
        return location

    async def callback(self, connection: ConnectionRecord, request: Any) -> AssertedIdentity:
        """Validate the IdP response and assert the verified identity.

        Token validation (signature/iss/aud/exp/nonce) happens inside authlib's
        ``authorize_access_token`` against the discovery ``jwks_uri``. We only
        enforce identity-level invariants (email present + not explicitly
        unverified) on top of the cryptographically-validated claims.
        """
        client = self._client(connection)
        token = await client.authorize_access_token(request)

        # OIDC: cryptographically-validated claims ride in token["userinfo"]
        # (authlib parsed + verified the id_token during the exchange when the
        # discovery doc exposes jwks_uri). When that's absent we fall back to the
        # UserInfo endpoint — fetched with a validated access token, but NOT itself
        # signed, so its claims are weaker. We record which source we used so a
        # downstream identity-join (4b.ii) can apply differential trust.
        userinfo = token.get("userinfo") or {}
        claims_source = "id_token"
        if not userinfo:
            userinfo = await client.userinfo(token=token)
            claims_source = "userinfo_endpoint"

        email = (userinfo.get("email") or "").strip().lower()
        if not email:
            # Refuse rather than assert an empty identity — an OIDC response with
            # no email can't be joined to a global Identity.
            raise ConnectionError(
                f"OIDC connection {connection.id!r}: provider returned no email claim"
            )
        # A missing email_verified is tolerated (some IdPs omit it); an explicit
        # false is a hard refusal (the IdP is telling us the address is unproven).
        if userinfo.get("email_verified") is False:
            raise ConnectionError(
                f"OIDC connection {connection.id!r}: provider asserted email_verified=false"
            )

        groups_claim = (connection.config or {}).get("groups_claim") or _DEFAULT_GROUPS_CLAIM
        groups = _coerce_groups(userinfo.get(groups_claim))
        return AssertedIdentity(
            email=email, attributes=dict(userinfo), groups=groups, claims_source=claims_source
        )


def register_native_oidc() -> None:
    """Register the native OIDC provider for ``(oidc, native)`` (called at startup)."""
    register_provider("oidc", "native", NativeOIDCProvider())
