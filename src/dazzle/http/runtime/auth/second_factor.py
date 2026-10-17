"""Second-factor checks shared by sign-in, enrolment and step-up (DD-014), and the
public step-up API for custom routes: :func:`require_second_factor`.

    from dazzle.http.runtime.auth import require_second_factor

    async def submit_vat_return(request: Request):
        auth = require_second_factor(request, max_age=15 * 60)
        ...  # 403 {"error": "second_factor_required", "step_up_url": ...} otherwise

``require_second_factor`` reads the session's ``mfa_verified_at`` — set when the
sign-in completed a second factor (TOTP, email code, recovery code, or an enterprise
IdP's ``amr``) or later by ``POST /auth/2fa/step-up`` on the same session.
"""

import base64
import importlib.util
import io
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import segno
from fastapi import HTTPException

from dazzle.core.ir.security import TwoFactorConfig
from dazzle.http.runtime.auth.connection_crypto import ConnectionSecretError, encrypt_secret
from dazzle.http.runtime.auth.cookie_name import read_session_id
from dazzle.http.runtime.auth.current import current_auth
from dazzle.http.runtime.auth.mailer import get_one_time_code_mailer
from dazzle.http.runtime.auth.models import AuthContext, SecondFactorProof
from dazzle.http.runtime.auth.store_two_factor import (
    EMAIL_CODE_TTL,
    factor_reference,
    generate_recovery_codes,
)
from dazzle.http.runtime.auth.totp import match_totp_step
from dazzle.http.runtime.step_up import second_factor_fresh, step_up_url

CODE_METHODS: tuple[str, ...] = ("totp", "email_otp", "recovery")
EMAIL_PURPOSE_SIGN_IN = "email_otp"
EMAIL_PURPOSE_ENROL = "email_otp_enrol"


def _request_auth(request: Any) -> AuthContext:
    """The request's AuthContext via the app's own store (falls back to the registered one)."""
    store = getattr(getattr(request, "app", None), "state", None)
    store = getattr(store, "auth_store", None)
    if store is None:
        return current_auth(request)
    session_id = read_session_id(request)
    if not session_id:
        return AuthContext()
    ctx: AuthContext = store.validate_session(session_id)
    return ctx


def require_second_factor(request: Any, *, max_age: int | None = None) -> AuthContext:
    """The request's AuthContext when its session completed a second factor.

    ``max_age`` (seconds) additionally requires that factor to be that recent.
    Raises 401 when the request is not signed in, and 403 with
    ``{"error": "second_factor_required", "step_up_url": "/2fa/step-up?next=…"}``
    when the session has no (fresh enough) second factor — send the user to
    ``step_up_url`` to verify on this session, then retry.
    """
    auth = _request_auth(request)
    if not auth.is_authenticated or auth.user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not second_factor_fresh(auth.mfa_verified_at, max_age):
        path = getattr(getattr(request, "url", None), "path", "") or ""
        raise HTTPException(
            status_code=403,
            detail={"error": "second_factor_required", "step_up_url": step_up_url(path)},
        )
    return auth


def allowed_methods(cfg: TwoFactorConfig | None) -> set[str]:
    return {m.value for m in cfg.methods} if cfg is not None else set()


def proof_for(user_id: str, method: str) -> SecondFactorProof:
    return SecondFactorProof(
        method=method, verified_at=datetime.now(UTC), reference=factor_reference(user_id, method)
    )


def verify_factor_code(
    store: Any, user: Any, cfg: TwoFactorConfig | None, method: str, code: str
) -> SecondFactorProof | None:
    """Check ``code`` against the user's enrolled ``method``; spend it on success.

    A TOTP code is accepted once (its time step is recorded), an email code and a
    recovery code are single use. Returns the proof to record on the session.
    """
    code = "".join(code.split())
    if not code or method not in CODE_METHODS:
        return None
    ok = False
    if method == "totp" and user.totp_enabled and "totp" in allowed_methods(cfg):
        ok = _totp_ok(store, user.id, code)
    elif method == "email_otp" and user.email_otp_enabled and "email_otp" in allowed_methods(cfg):
        ok = bool(store.check_email_code(user.id, code, EMAIL_PURPOSE_SIGN_IN))
    elif method == "recovery":
        ok = bool(store.consume_recovery_code(user.id, code))
    return proof_for(str(user.id), method) if ok else None


def _totp_ok(store: Any, user_id: UUID, code: str) -> bool:
    secret = store.get_totp_secret(user_id)
    if not secret:
        return False
    step = match_totp_step(secret, code)
    return step is not None and bool(store.accept_totp_step(user_id, step))


def confirm_enrolment(
    store: Any, user: Any, cfg: TwoFactorConfig, method: str, code: str
) -> tuple[SecondFactorProof, list[str] | None] | None:
    """Confirm a factor being enrolled with its first code; enable it.

    Returns the proof (enrolling proves possession) and the recovery codes minted on
    the user's first enrolment (shown once), or None when the code is wrong.
    """
    code = "".join(code.split())
    if method == "totp":
        ok = _totp_ok(store, user.id, code)
        if ok:
            store.enable_totp(user.id)
    elif method == "email_otp":
        ok = bool(store.check_email_code(user.id, code, EMAIL_PURPOSE_ENROL))
        if ok:
            store.enable_email_otp(user.id)
    else:
        return None
    if not ok:
        return None
    codes = None
    if not user.recovery_codes_generated:
        codes = generate_recovery_codes(cfg.recovery_code_count)
        store.replace_recovery_codes(user.id, codes)
    return proof_for(str(user.id), method), codes


def send_email_code(request: Any, store: Any, user: Any, purpose: str) -> None:
    """Issue a fresh email code for ``purpose`` and hand it to the registered mailer."""
    code = store.issue_email_code(user.id, purpose)
    mailer = get_one_time_code_mailer(request.app.state)
    mailer.send_one_time_code(
        to_email=user.email, code=code, ttl_minutes=int(EMAIL_CODE_TTL.total_seconds() // 60)
    )


def qr_data_uri(otpauth_uri: str) -> str:
    """The enrolment QR as a ``data:`` PNG, rendered on the server (never a QR service)."""
    buf = io.BytesIO()
    segno.make(otpauth_uri, error="L").save(buf, kind="png", scale=4)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


class TwoFactorBootError(RuntimeError):
    """``[auth.two_factor]`` is enabled but this deployment cannot run it safely."""


def require_two_factor_runtime(cfg: TwoFactorConfig) -> None:
    """Fail the boot when enabled two-factor sign-in cannot keep TOTP secrets encrypted.

    TOTP secrets are AES-GCM encrypted with ``DAZZLE_CONNECTION_SECRET`` (the same key
    and ``cryptography`` dependency as enterprise connections); there is no plaintext
    fallback, so a missing key or package stops the boot instead of the first enrolment.
    """
    if not cfg.enabled or "totp" not in allowed_methods(cfg):
        return
    if importlib.util.find_spec("cryptography") is None:
        raise TwoFactorBootError(
            "[auth.two_factor] enables totp but 'cryptography' is not installed. "
            "Install the extra: pip install 'dazzle-dsl[sso]'"
        )
    try:
        encrypt_secret("boot-probe")
    except ConnectionSecretError as exc:
        raise TwoFactorBootError(f"[auth.two_factor] enables totp: {exc}") from exc
