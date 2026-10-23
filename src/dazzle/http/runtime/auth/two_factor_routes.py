"""Two-factor sign-in routes (DD-014): challenge, enrolment, step-up, management.

Mounted only when ``[auth.two_factor] enabled = true``.

Pending sign-in (the ``dazzle_2fa`` challenge cookie, or ``challenge_token`` in a
JSON body — never a session):

* ``POST /auth/2fa/verify`` (JSON), ``POST /auth/2fa/verify/submit`` (form) — a TOTP,
  email or recovery code finishes the sign-in through ``sign_in.finish_sign_in``.
* ``POST /auth/2fa/challenge`` (JSON), ``POST /auth/2fa/email-otp-send/submit`` (form)
  — email a code (also for step-up on a signed-in session).
* ``POST /auth/2fa/challenge/extend`` — "More time" (#1842, WCAG 2.2.1): pushes the
  challenge deadline out by ``CHALLENGE_TTL``, capped at ``CHALLENGE_MAX_LIFETIME``.
  Answers JSON to the page script (``Accept: application/json``), else 303 back.
  CSRF-gated (``CSRFConfig.protected_paths``) although it carries no session.

A challenge that ran out of time sends the browser to ``/login?error=2fa_expired``
with the email filled in.

Enrolment (a signed-in session, or an ``enforce_for_roles`` enrolment challenge):
``POST /auth/2fa/setup/totp`` + ``/auth/2fa/verify/totp``, ``POST /auth/2fa/setup/email-otp``
+ ``/auth/2fa/verify/email-otp`` (JSON); ``/auth/2fa/setup/totp/submit``,
``/auth/2fa/setup/email-otp/submit``, ``/auth/2fa/verify/email-otp/submit`` (form).

Signed-in only: ``POST /auth/2fa/step-up`` (JSON) and ``/auth/2fa/step-up/submit`` (form)
record a second factor on the current session; ``GET /auth/2fa/status``;
``POST /auth/2fa/recovery/regenerate``, ``DELETE /auth/2fa/totp``,
``DELETE /auth/2fa/email-otp`` and ``POST /auth/2fa/settings/submit`` need a second
factor in the last 15 minutes.

Pages: ``/2fa/challenge``, ``/2fa/setup``, ``/2fa/settings``, ``/2fa/step-up``.

ADR-0014: no ``from __future__ import annotations`` in FastAPI route files.
"""

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Annotated, Any
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

import dazzle.http.runtime.rate_limit as _rl
from dazzle.core.ir.security import TwoFactorConfig
from dazzle.core.strings import normalize_role
from dazzle.http.runtime.auth.auth_views import leftover_honest_auth_token
from dazzle.http.runtime.auth.cookie_name import read_session_id
from dazzle.http.runtime.auth.models import (
    AuthContext,
    SecondFactorProof,
    TwoFactorCodeRequest,
    UserRecord,
)
from dazzle.http.runtime.auth.product_name import product_name
from dazzle.http.runtime.auth.redirect_safety import is_safe_redirect_path
from dazzle.http.runtime.auth.second_factor import (
    CODE_METHODS,
    EMAIL_PURPOSE_ENROL,
    EMAIL_PURPOSE_SIGN_IN,
    allowed_methods,
    confirm_enrolment,
    qr_data_uri,
    require_second_factor,
    send_email_code,
    verify_factor_code,
)
from dazzle.http.runtime.auth.sign_in import (
    CHALLENGE_COOKIE,
    enrolled_methods,
    finish_sign_in,
)
from dazzle.http.runtime.auth.store_two_factor import (
    EMAIL_CODE_TTL,
    PURPOSE_ENROL,
    PURPOSE_VERIFY,
    TwoFactorChallenge,
    generate_recovery_codes,
)
from dazzle.http.runtime.auth.totp import generate_totp_secret, get_totp_uri
from dazzle.http.runtime.auth.two_factor_views import (
    ChallengeTimeout,
    build_2fa_settings_view,
    build_2fa_setup_view,
    build_code_entry_view,
    build_recovery_codes_view,
)
from dazzle.render.fragment.renderer import FragmentRenderer

# Managing factors (disable, regenerate) needs a second factor this recent.
MANAGE_MAX_AGE_SECONDS = 15 * 60
JSON_SESSION_DAYS = 7
_INVALID_CODE = "That code didn't work. Check it and try again."
_LOCKED = "Too many wrong codes. Sign in again."
EXTEND_PATH = "/auth/2fa/challenge/extend"


@dataclass(frozen=True)
class _Enrolling:
    """Who is enrolling: a signed-in session, or an enrolment-only challenge."""

    user: UserRecord
    session_id: str | None
    challenge: TwoFactorChallenge | None


def _cfg(request: Request) -> TwoFactorConfig:
    cfg = getattr(request.app.state, "two_factor", None)
    assert isinstance(cfg, TwoFactorConfig)  # the router mounts only when configured
    return cfg


def _store(request: Request) -> Any:
    return request.app.state.auth_store


def _session_auth(request: Request) -> tuple[AuthContext, str] | None:
    session_id = read_session_id(request)
    if not session_id:
        return None
    ctx: AuthContext = _store(request).validate_session(session_id)
    if not ctx.is_authenticated or ctx.user is None:
        return None
    return ctx, session_id


def _challenge(request: Request, token: str = "") -> TwoFactorChallenge | None:
    raw = token or request.cookies.get(CHALLENGE_COOKIE, "")
    honest = leftover_honest_auth_token(raw)
    return _store(request).get_2fa_challenge(honest) if honest else None


def _challenge_gone(request: Request) -> RedirectResponse:
    """Back to sign-in when no live challenge is left (#1842, WCAG 2.2.1).

    A challenge that simply ran out of time names its user, so the sign-in page can
    say the code expired and fill in the email; a spent, locked or unknown token
    gets the same message without one.
    """
    url = "/login?error=2fa_expired"
    store = _store(request)
    honest = leftover_honest_auth_token(request.cookies.get(CHALLENGE_COOKIE, ""))
    user_id = store.expired_2fa_challenge_user_id(honest) if honest else None
    user: UserRecord | None = store.get_user_by_id(UUID(user_id)) if user_id else None
    if user is not None and user.is_active and user.email:
        url = f"{url}&email={quote(user.email, safe='@')}"
    return RedirectResponse(url=url, status_code=303)


def _challenge_timeout(ch: TwoFactorChallenge, method: str) -> ChallengeTimeout:
    """What the code page's timeout warning needs (#1842, WCAG 2.2.1)."""
    now = datetime.now(UTC)
    return ChallengeTimeout(
        expires_in=max(0, int((ch.expires_at - now).total_seconds())),
        extend_action=f"{EXTEND_PATH}?method={method}" if ch.can_extend else "",
        email_code_minutes=int(EMAIL_CODE_TTL.total_seconds() // 60),
    )


def _challenge_user(request: Request, ch: TwoFactorChallenge) -> UserRecord | None:
    user: UserRecord | None = _store(request).get_user_by_id(UUID(ch.user_id))
    return user if user is not None and user.is_active else None


def _enrolling(request: Request) -> _Enrolling | None:
    signed_in = _session_auth(request)
    if signed_in is not None:
        ctx, session_id = signed_in
        assert ctx.user is not None
        return _Enrolling(ctx.user, session_id, None)
    ch = _challenge(request)
    if ch is None or ch.purpose != PURPOSE_ENROL:
        return None
    user = _challenge_user(request, ch)
    return _Enrolling(user, None, ch) if user is not None else None


def _page(page: Any) -> HTMLResponse:
    return HTMLResponse(FragmentRenderer().render(page))


def _assets(request: Request) -> dict[str, Any]:
    """``css_links`` / ``js_scripts`` for the pages (per-deployment chrome overrides)."""
    state = request.app.state
    return {
        "css_links": tuple(
            getattr(state, "fragment_chrome_css_links", None) or ("/static/dist/dazzle.min.css",)
        ),
        "js_scripts": tuple(
            getattr(state, "fragment_chrome_js_scripts", None) or ("/static/dist/dazzle.min.js",)
        ),
    }


def _safe_next(raw: str, default: str = "/app") -> str:
    return raw if raw and raw != "/" and is_safe_redirect_path(raw) else default


def _user_json(user: UserRecord) -> dict[str, Any]:
    return {"id": str(user.id), "email": user.email, "username": user.username, "roles": user.roles}


def _enforced(cfg: TwoFactorConfig, user: UserRecord, ctx: AuthContext | None) -> bool:
    roles = [*user.roles, *(ctx.effective_roles if ctx is not None else [])]
    held = {normalize_role(r) for r in roles}
    return bool(held & {normalize_role(r) for r in cfg.enforce_for_roles})


def _method_or_400(method: str) -> str:
    if method not in CODE_METHODS:
        raise HTTPException(status_code=400, detail="Unknown two-factor method")
    return method


# ── finishing a pending sign-in ─────────────────────────────────────────────


async def _finish_challenge(
    request: Request,
    ch: TwoFactorChallenge,
    user: UserRecord,
    proof: SecondFactorProof,
    response: Response,
    *,
    session_days: int | None,
) -> Response:
    if not _store(request).consume_2fa_challenge(ch.token):
        raise HTTPException(status_code=401, detail="No pending sign-in")
    return await finish_sign_in(
        request,
        _store(request),
        user,
        response,
        membership_id=ch.membership_id,
        method=ch.primary_method,
        second_factor=proof,
        session_days=session_days,
    )


def _verify_pending(request: Request, ch: TwoFactorChallenge | None, method: str, code: str) -> Any:
    """``(user, proof)`` for a correct code on a live verify challenge; else an error token."""
    if ch is None or ch.purpose != PURPOSE_VERIFY:
        return "expired"
    user = _challenge_user(request, ch)
    if user is None:
        return "expired"
    proof = verify_factor_code(_store(request), user, _cfg(request), method, code)
    if proof is None:
        _store(request).fail_2fa_challenge(ch.token)
        return "invalid_code"
    return user, proof


# ── enrolment ────────────────────────────────────────────────────────────────


async def _confirm(
    request: Request, who: _Enrolling, method: str, code: str, *, as_json: bool
) -> Response:
    """Confirm the first code of a factor; finish sign-in (enrolment challenge) or record
    the factor on the signed-in session. Answers JSON or the recovery-codes page."""
    store = _store(request)
    action = f"enrol:{method}"
    if who.session_id and store.session_attempts_locked(who.session_id, action):
        raise HTTPException(status_code=429, detail=_LOCKED)
    result = confirm_enrolment(store, who.user, _cfg(request), method, code)
    if result is None:
        if who.challenge is not None:
            store.fail_2fa_challenge(who.challenge.token)
        elif who.session_id:
            store.fail_session_attempt(who.session_id, action, who.user.id)
        if as_json:
            raise HTTPException(status_code=400, detail="Invalid code")
        return RedirectResponse(url="/2fa/setup?error=invalid_code", status_code=303)
    proof, codes = result
    continue_url = who.challenge.redirect_to if who.challenge else "/2fa/settings"
    response: Response
    if as_json:
        body: dict[str, Any] = {"message": f"{method} enabled"}
        if codes:
            body["recovery_codes"] = codes
        if who.challenge is not None:
            body["user"] = _user_json(who.user)
            body["redirect_url"] = continue_url
        response = JSONResponse(content=body)
    elif codes:
        response = _page(
            build_recovery_codes_view(
                product_name=product_name(request),
                codes=codes,
                continue_url=continue_url,
                **_assets(request),
            )
        )
    else:
        response = RedirectResponse(url=continue_url, status_code=303)
    if who.challenge is not None:
        return await _finish_challenge(
            request,
            who.challenge,
            who.user,
            proof,
            response,
            session_days=JSON_SESSION_DAYS if as_json else None,
        )
    assert who.session_id is not None
    store.record_session_second_factor(who.session_id, proof)
    store.clear_session_attempts(who.session_id, action)
    return response


def _begin_totp(request: Request, who: _Enrolling) -> tuple[str, str]:
    """A fresh pending TOTP secret for ``who``: ``(secret, otpauth uri)``."""
    if who.user.totp_enabled:
        raise HTTPException(status_code=400, detail="The authenticator app is already on")
    secret = generate_totp_secret()
    _store(request).store_pending_totp_secret(who.user.id, secret)
    return secret, get_totp_uri(secret, who.user.email, issuer=product_name(request))


def _enrolling_or_401(request: Request) -> _Enrolling:
    who = _enrolling(request)
    if who is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return who


def _require_email_allowed(request: Request) -> None:
    if "email_otp" not in allowed_methods(_cfg(request)):
        raise HTTPException(status_code=400, detail="Email codes are not enabled")


# ── step-up and management ───────────────────────────────────────────────────


def _signed_in_or_401(request: Request) -> tuple[AuthContext, str]:
    signed_in = _session_auth(request)
    if signed_in is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return signed_in


def _step_up(request: Request, method: str, code: str) -> SecondFactorProof | None:
    ctx, session_id = _signed_in_or_401(request)
    assert ctx.user is not None
    store = _store(request)
    if store.session_attempts_locked(session_id, "step_up"):
        raise HTTPException(status_code=429, detail="Too many wrong codes. Try again later.")
    proof = verify_factor_code(store, ctx.user, _cfg(request), method, code)
    if proof is None:
        store.fail_session_attempt(session_id, "step_up", ctx.user.id)
        return None
    store.record_session_second_factor(session_id, proof)
    store.clear_session_attempts(session_id, "step_up")
    return proof


def _manage(request: Request, action: str) -> list[str] | None:
    """Run a settings action; returns new recovery codes for ``regenerate_recovery``."""
    auth = require_second_factor(request, max_age=MANAGE_MAX_AGE_SECONDS)
    user = auth.user
    assert user is not None
    store = _store(request)
    cfg = _cfg(request)
    if action == "regenerate_recovery":
        if not user.two_factor_enabled:
            raise HTTPException(status_code=400, detail="No two-step method is on")
        codes = generate_recovery_codes(cfg.recovery_code_count)
        store.replace_recovery_codes(user.id, codes)
        return codes
    if action not in ("disable_totp", "disable_email_otp"):
        raise HTTPException(status_code=400, detail="Unknown action")
    remaining = user.email_otp_enabled if action == "disable_totp" else user.totp_enabled
    if not remaining and _enforced(cfg, user, auth):
        raise HTTPException(status_code=400, detail="Your role needs a two-step method")
    if action == "disable_totp":
        store.disable_totp(user.id)
    else:
        store.disable_email_otp(user.id)
    return None


def create_two_factor_routes() -> APIRouter:
    """The two-factor API and pages (mounted when ``[auth.two_factor]`` is enabled)."""
    router = APIRouter(tags=["Two-Factor Authentication"])
    limited = _rl.safe_limit(_rl.limits.twofa_limit)

    # ── pending sign-in ──────────────────────────────────────────────────

    async def verify_json(request: Request, data: TwoFactorCodeRequest) -> Response:
        method = _method_or_400(data.method)
        ch = _challenge(request, data.challenge_token)
        outcome = _verify_pending(request, ch, method, data.code)
        if outcome == "expired":
            raise HTTPException(status_code=401, detail="No pending sign-in")
        if outcome == "invalid_code":
            raise HTTPException(status_code=401, detail="Invalid two-factor code")
        user, proof = outcome
        assert ch is not None
        response = JSONResponse(
            content={
                "user": _user_json(user),
                "redirect_url": ch.redirect_to,
                "message": "2FA verification successful",
            }
        )
        return await _finish_challenge(
            request, ch, user, proof, response, session_days=JSON_SESSION_DAYS
        )

    router.post("/auth/2fa/verify", include_in_schema=False)(limited(verify_json))

    async def verify_form(
        request: Request,
        code: Annotated[str, Form()] = "",
        method: Annotated[str, Query()] = "totp",
    ) -> Response:
        method = _method_or_400(method)
        ch = _challenge(request)
        outcome = _verify_pending(request, ch, method, code)
        if outcome == "expired":
            return _challenge_gone(request)
        if outcome == "invalid_code":
            return RedirectResponse(
                url=f"/2fa/challenge?method={method}&error=invalid_code", status_code=303
            )
        user, proof = outcome
        assert ch is not None
        response = RedirectResponse(url=ch.redirect_to, status_code=303)
        return await _finish_challenge(request, ch, user, proof, response, session_days=None)

    router.post("/auth/2fa/verify/submit", include_in_schema=False)(limited(verify_form))

    def _email_target(request: Request, token: str = "") -> UserRecord | None:
        """The user an email code goes to: a pending verify challenge, or the session."""
        ch = _challenge(request, token)
        if ch is not None and ch.purpose == PURPOSE_VERIFY:
            return _challenge_user(request, ch)
        signed_in = _session_auth(request)
        return signed_in[0].user if signed_in is not None else None

    async def send_code_json(request: Request, data: TwoFactorCodeRequest) -> dict[str, str]:
        user = _email_target(request, data.challenge_token)
        if user is None:
            raise HTTPException(status_code=401, detail="No pending sign-in")
        if not user.email_otp_enabled or "email_otp" not in allowed_methods(_cfg(request)):
            raise HTTPException(status_code=400, detail="Email codes are not on for this account")
        send_email_code(request, _store(request), user, EMAIL_PURPOSE_SIGN_IN)
        return {"message": "Code sent. Check your email."}

    router.post("/auth/2fa/challenge", include_in_schema=False)(limited(send_code_json))

    async def send_code_form(request: Request, next: Annotated[str, Query()] = "") -> Response:
        ch = _challenge(request)
        pending = ch is not None and ch.purpose == PURPOSE_VERIFY
        user = _email_target(request)
        if user is None:
            return _challenge_gone(request)
        if user.email_otp_enabled and "email_otp" in allowed_methods(_cfg(request)):
            send_email_code(request, _store(request), user, EMAIL_PURPOSE_SIGN_IN)
        target = (
            "/2fa/challenge?method=email_otp&sent=1"
            if pending
            else f"/2fa/step-up?method=email_otp&sent=1&next={_safe_next(next)}"
        )
        return RedirectResponse(url=target, status_code=303)

    router.post("/auth/2fa/email-otp-send/submit", include_in_schema=False)(limited(send_code_form))

    async def extend_challenge(request: Request, method: Annotated[str, Query()] = "") -> Response:
        """ "More time" on a pending sign-in (#1842, WCAG 2.2.1 Timing Adjustable).

        Extends only the challenge named by this browser's challenge cookie. An emailed
        code is NOT extended: it keeps its own ``EMAIL_CODE_TTL`` because it travelled
        by email, so the page offers "Email me a new code" alongside "More time".
        """
        wants_json = "application/json" in request.headers.get("accept", "")
        ch = _challenge(request)
        if ch is None:
            if wants_json:
                raise HTTPException(status_code=401, detail="No pending sign-in")
            return _challenge_gone(request)
        new_expiry = _store(request).extend_2fa_challenge(ch.token)
        if wants_json:
            if new_expiry is None:
                raise HTTPException(status_code=409, detail="This sign-in can't be extended")
            now = datetime.now(UTC)
            return JSONResponse(
                content={
                    "expires_in": max(0, int((new_expiry - now).total_seconds())),
                    "extendable": replace(ch, expires_at=new_expiry).can_extend,
                }
            )
        page = "/2fa/challenge" if ch.purpose == PURPOSE_VERIFY else "/2fa/setup"
        params = [f"method={method}"] if method in CODE_METHODS else []
        if new_expiry is not None and ch.purpose == PURPOSE_VERIFY:
            params.append("extended=1")
        return RedirectResponse(
            url=f"{page}?{'&'.join(params)}" if params else page, status_code=303
        )

    router.post(EXTEND_PATH, include_in_schema=False)(limited(extend_challenge))

    # ── enrolment ────────────────────────────────────────────────────────

    @router.post("/auth/2fa/setup/totp", include_in_schema=False)
    async def setup_totp_json(request: Request) -> dict[str, str]:
        who = _enrolling_or_401(request)
        if "totp" not in allowed_methods(_cfg(request)):
            raise HTTPException(status_code=400, detail="Authenticator apps are not enabled")
        secret, uri = _begin_totp(request, who)
        return {"secret": secret, "uri": uri, "qr_data_uri": qr_data_uri(uri)}

    async def verify_totp_json(request: Request, data: TwoFactorCodeRequest) -> Response:
        return await _confirm(request, _enrolling_or_401(request), "totp", data.code, as_json=True)

    router.post("/auth/2fa/verify/totp", include_in_schema=False)(limited(verify_totp_json))

    @router.post("/auth/2fa/setup/email-otp", include_in_schema=False)
    async def setup_email_json(request: Request) -> dict[str, str]:
        who = _enrolling_or_401(request)
        _require_email_allowed(request)
        send_email_code(request, _store(request), who.user, EMAIL_PURPOSE_ENROL)
        return {"message": "Code sent. Check your email."}

    async def verify_email_json(request: Request, data: TwoFactorCodeRequest) -> Response:
        _require_email_allowed(request)
        who = _enrolling_or_401(request)
        return await _confirm(request, who, "email_otp", data.code, as_json=True)

    router.post("/auth/2fa/verify/email-otp", include_in_schema=False)(limited(verify_email_json))

    async def setup_totp_form(request: Request, code: Annotated[str, Form()] = "") -> Response:
        who = _enrolling(request)
        if who is None:
            return RedirectResponse(url="/login?next=/2fa/setup", status_code=303)
        return await _confirm(request, who, "totp", code, as_json=False)

    router.post("/auth/2fa/setup/totp/submit", include_in_schema=False)(limited(setup_totp_form))

    @router.post("/auth/2fa/setup/email-otp/submit", include_in_schema=False)
    async def setup_email_form(request: Request) -> Response:
        who = _enrolling(request)
        if who is None:
            return RedirectResponse(url="/login?next=/2fa/setup", status_code=303)
        _require_email_allowed(request)
        send_email_code(request, _store(request), who.user, EMAIL_PURPOSE_ENROL)
        return RedirectResponse(url="/2fa/setup?sent=1", status_code=303)

    async def verify_email_form(request: Request, code: Annotated[str, Form()] = "") -> Response:
        who = _enrolling(request)
        if who is None:
            return RedirectResponse(url="/login?next=/2fa/setup", status_code=303)
        _require_email_allowed(request)
        return await _confirm(request, who, "email_otp", code, as_json=False)

    router.post("/auth/2fa/verify/email-otp/submit", include_in_schema=False)(
        limited(verify_email_form)
    )

    # ── step-up and management (signed in) ───────────────────────────────

    async def step_up_json(request: Request, data: TwoFactorCodeRequest) -> dict[str, str]:
        proof = _step_up(request, _method_or_400(data.method), data.code)
        if proof is None:
            raise HTTPException(status_code=401, detail="Invalid two-factor code")
        return {
            "message": "Second factor verified",
            "mfa_method": proof.method,
            "mfa_verified_at": proof.verified_at.isoformat(),
        }

    router.post("/auth/2fa/step-up", include_in_schema=False)(limited(step_up_json))

    async def step_up_form(
        request: Request,
        code: Annotated[str, Form()] = "",
        method: Annotated[str, Query()] = "totp",
        next: Annotated[str, Query()] = "",
    ) -> Response:
        if _session_auth(request) is None:
            return RedirectResponse(url="/login", status_code=303)
        method = _method_or_400(method)
        if _step_up(request, method, code) is None:
            return RedirectResponse(
                url=f"/2fa/step-up?method={method}&error=invalid_code&next={_safe_next(next)}",
                status_code=303,
            )
        return RedirectResponse(url=_safe_next(next), status_code=303)

    router.post("/auth/2fa/step-up/submit", include_in_schema=False)(limited(step_up_form))

    @router.get("/auth/2fa/status")
    async def status(request: Request) -> dict[str, Any]:
        ctx, _sid = _signed_in_or_401(request)
        user = ctx.user
        assert user is not None
        return {
            "two_factor_enabled": user.two_factor_enabled,
            "totp_enabled": user.totp_enabled,
            "email_otp_enabled": user.email_otp_enabled,
            "recovery_codes_remaining": _store(request).recovery_codes_remaining(user.id),
            "session_mfa_method": ctx.mfa_method,
            "session_mfa_verified_at": (
                ctx.mfa_verified_at.isoformat() if ctx.mfa_verified_at else None
            ),
        }

    @router.post("/auth/2fa/recovery/regenerate", include_in_schema=False)
    async def regenerate(request: Request) -> dict[str, Any]:
        codes = _manage(request, "regenerate_recovery") or []
        return {"recovery_codes": codes, "count": len(codes)}

    @router.delete("/auth/2fa/totp", include_in_schema=False)
    async def disable_totp(request: Request) -> dict[str, str]:
        _manage(request, "disable_totp")
        return {"message": "Authenticator app turned off"}

    @router.delete("/auth/2fa/email-otp", include_in_schema=False)
    async def disable_email(request: Request) -> dict[str, str]:
        _manage(request, "disable_email_otp")
        return {"message": "Email codes turned off"}

    @router.post("/auth/2fa/settings/submit", include_in_schema=False)
    async def settings_form(request: Request, action: Annotated[str, Query()] = "") -> Response:
        if _session_auth(request) is None:
            return RedirectResponse(url="/login?next=/2fa/settings", status_code=303)
        try:
            codes = _manage(request, action)
        except HTTPException as exc:
            if exc.status_code == 403:
                return RedirectResponse(url="/2fa/step-up?next=/2fa/settings", status_code=303)
            raise
        if codes:
            return _page(
                build_recovery_codes_view(
                    product_name=product_name(request),
                    codes=codes,
                    continue_url="/2fa/settings",
                    **_assets(request),
                )
            )
        return RedirectResponse(url="/2fa/settings", status_code=303)

    # ── pages ────────────────────────────────────────────────────────────

    @router.get("/2fa/challenge", include_in_schema=False)
    async def challenge_page(
        request: Request,
        method: Annotated[str, Query()] = "",
        sent: Annotated[str, Query()] = "",
        error: Annotated[str, Query()] = "",
        extended: Annotated[str, Query()] = "",
    ) -> Response:
        ch = _challenge(request)
        user = _challenge_user(request, ch) if ch and ch.purpose == PURPOSE_VERIFY else None
        if user is None:
            return _challenge_gone(request)
        assert ch is not None
        methods = tuple(enrolled_methods(_cfg(request), user))
        if not methods:  # every enrolled factor was switched off in dazzle.toml
            return RedirectResponse(url="/login?error=2fa_expired", status_code=303)
        mode = method if method in methods else methods[0]
        return _page(
            build_code_entry_view(
                product_name=product_name(request),
                heading="Verify it's you",
                mode=mode,
                methods=methods,
                verify_action="/auth/2fa/verify/submit",
                send_action="/auth/2fa/email-otp-send/submit",
                page_path="/2fa/challenge",
                code_sent=sent == "1",
                error_message=_INVALID_CODE if error == "invalid_code" else "",
                timeout=_challenge_timeout(ch, mode),
                extended=extended == "1",
                **_assets(request),
            )
        )

    @router.get("/2fa/step-up", include_in_schema=False)
    async def step_up_page(
        request: Request,
        method: Annotated[str, Query()] = "",
        next: Annotated[str, Query()] = "",
        sent: Annotated[str, Query()] = "",
        error: Annotated[str, Query()] = "",
    ) -> Response:
        signed_in = _session_auth(request)
        if signed_in is None:
            return RedirectResponse(url="/login", status_code=303)
        user = signed_in[0].user
        assert user is not None
        methods = tuple(enrolled_methods(_cfg(request), user))
        if not methods:
            return RedirectResponse(url="/2fa/setup", status_code=303)
        mode = method if method in methods else methods[0]
        return _page(
            build_code_entry_view(
                product_name=product_name(request),
                heading="Verify it's you",
                mode=mode,
                methods=methods,
                verify_action="/auth/2fa/step-up/submit",
                send_action="/auth/2fa/email-otp-send/submit",
                page_path="/2fa/step-up",
                next_url=_safe_next(next),
                code_sent=sent == "1",
                error_message=_INVALID_CODE if error == "invalid_code" else "",
                **_assets(request),
            )
        )

    @router.get("/2fa/setup", include_in_schema=False)
    async def setup_page(
        request: Request,
        sent: Annotated[str, Query()] = "",
        error: Annotated[str, Query()] = "",
    ) -> Response:
        who = _enrolling(request)
        if who is None:
            return RedirectResponse(url="/login?next=/2fa/setup", status_code=303)
        allowed = allowed_methods(_cfg(request))
        secret, uri = "", ""
        if "totp" in allowed and not who.user.totp_enabled:
            secret, uri = _begin_totp(request, who)
        return _page(
            build_2fa_setup_view(
                product_name=product_name(request),
                qr_data_uri=qr_data_uri(uri) if uri else "",
                secret=secret,
                totp_allowed=bool(uri),
                email_otp_allowed="email_otp" in allowed and not who.user.email_otp_enabled,
                email_code_sent=sent == "1",
                error_message=_INVALID_CODE if error == "invalid_code" else "",
                required=who.challenge is not None,
                **_assets(request),
            )
        )

    @router.get("/2fa/settings", include_in_schema=False)
    async def settings_page(request: Request) -> Response:
        signed_in = _session_auth(request)
        if signed_in is None:
            return RedirectResponse(url="/login?next=/2fa/settings", status_code=303)
        user = signed_in[0].user
        assert user is not None
        return _page(
            build_2fa_settings_view(
                product_name=product_name(request),
                totp_enabled=user.totp_enabled,
                email_otp_enabled=user.email_otp_enabled,
                email_otp_allowed="email_otp" in allowed_methods(_cfg(request)),
                recovery_remaining=_store(request).recovery_codes_remaining(user.id),
                **_assets(request),
            )
        )

    return router
