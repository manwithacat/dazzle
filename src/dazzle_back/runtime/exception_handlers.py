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


def register_site_error_handlers(
    app: FastAPI,
    sitespec_data: dict[str, Any],
    project_root: Path | None = None,
) -> None:
    """
    Register custom HTTP error handlers for site pages.

    Returns HTML error pages for browser requests when a SiteSpec is configured:
    - 403: Access denied page
    - 404: Page not found page
    API requests still receive JSON responses.

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

    @app.exception_handler(StarletteHTTPException)
    async def custom_http_error_handler(request: Any, exc: StarletteHTTPException) -> Any:
        """Custom error handler that renders HTML for browser requests."""
        from fastapi.responses import HTMLResponse

        accept = request.headers.get("accept", "")
        is_browser = "text/html" in accept

        if exc.status_code == 403 and is_browser:
            message = exc.detail if isinstance(exc.detail, str) else "Access denied"
            ctx = build_site_error_context(
                sitespec_data, message=message, custom_css=has_custom_css
            )
            return HTMLResponse(
                content=render_site_page("site/403.html", ctx),
                status_code=403,
            )

        if exc.status_code == 404 and is_browser:
            ctx = build_site_404_context(sitespec_data, custom_css=has_custom_css)
            return HTMLResponse(
                content=render_site_page("site/404.html", ctx),
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
