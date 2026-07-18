"""Workspace request → current-user entity resolution.

Extracted from workspace_rendering.py in #1057 cut 5 (v0.67.104).
Maps the auth-context user (cookie/JWT-derived) to the DSL user
entity row by email, so scope filters can compare against the
entity ID rather than the auth subject (#588). Falls back to the
auth user id when no entity row matches.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def _resolve_workspace_user(
    request: Any,
    auth_middleware: Any,
    repositories: dict[str, Any] | None,
    user_entity_name: str = "User",
) -> tuple[str | None, dict[str, Any] | None]:
    """Resolve the current authenticated user to a DSL User entity UUID and attributes dict.

    Returns (entity_uuid, entity_dict) or (auth_user_id, None) as fallback.
    If no user can be resolved, returns (None, None).
    """
    if not auth_middleware:
        return None, None
    try:
        auth = auth_middleware.get_auth_context(request)
        if not (auth and auth.is_authenticated and auth.user):
            return None, None
    except Exception:
        logger.debug("Failed to resolve current user for filter context", exc_info=True)
        return None, None

    # Prefer the auth principal UUID for ``current_user`` filters (#1626).
    # Assignment-aware demo seeds use STABLE_PERSONA_USER_IDS which match
    # auth user ids after reset rekey. Looking up domain User *only* by email
    # can return a stale row with a different id (pre-rekey mirror) and empty
    # every ``assigned_to = current_user`` desk while seeds look correct.
    auth_id = str(auth.user.id)
    email = getattr(auth.user, "email", None)
    if repositories:
        user_repo = repositories.get(user_entity_name)
        if user_repo:
            entity_user = None
            try:
                # Prefer id match when the domain User row is the auth principal.
                by_id = await user_repo.list(filters={"id": auth_id}, page_size=1)
                id_items = (
                    by_id.get("items", [])
                    if isinstance(by_id, dict)
                    else getattr(by_id, "items", [])
                )
                if id_items:
                    entity_user = id_items[0]
                elif email:
                    user_result = await user_repo.list(filters={"email": email}, page_size=1)
                    user_items = (
                        user_result.get("items", [])
                        if isinstance(user_result, dict)
                        else getattr(user_result, "items", [])
                    )
                    if user_items:
                        candidate = user_items[0]
                        cand_id = (
                            candidate.get("id")
                            if isinstance(candidate, dict)
                            else getattr(candidate, "id", None)
                        )
                        # Only trust email hit when ids match; else keep auth_id.
                        if cand_id is not None and str(cand_id) == auth_id:
                            entity_user = candidate
            except Exception:
                logger.debug("Could not resolve User entity for filter context", exc_info=True)
            if entity_user is not None:
                entity_dict = (
                    entity_user
                    if isinstance(entity_user, dict)
                    else entity_user.model_dump()
                    if hasattr(entity_user, "model_dump")
                    else {}
                )
                return auth_id, entity_dict

    return auth_id, None
