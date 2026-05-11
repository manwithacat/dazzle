"""SSO provider configuration (Phase 1.C, v0.67.39).

Deployments enable SSO by setting environment variables (or
loading a `[auth.sso.<provider>]` block from `dazzle.toml`) and
attaching the resulting list of `SsoProviderConfig` to
`app.state.sso_providers`. The auth views consult that list to
decide which "Continue with X" buttons to render; the route
handlers in `sso_routes.py` consult the same list to drive the
OAuth dance.

Same-domain callback only — per the Phase 1 locked decision (Q3).
The callback URL is computed at request time as
`<request.base_url>/auth/sso/<provider>/callback`, so a deployment
that only sets `client_id` + `client_secret` works without
configuring redirect URIs separately.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

ProviderName = Literal["google", "microsoft"]


_PROVIDER_DEFAULTS: dict[ProviderName, dict[str, str]] = {
    "google": {
        "display_name": "Google",
        "discovery_url": "https://accounts.google.com/.well-known/openid-configuration",
        "default_scopes": "openid email profile",
    },
    "microsoft": {
        "display_name": "Microsoft",
        # The /common tenant accepts both personal accounts and any
        # work/school AAD tenant — appropriate default for the
        # "consumer + corporate" deployment.
        "discovery_url": (
            "https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration"
        ),
        "default_scopes": "openid email profile User.Read",
    },
}


@dataclass(frozen=True)
class SsoProviderConfig:
    """One enabled OIDC provider.

    Fields:
        name: canonical provider key (``"google"`` or ``"microsoft"``).
        display_name: human-readable label rendered on the sign-in
            button (e.g. ``"Continue with Google"`` — the "Continue
            with" prefix is added by the view).
        client_id: OAuth2 client ID issued by the provider.
        client_secret: OAuth2 client secret. Treat as sensitive;
            never logged.
        discovery_url: OIDC discovery document URL. Authlib reads
            authorize / token / userinfo endpoints from this metadata.
        scopes: space-separated OAuth scopes. Defaults to the
            provider's minimum-viable set (openid + email + profile).
    """

    name: ProviderName
    display_name: str
    client_id: str
    client_secret: str
    discovery_url: str
    scopes: str

    def __post_init__(self) -> None:
        if not self.client_id:
            raise ValueError(f"SSO provider {self.name!r}: client_id is required")
        if not self.client_secret:
            raise ValueError(f"SSO provider {self.name!r}: client_secret is required")


def load_sso_providers_from_env(
    *,
    env: dict[str, str] | None = None,
) -> tuple[SsoProviderConfig, ...]:
    """Construct `SsoProviderConfig`s from environment variables.

    Recognised variables:
        DAZZLE_SSO_GOOGLE_CLIENT_ID, DAZZLE_SSO_GOOGLE_CLIENT_SECRET,
        DAZZLE_SSO_GOOGLE_SCOPES (optional)
        DAZZLE_SSO_MICROSOFT_CLIENT_ID, DAZZLE_SSO_MICROSOFT_CLIENT_SECRET,
        DAZZLE_SSO_MICROSOFT_SCOPES (optional)

    A provider is enabled when both its client_id and client_secret
    are set. Missing either → provider silently omitted (no SSO
    button rendered, no route handler matches). This is the
    deployment-time opt-in pattern.

    Returns an immutable tuple — pass it to
    `app.state.sso_providers = ...` at app construction time.
    """
    source = env if env is not None else dict(os.environ)
    providers: list[SsoProviderConfig] = []
    for name, defaults in _PROVIDER_DEFAULTS.items():
        upper = name.upper()
        client_id = source.get(f"DAZZLE_SSO_{upper}_CLIENT_ID", "").strip()
        client_secret = source.get(f"DAZZLE_SSO_{upper}_CLIENT_SECRET", "").strip()
        if not client_id or not client_secret:
            continue
        scopes = (
            source.get(f"DAZZLE_SSO_{upper}_SCOPES", defaults["default_scopes"]).strip()
            or defaults["default_scopes"]
        )
        providers.append(
            SsoProviderConfig(
                name=name,
                display_name=defaults["display_name"],
                client_id=client_id,
                client_secret=client_secret,
                discovery_url=defaults["discovery_url"],
                scopes=scopes,
            )
        )
    return tuple(providers)


def get_provider(app_state: object, name: str) -> SsoProviderConfig | None:
    """Return the registered config for ``name`` or ``None``.

    Used by the route handlers to validate the `{provider}` path
    parameter without trusting the user-supplied string.
    """
    providers: tuple[SsoProviderConfig, ...] = getattr(app_state, "sso_providers", ())
    for p in providers:
        if p.name == name:
            return p
    return None
