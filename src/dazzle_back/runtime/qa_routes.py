"""Dev-only QA mode endpoints. Never mount in production.

This module is imported and its router registered ONLY when both:
- DAZZLE_ENV=development
- DAZZLE_QA_MODE=1

The serve command sets DAZZLE_QA_MODE=1 when --local is active.

SECURITY: the /qa/magic-link endpoint creates a session for any
provisioned persona without authentication. It is gated at both
mount time AND request time (double-check in case of config drift).
"""

import logging
import os

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class MagicLinkRequest(BaseModel):
    persona_id: str


class MagicLinkResponse(BaseModel):
    url: str


def _qa_mode_active() -> bool:
    """Return True iff both env flags are set."""
    return os.environ.get("DAZZLE_ENV") == "development" and os.environ.get("DAZZLE_QA_MODE") == "1"


def create_qa_routes() -> APIRouter:
    """Create the dev-gated QA router.

    The router checks env flags at request time as a defence-in-depth
    measure. The caller should ALSO check these flags at mount time
    and refuse to include the router in production builds.
    """
    router = APIRouter(tags=["qa"])

    @router.post("/qa/magic-link", response_model=MagicLinkResponse)
    async def generate_qa_magic_link(
        body: MagicLinkRequest,
        request: Request,
    ) -> MagicLinkResponse:
        """Generate a magic link for a provisioned dev persona.

        Returns 404 if:
        - QA mode is not active (env flags missing)
        - The persona has not been provisioned (no user with matching email)
        """
        if not _qa_mode_active():
            raise HTTPException(status_code=404)

        auth_store = request.app.state.auth_store
        email = f"{body.persona_id}@example.test"
        user = auth_store.get_user_by_email(email)
        if user is None:
            raise HTTPException(status_code=404, detail="persona not provisioned")

        token = auth_store.create_magic_link(
            user_id=str(user.id),
            ttl_seconds=60,  # short TTL — used immediately
            created_by="qa_panel",
        )

        logger.warning(
            "[QA MODE] Magic link generated for persona %r",
            body.persona_id,
        )

        return MagicLinkResponse(url=f"/auth/magic/{token}")

    return router
