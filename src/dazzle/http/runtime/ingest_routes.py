"""HTTP ingest: JSON rows or multipart file → declared upsert (#1676)."""

import json
import os
from typing import Any

from fastapi import APIRouter, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from dazzle.core.ir.ingest import IngestSpec
from dazzle.http.runtime.http_errors import require_found
from dazzle.http.runtime.ingest_engine import (
    apply_ingest,
    canonical_fingerprint,
    parse_ingest_bytes,
)


def _ingest_token_ok(request: Request, header_token: str | None) -> bool:
    expected = os.environ.get("DAZZLE_INGEST_TOKEN", "")
    if not expected:
        return False
    if header_token and header_token == expected:
        return True
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer ") and auth.split(" ", 1)[1] == expected:
        return True
    return False


def create_ingest_routes(
    *,
    ingests: list[IngestSpec],
    repositories: dict[str, Any],
    event_bus: Any | None = None,
    optional_auth_dep: Any = None,
) -> APIRouter:
    """POST /api/ingest/{name} — Bearer ingest token or authenticated session."""
    router = APIRouter(prefix="/api/ingest", tags=["ingest"])
    by_name = {spec.name: spec for spec in ingests}

    async def _auth(request: Request, x_dazzle_ingest_token: str | None) -> None:
        if _ingest_token_ok(request, x_dazzle_ingest_token):
            return
        if optional_auth_dep is not None:
            try:
                ctx = await optional_auth_dep(request)
            except TypeError:
                ctx = optional_auth_dep()
            if ctx is not None and getattr(ctx, "is_authenticated", False):
                return
        raise HTTPException(status_code=401, detail="Authentication required")

    @router.post("/{name}")
    async def ingest_post(
        name: str,
        request: Request,
        file: UploadFile | None = File(default=None),
        x_dazzle_ingest_token: str | None = Header(default=None),
    ) -> JSONResponse:
        await _auth(request, x_dazzle_ingest_token)
        spec = require_found(by_name.get(name), f"Unknown ingest '{name}'")
        repo = repositories.get(spec.entity)
        if repo is None:
            raise HTTPException(status_code=500, detail=f"No repository for {spec.entity}")

        source_kind: str | None = None
        if file is not None:
            raw = await file.read()
            try:
                rows = parse_ingest_bytes(raw, file.filename)
            except (ValueError, json.JSONDecodeError) as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            fingerprint = canonical_fingerprint(raw)
        else:
            try:
                body = await request.json()
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=400, detail="JSON body required") from exc
            if isinstance(body, list):
                rows = [r for r in body if isinstance(r, dict)]
            elif isinstance(body, dict):
                source_kind = body.get("source_kind")
                raw_rows = body.get("rows", [])
                if not isinstance(raw_rows, list):
                    raise HTTPException(status_code=400, detail="rows must be an array")
                rows = [r for r in raw_rows if isinstance(r, dict)]
            else:
                raise HTTPException(status_code=400, detail="JSON object or array required")
            fingerprint = canonical_fingerprint(
                json.dumps(rows, sort_keys=True, default=str).encode()
            )

        user_id = None
        result = await apply_ingest(
            spec=spec,
            rows=rows,
            repository=repo,
            fingerprint=fingerprint,
            source_kind=source_kind,
            event_bus=event_bus,
            user_id=user_id,
        )
        return JSONResponse(result)

    return router
