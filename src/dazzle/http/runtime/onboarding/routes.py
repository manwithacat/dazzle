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

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from dazzle.render.fragment.renderer._render_interactive import leftover_honest_catalog_id

if TYPE_CHECKING:
    from .state_repository import OnboardingStateRepository


def _guide_step_ids(guide: Any) -> tuple[str, ...]:
    """Declared step names for one guide (``steps`` then ``step_order``)."""
    seen: list[str] = []
    for step in getattr(guide, "steps", None) or ():
        sid = str(getattr(step, "name", "") or "")
        if sid and sid not in seen:
            seen.append(sid)
    for sid in getattr(guide, "step_order", None) or ():
        text = str(sid or "")
        if text and text not in seen:
            seen.append(text)
    return tuple(seen)


def _onboarding_step_catalog(guides: Any) -> dict[str, tuple[str, ...]]:
    """Guide name → declared step ids."""
    catalog: dict[str, tuple[str, ...]] = {}
    for guide in guides or ():
        name = str(getattr(guide, "name", "") or "")
        if name:
            catalog[name] = _guide_step_ids(guide)
    return catalog


def leftover_honest_onboarding_step(
    guide_name: Any,
    step_name: Any,
    guides: Any,
) -> tuple[str, str]:
    """Valid declared guide+step ride. Leftover restores ``("", "")``.

    Leftover ``/api/onboarding/zzz/ghost/complete`` used to persist
    invented completed/dismissed rows. Valid names ride; leftover
    stays put (no write). Live simple_task ``workspace_setup`` /
    ``welcome_empty``. Cycle 2208.
    """
    catalog = _onboarding_step_catalog(guides)
    honest_guide = leftover_honest_catalog_id(guide_name, tuple(catalog), "", allow_empty_rest=True)
    if not honest_guide:
        return "", ""
    honest_step = leftover_honest_catalog_id(
        step_name, catalog.get(honest_guide, ()), "", allow_empty_rest=True
    )
    if not honest_step:
        return "", ""
    return honest_guide, honest_step


def _require_honest_onboarding_step(
    request: Request, guide_name: str, step_name: str
) -> tuple[str, str]:
    """404 leftover guide/step so htmx does not invent overlay dismiss."""
    appspec = getattr(request.app.state, "appspec", None)
    honest_guide, honest_step = leftover_honest_onboarding_step(
        guide_name, step_name, getattr(appspec, "guides", None)
    )
    if not honest_guide or not honest_step:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown onboarding guide or step",
        )
    return honest_guide, honest_step


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
        honest_guide, honest_step = _require_honest_onboarding_step(request, guide_name, step_name)
        repo.mark_step_completed(
            user_id=user_id,
            guide_name=honest_guide,
            guide_version=1,
            step_name=honest_step,
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
        honest_guide, honest_step = _require_honest_onboarding_step(request, guide_name, step_name)
        repo.mark_step_dismissed(
            user_id=user_id,
            guide_name=honest_guide,
            guide_version=1,
            step_name=honest_step,
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
