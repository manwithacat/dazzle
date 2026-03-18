"""
FastAPI optional-import compatibility shim.

All FastAPI symbols used across ``dazzle_back.runtime`` are imported here in a
single try/except block.  Every other module imports from here instead of
repeating the guard locally.

When FastAPI is not installed every symbol is set to ``None`` so that
``if not FASTAPI_AVAILABLE`` guards still work correctly at runtime.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Core FastAPI symbols
# ---------------------------------------------------------------------------
try:
    from fastapi import (  # type: ignore[assignment]
        APIRouter,
        Cookie,
        Depends,
        HTTPException,
        Query,
        Request,
        Response,
    )
    from fastapi import FastAPI as _FastAPI  # type: ignore[assignment]
    from fastapi import Request as FastAPIRequest  # type: ignore[assignment]
    from fastapi.middleware.cors import CORSMiddleware  # type: ignore[assignment]
    from fastapi.responses import (  # type: ignore[assignment]
        HTMLResponse,
        JSONResponse,
        RedirectResponse,
    )
    from starlette.responses import Response as StarletteResponse  # type: ignore[assignment]

    FASTAPI_AVAILABLE = True

except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = None  # type: ignore[assignment,misc]
    Cookie = None  # type: ignore[assignment,misc]
    CORSMiddleware = None  # type: ignore[assignment,misc]
    Depends = None  # type: ignore[assignment,misc]
    _FastAPI = None  # type: ignore[assignment,misc]
    FastAPIRequest = None  # type: ignore[assignment,misc]
    HTMLResponse = None  # type: ignore[assignment,misc]
    HTTPException = None  # type: ignore[assignment,misc]
    JSONResponse = None  # type: ignore[assignment,misc]
    Query = None  # type: ignore[assignment,misc]
    RedirectResponse = None  # type: ignore[assignment,misc]
    Request = None  # type: ignore[assignment,misc]
    Response = None  # type: ignore[assignment,misc]
    StarletteResponse = None  # type: ignore[assignment,misc]

# Expose FastAPI under its canonical name for callers that reference it.
FastAPI = _FastAPI

__all__ = [
    "FASTAPI_AVAILABLE",
    "APIRouter",
    "Cookie",
    "CORSMiddleware",
    "Depends",
    "FastAPI",
    "FastAPIRequest",
    "HTMLResponse",
    "HTTPException",
    "JSONResponse",
    "Query",
    "RedirectResponse",
    "Request",
    "Response",
    "StarletteResponse",
]
