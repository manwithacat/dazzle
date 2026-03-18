"""
FastAPI optional-import compatibility shim.

All FastAPI symbols used across ``dazzle_back.runtime`` are imported here in a
single try/except block.  Every other module imports from here instead of
repeating the guard locally.

When FastAPI is not installed every symbol is set to ``None`` so that
``if not FASTAPI_AVAILABLE`` guards still work correctly at runtime.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Core FastAPI symbols
# ---------------------------------------------------------------------------
FASTAPI_AVAILABLE: bool
APIRouter: Any
Cookie: Any
CORSMiddleware: Any
Depends: Any
FastAPIRequest: Any
HTMLResponse: Any
HTTPException: Any
JSONResponse: Any
Query: Any
RedirectResponse: Any
Request: Any
Response: Any
StarletteResponse: Any
_FastAPI: Any

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
