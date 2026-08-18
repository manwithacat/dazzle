"""Leftover-honest SSO connection ids (cycle 2240, oral #110).

Reuses leftover_honest_auth_token — store mint is secrets.token_urlsafe(24).
Login stay-put is leftover_honest_sso_login_query (OIDC + SAML).
Metadata stay-put is inlined (clone ratchet vs leftover_auth_email_or_400).
"""

from typing import Any

from fastapi.responses import HTMLResponse

from dazzle.http.runtime.auth.auth_views import (
    leftover_auth_email_or_400,
    leftover_honest_auth_token,
)


def leftover_honest_connection_id(raw: Any) -> str | None:
    """Valid connection token_urlsafe ids ride. Leftover stays put (None).

    Leftover ``?connection=zzz`` / ``ghost`` on GET
    ``/auth/enterprise/login`` and ``/auth/saml/login`` used to invent
    ``303 /login?error=sso_no_connection`` theater (store miss). The
    same leftover on GET ``/auth/saml/metadata`` invented app-level
    metadata (omit-as-absent). ``secrets.token_urlsafe(24)`` ids ride
    via leftover_honest_auth_token. Absent / blank is first-visit
    (``""`` — email-domain / host-pin / app-level metadata).
    Well-formed ids that miss the store still bounce
    ``sso_no_connection`` (login) or fall back to app-level metadata
    (no id-enumeration). Distinct from leftover ``?new=`` catalog
    (oral #97), leftover consume token (oral #109), leftover
    membership_id (oral #107), and leftover entity-id (oral #71).
    Live doctor runbook ``/auth/enterprise/login?connection=``.
    Cycle 2240.
    """
    return leftover_honest_auth_token(raw)


def leftover_honest_sso_login_query(email: Any, connection: Any) -> tuple[str, str] | HTMLResponse:
    """Honest ``?email=`` + ``?connection=`` for enterprise / SAML login.

    Leftover email or leftover connection stays put (400). Valid /
    absent ride. Shared so OIDC and SAML login do not re-implement
    the same stay-put preamble (clone ratchet).
    """
    honest_email = leftover_auth_email_or_400(email)
    if not isinstance(honest_email, str):
        return honest_email
    honest_conn = leftover_honest_connection_id(connection)
    if honest_conn is None:
        return HTMLResponse("Unknown connection", status_code=400)
    return honest_email, honest_conn
