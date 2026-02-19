"""
Experience flow route handler.

Creates FastAPI routes for multi-step experience flows:
- GET /experiences/{name} — redirect to current/start step
- GET /experiences/{name}/{step} — render a step
- POST /experiences/{name}/{step}?event=X — process transition
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from dazzle.core import ir
from dazzle.core.ir.experiences import StepKind
from dazzle.core.strings import to_api_plural
from dazzle_ui.utils.expression_eval import evaluate_simple_condition

logger = logging.getLogger(__name__)

try:
    from fastapi import APIRouter, Request
    from fastapi.responses import HTMLResponse, RedirectResponse, Response

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False


def _sync_post(
    url: str,
    body: bytes,
    cookies: dict[str, str] | None = None,
    method: str = "POST",
    timeout: int = 10,
) -> tuple[int, bytes]:
    """Synchronous HTTP POST — runs in a thread to avoid blocking the event loop."""
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    if cookies:
        req.add_header("Cookie", "; ".join(f"{k}={v}" for k, v in cookies.items()))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data: bytes = resp.read()
            return resp.status, data
    except urllib.error.HTTPError as e:
        return e.code, e.read()


async def _proxy_to_backend(
    backend_url: str,
    entity_ref: str,
    body: dict[str, Any],
    cookies: dict[str, str] | None = None,
    method: str = "POST",
) -> tuple[bool, dict[str, Any]]:
    """Forward form data to the backend entity API.

    Returns:
        (success, response_data) — success is True if status is 2xx.
    """
    api_path = f"/{to_api_plural(entity_ref)}"
    url = f"{backend_url}{api_path}"
    json_body = json.dumps(body).encode("utf-8")

    status, raw = await asyncio.to_thread(_sync_post, url, json_body, cookies, method)
    try:
        data: dict[str, Any] = json.loads(raw)
    except Exception:
        data = {}

    return 200 <= status < 300, data


def create_experience_routes(
    appspec: ir.AppSpec,
    backend_url: str = "http://127.0.0.1:8000",
    theme_css: str = "",
    get_auth_context: Callable[..., Any] | None = None,
    app_prefix: str = "",
    project_root: Path | None = None,
) -> APIRouter:
    """Create FastAPI routes for all experiences in the appspec.

    Args:
        appspec: Complete application specification.
        backend_url: URL of the backend API for data proxying.
        theme_css: Pre-compiled theme CSS to inject.
        get_auth_context: Optional callable(request) -> AuthContext for user info.
        app_prefix: URL prefix for page routes (e.g. "/app").
        project_root: Project root for durable progress persistence.

    Returns:
        FastAPI router with experience routes.
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI is not installed")

    from dazzle_ui.converters.experience_compiler import compile_experience_context
    from dazzle_ui.runtime.experience_persistence import (
        ExperienceProgress,
        ExperienceProgressStore,
    )
    from dazzle_ui.runtime.experience_state import (
        cookie_name,
        create_initial_state,
        sign_state,
        verify_state,
    )
    from dazzle_ui.runtime.page_routes import _resolve_backend_url
    from dazzle_ui.runtime.template_renderer import render_fragment

    # Durable progress store (file-based, survives cookie expiry)
    progress_store: ExperienceProgressStore | None = None
    if project_root:
        progress_store = ExperienceProgressStore(project_root)

    router = APIRouter()

    # Index experiences by name for fast lookup
    experiences_by_name: dict[str, ir.ExperienceSpec] = {
        exp.name: exp for exp in appspec.experiences
    }

    # Build nav items for sidebar context
    nav_items: list[dict[str, str]] = []
    for ws in appspec.workspaces:
        nav_items.append(
            {
                "label": ws.title or ws.name.replace("_", " ").title(),
                "route": f"{app_prefix}/workspaces/{ws.name}",
            }
        )
    app_name = appspec.title or appspec.name.replace("_", " ").title()

    def _inject_auth(request: Request) -> dict[str, Any]:
        """Extract auth context for template variables."""
        ctx: dict[str, Any] = {
            "is_authenticated": False,
            "user_email": "",
            "user_name": "",
            "user_roles": [],
        }
        if get_auth_context is not None:
            try:
                auth_ctx = get_auth_context(request)
                if auth_ctx and auth_ctx.is_authenticated:
                    ctx["is_authenticated"] = True
                    if auth_ctx.user:
                        ctx["user_email"] = auth_ctx.user.email or ""
                        ctx["user_name"] = auth_ctx.user.username or ""
                        ctx["user_roles"] = list(getattr(auth_ctx.user, "roles", None) or [])
            except Exception:
                logger.debug("Failed to resolve auth context for experience", exc_info=True)
        return ctx

    def _get_user_email(request: Request) -> str:
        """Extract user email from auth context for progress keying."""
        auth_ctx = _inject_auth(request)
        email: str = auth_ctx.get("user_email", "")
        return email

    # GET /experiences/{name} — redirect to current or start step
    async def experience_entry(request: Request, name: str) -> Response:
        experience = experiences_by_name.get(name)
        if not experience:
            return RedirectResponse(url=f"{app_prefix}/", status_code=302)

        # Check for existing state: cookie first, then durable store
        cname = cookie_name(name)
        raw_cookie = request.cookies.get(cname)
        state = verify_state(raw_cookie) if raw_cookie else None

        if state:
            target_step = state.step
        elif progress_store:
            # Cookie expired or missing — try durable store for resume
            user_email = _get_user_email(request)
            saved = progress_store.load(name, user_email)
            if saved:
                logger.info(
                    "Resuming experience '%s' from step '%s' (saved progress)",
                    name,
                    saved.current_step,
                )
                target_step = saved.current_step
                # Restore cookie from saved progress
                state = create_initial_state(saved.current_step)
                state = state.model_copy(
                    update={
                        "completed": saved.completed_steps,
                        "data": saved.step_data,
                        "started_at": saved.started_at,
                    }
                )
            else:
                target_step = experience.start_step
        else:
            target_step = experience.start_step

        response = RedirectResponse(
            url=f"{app_prefix}/experiences/{name}/{target_step}",
            status_code=302,
        )

        # If we restored state from the file store, set the cookie
        if state and not raw_cookie:
            response.set_cookie(
                cname,
                sign_state(state),
                httponly=True,
                samesite="lax",
                max_age=86400,
            )

        return response

    # GET /experiences/{name}/{step} — render a step
    async def experience_step_get(request: Request, name: str, step: str) -> Response:
        experience = experiences_by_name.get(name)
        if not experience:
            return RedirectResponse(url=f"{app_prefix}/", status_code=302)

        # Validate step exists
        step_spec = experience.get_step(step)
        if not step_spec:
            return RedirectResponse(
                url=f"{app_prefix}/experiences/{name}",
                status_code=302,
            )

        # Load or create state: cookie → file store → fresh
        cname = cookie_name(name)
        raw_cookie = request.cookies.get(cname)
        state = verify_state(raw_cookie) if raw_cookie else None

        if not state and progress_store:
            user_email = _get_user_email(request)
            saved = progress_store.load(name, user_email)
            if saved:
                state = create_initial_state(saved.current_step)
                state = state.model_copy(
                    update={
                        "completed": saved.completed_steps,
                        "data": saved.step_data,
                        "started_at": saved.started_at,
                    }
                )

        if not state:
            state = create_initial_state(experience.start_step)

        # Skip prevention: can't access a step that hasn't been reached yet
        # (unless it's the current step or a completed step)
        if step != state.step and step not in state.completed:
            # Check if this step is ahead of the current step
            step_names = [s.name for s in experience.steps]
            if step in step_names:
                current_idx = step_names.index(state.step) if state.step in step_names else 0
                target_idx = step_names.index(step)
                if target_idx > current_idx:
                    # Can't skip ahead — redirect to current
                    return RedirectResponse(
                        url=f"{app_prefix}/experiences/{name}/{state.step}",
                        status_code=302,
                    )

        # Conditional step guard: skip if condition is false
        if step_spec.when and not evaluate_simple_condition(step_spec.when, state.data):
            # Mark step as completed (skipped) and follow success transition
            completed = list(state.completed)
            if step not in completed:
                completed.append(step)
            next_step_name: str | None = None
            for tr in step_spec.transitions:
                if tr.event == "success":
                    next_step_name = tr.next_step
                    break
            if next_step_name:
                state = state.model_copy(update={"step": next_step_name, "completed": completed})
                response = RedirectResponse(
                    url=f"{app_prefix}/experiences/{name}/{next_step_name}",
                    status_code=302,
                )
                response.set_cookie(
                    cname,
                    sign_state(state),
                    httponly=True,
                    samesite="lax",
                    max_age=86400,
                )
                return response

        # Back navigation: revisiting a completed step rewinds state
        if step in state.completed and step != state.step:
            # Remove this step and all subsequent steps from completed
            step_names = [s.name for s in experience.steps]
            if step in step_names:
                step_idx = step_names.index(step)
                state = state.model_copy(
                    update={
                        "step": step,
                        "completed": [s for s in state.completed if s in step_names[:step_idx]],
                    }
                )

        # Update current step in state
        if step != state.step:
            state = state.model_copy(update={"step": step})

        # Compile the experience context
        exp_ctx = compile_experience_context(experience, state, appspec, app_prefix)

        # Build template variables
        auth_ctx = _inject_auth(request)

        from dazzle_back.runtime.htmx_response import HtmxDetails

        htmx = HtmxDetails.from_request(request)
        current_route = f"{app_prefix}/experiences/{name}/{step}"

        # Fragment targeting: return only the content
        if htmx.wants_fragment:
            html = render_fragment(
                "experience/_content.html",
                experience=exp_ctx,
            )
            headers = {
                "HX-Trigger": json.dumps({"dz:titleUpdate": exp_ctx.title}),
            }
            response = HTMLResponse(content=html, headers=headers)
        else:
            html = render_fragment(
                "experience/experience.html",
                experience=exp_ctx,
                nav_items=nav_items,
                app_name=app_name,
                current_route=current_route,
                theme_css=theme_css,
                _htmx_partial=htmx.is_htmx and not htmx.is_history_restore,
                **auth_ctx,
            )
            response = HTMLResponse(content=html)

        # Set state cookie on every response
        response.set_cookie(
            cname,
            sign_state(state),
            httponly=True,
            samesite="lax",
            max_age=86400,
        )

        # Persist progress durably (survives cookie expiry / browser close)
        if progress_store:
            user_email = _get_user_email(request)
            progress_store.save(
                ExperienceProgress(
                    experience_name=name,
                    current_step=state.step,
                    completed_steps=list(state.completed),
                    step_data=dict(state.data),
                    started_at=state.started_at,
                    user_email=user_email,
                )
            )

        return response

    # POST /experiences/{name}/{step}?event=X — process transition
    async def experience_step_post(request: Request, name: str, step: str) -> Response:
        experience = experiences_by_name.get(name)
        if not experience:
            return RedirectResponse(url=f"{app_prefix}/", status_code=302)

        step_spec = experience.get_step(step)
        if not step_spec:
            return RedirectResponse(
                url=f"{app_prefix}/experiences/{name}",
                status_code=302,
            )

        # Load state: cookie → file store → fresh
        cname = cookie_name(name)
        raw_cookie = request.cookies.get(cname)
        state = verify_state(raw_cookie) if raw_cookie else None

        if not state and progress_store:
            user_email = _get_user_email(request)
            saved = progress_store.load(name, user_email)
            if saved:
                state = create_initial_state(saved.current_step)
                state = state.model_copy(
                    update={
                        "completed": saved.completed_steps,
                        "data": saved.step_data,
                        "started_at": saved.started_at,
                    }
                )

        if not state:
            state = create_initial_state(experience.start_step)

        # Determine event from query param
        event = request.query_params.get("event", "success")

        # For form steps, proxy the form data to the backend
        # Only proxy when there's actually a matching transition (not terminal steps)
        has_matching_transition = any(tr.event == event for tr in step_spec.transitions)
        effective_backend_url = _resolve_backend_url(request, backend_url)
        _cookies = dict(request.cookies) if request.cookies else None

        if step_spec.kind == StepKind.SURFACE and step_spec.surface and has_matching_transition:
            surface = None
            for s in appspec.surfaces:
                if s.name == step_spec.surface:
                    surface = s
                    break

            if surface and surface.entity_ref and event == "success":
                # Read request body
                try:
                    body = await request.json()
                except Exception:
                    body = {}

                success, resp_data = await _proxy_to_backend(
                    effective_backend_url,
                    surface.entity_ref,
                    body,
                    _cookies,
                )

                if not success:
                    # Proxy failed — re-render the step with error
                    from dazzle_back.runtime.htmx_response import HtmxDetails, htmx_error_response

                    htmx = HtmxDetails.from_request(request)
                    if htmx.is_htmx:
                        errors = resp_data.get("detail", [])
                        if isinstance(errors, str):
                            errors = [errors]
                        elif isinstance(errors, list):
                            messages = []
                            for err in errors:
                                if isinstance(err, dict):
                                    loc = err.get("loc", [])
                                    msg = err.get("msg", str(err))
                                    field = ".".join(str(p) for p in loc if p != "body")
                                    messages.append(f"{field}: {msg}" if field else msg)
                                else:
                                    messages.append(str(err))
                            errors = messages
                        return htmx_error_response(errors if errors else ["Submission failed"])
                    # Non-HTMX: redirect back to the step
                    return RedirectResponse(
                        url=f"{app_prefix}/experiences/{name}/{step}",
                        status_code=302,
                    )

                # Store the created entity ID in the data map (backward compat)
                new_data = {**state.data}
                if "id" in resp_data:
                    new_data[f"{surface.entity_ref}_id"] = resp_data["id"]
                # Full entity capture via saves_to
                if step_spec.saves_to:
                    parts = step_spec.saves_to.split(".", 1)
                    if len(parts) == 2 and parts[0] == "context":
                        new_data[parts[1]] = resp_data
                state = state.model_copy(update={"data": new_data})

        # Find the matching transition
        next_step: str | None = None
        for tr in step_spec.transitions:
            if tr.event == event:
                next_step = tr.next_step
                break

        if next_step is None:
            # Terminal step — no matching transition
            # Mark current step as completed, clear cookie, redirect to app root
            completed = list(state.completed)
            if step not in completed:
                completed.append(step)

            from dazzle_back.runtime.htmx_response import HtmxDetails

            htmx = HtmxDetails.from_request(request)
            redirect_url = f"{app_prefix}/"

            response: Response
            if htmx.is_htmx:
                response = HTMLResponse(
                    content="",
                    headers={"HX-Redirect": redirect_url},
                )
            else:
                response = RedirectResponse(url=redirect_url, status_code=302)

            # Clear the cookie and durable progress
            response.delete_cookie(cname)
            if progress_store:
                user_email = _get_user_email(request)
                progress_store.delete(name, user_email)
            return response

        # Update state: mark current step as completed, advance to next
        completed = list(state.completed)
        if step not in completed:
            completed.append(step)

        state = state.model_copy(
            update={
                "step": next_step,
                "completed": completed,
            }
        )

        redirect_url = f"{app_prefix}/experiences/{name}/{next_step}"

        from dazzle_back.runtime.htmx_response import HtmxDetails

        htmx = HtmxDetails.from_request(request)

        if htmx.is_htmx:
            response = HTMLResponse(
                content="",
                headers={"HX-Redirect": redirect_url},
            )
        else:
            response = RedirectResponse(url=redirect_url, status_code=302)

        # Set state cookie
        response.set_cookie(
            cname,
            sign_state(state),
            httponly=True,
            samesite="lax",
            max_age=86400,
        )

        # Persist progress durably
        if progress_store:
            user_email = _get_user_email(request)
            progress_store.save(
                ExperienceProgress(
                    experience_name=name,
                    current_step=state.step,
                    completed_steps=list(state.completed),
                    step_data=dict(state.data),
                    started_at=state.started_at,
                    user_email=user_email,
                )
            )

        return response

    # Register routes
    router.get("/experiences/{name}", response_class=HTMLResponse)(experience_entry)
    router.get("/experiences/{name}/{step}", response_class=HTMLResponse)(experience_step_get)
    router.post("/experiences/{name}/{step}", response_class=HTMLResponse)(experience_step_post)

    return router
