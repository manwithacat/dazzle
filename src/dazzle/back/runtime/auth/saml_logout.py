"""SP-initiated SAML SLO resolution for the generic logout (#1342).

Kept out of ``routes.py`` / ``saml_routes.py`` so generic auth carries no SAML dependency;
imported lazily by ``_logout``. The whole module is best-effort: any failure resolving the
SAML connection falls back to plain local logout (never breaks logout)."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

_logger = logging.getLogger(__name__)


def saml_slo_redirect_url(store: Any, request: Any, *, session_id: str) -> str | None:
    """If ``session_id`` is a SAML SSO session whose org has an SLO-configured SAML connection,
    return the IdP SLO redirect (a signed ``LogoutRequest``) to send the browser to; else
    ``None``. Called BEFORE the session is deleted. Never raises — any failure → ``None``."""
    try:
        session = store.get_session(session_id)
        if session is None or not getattr(session, "active_membership_id", None):
            return None
        membership = store.get_membership(session.active_membership_id)
        if membership is None:
            return None
        conn = next(
            (
                c
                for c in store.get_connections_for_tenant(membership.tenant_id)
                if c.type == "saml" and c.status == "active" and (c.config or {}).get("idp_slo_url")
            ),
            None,
        )
        if conn is None:
            return None
        user = store.get_user_by_id(UUID(str(membership.identity_id)))
        email = getattr(user, "email", "") if user is not None else ""
        if not email:
            return None
        from dazzle.back.runtime.auth.connections import resolve_provider

        provider = resolve_provider(conn)
        # initiate_logout is SAML-specific (not on the ConnectionProvider Protocol); this path
        # only runs for an active SAML connection, so the attribute is present.
        url: str = provider.initiate_logout(conn, request, name_id=email)  # type: ignore[attr-defined]
        return url
    except Exception as exc:  # noqa: BLE001 — logout must never break on SLO resolution
        _logger.warning("SAML SP-SLO resolution failed; falling back to local logout: %s", exc)
        return None
