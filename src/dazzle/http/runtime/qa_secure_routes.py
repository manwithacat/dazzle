"""Secret-gated, contained QA-auth mint (RLS Phase E.2, #1339).

Physically separate from the dev-only ``qa_routes.py`` (the "dev route stays
dev" promise). **Self-disabling:** ``create_qa_secure_routes()`` returns None
when ``QA_AUTH_SECRET`` is unset, so it is never mounted in prod-by-default. The
mint enforces the DB containment invariant (ADR-0035): a session may be minted
only into a ``qa-``-namespaced, ``is_test=true``, run-matched org the target user
belongs to — the QA secret can NEVER reach a real tenant.
"""

import logging
import os
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from dazzle.http.runtime.auth.crypto import cookie_secure
from dazzle.http.runtime.auth.qa_provision import QA_SLUG_PREFIX
from dazzle.http.runtime.auth.qa_sign import QaTokenError, verify_qa_token

logger = logging.getLogger(__name__)


class MintRequest(BaseModel):
    token: str


def create_qa_secure_routes() -> APIRouter | None:
    """Build the secret-gated mint router, or None when QA_AUTH_SECRET is unset."""
    if not os.environ.get("QA_AUTH_SECRET"):
        return None

    router = APIRouter(tags=["qa"])

    @router.post("/qa/secure/mint")
    async def mint(body: MintRequest, request: Request, response: Response) -> dict[str, Any]:
        # Defence-in-depth: re-read the secret at request time (config drift).
        live_secret = os.environ.get("QA_AUTH_SECRET")
        if not live_secret:
            raise HTTPException(status_code=404)
        try:
            claims = verify_qa_token(body.token, secret=live_secret, now=time.time())
        except QaTokenError as exc:
            # Don't echo the reason to the client (no oracle); log server-side.
            logger.warning("[QA-AUTH] token verification failed: %s", exc)
            raise HTTPException(status_code=403, detail="invalid token") from exc

        auth_store = request.app.state.auth_store

        # ── Containment invariant (ADR-0035), resolved from the DB ──────────
        # The target org is derived from the SIGNED run_id, never a
        # request-supplied tenant id. It must be reserved-namespaced AND
        # is_test — both unforgeable from the request.
        # All post-signature refusals return ONE opaque 403 (no client-facing
        # oracle distinguishing which gate failed); the specific reason is logged
        # server-side for the operator. (Only reachable by a holder of the QA
        # secret, but opaque-by-default is cheap.)
        def _refuse(reason: str) -> HTTPException:
            logger.warning("[QA-AUTH] refused mint (run_id=%r): %s", claims.run_id, reason)
            return HTTPException(status_code=403, detail="forbidden")

        org = auth_store.get_organization_by_slug(f"{QA_SLUG_PREFIX}{claims.run_id}")
        if org is None or not org.is_test or not org.slug.startswith(QA_SLUG_PREFIX):
            raise _refuse("org for run_id is not a reserved is_test tenant")

        user = auth_store.get_user_by_email(claims.email.strip().lower())
        if user is None:
            raise _refuse("unknown user")
        membership = next(
            (
                m
                for m in auth_store.get_memberships_for_identity(str(user.id))
                if m.tenant_id == org.id and m.status == "active"
            ),
            None,
        )
        if membership is None:
            raise _refuse("no active membership in test tenant")

        # Mint a session scoped to the test org's membership (binds dazzle.tenant_id).
        session = auth_store.create_session(user, active_membership_id=membership.id)
        response.set_cookie(
            key="dazzle_session",
            value=session.id,
            httponly=True,
            secure=cookie_secure(request),
            samesite="lax",
        )
        response.set_cookie(
            key="dazzle_csrf",
            value=session.csrf_secret,
            httponly=False,
            secure=cookie_secure(request),
            samesite="lax",
        )
        logger.warning("[QA-AUTH] minted contained session for run_id=%r", claims.run_id)
        return {"ok": True, "tenant_id": org.id}

    return router
