"""
Experience flow route handler.

Creates FastAPI routes for multi-step experience flows:
- GET /experiences/{name} — redirect to current/start step
- GET /experiences/{name}/{step} — render a step
- POST /experiences/{name}/{step}?event=X — process transition
"""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from dazzle.core import ir
from dazzle.core.ir.experiences import StepKind
from dazzle.core.strings import entity_slug
from dazzle.page.utils.expression_eval import evaluate_simple_condition

logger = logging.getLogger(__name__)

# =============================================================================
# Dependencies Container
# =============================================================================


@dataclass
class _ExperienceDeps:
    appspec: ir.AppSpec
    theme_css: str
    get_auth_context: Callable[..., Any] | None
    app_prefix: str
    experiences_by_name: dict[str, ir.ExperienceSpec]
    nav_items: list[dict[str, Any]] = field(default_factory=list)
    nav_groups: list[dict[str, Any]] = field(default_factory=list)
    app_name: str = ""
    progress_store: Any = None


# =============================================================================
# Shared helpers (module-level)
# =============================================================================


def _inject_auth(deps: _ExperienceDeps, request: Any) -> dict[str, Any]:
    """Extract auth context for template variables."""
    ctx: dict[str, Any] = {
        "is_authenticated": False,
        "user_email": "",
        "user_name": "",
        "user_roles": [],
    }
    if deps.get_auth_context is not None:
        try:
            auth_ctx = deps.get_auth_context(request)
            if auth_ctx and auth_ctx.is_authenticated:
                ctx["is_authenticated"] = True
                if auth_ctx.user:
                    ctx["user_email"] = auth_ctx.user.email or ""
                    ctx["user_name"] = auth_ctx.user.username or ""
                    ctx["user_roles"] = list(getattr(auth_ctx.user, "roles", None) or [])
        except Exception:
            logger.warning("Failed to resolve auth context for experience", exc_info=True)
    return ctx


def _get_user_email(deps: _ExperienceDeps, request: Any) -> str:
    """Extract user email from auth context for progress keying."""
    auth_ctx = _inject_auth(deps, request)
    email: str = auth_ctx.get("user_email", "")
    return email


def _load_state(
    deps: _ExperienceDeps,
    request: Any,
    experience_name: str,
    start_step: str,
) -> tuple[Any, str | None]:
    """Load experience state from cookie or durable store.

    Returns (state, raw_cookie) where state may be None.
    """
    from dazzle.page.runtime.experience_state import (
        cookie_name,
        create_initial_state,
        verify_state,
    )

    cname = cookie_name(experience_name)
    raw_cookie = request.cookies.get(cname)
    state = verify_state(raw_cookie) if raw_cookie else None

    if not state and deps.progress_store:
        user_email = _get_user_email(deps, request)
        saved = deps.progress_store.load(experience_name, user_email)
        if saved:
            state = create_initial_state(saved.current_step)
            state = state.model_copy(
                update={
                    "completed": saved.completed_steps,
                    "data": saved.step_data,
                    "started_at": saved.started_at,
                }
            )

    return state, raw_cookie


def _persist_progress(
    deps: _ExperienceDeps,
    request: Any,
    name: str,
    state: Any,
) -> None:
    """Save experience progress to durable store."""
    if not deps.progress_store:
        return

    from dazzle.page.runtime.experience_persistence import ExperienceProgress

    user_email = _get_user_email(deps, request)
    deps.progress_store.save(
        ExperienceProgress(
            experience_name=name,
            current_step=state.step,
            completed_steps=list(state.completed),
            step_data=dict(state.data),
            started_at=state.started_at,
            user_email=user_email,
        )
    )


# =============================================================================
# Module-level handler functions
# =============================================================================


def _make_experience_entry_handler(deps: _ExperienceDeps) -> Any:
    """Closure factory — preserves the `request: Request` annotation through
    FastAPI's `inspect.signature` pass. Mirrors `_make_page_handler` /
    `_make_workspace_handler` in `page_routes.py` (issue #1034, follow-up
    #1112). `partial(_experience_entry, deps)` strips the annotation; pydantic
    then defaults `request` to `Query(...)` and hard-fails building a
    TypeAdapter for the `Request` forward-ref, poisoning the shared adapter
    cache for every other route in the app."""

    async def handler(request: Request, name: str) -> Response:
        return await _experience_entry(deps, request, name)

    return handler


def _make_experience_step_get_handler(deps: _ExperienceDeps) -> Any:
    """Closure factory for GET /experiences/{name}/{step} — see
    `_make_experience_entry_handler` for rationale (#1034 / #1112)."""

    async def handler(request: Request, name: str, step: str) -> Response:
        return await _experience_step_get(deps, request, name, step)

    return handler


def _make_experience_step_post_handler(deps: _ExperienceDeps) -> Any:
    """Closure factory for POST /experiences/{name}/{step} — see
    `_make_experience_entry_handler` for rationale (#1034 / #1112)."""

    async def handler(request: Request, name: str, step: str) -> Response:
        return await _experience_step_post(deps, request, name, step)

    return handler


async def _experience_entry(deps: _ExperienceDeps, request: Request, name: str) -> Response:
    """GET /experiences/{name} — redirect to current or start step."""
    from dazzle.page.runtime.experience_state import (
        cookie_name,
        create_initial_state,
        sign_state,
    )

    experience = deps.experiences_by_name.get(name)
    if not experience:
        return RedirectResponse(url=f"{deps.app_prefix}/", status_code=302)

    # Check for existing state: cookie first, then durable store
    cname = cookie_name(name)
    raw_cookie = request.cookies.get(cname)
    from dazzle.page.runtime.experience_state import verify_state

    state = verify_state(raw_cookie) if raw_cookie else None

    if state:
        target_step = state.step
    elif deps.progress_store:
        # Cookie expired or missing — try durable store for resume
        user_email = _get_user_email(deps, request)
        saved = deps.progress_store.load(name, user_email)
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
        url=f"{deps.app_prefix}/experiences/{name}/{target_step}",  # nosemgrep
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


async def _experience_step_get(
    deps: _ExperienceDeps, request: Request, name: str, step: str
) -> Response:
    """GET /experiences/{name}/{step} — render a step."""
    from dazzle.page.runtime.experience_renderer import render_experience_inner_html
    from dazzle.page.runtime.experience_state import (
        cookie_name,
        create_initial_state,
        sign_state,
    )

    experience = deps.experiences_by_name.get(name)
    if not experience:
        return RedirectResponse(url=f"{deps.app_prefix}/", status_code=302)

    # Validate step exists
    step_spec = experience.get_step(step)
    if not step_spec:
        return RedirectResponse(
            url=f"{deps.app_prefix}/experiences/{name}",
            status_code=302,
        )

    # Load or create state: cookie -> file store -> fresh
    state, _raw_cookie = _load_state(deps, request, name, experience.start_step)

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
                    url=f"{deps.app_prefix}/experiences/{name}/{state.step}",
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
            cname = cookie_name(name)
            state = state.model_copy(update={"step": next_step_name, "completed": completed})
            response = RedirectResponse(
                url=f"{deps.app_prefix}/experiences/{name}/{next_step_name}",
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
    from dazzle.page.converters.experience_compiler import compile_experience_context

    exp_ctx = compile_experience_context(experience, state, deps.appspec, deps.app_prefix)

    # Build template variables
    auth_ctx = _inject_auth(deps, request)

    from dazzle.http.runtime.htmx import HtmxDetails

    htmx = HtmxDetails.from_request(request)
    current_route = f"{deps.app_prefix}/experiences/{name}/{step}"

    # Fragment targeting: return only the content
    if htmx.wants_fragment:
        html = render_experience_inner_html(exp_ctx)
        headers = {
            "HX-Trigger": json.dumps({"dz:titleUpdate": exp_ctx.title}),
        }
        response = HTMLResponse(content=html, headers=headers)  # type: ignore[assignment]  # nosemgrep
    else:
        # Phase 4 experience-shell migration (v0.67.54): the outer
        # `experience/experience.html` Jinja shell (which extended
        # `layouts/app_shell.html`) is retired. We render the inner
        # `_content.html` via Jinja (form/detail/table step still
        # need its rich step-body logic) and wrap it in a typed
        # `Page` + `AppShell` via `dispatch_render_page` — same shape
        # used by the marketing-page + entity-surface routes.
        from dazzle.render.context import NavItemContext, PageContext
        from dazzle.render.dispatch import dispatch_render_page

        inner_html = render_experience_inner_html(exp_ctx)
        nav_items_ctx = [
            NavItemContext(
                label=getattr(n, "label", None) or n.get("label", "")
                if isinstance(n, dict)
                else getattr(n, "label", ""),
                route=getattr(n, "route", None) or n.get("route", "")
                if isinstance(n, dict)
                else getattr(n, "route", ""),
            )
            for n in (deps.nav_items or [])
        ]
        page_ctx = PageContext(
            page_title=exp_ctx.title or "",
            app_name=deps.app_name or "Dazzle",
            current_route=current_route,
            nav_items=nav_items_ctx,
            nav_groups=deps.nav_groups or [],
        )
        app_state = request.app.state
        css_links = tuple(
            getattr(app_state, "fragment_chrome_css_links", None)
            or ("/static/dist/dazzle.min.css",)
        )
        js_scripts = tuple(
            getattr(app_state, "fragment_chrome_js_scripts", None)
            or ("/static/dist/dazzle.min.js",)
        )
        theme = getattr(app_state, "fragment_chrome_theme", None)
        font_preconnect = tuple(getattr(app_state, "fragment_chrome_font_preconnect", None) or ())
        favicon = getattr(
            app_state,
            "fragment_chrome_favicon",
            "/static/assets/dazzle-favicon.svg",
        )
        html = dispatch_render_page(
            page_ctx,
            inner_html,
            css_links=css_links,
            js_scripts=js_scripts,
            theme=theme,
            font_preconnect=font_preconnect,
            favicon=favicon,
        )
        # auth_ctx + theme_css fields previously threaded into the
        # Jinja layout are dropped — the typed AppShell doesn't yet
        # surface persona affordances per the Phase 4 trade-off.
        _ = (auth_ctx, htmx)
        response = HTMLResponse(content=html)  # type: ignore[assignment]  # nosemgrep

    # Set state cookie on every response
    cname = cookie_name(name)
    response.set_cookie(
        cname,
        sign_state(state),
        httponly=True,
        samesite="lax",
        max_age=86400,
    )

    # Persist progress durably (survives cookie expiry / browser close)
    _persist_progress(deps, request, name, state)

    return response


async def _experience_step_post(
    deps: _ExperienceDeps, request: Request, name: str, step: str
) -> Response:
    """POST /experiences/{name}/{step}?event=X — process transition."""
    from dazzle.page.runtime.experience_state import (
        cookie_name,
        create_initial_state,
        sign_state,
    )

    experience = deps.experiences_by_name.get(name)
    if not experience:
        return RedirectResponse(url=f"{deps.app_prefix}/", status_code=302)

    step_spec = experience.get_step(step)
    if not step_spec:
        return RedirectResponse(
            url=f"{deps.app_prefix}/experiences/{name}",
            status_code=302,
        )

    # Load state: cookie -> file store -> fresh
    state, _raw_cookie = _load_state(deps, request, name, experience.start_step)

    if not state:
        state = create_initial_state(experience.start_step)

    # Determine event from query param
    event = request.query_params.get("event", "success")

    # For form steps, create the entity IN-PROCESS via the registered create
    # invoker. Only act when there's actually a matching transition (not terminal
    # steps).
    has_matching_transition = any(tr.event == event for tr in step_spec.transitions)

    if step_spec.kind == StepKind.SURFACE and has_matching_transition:
        # Resolve entity_ref from either the surface or the step directly
        entity_ref: str | None = None
        if step_spec.surface:
            for s in deps.appspec.surfaces:
                if s.name == step_spec.surface:
                    entity_ref = s.entity_ref
                    break
        elif step_spec.entity_ref:
            entity_ref = step_spec.entity_ref

        if entity_ref and event == "success":
            # Read request body. htmx 4 posts application/x-www-form-urlencoded
            # by default (the json-enc extension was dropped in the htmx 4
            # migration), so accept BOTH form-encoded and JSON — mirroring the
            # main write path's tolerant parser. Inlined (not imported) because
            # ui/ must not import back/ (ADR-0038).
            try:
                content_type = (request.headers.get("content-type") or "").lower()
                if (
                    "application/x-www-form-urlencoded" in content_type
                    or "multipart/form-data" in content_type
                ):
                    form = await request.form()
                    body = {k: (None if v == "" else v) for k, v in dict(form).items()}
                else:
                    body = await request.json()
            except Exception:
                body = {}

            # #1422: create IN-PROCESS via the SAME enforced create path (permit
            # gate + create-scope + ref/persona injection + audit + service.create).
            # Every create route — cedar / auth / noauth — registers an
            # `_inprocess_create` invoker (see route_generator + audit_wrap), so
            # there is no loopback self-fetch on the write path: the #1421
            # tenant-Host-loss class is structurally eliminated for writes too.
            from fastapi import HTTPException as _HTTPExc
            from fastapi.encoders import jsonable_encoder as _jse

            _invoker = getattr(request.app.state, "entity_create_invokers", {}).get(entity_ref)
            if _invoker is None:
                # Provably unreachable: an experience step that creates entity X
                # implies X has a create route, which always registers an invoker.
                # Fail loud (a framework bug) rather than silently self-fetching.
                raise RuntimeError(
                    f"No in-process create invoker registered for entity '{entity_ref}' "
                    "(experience-form POST). Every create route must register one."
                )

            _auth = deps.get_auth_context(request) if deps.get_auth_context else None
            try:
                _created = await _invoker(_auth, request, body=body)
                success, resp_data = True, _jse(_created)
            except _HTTPExc as _e:
                # Permit/scope/validation denial → re-render the step with the error.
                success = False
                resp_data = _e.detail if isinstance(_e.detail, dict) else {"detail": _e.detail}

            if not success:
                # Create denied/failed — re-render the step with error
                from dazzle.http.runtime.htmx import HtmxDetails, htmx_error_response

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
                                field_name = ".".join(str(p) for p in loc if p != "body")
                                messages.append(f"{field_name}: {msg}" if field_name else msg)
                            else:
                                messages.append(str(err))
                        errors = messages
                    return htmx_error_response(errors if errors else ["Submission failed"])
                # Non-HTMX: redirect back to the step
                return RedirectResponse(
                    url=f"{deps.app_prefix}/experiences/{name}/{step}",
                    status_code=302,
                )

            # Store the created entity ID in the data map (backward compat)
            new_data = {**state.data}
            if "id" in resp_data:
                new_data[f"{entity_ref}_id"] = resp_data["id"]
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

        from dazzle.http.runtime.htmx import HtmxDetails

        htmx = HtmxDetails.from_request(request)
        redirect_url = f"{deps.app_prefix}/"

        response: Response
        if htmx.is_htmx:
            response = HTMLResponse(  # nosemgrep
                content="",
                headers={"HX-Redirect": redirect_url},
            )
        else:
            response = RedirectResponse(url=redirect_url, status_code=302)

        # Clear the cookie and durable progress
        cname = cookie_name(name)
        response.delete_cookie(cname)
        if deps.progress_store:
            user_email = _get_user_email(deps, request)
            deps.progress_store.delete(name, user_email)
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

    redirect_url = f"{deps.app_prefix}/experiences/{name}/{next_step}"

    from dazzle.http.runtime.htmx import HtmxDetails

    htmx = HtmxDetails.from_request(request)

    if htmx.is_htmx:
        response = HTMLResponse(  # nosemgrep
            content="",
            headers={"HX-Redirect": redirect_url},
        )
    else:
        response = RedirectResponse(url=redirect_url, status_code=302)

    # Set state cookie
    cname = cookie_name(name)
    response.set_cookie(  # nosemgrep
        cname,
        sign_state(state),
        httponly=True,
        samesite="lax",
        max_age=86400,
    )

    # Persist progress durably
    _persist_progress(deps, request, name, state)

    return response


# =============================================================================
# Factory
# =============================================================================


def create_experience_routes(
    appspec: ir.AppSpec,
    theme_css: str = "",
    get_auth_context: Callable[..., Any] | None = None,
    app_prefix: str = "",
    project_root: Path | None = None,
) -> APIRouter:
    """Create FastAPI routes for all experiences in the appspec.

    Args:
        appspec: Complete application specification.
        theme_css: Pre-compiled theme CSS to inject.
        get_auth_context: Optional callable(request) -> AuthContext for user info.
        app_prefix: URL prefix for page routes (e.g. "/app").
        project_root: Project root for durable progress persistence.

    Returns:
        FastAPI router with experience routes.
    """
    from dazzle.page.runtime.experience_persistence import ExperienceProgressStore

    # Durable progress store (file-based, survives cookie expiry)
    progress_store: ExperienceProgressStore | None = None
    if project_root:
        progress_store = ExperienceProgressStore(project_root)

    router = APIRouter()

    # Index experiences by name for fast lookup
    experiences_by_name: dict[str, ir.ExperienceSpec] = {
        exp.name: exp for exp in appspec.experiences
    }

    # Build nav items and groups for sidebar context
    nav_items: list[dict[str, Any]] = []
    nav_groups: list[dict[str, Any]] = []

    # Build list-surface lookup for better nav_group labels
    _list_surfaces_by_entity: dict[str, Any] = {}
    for surface in getattr(appspec, "surfaces", []) or []:
        if surface.mode.value == "list" and surface.entity_ref:
            _list_surfaces_by_entity.setdefault(surface.entity_ref, surface)

    # Collect nav_groups; track workspaces that have groups
    workspaces_with_groups: set[str] = set()
    for ws in appspec.workspaces:
        if ws.nav_groups:
            workspaces_with_groups.add(ws.name)
        for ng in ws.nav_groups:
            nav_groups.append(
                {
                    "label": ng.label,
                    "icon": ng.icon,
                    "collapsed": ng.collapsed,
                    "children": [
                        {
                            "label": (
                                _list_surfaces_by_entity[item.entity].title
                                if item.entity in _list_surfaces_by_entity
                                and _list_surfaces_by_entity[item.entity].title
                                else item.entity.replace("_", " ").title()
                            ),
                            "route": f"{app_prefix}/{entity_slug(item.entity)}",
                            "icon": item.icon,
                        }
                        for item in ng.items
                    ],
                }
            )

    # Ungrouped workspaces become flat nav items
    for ws in appspec.workspaces:
        if ws.name not in workspaces_with_groups:
            nav_items.append(
                {
                    "label": ws.title or ws.name.replace("_", " ").title(),
                    "route": f"{app_prefix}/workspaces/{ws.name}",
                }
            )
    app_name = appspec.title or appspec.name.replace("_", " ").title()

    deps = _ExperienceDeps(
        appspec=appspec,
        theme_css=theme_css,
        get_auth_context=get_auth_context,
        app_prefix=app_prefix,
        experiences_by_name=experiences_by_name,
        nav_items=nav_items,
        nav_groups=nav_groups,
        app_name=app_name,
        progress_store=progress_store,
    )

    # Register routes — closure factories preserve the `request: Request`
    # annotation through FastAPI's signature introspection. See #1112.
    router.get("/experiences/{name}", response_class=HTMLResponse)(
        _make_experience_entry_handler(deps)
    )
    router.get("/experiences/{name}/{step}", response_class=HTMLResponse)(
        _make_experience_step_get_handler(deps)
    )
    router.post("/experiences/{name}/{step}", response_class=HTMLResponse)(
        _make_experience_step_post_handler(deps)
    )

    return router
