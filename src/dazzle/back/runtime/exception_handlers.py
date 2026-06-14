"""
Exception handlers for Dazzle backend runtime applications.

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

    from dazzle.back.runtime.htmx_response import HtmxDetails, json_or_htmx_error
    from dazzle.back.runtime.invariant_evaluator import InvariantViolationError
    from dazzle.back.runtime.repository import ConstraintViolationError
    from dazzle.back.runtime.state_machine import TransitionError

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
        """Convert invariant violations to 422 Unprocessable Entity.

        Surfaces the violated invariant's source expression, its declared
        ``code``, and the entity name so the UI can render an actionable error
        instead of a generic "constraint violated" (#1387).
        """
        from dazzle.back.runtime.invariant_evaluator import render_invariant_expr

        content: dict[str, Any] = {"detail": str(exc), "type": "invariant_violation"}
        inv = exc.invariant
        if inv is not None and getattr(inv, "expression", None) is not None:
            rendered = render_invariant_expr(inv.expression)
            if rendered:
                content["invariant"] = rendered
        if exc.entity:
            content["entity"] = exc.entity
        if HtmxDetails.from_request(request).is_htmx:
            return json_or_htmx_error(
                request,
                [{"loc": [], "msg": str(exc)}],
                error_type="invariant_violation",
            )
        return _JSONResponse(status_code=422, content=content)

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


def _typed_error_assets(request: Any) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Resolve the CSS+JS asset tuples for typed-Fragment error pages.

    Mirrors `_typed_chrome_assets` in `site_routes.py` — per-deployment
    overrides live on `app.state.fragment_chrome_css_links` and
    `app.state.fragment_chrome_js_scripts`, falling back to the
    framework-default minified bundles.
    """
    app_state = getattr(getattr(request, "app", None), "state", None)
    css = tuple(
        getattr(app_state, "fragment_chrome_css_links", None) or ("/static/dist/dazzle.min.css",)
    )
    js = tuple(
        getattr(app_state, "fragment_chrome_js_scripts", None) or ("/static/dist/dazzle.min.js",)
    )
    return css, js


def _render_app_shell_error(
    *,
    status_code: int,
    message: str,
    request: Any,
    app_name: str,
    forbidden_detail: dict[str, Any] | None = None,
    suggestions: list[dict[str, str]] | None = None,
) -> Any:
    """Render an in-app error page via the typed-Fragment views.

    Phase 2.B full (v0.67.40): replaces the Jinja `app/403.html` /
    `app/404.html` templates (which extended `layouts/app_shell.html`)
    with typed views in `dazzle_back.runtime.app_error_views`. The
    legacy templates already rendered with an empty sidebar / empty
    persona chrome because the helper passed empty `nav_items` /
    `user_email`, so the visual UX is comparable — but the rendering
    layer no longer depends on the much bigger app-shell Jinja chain.

    `forbidden_detail` carries the structured `#808` disclosure for
    403s; `suggestions` carries the `#811` "did you mean" list for
    404s. The 500 path uses neither — it's a generic apology page
    (CWE-209: exception detail never leaks to the response body).

    `status_code` selects the view: 403 / 404 / 500. Any other status
    code is rejected — the caller should route it through the JSON
    fallback in the dispatcher.
    """
    from fastapi.responses import HTMLResponse

    from dazzle.back.runtime.app_error_views import (
        build_app_403_view,
        build_app_404_view,
        build_app_500_view,
    )
    from dazzle.render.fragment.renderer import FragmentRenderer

    css_links, js_scripts = _typed_error_assets(request)
    back = _compute_back_affordance(str(request.url.path))
    back_url, back_label = back if back else ("", "")

    if status_code == 403:
        page = build_app_403_view(
            app_name=app_name,
            message=message,
            forbidden_detail=forbidden_detail,
            back_url=back_url,
            back_label=back_label,
            css_links=css_links,
            js_scripts=js_scripts,
        )
    elif status_code == 404:
        page = build_app_404_view(
            app_name=app_name,
            message=message,
            suggestions=suggestions,
            back_url=back_url,
            back_label=back_label,
            css_links=css_links,
            js_scripts=js_scripts,
        )
    elif status_code == 500:
        page = build_app_500_view(
            app_name=app_name,
            back_url=back_url,
            back_label=back_label,
            css_links=css_links,
            js_scripts=js_scripts,
        )
    else:
        raise ValueError(
            f"_render_app_shell_error: unsupported status_code {status_code}; "
            "expected 403, 404, or 500"
        )

    return HTMLResponse(content=FragmentRenderer().render(page), status_code=status_code)


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

    from dazzle.back.runtime.error_views import (
        build_site_403_view,
        build_site_404_view,
        build_site_500_view,
    )
    from dazzle.render.fragment.renderer import FragmentRenderer

    # Phase 2.A (v0.67.34): marketing-site error pages render via
    # typed-Fragment views that pull CSS/JS from `app.state` overrides
    # (same shape as the auth views in Phase 1). `project_root` is no
    # longer consulted here; the per-deployment override lives on
    # `app.state.fragment_chrome_css_links` instead.
    _ = project_root
    # Phase 2.A: brand-nested lookup matches the auth views' convention
    # (`sitespec.brand.product_name`). The pre-2.A code path read a
    # flat top-level `product_name` / `name`; sitespecs use the nested
    # `brand` key, so the marketing 403/404 used to fall back to
    # "Dazzle" in nearly every deployment.
    _brand = sitespec_data.get("brand") or {}
    app_name = (
        _brand.get("product_name")
        or sitespec_data.get("product_name")
        or sitespec_data.get("name")
        or "Dazzle"
    )

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
            css_links, js_scripts = _typed_error_assets(request)
            page = build_site_403_view(
                product_name=app_name,
                message=message,
                forbidden_detail=forbidden_detail,
                css_links=css_links,
                js_scripts=js_scripts,
            )
            return HTMLResponse(
                content=FragmentRenderer().render(page),
                status_code=403,
            )

        if exc.status_code == 404 and is_browser:
            if _is_app_path(str(request.url.path)):
                path_suggestions = _compute_404_suggestions(
                    str(request.url.path), entity_slugs, workspace_slugs
                )
                return _render_app_shell_error(
                    status_code=404,
                    message="The page you're looking for doesn't exist.",
                    request=request,
                    app_name=app_name,
                    suggestions=path_suggestions or None,
                )
            css_links, js_scripts = _typed_error_assets(request)
            page = build_site_404_view(
                product_name=app_name,
                css_links=css_links,
                js_scripts=js_scripts,
            )
            return HTMLResponse(
                content=FragmentRenderer().render(page),
                status_code=404,
            )

        if exc.status_code == 500 and is_browser:
            # Phase 2.B full (v0.67.40): both marketing AND app-shell
            # 500 paths render a typed view now. The app-shell variant
            # uses the typed app-shell-lite view via
            # `_render_app_shell_error`; the marketing variant uses
            # `build_site_500_view` directly.
            if _is_app_path(str(request.url.path)):
                return _render_app_shell_error(
                    status_code=500,
                    message="",
                    request=request,
                    app_name=app_name,
                )
            css_links, js_scripts = _typed_error_assets(request)
            page = build_site_500_view(
                product_name=app_name,
                css_links=css_links,
                js_scripts=js_scripts,
            )
            return HTMLResponse(
                content=FragmentRenderer().render(page),
                status_code=500,
            )

        # For API requests or other status codes, return JSON
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Any, exc: Exception) -> Any:
        """Phase 2.B partial (v0.67.36): convert unhandled exceptions
        to a typed-Fragment 500 page for browsers (or JSON for API
        callers). Pre-2.B the framework relied on Starlette's
        plain-text default, which leaked nothing useful and skipped
        the framework's CSS chrome.

        The exception is re-raised in test mode (when the FastAPI
        ``debug`` flag is set), so test failures still surface the
        traceback. In production, the exception is swallowed at this
        layer; upstream logging middleware is responsible for the
        traceback record.
        """
        import logging

        from fastapi.responses import HTMLResponse, JSONResponse

        # In debug mode (tests + local development), re-raise so the
        # traceback isn't hidden behind a friendly page.
        if getattr(app, "debug", False):
            raise exc

        logging.getLogger("dazzle.errors").exception(
            "Unhandled exception on %s %s",
            getattr(request, "method", "?"),
            getattr(getattr(request, "url", None), "path", "?"),
        )

        accept = request.headers.get("accept", "") if hasattr(request, "headers") else ""
        is_browser = "text/html" in accept

        if is_browser:
            request_path = str(getattr(request.url, "path", "/"))
            if _is_app_path(request_path):
                return _render_app_shell_error(
                    status_code=500,
                    message="",
                    request=request,
                    app_name=app_name,
                )
            css_links, js_scripts = _typed_error_assets(request)
            page = build_site_500_view(
                product_name=app_name,
                css_links=css_links,
                js_scripts=js_scripts,
            )
            return HTMLResponse(
                content=FragmentRenderer().render(page),
                status_code=500,
            )

        return JSONResponse(
            status_code=500,
            content={"detail": "Internal Server Error"},
        )
