"""
Exception handlers for DNR-Back applications.

Provides centralized exception handling for:
- State machine transition errors
- Invariant violations
- Pydantic validation errors
- Custom 404 pages for site rendering
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import FastAPI


def register_exception_handlers(app: FastAPI) -> None:
    """
    Register standard exception handlers on a FastAPI application.

    Handles:
    - TransitionError: State machine transition failures (422)
    - InvariantViolationError: Business rule violations (422)
    - ValidationError: Pydantic validation errors (422)

    Args:
        app: FastAPI application instance
    """
    from fastapi import Request
    from fastapi.responses import JSONResponse
    from pydantic import ValidationError

    from dazzle_back.runtime.invariant_evaluator import InvariantViolationError
    from dazzle_back.runtime.repository import ConstraintViolationError
    from dazzle_back.runtime.state_machine import TransitionError

    @app.exception_handler(ConstraintViolationError)
    async def constraint_violation_handler(
        request: Request, exc: ConstraintViolationError
    ) -> JSONResponse:
        """Convert database constraint violations to 422 Unprocessable Entity."""
        detail: dict[str, Any] = {
            "detail": str(exc),
            "type": "constraint_violation",
            "constraint_type": exc.constraint_type,
        }
        if exc.field:
            detail["field"] = exc.field
        return JSONResponse(status_code=422, content=detail)

    @app.exception_handler(TransitionError)
    async def transition_error_handler(request: Request, exc: TransitionError) -> JSONResponse:
        """Convert state machine errors to 422 Unprocessable Entity."""
        return JSONResponse(
            status_code=422,
            content={"detail": str(exc), "type": "transition_error"},
        )

    @app.exception_handler(InvariantViolationError)
    async def invariant_error_handler(
        request: Request, exc: InvariantViolationError
    ) -> JSONResponse:
        """Convert invariant violations to 422 Unprocessable Entity."""
        return JSONResponse(
            status_code=422,
            content={"detail": str(exc), "type": "invariant_violation"},
        )

    @app.exception_handler(ValidationError)
    async def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
        """Convert validation errors to 422 Unprocessable Entity with field details."""
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
        return JSONResponse(
            status_code=422,
            content={"detail": errors, "type": "validation_error"},
        )


def register_site_404_handler(app: FastAPI, sitespec_data: dict[str, Any]) -> None:
    """
    Register custom 404 handler for site pages.

    Returns HTML 404 pages for browser requests when a SiteSpec is configured.
    API requests still receive JSON responses.

    Args:
        app: FastAPI application instance
        sitespec_data: SiteSpec configuration dictionary
    """
    from starlette.exceptions import HTTPException as StarletteHTTPException

    from dazzle_ui.runtime.site_renderer import render_404_page_html

    @app.exception_handler(StarletteHTTPException)
    async def custom_404_handler(request: Any, exc: StarletteHTTPException) -> Any:
        """Custom 404 handler that renders HTML for browser requests."""
        if exc.status_code == 404:
            from fastapi.responses import HTMLResponse

            # Only serve HTML 404 for browser requests (not API calls)
            accept = request.headers.get("accept", "")
            if "text/html" in accept:
                return HTMLResponse(
                    content=render_404_page_html(sitespec_data, str(request.url.path)),
                    status_code=404,
                )

        # For non-404 or API requests, return default JSON response
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )
