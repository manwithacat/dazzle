"""Public helper for rendering project-side routes inside the
framework app shell (#951).

Background: the `# dazzle:route-override` decorator (and any other
project-registered FastAPI handler) can return arbitrary `Response`s,
but until #951 there was no first-class way to render the page
*inside* the framework's standard `dz://layouts/app_shell.html`. The
shell needs `app_name`, `nav_items`, `nav_groups`, auth context,
and a handful of optional metadata fields the page handler usually
populates per-request.

This module exposes:

- `ShellState` — registered on `app.state.shell_state` during
  framework boot, carrying the nav data + app-wide config the
  shell template reads.
- `register_shell_state(app, ...)` — called from
  `create_page_routes` so the shell helpers are available without
  the project depending on `_PageDeps` internals.
- `render_in_app_shell(request, *, template, ...) -> Response` —
  the public one-liner project authors call. Resolves auth + nav
  per-request and returns a TemplateResponse extending the
  framework app shell.

The project-side template should `{% extends "layouts/app_shell.html" %}`
and provide a `{% block content %}…{% endblock %}` body.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ShellState:
    """Per-app shell context registered on `app.state.shell_state`.

    The framework populates this once at boot via
    `register_shell_state()`. Project routes read it via the public
    `render_in_app_shell()` helper.

    Fields:
        app_name: Display name in topbar + sidebar brand. Defaults
            to "Dazzle" if unset.
        nav_items: Flat sidebar nav list (NavItemContext-shaped dicts
            or objects). Used as the fallback when no per-persona
            variant matches.
        nav_groups: Collapsible sidebar nav groups (NavGroupContext-
            shaped). Same fallback behaviour as `nav_items`.
        nav_by_persona: Mapping of persona-id → flat nav list.
            Persona-aware nav surfaces only the items the user's
            role(s) can access.
        nav_groups_by_persona: Same shape as `nav_by_persona` for
            groups.
        get_auth_context: Callable(request) → AuthContext. Resolves
            auth at render time so the shell shows the right user
            and gates the dark-mode toggle.
        dark_mode_toggle_enabled: Boolean / callable controlling
            the topbar's theme switcher.
        app_prefix: URL prefix for app pages (e.g. `/app`). Used
            for active-nav highlighting.
    """

    app_name: str = "Dazzle"
    nav_items: list[Any] = field(default_factory=list)
    nav_groups: list[dict[str, Any]] = field(default_factory=list)
    nav_by_persona: dict[str, list[Any]] = field(default_factory=dict)
    nav_groups_by_persona: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    get_auth_context: Callable[..., Any] | None = None
    dark_mode_toggle_enabled: bool = True
    app_prefix: str = ""


def register_shell_state(app: Any, state: ShellState) -> None:
    """Attach `ShellState` to `app.state.shell_state` so
    `render_in_app_shell()` can find it.

    Called once during framework boot from `app_factory.py` after
    `create_page_routes` has built the nav data. Idempotent —
    repeated calls overwrite, which matches the framework's
    boot-once-per-app contract."""
    app.state.shell_state = state


def build_shell_state(
    appspec: Any,
    *,
    get_auth_context: Callable[..., Any] | None = None,
    app_prefix: str = "/app",
    dark_mode_toggle_enabled: bool = True,
) -> ShellState:
    """Compute a `ShellState` from an AppSpec.

    Mirrors the nav-building logic in
    `template_compiler.compile_appspec_to_templates` but emits a
    standalone snapshot suitable for project-side `render_in_app_shell`
    callers. Workspace iteration order matches the framework's
    sidebar order so projects see the same nav structure as
    auto-generated pages.

    Args:
        appspec: The compiled AppSpec.
        get_auth_context: Optional callable(request) → AuthContext.
            When set, the helper resolves auth at render time so the
            shell shows the right user.
        app_prefix: URL prefix for app pages (e.g. `/app`).
        dark_mode_toggle_enabled: Boolean controlling the topbar
            theme switcher.

    Returns:
        Fully-populated `ShellState`. Pass to `register_shell_state`
        to attach it to a FastAPI app.
    """
    app_name = (
        getattr(appspec, "title", None)
        or str(getattr(appspec, "name", "")).replace("_", " ").title()
        or "Dazzle"
    )

    # Persona-aware nav. Rebuild from workspace access + entity
    # surface presence — same shape `template_compiler` emits.
    from dazzle_ui.converters.workspace_converter import (
        workspace_allowed_personas,
    )

    nav_items: list[dict[str, str]] = []
    nav_by_persona: dict[str, list[dict[str, str]]] = {}

    personas_list = list(getattr(appspec, "personas", []) or [])
    all_pids = [p.id for p in personas_list if p.id]

    for ws in getattr(appspec, "workspaces", []) or []:
        item = {
            "label": ws.title or ws.name.replace("_", " ").title(),
            "route": f"{app_prefix}/workspaces/{ws.name}",
        }
        nav_items.append(item)
        allowed = workspace_allowed_personas(ws, personas_list)
        pids_for_ws = all_pids if allowed is None else list(allowed)
        for pid in pids_for_ws:
            nav_by_persona.setdefault(pid, []).append(item)

    return ShellState(
        app_name=app_name,
        nav_items=nav_items,
        nav_groups=[],
        nav_by_persona=nav_by_persona,
        nav_groups_by_persona={},
        get_auth_context=get_auth_context,
        dark_mode_toggle_enabled=dark_mode_toggle_enabled,
        app_prefix=app_prefix,
    )


def get_shell_state(request: Any) -> ShellState:
    """Resolve the shell state from the current request's app.

    Returns an empty default `ShellState` when nothing was
    registered (e.g. unit tests using a bare FastAPI app). The
    helper still works in that mode — pages just render with empty
    nav, which is preferable to throwing an exception during
    rendering."""
    try:
        state = request.app.state.shell_state
        if isinstance(state, ShellState):
            return state
    except AttributeError:
        pass
    return ShellState()


def render_in_app_shell(
    request: Any,
    *,
    template: str,
    title: str | None = None,
    purpose: str | None = None,
    active_nav_route: str | None = None,
    surface_name: str | None = None,
    view_name: str | None = None,
    workspace_name: str | None = None,
    context: dict[str, Any] | None = None,
) -> Any:
    """Render a project template inside the framework app shell.

    The project template must `{% extends "layouts/app_shell.html" %}`
    and provide a `{% block content %}…{% endblock %}` body. The
    helper supplies every variable `app_shell.html` reads, derived
    from request auth + the registered `ShellState` + the kwargs.

    Args:
        request: The FastAPI request. Used to resolve auth + the
            current URL for active-nav highlighting.
        template: Project template path, e.g. `"fastmark/upload.html"`.
            Must be discoverable by the framework's Jinja env (i.e.
            inside the project's templates/ dir).
        title: Optional `<title>` text and topbar headline. Defaults
            to the manifest's `app_name`.
        purpose: Optional muted subtitle line under the topbar
            heading (the framework's `page_purpose` slot).
        active_nav_route: Optional route to mark as the current
            page in the sidebar. Falls back to `request.url.path`
            so the right item highlights without manual tagging
            in most cases.
        surface_name / view_name / workspace_name: Optional
            attributes the shell exposes via `data-dz-surface`,
            `data-dazzle-view`, `data-dz-workspace` for
            instrumentation / agent introspection.
        context: Project-specific variables the page template's
            `{% block content %}` consumes. Merged into the render
            context after the framework's keys, so projects can
            override anything except the structural shell fields.

    Returns:
        Starlette `HTMLResponse` ready to return from the FastAPI
        handler. Status code 200 in the success path.
    """
    from fastapi.templating import Jinja2Templates

    from dazzle_ui.runtime.template_renderer import get_jinja_env

    state = get_shell_state(request)

    # Auth: best-effort — if the project's route is unauthenticated
    # the shell still renders, just without user identity. Project
    # handlers that require auth should guard themselves before
    # calling this helper (status 302 / 401 / etc.).
    is_authenticated = False
    user_email = ""
    user_name = ""
    user_roles: list[str] = []
    if state.get_auth_context is not None:
        try:
            auth_ctx = state.get_auth_context(request)
            if auth_ctx and auth_ctx.is_authenticated:
                is_authenticated = True
                user_email = (auth_ctx.user.email if auth_ctx.user else "") or ""
                user_name = (auth_ctx.user.username if auth_ctx.user else "") or ""
                user_roles = list(getattr(auth_ctx.user, "roles", None) or [])
        except Exception:
            logger.debug(
                "Failed to resolve auth for app-shell render",
                exc_info=True,
            )

    # Persona-aware nav: pick the per-persona variant for the user's
    # first matching role. Roles are prefixed `role_` in the auth
    # store; persona ids on the nav-by-persona map are not. Strip
    # the prefix when matching.
    nav_items: list[Any] = list(state.nav_items)
    nav_groups: list[dict[str, Any]] = list(state.nav_groups)
    if state.nav_by_persona and user_roles:
        for role in user_roles:
            persona_nav = state.nav_by_persona.get(role.removeprefix("role_"))
            if persona_nav is not None:
                nav_items = list(persona_nav)
                break
    if state.nav_groups_by_persona and user_roles:
        for role in user_roles:
            persona_groups = state.nav_groups_by_persona.get(role.removeprefix("role_"))
            if persona_groups is not None:
                nav_groups = list(persona_groups)
                break

    # Active-nav route. Fall back to the request's current path so
    # nav highlighting works without the project route having to
    # know which sidebar entry maps to it.
    current_route = active_nav_route or str(getattr(request.url, "path", ""))

    # Build the merged template context.
    merged_context: dict[str, Any] = {
        "request": request,
        "page_title": title or state.app_name,
        "app_name": state.app_name,
        "is_authenticated": is_authenticated,
        "user_email": user_email,
        "user_name": user_name,
        "user_roles": user_roles,
        "nav_items": nav_items,
        "nav_groups": nav_groups,
        "current_route": current_route,
        "page_purpose": purpose or "",
        "surface_name": surface_name or "",
        "view_name": view_name or "",
        "workspace_name": workspace_name or "",
    }
    if context:
        # Project context wins over framework defaults — lets a
        # project override e.g. `app_name` for a one-off page.
        merged_context.update(context)

    env = get_jinja_env()
    templates = Jinja2Templates(env=env)
    # Starlette deprecated the old `TemplateResponse(name, ctx)` form
    # in favour of `TemplateResponse(request, name, ctx)`. Pass the
    # request explicitly to silence the warning AND ensure
    # request-context-dependent template features (e.g. url_for)
    # have access to it.
    return templates.TemplateResponse(request, template, merged_context)
