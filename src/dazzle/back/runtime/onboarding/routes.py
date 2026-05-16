"""HTTP routes for onboarding-step completion and dismissal (v0.71.2).

Two endpoints, both POST + htmx-friendly (return empty 200 so the
client-side ``hx-swap=outerHTML`` removes the popover from the DOM):

- ``POST /api/onboarding/{guide_name}/{step_name}/complete``
- ``POST /api/onboarding/{guide_name}/{step_name}/dismiss``

The renderer (``onboarding/renderer.py``) emits the htmx attributes
pointing at these URLs. Both endpoints require an authenticated user
— anonymous traffic gets a 401 (the popover overlay only renders for
logged-in users anyway).

Versioning: routes are not gated on a specific ``guide_version`` in
v0.71.2 — the repository defaults to version 1. Multi-version guides
arrive in v0.71.3 alongside the page-routes wiring that knows the
active version per user.
"""

from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse

if TYPE_CHECKING:
    from .state_repository import OnboardingStateRepository


def create_onboarding_routes() -> APIRouter:
    """Build the onboarding completion + dismissal router.

    Reads the repository instance off ``request.app.state.onboarding_state``
    (populated by the auth subsystem at boot when guides exist).
    """
    router = APIRouter(tags=["onboarding"])

    @router.post("/api/onboarding/{guide_name}/{step_name}/complete")
    async def complete_step(
        guide_name: str,
        step_name: str,
        request: Request,
    ) -> HTMLResponse:
        repo, user_id = _resolve_repo_and_user(request)
        repo.mark_step_completed(
            user_id=user_id,
            guide_name=guide_name,
            guide_version=1,
            step_name=step_name,
        )
        # Empty body — htmx swaps outerHTML on the popover so the
        # overlay disappears. 200 OK rather than 204 so htmx can
        # parse the body length consistently.
        return HTMLResponse(content="", status_code=200)

    @router.post("/api/onboarding/{guide_name}/{step_name}/dismiss")
    async def dismiss_step(
        guide_name: str,
        step_name: str,
        request: Request,
    ) -> HTMLResponse:
        repo, user_id = _resolve_repo_and_user(request)
        repo.mark_step_dismissed(
            user_id=user_id,
            guide_name=guide_name,
            guide_version=1,
            step_name=step_name,
        )
        return HTMLResponse(content="", status_code=200)

    return router


def _resolve_repo_and_user(request: Request) -> "tuple[OnboardingStateRepository, str]":
    """Pull the configured repository + the current user's ID off the
    request. Raises 401/503 with actionable messages if either is
    missing.
    """
    repo = getattr(request.app.state, "onboarding_state", None)
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "OnboardingStateRepository not configured on app.state — "
                "auth subsystem skipped it (no guides declared or "
                "DATABASE_URL absent)"
            ),
        )

    # The current-user context is set by the auth middleware on the
    # request scope. Accept either an authenticated UserRecord (with
    # .id) or a plain dict-shaped user payload — the route is
    # request-pipeline agnostic at this layer.
    user_obj = getattr(request.state, "current_user", None)
    if user_obj is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="onboarding endpoints require authentication",
        )
    user_id = getattr(user_obj, "id", None) or (
        user_obj.get("id") if isinstance(user_obj, dict) else None
    )
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="onboarding endpoints require authentication",
        )
    return repo, str(user_id)
