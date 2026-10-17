"""The one place a proven identity becomes a signed-in session (#1804, DD-014).

Every primary sign-in path — password (JSON and form), signup, magic link, social
OAuth, enterprise OIDC, password reset/change — ends in :func:`complete_sign_in`,
and a verified second factor ends in :func:`finish_sign_in`. Nothing else in the
sign-in flows calls ``AuthStore.create_session``.

``complete_sign_in``:

1. resolves the org the session lands in (``activate_session_for_login``: one
   membership or the host's pins ``active_membership_id``; several → the picker;
   host-pinned with none → 403) — or takes the membership an enterprise IdP join
   already proved;
2. if two-factor sign-in is enabled and the user has a factor enrolled, or holds a
   role in ``enforce_for_roles``, opens a challenge instead of a session: a short-lived,
   hashed, single-use token in the ``dazzle_2fa`` cookie (and the JSON body) that is
   not a session and authenticates nothing but the second-factor step;
3. otherwise calls ``finish_sign_in``.

``finish_sign_in`` mints the session with the resolved membership and the second
factor it completed (``sessions.mfa_*``), deletes any pre-auth session id (#1198),
sets the session + CSRF cookies, clears the challenge cookie and emits
``auth.user.logged_in``. The 2FA verify routes (JSON and form) call it with the
membership and landing page the challenge recorded, so a password + TOTP sign-in
lands in exactly the org a password-only one would (#1804).
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Literal

from fastapi import HTTPException
from fastapi.responses import JSONResponse, RedirectResponse, Response

from dazzle.core.ir.security import TwoFactorConfig
from dazzle.core.strings import normalize_role
from dazzle.http.runtime.auth.cookie_name import read_session_id, set_session_cookies
from dazzle.http.runtime.auth.crypto import cookie_secure
from dazzle.http.runtime.auth.events import emit_user_logged_in, emit_user_registered
from dazzle.http.runtime.auth.forbidden_org import forbidden_org_response
from dazzle.http.runtime.auth.models import SecondFactorProof
from dazzle.http.runtime.auth.org_activation import (
    FORBIDDEN_SENTINEL,
    Activated,
    HostForbidden,
    _login_redirect_for_outcome,
    activate_session_for_login,
    memberships_required,
)
from dazzle.http.runtime.auth.store_two_factor import (
    CHALLENGE_TTL,
    PURPOSE_ENROL,
    PURPOSE_VERIFY,
)

CHALLENGE_COOKIE = "dazzle_2fa"
# app.state attribute carrying the app's TwoFactorConfig (set by AuthSubsystem).
TWO_FACTOR_STATE_ATTR = "two_factor"
CHALLENGE_PAGE = "/2fa/challenge"
SETUP_PAGE = "/2fa/setup"

SignInMode = Literal["json", "redirect"]
SignInEvent = Literal["logged_in", "registered", "none"]


@dataclass(frozen=True)
class Landing:
    """Where a sign-in lands: the pinned membership (if one resolved) and the page."""

    membership_id: str | None
    redirect_to: str


def two_factor_config(request: Any) -> TwoFactorConfig | None:
    """The app's two-factor policy when ``[auth.two_factor]`` is enabled, else None."""
    state = getattr(getattr(request, "app", None), "state", None)
    cfg = getattr(state, TWO_FACTOR_STATE_ATTR, None)
    return cfg if isinstance(cfg, TwoFactorConfig) and cfg.enabled else None


def json_active_membership_id(auth_store: Any, user: Any, request: Any) -> str | None:
    """Phase-2 activation for the JSON sign-in paths (auth Plan 1b).

    The membership id to pin when exactly one org resolves (single membership or
    host-pin match); 403 when host-pinned to an org the identity isn't in. For the
    picker/no-orgs cases there is no HTML redirect to serve, so the session is
    created membership-less — the RLS fence then denies until the client picks via
    ``POST /auth/switch-org``. #1418: the host-pin 403 applies only when the app
    gates login on membership.
    """
    outcome = activate_session_for_login(auth_store, user, request)
    if isinstance(outcome, HostForbidden):
        if memberships_required(request):
            raise HTTPException(status_code=403, detail="no membership for this organization")
        return None
    if isinstance(outcome, Activated):
        return outcome.membership_id
    return None


def _resolve_landing(
    request: Any, store: Any, user: Any, mode: SignInMode, next_url: str
) -> Landing | Response:
    if mode == "json":
        return Landing(json_active_membership_id(store, user, request), next_url)
    outcome = activate_session_for_login(store, user, request)
    membership_id, redirect_to = _login_redirect_for_outcome(
        outcome, next_url, memberships_required=memberships_required(request)
    )
    if redirect_to == FORBIDDEN_SENTINEL:
        return forbidden_org_response(request)  # #1393: branded host-pin 403
    return Landing(membership_id, redirect_to)


def _membership_roles(store: Any, membership_id: str | None) -> list[str]:
    if not membership_id:
        return []
    membership = store.get_membership(membership_id)
    return list(getattr(membership, "roles", None) or [])


def second_factor_owed(
    cfg: TwoFactorConfig | None, user: Any, membership_roles: list[str]
) -> str | None:
    """``verify`` / ``enrol`` when this sign-in must complete a second factor, else None."""
    if cfg is None:
        return None
    if getattr(user, "two_factor_enabled", False) is True:
        return PURPOSE_VERIFY
    enforced = {normalize_role(r) for r in cfg.enforce_for_roles}
    held = {normalize_role(r) for r in [*(getattr(user, "roles", None) or []), *membership_roles]}
    return PURPOSE_ENROL if enforced & held else None


def enrolled_methods(cfg: TwoFactorConfig | None, user: Any) -> list[str]:
    """The challenge methods this user can answer (recovery when codes were issued)."""
    allowed = {m.value for m in cfg.methods} if cfg else set()
    methods = [
        m
        for m, on in (("totp", user.totp_enabled), ("email_otp", user.email_otp_enabled))
        if on and m in allowed
    ]
    if getattr(user, "recovery_codes_generated", False):
        methods.append("recovery")
    return methods


def set_challenge_cookie(response: Response, request: Any, token: str) -> None:
    response.set_cookie(
        key=CHALLENGE_COOKIE,
        value=token,
        httponly=True,
        secure=cookie_secure(request),
        samesite="lax",
        path="/",
        max_age=int(CHALLENGE_TTL.total_seconds()),
    )


async def complete_sign_in(
    request: Any,
    store: Any,
    user: Any,
    *,
    method: str,
    mode: SignInMode,
    next_url: str = "/app",
    pinned_membership_id: str | None = None,
    membership_pinned: bool = False,
    second_factor: SecondFactorProof | None = None,
    json_body: dict[str, Any] | None = None,
    status_code: int = 200,
    session_days: int | None = None,
    cookie_name: str = "dazzle_session",
    event: SignInEvent = "logged_in",
) -> Response:
    """Finish a proven primary sign-in: a session, or a second-factor challenge.

    ``mode="redirect"`` answers 303 to the landing page (or the challenge / enrolment
    page); ``mode="json"`` answers ``json_body`` (or ``{"status": "2fa_required", …}``).
    ``membership_pinned`` skips activation for a membership the caller already proved
    (enterprise OIDC). ``second_factor`` is a factor this sign-in already carries (an
    IdP ``amr``, or the old session's on a password change), which skips the challenge.
    """
    if membership_pinned:
        landing: Landing | Response = Landing(pinned_membership_id, next_url)
    else:
        landing = _resolve_landing(request, store, user, mode, next_url)
    if isinstance(landing, Response):
        return landing

    cfg = two_factor_config(request)
    purpose = None
    if second_factor is None and cfg is not None:
        purpose = second_factor_owed(cfg, user, _membership_roles(store, landing.membership_id))
    if purpose is not None:
        token = store.create_2fa_challenge(
            user.id,
            purpose=purpose,
            primary_method=method,
            membership_id=landing.membership_id,
            redirect_to=landing.redirect_to,
        )
        response: Response
        if mode == "json":
            response = JSONResponse(
                content={
                    "status": "2fa_required" if purpose == PURPOSE_VERIFY else "2fa_enrol_required",
                    "methods": enrolled_methods(cfg, user),
                    "challenge_token": token,
                }
            )
        else:
            page = CHALLENGE_PAGE if purpose == PURPOSE_VERIFY else SETUP_PAGE
            response = RedirectResponse(url=page, status_code=303)
        set_challenge_cookie(response, request, token)
        if event == "registered":  # the account exists even though no session does yet
            await emit_user_registered(user, session_id=None)
        return response

    if mode == "json":
        body = json_body if json_body is not None else _default_json(user, landing.redirect_to)
        response = JSONResponse(content=body, status_code=status_code)
    else:
        response = RedirectResponse(url=landing.redirect_to, status_code=303)
    return await finish_sign_in(
        request,
        store,
        user,
        response,
        membership_id=landing.membership_id,
        method=method,
        second_factor=second_factor,
        session_days=session_days,
        cookie_name=cookie_name,
        event=event,
    )


def _default_json(user: Any, redirect_url: str) -> dict[str, Any]:
    return {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "roles": user.roles,
        },
        "redirect_url": redirect_url,
        "message": "Login successful",
    }


async def finish_sign_in(
    request: Any,
    store: Any,
    user: Any,
    response: Response,
    *,
    membership_id: str | None,
    method: str,
    second_factor: SecondFactorProof | None,
    session_days: int | None = None,
    cookie_name: str = "dazzle_session",
    event: SignInEvent = "logged_in",
) -> Response:
    """Mint the session on ``response``: membership, second factor, cookies, event."""
    pre_auth_sid = read_session_id(request, default=cookie_name)
    kwargs: dict[str, Any] = {}
    if session_days is not None:
        kwargs["expires_in"] = timedelta(days=session_days)
    session = store.create_session(
        user,
        ip_address=request.client.host if getattr(request, "client", None) else None,
        user_agent=request.headers.get("user-agent"),
        active_membership_id=membership_id,
        second_factor=second_factor,
        **kwargs,
    )
    # Session-fixation defence (#1198): the pre-auth id never survives sign-in.
    if pre_auth_sid and pre_auth_sid != session.id:
        store.delete_session(pre_auth_sid)
    set_session_cookies(
        response,
        request,
        session_id=session.id,
        csrf_secret=session.csrf_secret,
        user_roles=list(getattr(user, "roles", None) or []),
        default_cookie_name=cookie_name,
        max_age=session_days * 24 * 60 * 60 if session_days is not None else None,
    )
    if request.cookies.get(CHALLENGE_COOKIE):
        response.delete_cookie(CHALLENGE_COOKIE, path="/")
    if event == "logged_in":
        factor = f"+{second_factor.method}" if second_factor is not None else ""
        await emit_user_logged_in(user, session_id=session.id, method=f"{method}{factor}")
    elif event == "registered":
        await emit_user_registered(user, session_id=session.id)
    return response
