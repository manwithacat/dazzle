"""
Exception handlers for DNR-Back applications.

Provides centralized exception handling for:
- State machine transition errors
- Invariant violations
- Pydantic validation errors
- Custom 404 pages for site rendering

HTMX-aware: when HX-Request header is present, validation errors return
rendered HTML fragments with HX-Retarget instead of raw JSON.
"""

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import Response


def register_exception_handlers(app: FastAPI) -> None:
    """
    Register standard exception handlers on a FastAPI application.

    Handles:
    - TransitionError: State machine transition failures (422)
    - InvariantViolationError: Business rule violations (422)
    - ValidationError: Pydantic validation errors (422)
    - ConstraintViolationError: Database constraint violations (422)

    For HTMX requests, validation errors return rendered HTML fragments
    targeted at #form-errors instead of raw JSON.

    Args:
        app: FastAPI application instance
    """
    from fastapi import Request
    from fastapi.responses import JSONResponse as _JSONResponse
    from pydantic import ValidationError

    from dazzle_back.runtime.htmx_response import HtmxDetails, json_or_htmx_error
    from dazzle_back.runtime.invariant_evaluator import InvariantViolationError
    from dazzle_back.runtime.repository import ConstraintViolationError
    from dazzle_back.runtime.state_machine import TransitionError

    @app.exception_handler(ConstraintViolationError)
    async def constraint_violation_handler(
        request: Request, exc: ConstraintViolationError
    ) -> Response:
        """Convert database constraint violations to 422 Unprocessable Entity."""
        if HtmxDetails.from_request(request).is_htmx:
            return json_or_htmx_error(
                request,
                [{"loc": [exc.field] if exc.field else [], "msg": str(exc)}],
                error_type="constraint_violation",
            )
        detail: dict[str, Any] = {
            "detail": str(exc),
            "type": "constraint_violation",
            "constraint_type": exc.constraint_type,
        }
        if exc.field:
            detail["field"] = exc.field
        return _JSONResponse(status_code=422, content=detail)

    @app.exception_handler(TransitionError)
    async def transition_error_handler(request: Request, exc: TransitionError) -> Response:
        """Convert state machine errors to 422 Unprocessable Entity."""
        if HtmxDetails.from_request(request).is_htmx:
            return json_or_htmx_error(
                request,
                [{"loc": [], "msg": str(exc)}],
                error_type="transition_error",
            )
        return _JSONResponse(
            status_code=422,
            content={"detail": str(exc), "type": "transition_error"},
        )

    @app.exception_handler(InvariantViolationError)
    async def invariant_error_handler(request: Request, exc: InvariantViolationError) -> Response:
        """Convert invariant violations to 422 Unprocessable Entity."""
        if HtmxDetails.from_request(request).is_htmx:
            return json_or_htmx_error(
                request,
                [{"loc": [], "msg": str(exc)}],
                error_type="invariant_violation",
            )
        return _JSONResponse(
            status_code=422,
            content={"detail": str(exc), "type": "invariant_violation"},
        )

    @app.exception_handler(ValidationError)
    async def validation_error_handler(request: Request, exc: ValidationError) -> Response:
        """Convert validation errors to 422 Unprocessable Entity with field details.

        For HTMX requests: renders form_errors.html fragment with HX-Retarget
        to #form-errors so the error displays in-place without destroying the form.

        For API requests: returns JSON with structured error details.
        """
        # Pydantic errors() can contain non-serializable objects in ctx
        # (e.g. raw ValueError instances from AfterValidator). Sanitize them.
        errors: list[dict[str, Any]] = []
        for err in exc.errors():
            clean: dict[str, Any] = {}
            for k, v in err.items():
                if k == "ctx" and isinstance(v, dict):
                    clean[k] = {ck: str(cv) for ck, cv in v.items()}
                else:
                    clean[k] = v
            errors.append(clean)

        return json_or_htmx_error(request, errors, error_type="validation_error")


def _is_app_path(path: str) -> bool:
    """Return True if the given request path is inside the authenticated app shell.

    The authenticated app runs under ``/app/*``; the marketing site is
    everything else. Error pages under ``/app/*`` need to render inside
    the app shell so logged-in users keep their sidebar and persona
    context — see manwithacat/dazzle#776.
    """
    return path == "/app" or path.startswith("/app/")


def _levenshtein(a: str, b: str) -> int:
    """Minimal Levenshtein distance between two strings. Used for
    fuzzy-matching failed URL segments against known entity slugs.
    We roll our own to avoid pulling ``python-Levenshtein`` for a
    handful of length-≤20 inputs hit only on 404 paths.
    """
    if len(a) < len(b):
        return _levenshtein(b, a)
    if not b:
        return len(a)
    prev: list[int] = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr: list[int] = [i + 1]
        for j, cb in enumerate(b):
            insert = curr[j] + 1
            delete = prev[j + 1] + 1
            subst = prev[j] + (0 if ca == cb else 1)
            curr.append(min(insert, delete, subst))
        prev = curr
    return prev[-1]


def _compute_404_suggestions(
    path: str,
    entity_slugs: list[str],
    workspace_slugs: list[str],
) -> list[dict[str, str]]:
    """Return up to 3 plausible URL suggestions for a failed ``path``.

    Three heuristics, in order of precedence:

    1. **Plural/singular flip** — ``/app/tickets`` when ``ticket`` is
       a known entity slug yields ``/app/ticket``.
    2. **'Dashboard' alias** — bare ``/dashboard`` or ``/app/dashboard``
       yields ``/app`` (the default workspace entry point).
    3. **Fuzzy match** — Levenshtein ≤ 2 against entity or workspace
       slugs; e.g. ``/app/conatct`` → ``/app/contact``.

    Output is a list of ``{"url": ..., "label": ...}`` dicts for the
    404 template to render as links. Empty list if nothing plausible.
    """
    suggestions: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    def _push(url: str, label: str) -> None:
        if url in seen_urls:
            return
        seen_urls.add(url)
        suggestions.append({"url": url, "label": label})

    normalised = path.rstrip("/") or "/"
    segments = [s for s in normalised.split("/") if s]

    # "Dashboard" alias: /dashboard or /app/dashboard
    if segments in (["dashboard"], ["app", "dashboard"]):
        _push("/app", "Dashboard")
        return suggestions

    # /app/{slug}[/...] — try plural/singular flip, then fuzzy match
    if len(segments) >= 2 and segments[0] == "app" and segments[1] != "workspaces":
        candidate = segments[1]

        if candidate.endswith("s") and candidate[:-1] in entity_slugs:
            _push(f"/app/{candidate[:-1]}", candidate[:-1].replace("-", " ").title())

        for slug in entity_slugs:
            if slug == candidate or slug in seen_urls:
                continue
            if _levenshtein(slug, candidate) <= 2:
                _push(f"/app/{slug}", slug.replace("-", " ").title())
                if len(suggestions) >= 3:
                    break

    # /app/workspaces/{name} — fuzzy match against known workspace slugs
    if len(segments) >= 3 and segments[0] == "app" and segments[1] == "workspaces":
        candidate = segments[2]
        for ws in workspace_slugs:
            if _levenshtein(ws, candidate) <= 2:
                _push(f"/app/workspaces/{ws}", ws.replace("_", " ").title())
                if len(suggestions) >= 3:
                    break

    return suggestions[:3]


def _compute_back_affordance(path: str) -> tuple[str, str] | None:
    """Compute a 'Back to {parent}' affordance for an in-app error page.

    Given ``/app/contact/{bad_id}``, returns ``('/app/contact', 'Back to List')``.
    Given ``/app/workspaces/{bad_ws}``, returns ``('/app', 'Back to Dashboard')``.
    Returns None for paths where no sensible parent exists.
    """
    segments = [s for s in path.split("/") if s]
    # segments: ['app', <surface>, <...>]
    if len(segments) < 2 or segments[0] != "app":
        return None
    if len(segments) == 2:
        # /app/<surface> — parent is /app
        return ("/app", "Back to Dashboard")
    # /app/<surface>/<id-or-more> — parent is /app/<surface>
    surface = segments[1]
    if surface == "workspaces":
        return ("/app", "Back to Dashboard")
    return (f"/app/{surface}", "Back to List")


def _render_app_shell_error(
    *,
    template_name: str,
    status_code: int,
    message: str,
    request: Any,
    app_name: str,
    forbidden_detail: dict[str, Any] | None = None,
    suggestions: list[dict[str, str]] | None = None,
) -> Any:
    """Render an in-app error page inside the authenticated app shell.

    Builds a minimal context that the ``layouts/app_shell.html`` layout
    can render without crashing — the sidebar uses ``nav_items|default([])``
    so an empty nav is harmless; the navbar uses ``user_email|default('')``
    so a missing email is also fine. The page looks like an authenticated
    surface (sidebar present, persona chrome visible) even though the
    error handler doesn't have access to the full ``PageRouteContext``.

    When ``forbidden_detail`` is provided (see ``#808``), the 403
    template receives the structured disclosure — which roles are
    permitted, which roles the user actually has — so the page can
    tell the user "signed in as X; this page requires Y" rather than
    leaving them stranded with a bare "Forbidden".
    """
    from fastapi.responses import HTMLResponse

    # Delegate to the existing render_fragment wrapper. It uses the same
    # autoescape-configured Jinja env as render_page / render_site_page,
    # and the templates we render here (app/404.html, app/403.html)
    # extend layouts/app_shell.html so inheritance resolves normally.
    from dazzle_ui.runtime.template_renderer import render_fragment

    back = _compute_back_affordance(str(request.url.path))

    # Minimal context — the app_shell layout's blocks all use `| default`
    # for optional keys, so we only need to fill in what this error page
    # template references directly. The sidebar renders empty but the
    # chrome stays intact.
    ctx: dict[str, Any] = {
        "app_name": app_name,
        "message": message,
        "is_authenticated": True,
        "nav_items": [],
        "nav_groups": [],
        "user_email": "",
        "user_name": "",
        "user_roles": [],
        "current_route": str(request.url.path),
    }
    if back:
        ctx["back_url"], ctx["back_label"] = back

    if forbidden_detail:
        ctx["forbidden_detail"] = forbidden_detail

    if suggestions:
        ctx["suggestions"] = suggestions

    html = render_fragment(template_name, **ctx)
    return HTMLResponse(content=html, status_code=status_code)


def register_site_error_handlers(
    app: FastAPI,
    sitespec_data: dict[str, Any],
    project_root: Path | None = None,
    appspec: Any = None,
) -> None:
    """
    Register custom HTTP error handlers for site pages.

    Returns HTML error pages for browser requests when a SiteSpec is configured:
    - 403: Access denied page
    - 404: Page not found page
    API requests still receive JSON responses.

    **In-app vs marketing dispatch (manwithacat/dazzle#776):** when the request path
    starts with ``/app/``, renders the error inside the authenticated
    app shell so logged-in users keep their sidebar and persona
    context. Otherwise renders the public marketing-site variant.

    Args:
        app: FastAPI application instance
        sitespec_data: SiteSpec configuration dictionary
        project_root: Project root for detecting custom CSS
    """
    from starlette.exceptions import HTTPException as StarletteHTTPException

    from dazzle_ui.runtime.site_context import build_site_404_context, build_site_error_context
    from dazzle_ui.runtime.template_renderer import render_site_page

    has_custom_css = bool(
        project_root and (project_root / "static" / "css" / "custom.css").is_file()
    )
    app_name = sitespec_data.get("product_name") or sitespec_data.get("name") or "Dazzle"

    # Precompute known slugs once; the 404 handler closes over these
    # to suggest plausible alternatives when a path misses (#811).
    entity_slugs: list[str] = []
    workspace_slugs: list[str] = []
    if appspec is not None:
        try:
            entity_slugs = [e.name.lower().replace("_", "-") for e in appspec.domain.entities]
            workspace_slugs = [w.name for w in getattr(appspec, "workspaces", []) or []]
        except AttributeError:
            pass

    @app.exception_handler(StarletteHTTPException)
    async def custom_http_error_handler(request: Any, exc: StarletteHTTPException) -> Any:
        """Custom error handler that renders HTML for browser requests."""
        from fastapi.responses import HTMLResponse

        accept = request.headers.get("accept", "")
        is_browser = "text/html" in accept

        if exc.status_code == 403 and is_browser:
            # #808: detail may arrive as a structured dict carrying the
            # role disclosure (from route_generator._forbidden_detail).
            # Unpack it so the template can render "signed in as X;
            # requires Y" affordances.
            forbidden_detail: dict[str, Any] | None = None
            if isinstance(exc.detail, dict):
                forbidden_detail = exc.detail
                message = exc.detail.get("message") or "Access denied"
            elif isinstance(exc.detail, str):
                message = exc.detail
            else:
                message = "Access denied"

            is_htmx = request.headers.get("hx-request", "").lower() == "true"

            if _is_app_path(str(request.url.path)):
                resp = _render_app_shell_error(
                    template_name="app/403.html",
                    status_code=403,
                    message=message,
                    request=request,
                    app_name=app_name,
                    forbidden_detail=forbidden_detail,
                )
                # For HTMX fragment fetches, set HX-Retarget + HX-Reswap
                # so the error page renders into the main content area
                # rather than being silently swallowed as a non-2xx
                # response (HTMX default behaviour).
                if is_htmx:
                    resp.headers["HX-Retarget"] = "#main-content"
                    resp.headers["HX-Reswap"] = "innerHTML"
                    # Restore the URL so the user sees where they were
                    # denied, rather than the bare page they were on.
                    resp.headers["HX-Push-Url"] = str(request.url.path)
                return resp
            ctx = build_site_error_context(
                sitespec_data, message=message, custom_css=has_custom_css
            )
            return HTMLResponse(
                content=render_site_page("site/403.html", ctx),
                status_code=403,
            )

        if exc.status_code == 404 and is_browser:
            if _is_app_path(str(request.url.path)):
                path_suggestions = _compute_404_suggestions(
                    str(request.url.path), entity_slugs, workspace_slugs
                )
                return _render_app_shell_error(
                    template_name="app/404.html",
                    status_code=404,
                    message="The page you're looking for doesn't exist.",
                    request=request,
                    app_name=app_name,
                    suggestions=path_suggestions or None,
                )
            ctx_404 = build_site_404_context(sitespec_data, custom_css=has_custom_css)
            return HTMLResponse(
                content=render_site_page("site/404.html", ctx_404),
                status_code=404,
            )

        # For API requests or other status codes, return JSON
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )


# Backward-compatible alias
register_site_404_handler = register_site_error_handlers
