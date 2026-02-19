"""
Mock server generator — creates FastAPI apps from API pack TOML definitions.

Reads operations, foreign models, and auth specs from API packs and generates
a fully functional mock server with stateful CRUD and auth validation.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import time
from typing import Any

from dazzle.api_kb.loader import ApiPack, load_pack
from dazzle.testing.vendor_mock.data_generators import DataGenerator
from dazzle.testing.vendor_mock.state import MockStateStore

logger = logging.getLogger(__name__)

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from starlette.middleware.base import BaseHTTPMiddleware

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False


def create_mock_server(
    pack_name: str,
    *,
    seed: int | None = None,
    auth_tokens: dict[str, str] | None = None,
) -> FastAPI:
    """Create a mock FastAPI server from an API pack definition.

    Args:
        pack_name: Name of the API pack (e.g. "sumsub_kyc").
        seed: Optional seed for deterministic data generation.
        auth_tokens: Optional dict of valid auth credentials for validation.
            Keys depend on auth type: 'api_key', 'token', 'secret', etc.
            If not provided, any correctly-formatted auth is accepted.

    Returns:
        A FastAPI application with routes for all pack operations.

    Raises:
        ValueError: If the pack is not found.
        RuntimeError: If FastAPI is not installed.
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI is required for mock servers")

    pack = load_pack(pack_name)
    if not pack:
        raise ValueError(f"API pack '{pack_name}' not found")

    return _build_app(pack, seed=seed, auth_tokens=auth_tokens)


def _build_app(
    pack: ApiPack,
    *,
    seed: int | None = None,
    auth_tokens: dict[str, str] | None = None,
) -> FastAPI:
    """Build the FastAPI app from a loaded pack."""
    generator = DataGenerator(seed=seed)

    # Build foreign model definitions for the state store
    fm_defs: dict[str, dict[str, Any]] = {}
    for fm in pack.foreign_models:
        fm_defs[fm.name] = {
            "description": fm.description,
            "key": fm.key_field,
            "fields": fm.fields,
        }

    store = MockStateStore(foreign_models=fm_defs, generator=generator)
    request_log: list[dict[str, Any]] = []

    app = FastAPI(
        title=f"Mock: {pack.provider}",
        description=f"Auto-generated mock for {pack.name}",
    )

    # Attach store and log to the app for test access
    app.state.store = store
    app.state.request_log = request_log
    app.state.pack = pack

    # Auth middleware
    if pack.auth:
        auth_middleware = _create_auth_middleware(pack, auth_tokens)
        app.add_middleware(BaseHTTPMiddleware, dispatch=auth_middleware)

    # Health check (no auth)
    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "provider": pack.provider}

    # Generate routes for each operation
    for op in pack.operations:
        _register_operation(app, op, pack, store, generator, request_log, fm_defs)

    return app


def _create_auth_middleware(pack: ApiPack, auth_tokens: dict[str, str] | None) -> Any:
    """Create auth validation middleware based on pack auth spec."""
    auth = pack.auth
    assert auth is not None

    async def dispatch(request: Request, call_next: Any) -> Any:
        # Skip auth for health check
        if request.url.path == "/health":
            return await call_next(request)

        if auth.auth_type == "api_key":
            header_name = auth.header or "Authorization"
            token = request.headers.get(header_name)
            if not token:
                return JSONResponse(
                    {
                        "error": "Missing authentication",
                        "detail": f"Header '{header_name}' required",
                    },
                    status_code=401,
                )
            if auth_tokens and auth_tokens.get("api_key") and token != auth_tokens["api_key"]:
                return JSONResponse({"error": "Invalid credentials"}, status_code=401)

        elif auth.auth_type in ("oauth2", "bearer"):
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return JSONResponse(
                    {
                        "error": "Missing or invalid Authorization header",
                        "detail": "Bearer token required",
                    },
                    status_code=401,
                )
            if auth_tokens and auth_tokens.get("token"):
                token = auth_header[7:]  # Strip "Bearer "
                if token != auth_tokens["token"]:
                    return JSONResponse({"error": "Invalid token"}, status_code=401)

        elif auth.auth_type == "hmac":
            # SumSub-style HMAC: X-App-Token + X-App-Access-Ts + X-App-Access-Sig
            app_token = request.headers.get("X-App-Token")
            timestamp = request.headers.get("X-App-Access-Ts")
            signature = request.headers.get("X-App-Access-Sig")

            if not app_token or not timestamp:
                return JSONResponse(
                    {
                        "error": "Missing HMAC authentication headers",
                        "detail": "X-App-Token and X-App-Access-Ts required",
                    },
                    status_code=401,
                )

            if auth_tokens and auth_tokens.get("secret") and signature:
                # Validate HMAC signature
                secret = auth_tokens["secret"]
                body = b""
                if request.method in ("POST", "PUT", "PATCH"):
                    body = await request.body()
                method = request.method
                path = request.url.path
                if request.url.query:
                    path = f"{path}?{request.url.query}"
                message = f"{timestamp}{method}{path}".encode() + body
                expected = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
                if not hmac.compare_digest(signature, expected):
                    return JSONResponse({"error": "Invalid HMAC signature"}, status_code=401)

        elif auth.auth_type == "basic":
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Basic "):
                return JSONResponse(
                    {"error": "Missing Basic authentication"},
                    status_code=401,
                )

        return await call_next(request)

    return dispatch


def _path_to_fastapi(path: str) -> str:
    """Convert API pack path pattern to FastAPI path pattern.

    API packs use ``{param_name}`` which is already FastAPI-compatible,
    but query params (``?key={value}``) need to be stripped from the route.

    Examples:
        /resources/applicants/{applicant_id} -> /resources/applicants/{applicant_id}
        /resources/applicants?levelName={level} -> /resources/applicants
        /resources/applicants/-;externalUserId={id} -> /resources/applicants/-;externalUserId/{id}
    """
    # Strip query string portion
    path = path.split("?")[0]

    # Handle SumSub-style semicolon params: /-;key={value} → /-;key/{value}
    # Convert "-;externalUserId={external_user_id}" to a path param
    path = re.sub(r"-;(\w+)=\{(\w+)\}", r"{\2}", path)

    return path


def _infer_model_for_operation(
    op_name: str, path: str, method: str, fm_defs: dict[str, dict[str, Any]]
) -> str | None:
    """Infer which foreign model an operation works with based on path and name.

    Returns the model name or None.
    """
    # Try to find a model whose name appears in the operation name or path.
    # Check both CamelCase and snake_case forms since paths use snake_case
    # but model names use CamelCase (e.g. PaymentIntent vs /payment_intents).
    path_lower = path.lower()
    op_lower = op_name.lower()

    for model_name in fm_defs:
        model_lower = model_name.lower()
        # Also try snake_case: PaymentIntent → payment_intent
        snake = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", model_name).lower()
        if model_lower in path_lower or model_lower in op_lower:
            return model_name
        if snake != model_lower and (snake in path_lower or snake in op_lower):
            return model_name

    # Fallback: use the first model if there's only one
    if len(fm_defs) == 1:
        return next(iter(fm_defs))

    return None


def _register_operation(
    app: FastAPI,
    op: Any,
    pack: ApiPack,
    store: MockStateStore,
    generator: DataGenerator,
    request_log: list[dict[str, Any]],
    fm_defs: dict[str, dict[str, Any]],
) -> None:
    """Register a single API operation as a FastAPI route."""
    fastapi_path = _path_to_fastapi(op.path)
    method = op.method.upper()
    model_name = _infer_model_for_operation(op.name, op.path, method, fm_defs)

    async def handler(request: Request) -> JSONResponse:
        """Generic handler for a mock operation."""
        start = time.monotonic()
        path_params = request.path_params

        # Log the request
        body: dict[str, Any] | None = None
        if method in ("POST", "PUT", "PATCH"):
            try:
                body = await request.json()
            except Exception:
                body = {}

        log_entry = {
            "operation": op.name,
            "method": method,
            "path": str(request.url.path),
            "query": dict(request.query_params),
            "body": body,
            "timestamp": time.time(),
        }

        # Route to appropriate handler
        if method == "GET" and model_name:
            # Check if this is a get-by-id or list operation
            if any(f"{{{p}}}" in op.path for p in path_params if p not in ("level_name",)):
                # Get by ID — find the ID param
                record_id = _extract_record_id(path_params, op.path)
                record = store.get(model_name, record_id) if record_id else None
                if record:
                    status = 200
                    response_data = record
                else:
                    status = 404
                    response_data = {"error": "Not found", "detail": f"{model_name} not found"}
            else:
                # List operation
                response_data = store.list(model_name)  # type: ignore[assignment]
                status = 200

        elif method == "POST" and model_name:
            data = body or {}
            # Merge query params (e.g., levelName from ?levelName=basic-kyc-level)
            for qk, qv in request.query_params.items():
                if qk not in data:
                    data[qk] = qv
            record = store.create(model_name, data)
            status = 201
            response_data = record

        elif method == "PUT" and model_name:
            record_id = _extract_record_id(path_params, op.path)
            if record_id:
                updated = store.update(model_name, record_id, body or {})
                if updated:
                    status = 200
                    response_data = updated
                else:
                    status = 404
                    response_data = {"error": "Not found"}
            else:
                status = 400
                response_data = {"error": "Missing ID"}

        elif method == "DELETE" and model_name:
            record_id = _extract_record_id(path_params, op.path)
            if record_id and store.delete(model_name, record_id):
                status = 200
                response_data = {"ok": True}
            else:
                status = 404
                response_data = {"error": "Not found"}

        else:
            # Unknown operation — return a generic success with generated data
            if model_name:
                fields = fm_defs.get(model_name, {}).get("fields", {})
                response_data = generator.generate_model(model_name, fields)
            else:
                response_data = {"ok": True, "operation": op.name}
            status = 200

        elapsed_ms = (time.monotonic() - start) * 1000
        log_entry["status"] = status
        log_entry["elapsed_ms"] = round(elapsed_ms, 2)
        request_log.append(log_entry)

        return JSONResponse(response_data, status_code=status)

    # Register with FastAPI using the correct HTTP method
    route_kwargs = {"path": fastapi_path, "name": op.name, "summary": op.description}
    if method == "GET":
        app.get(**route_kwargs)(handler)
    elif method == "POST":
        app.post(**route_kwargs)(handler)
    elif method == "PUT":
        app.put(**route_kwargs)(handler)
    elif method == "DELETE":
        app.delete(**route_kwargs)(handler)
    elif method == "PATCH":
        app.patch(**route_kwargs)(handler)
    else:
        app.api_route(**route_kwargs, methods=[method])(handler)


def _extract_record_id(path_params: dict[str, str], op_path: str) -> str | None:
    """Extract the record ID from path parameters.

    Looks for common ID param names: *_id, id, etc.
    """
    # Priority: params with '_id' suffix, then 'id'
    for key, value in path_params.items():
        if key.endswith("_id") or key == "id":
            return value

    # Fallback: return the last path param
    if path_params:
        return list(path_params.values())[-1]

    return None
