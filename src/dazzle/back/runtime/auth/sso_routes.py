"""SSO route handlers (Phase 1.C, v0.67.39).

Two endpoints per provider:
  GET /auth/sso/{provider}            — kick off OAuth flow
  GET /auth/sso/{provider}/callback   — receive code, finish flow

The OAuth dance is driven by Authlib's `StarletteOAuth2App`. Each
configured provider is registered once at startup (lazy import so
the framework is usable without the optional `authlib` dep when
no SSO providers are configured).

User provisioning policy: on a successful callback, if the email
matches an existing user we treat it as a sign-in (the OAuth proof
that the user controls the email is sufficient — same trust level
as a magic-link consumer). Otherwise we create a passwordless user
and sign them in.

Same-origin redirect protection: the `?next=` parameter is checked
via the same `_is_safe_redirect_path` helper used in the magic-link
routes. Unsafe values silently fall back to `/app`.
"""

import logging
import secrets
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse, Response

from dazzle.back.runtime.auth.cookie_name import read_session_id, select_write_name
from dazzle.back.runtime.auth.crypto import cookie_secure
from dazzle.back.runtime.auth.forbidden_org import forbidden_org_response
from dazzle.back.runtime.auth.org_activation import (
    FORBIDDEN_SENTINEL,
    _login_redirect_for_outcome,
    activate_session_for_login,
    memberships_required,
)
from dazzle.back.runtime.auth.redirect_safety import (
    is_safe_redirect_path as _is_safe_redirect_path,
)
from dazzle.back.runtime.auth.sso_config import SsoProviderConfig, get_provider

_logger = logging.getLogger(__name__)


def _build_callback_url(request: Request, provider_name: str) -> str:
    """Compose the absolute same-origin callback URL.

    Same shape as the magic-link `_build_magic_link_url` helper —
    `request.base_url` already carries the deployment's
    scheme + host + (optional) prefix.
    """
    base = str(request.base_url).rstrip("/")
    return f"{base}/auth/sso/{provider_name}/callback"


def _get_or_create_oauth_client(app_state: object, provider: SsoProviderConfig) -> Any:
    """Return a memoised Authlib `StarletteOAuth2App` for ``provider``.

    Built lazily so `authlib` only imports when SSO is in use.
    The clients live on `app.state._sso_clients` keyed by provider
    name; first access for a given provider creates and registers it.
    """
    clients = getattr(app_state, "_sso_clients", None)
    if clients is None:
        clients = {}
        # `app.state` is a SimpleNamespace; setattr is sufficient.
        app_state._sso_clients = clients  # type: ignore[attr-defined]

    existing = clients.get(provider.name)
    if existing is not None:
        return existing

    # Lazy import — keeps `authlib` an optional dep.
    from authlib.integrations.starlette_client import OAuth

    oauth = OAuth()
    oauth.register(
        name=provider.name,
        client_id=provider.client_id,
        client_secret=provider.client_secret,
        server_metadata_url=provider.discovery_url,
        client_kwargs={"scope": provider.scopes},
    )
    client = getattr(oauth, provider.name)
    clients[provider.name] = client
    return client


async def _provision_or_login(
    *,
    auth_store: Any,
    email: str,
    display_name: str,
) -> Any:
    """Resolve a `UserRecord` for the OAuth-verified ``email``.

    If a user with that email already exists, return them. Otherwise
    create a passwordless user (random unguessable password fills the
    column — the user can later enable a real password via account
    settings if password-mode is on).
    """
    user = auth_store.get_user_by_email(email)
    if user is not None:
        return user
    return auth_store.create_user(
        email=email,
        password=secrets.token_urlsafe(48),
        username=display_name or None,
    )


def create_sso_routes(*, cookie_name: str = "dazzle_session") -> APIRouter:
    """SSO initiation + callback endpoints."""
    router = APIRouter(tags=["auth"])

    @router.get("/auth/sso/{provider}")
    async def sso_initiate(
        provider: str,
        request: Request,
        next: Annotated[str, Query()] = "/",
    ) -> RedirectResponse:
        """Redirect the user to the OAuth provider's authorize URL."""
        config = get_provider(request.app.state, provider)
        if config is None:
            return RedirectResponse(url="/login?error=sso_provider_unknown", status_code=303)
        client = _get_or_create_oauth_client(request.app.state, config)
        # Authlib stashes `next` in session via state; we pass it as
        # the redirect's `state=` kwarg so the callback can read it
        # back out without trusting the URL.
        if next and _is_safe_redirect_path(next) and next != "/":
            request.session["sso_next"] = next
        else:
            request.session.pop("sso_next", None)
        callback_url = _build_callback_url(request, provider)
        result: RedirectResponse = await client.authorize_redirect(request, callback_url)
        return result

    @router.get("/auth/sso/{provider}/callback")
    async def sso_callback(
        provider: str,
        request: Request,
    ) -> Response:
        """Exchange the code, fetch userinfo, sign the user in."""
        config = get_provider(request.app.state, provider)
        if config is None:
            return RedirectResponse(url="/login?error=sso_provider_unknown", status_code=303)

        client = _get_or_create_oauth_client(request.app.state, config)
        try:
            token = await client.authorize_access_token(request)
        except Exception as exc:  # noqa: BLE001 — surface in logs
            _logger.warning(  # nosemgrep
                "SSO callback: exchange failed for %s: %s",  # nosemgrep
                provider,
                exc,
            )
            return RedirectResponse(url="/login?error=sso_failed", status_code=303)

        # OpenID Connect: userinfo embedded in id_token or fetched
        # via `client.userinfo`. Authlib's `parse_id_token` already
        # ran during `authorize_access_token` when the discovery doc
        # exposes `jwks_uri`, so the verified claims are in
        # `token['userinfo']`.
        userinfo = token.get("userinfo") or {}
        if not userinfo:
            try:
                userinfo = await client.userinfo(token=token)
            except Exception as exc:  # noqa: BLE001 — surface in logs
                _logger.warning(
                    "SSO callback: userinfo fetch failed for %s: %s",
                    provider,
                    exc,
                )
                return RedirectResponse(url="/login?error=sso_failed", status_code=303)

        email = (userinfo.get("email") or "").strip().lower()
        if not email:
            _logger.warning(
                "SSO callback: provider %s returned no email — refusing",
                provider,
            )
            return RedirectResponse(url="/login?error=sso_no_email", status_code=303)

        # Some providers (Microsoft) omit `email_verified`; Google
        # always populates it. When present, require True.
        if userinfo.get("email_verified") is False:
            return RedirectResponse(url="/login?error=sso_email_unverified", status_code=303)

        display_name = userinfo.get("name") or userinfo.get("preferred_username") or ""
        auth_store = request.app.state.auth_store
        try:
            user = await _provision_or_login(
                auth_store=auth_store,
                email=email,
                display_name=display_name,
            )
        except Exception as exc:  # noqa: BLE001 — surface in logs
            _logger.warning(
                "SSO callback: provision_or_login failed for %s: %s",
                email,
                exc,
            )
            return RedirectResponse(url="/login?error=sso_failed", status_code=303)

        # Session-fixation defence (#1198): regenerate the session id on
        # SSO callback success — invalidate any pre-auth session cookie the
        # client presented so an attacker-planted id can't survive into the
        # authenticated state.
        pre_auth_sid = read_session_id(request, default=cookie_name)

        # Pull the next-URL the initiate route stashed in the session.
        next_url = request.session.pop("sso_next", "") if hasattr(request, "session") else ""
        safe_next = next_url if next_url and _is_safe_redirect_path(next_url) else "/app"

        # Phase 2 (auth Plan 1b): activate an org context for the proven identity.
        # For Activated the SSO next-URL is honoured; NeedsPicker/NoOrgs override it
        # to the picker / no-orgs page; HostForbidden → 403.
        outcome = activate_session_for_login(auth_store, user, request)
        membership_id, redirect_to = _login_redirect_for_outcome(
            outcome, safe_next, memberships_required=memberships_required(request)
        )
        if redirect_to == FORBIDDEN_SENTINEL:
            return forbidden_org_response(request)  # #1393: branded host-pin 403
        session = auth_store.create_session(user, active_membership_id=membership_id)
        if pre_auth_sid and pre_auth_sid != session.id:
            auth_store.delete_session(pre_auth_sid)

        response = RedirectResponse(url=redirect_to, status_code=303)
        response.set_cookie(
            key=select_write_name(
                request,
                user_roles=list(getattr(user, "roles", []) or []),
                default=cookie_name,
            ),
            value=session.id,
            httponly=True,
            secure=cookie_secure(request),
            samesite="lax",
        )
        # Declarative-CSRF Phase 1: bind the CSRF token to the full session minted
        # on SSO-callback success. httponly=False so htmx/JS can echo it into the
        # X-CSRF-Token header. Mirrors the auth cookie's flags above (no max_age =
        # session cookie). See
        # docs/superpowers/specs/2026-06-03-declarative-csrf-design.md.
        response.set_cookie(
            key="dazzle_csrf",
            value=session.csrf_secret,
            httponly=False,
            secure=cookie_secure(request),
            samesite="lax",
        )
        return response

    return router
