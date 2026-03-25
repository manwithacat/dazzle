"""
FastAPI optional-import compatibility shim.

All FastAPI symbols used across ``dazzle_back.runtime`` are imported here in a
single try/except block.  Every other module imports from here instead of
repeating the guard locally.

When FastAPI is not installed every symbol is set to ``None`` so that
``if not FASTAPI_AVAILABLE`` guards still work correctly at runtime.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

# ---------------------------------------------------------------------------
# Core FastAPI symbols
# ---------------------------------------------------------------------------
# Under TYPE_CHECKING mypy sees the real types; at runtime the try/except
# block below provides the actual imports (or None fallbacks).
if TYPE_CHECKING:
    from fastapi import (
        APIRouter,
        Cookie,
        Depends,
        HTTPException,
        Query,
        Request,
        Response,
    )
    from fastapi import FastAPI as _FastAPI
    from fastapi import Request as FastAPIRequest
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import (
        HTMLResponse,
        JSONResponse,
        RedirectResponse,
    )
    from starlette.responses import Response as StarletteResponse

    FASTAPI_AVAILABLE: bool
else:
    try:
        from fastapi import (
            APIRouter,
            Cookie,
            Depends,
            HTTPException,
            Query,
            Request,
            Response,
        )
        from fastapi import FastAPI as _FastAPI
        from fastapi import Request as FastAPIRequest
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import (
            HTMLResponse,
            JSONResponse,
            RedirectResponse,
        )
        from starlette.responses import Response as StarletteResponse

        FASTAPI_AVAILABLE = True

    except ImportError:
        FASTAPI_AVAILABLE = False
        APIRouter = None
        Cookie = None
        CORSMiddleware = None
        Depends = None
        _FastAPI = None
        FastAPIRequest = None
        HTMLResponse = None
        HTTPException = None
        JSONResponse = None
        Query = None
        RedirectResponse = None
        Request = None
        Response = None
        StarletteResponse = None

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
