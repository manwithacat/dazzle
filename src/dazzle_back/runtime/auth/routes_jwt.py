"""JWT token authentication routes (for mobile clients)."""

from dataclasses import dataclass
from functools import partial
from typing import Any

from dazzle_back.runtime._fastapi_compat import FASTAPI_AVAILABLE, APIRouter, FastAPIRequest
from dazzle_back.runtime.jwt_auth import JWTService
from dazzle_back.runtime.token_store import TokenStore

from .models import RefreshTokenRequest, TokenRequest, TokenRevokeRequest
from .store import AuthStore

# =============================================================================
# Dependencies Container
# =============================================================================


@dataclass
class _JwtDeps:
    auth_store: AuthStore
    jwt_service: JWTService
    token_store: TokenStore


# =============================================================================
# Module-level handler functions
# =============================================================================


async def _login_for_token(
    deps: _JwtDeps,
    form_data: Any = None,
    credentials: TokenRequest | None = None,
    request: FastAPIRequest | None = None,
) -> Any:
    """OAuth2 compatible token endpoint.

    Accepts either OAuth2 form data or JSON body.
    Returns access_token and refresh_token.
    """
    from fastapi import HTTPException

    from dazzle_back.runtime.jwt_auth import TokenResponse

    # Extract credentials from either form or JSON
    if form_data:
        email = form_data.username
        password = form_data.password
    elif credentials:
        email = credentials.username
        password = credentials.password
    else:
        raise HTTPException(status_code=400, detail="Missing credentials")

    # Authenticate user
    user = deps.auth_store.authenticate(email, password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Create tokens
    token_pair = deps.jwt_service.create_token_pair(user)

    # Store refresh token
    deps.token_store.create_token(
        user,
        ip_address=request.client.host if request and request.client else None,
        user_agent=request.headers.get("user-agent") if request else None,
    )

    return TokenResponse(
        access_token=token_pair.access_token,
        refresh_token=token_pair.refresh_token,
        token_type=token_pair.token_type,
        expires_in=token_pair.expires_in,
    )


async def _refresh_access_token(
    deps: _JwtDeps,
    data: RefreshTokenRequest,
    request: FastAPIRequest | None = None,
) -> Any:
    """Exchange refresh token for new token pair.

    Implements token rotation: old refresh token is invalidated.
    """
    from fastapi import HTTPException

    from dazzle_back.runtime.jwt_auth import TokenResponse

    # Validate refresh token
    token_record = deps.token_store.validate_token(data.refresh_token)
    if not token_record:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    # Get user
    user = deps.auth_store.get_user_by_id(token_record.user_id)
    if not user or not user.is_active:
        deps.token_store.revoke_token(data.refresh_token)
        raise HTTPException(status_code=401, detail="User not found or inactive")

    # Rotate token
    new_refresh_token = deps.token_store.rotate_token(
        data.refresh_token,
        user,
        ip_address=request.client.host if request and request.client else None,
        user_agent=request.headers.get("user-agent") if request else None,
    )

    if not new_refresh_token:
        raise HTTPException(status_code=401, detail="Token rotation failed")

    # Create new access token
    access_token, _ = deps.jwt_service.create_access_token(
        user_id=user.id,
        email=user.email,
        roles=user.roles,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="Bearer",  # nosec B106 - OAuth2 token type, not a password
        expires_in=deps.jwt_service.config.access_token_expire_minutes * 60,
    )


async def _revoke_token(deps: _JwtDeps, data: TokenRevokeRequest) -> dict[str, str]:
    """Revoke a refresh token (logout from device)."""
    revoked = deps.token_store.revoke_token(data.refresh_token)
    if not revoked:
        # Don't reveal if token existed
        pass
    return {"status": "revoked"}


async def _get_me_jwt(deps: _JwtDeps, request: FastAPIRequest) -> dict[str, Any]:
    """Get current user from JWT token.

    Requires Authorization: Bearer <token> header.
    """
    from fastapi import HTTPException

    from dazzle_back.runtime.jwt_middleware import JWTMiddleware

    # Create temporary middleware to validate
    middleware = JWTMiddleware(deps.jwt_service, exclude_paths=[])
    context = middleware.get_auth_context(request)

    if not context.is_authenticated:
        raise HTTPException(
            status_code=401,
            detail=context.error or "Not authenticated",
        )

    if context.claims is None:
        raise HTTPException(status_code=401, detail="No claims found")

    # Get full user from store
    user = deps.auth_store.get_user_by_id(context.claims.user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return {
        "id": str(user.id),
        "email": user.email,
        "username": user.username,
        "roles": user.roles,
        "is_superuser": user.is_superuser,
    }


async def _list_sessions(deps: _JwtDeps, request: FastAPIRequest) -> dict[str, Any]:
    """List active refresh tokens/sessions for current user.

    Requires JWT authentication.
    """
    from fastapi import HTTPException

    from dazzle_back.runtime.jwt_middleware import JWTMiddleware

    middleware = JWTMiddleware(deps.jwt_service, exclude_paths=[])
    context = middleware.get_auth_context(request)

    if not context.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if context.claims is None:
        raise HTTPException(status_code=401, detail="No claims found")

    tokens = deps.token_store.get_user_tokens(context.claims.user_id)

    return {
        "sessions": [
            {
                "device_id": t.device_id,
                "created_at": t.created_at.isoformat(),
                "last_used_at": t.last_used_at.isoformat() if t.last_used_at else None,
                "ip_address": t.ip_address,
                "user_agent": t.user_agent,
            }
            for t in tokens
        ],
        "count": len(tokens),
    }


async def _revoke_all_sessions(deps: _JwtDeps, request: FastAPIRequest) -> dict[str, int]:
    """Revoke all refresh tokens except current (logout from all devices)."""
    from fastapi import HTTPException

    from dazzle_back.runtime.jwt_middleware import JWTMiddleware

    middleware = JWTMiddleware(deps.jwt_service, exclude_paths=[])
    context = middleware.get_auth_context(request)

    if not context.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if context.claims is None:
        raise HTTPException(status_code=401, detail="No claims found")

    count = deps.token_store.revoke_user_tokens(context.claims.user_id)

    return {"revoked_count": count}


# =============================================================================
# Factory
# =============================================================================


def create_jwt_auth_routes(
    auth_store: AuthStore,
    jwt_service: JWTService,
    token_store: TokenStore,
) -> APIRouter:
    """Create JWT authentication routes for mobile clients.

    Returns a router with OAuth2-compatible token endpoints.

    Args:
        auth_store: Auth store for user lookup
        jwt_service: JWT service for token creation
        token_store: Token store for refresh tokens
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI is required for auth routes")

    from dazzle_back.runtime.jwt_auth import TokenResponse

    router = APIRouter(prefix="/auth", tags=["Authentication"])

    deps = _JwtDeps(
        auth_store=auth_store,
        jwt_service=jwt_service,
        token_store=token_store,
    )

    # Token (Login)
    router.post("/token", response_model=TokenResponse)(partial(_login_for_token, deps))

    # Token Refresh
    router.post("/token/refresh", response_model=TokenResponse)(
        partial(_refresh_access_token, deps)
    )

    # Token Revoke (Logout)
    router.post("/token/revoke")(partial(_revoke_token, deps))

    # Current User (JWT)
    router.get("/me/jwt")(partial(_get_me_jwt, deps))

    # Active Sessions/Devices
    router.get("/sessions")(partial(_list_sessions, deps))
    router.delete("/sessions")(partial(_revoke_all_sessions, deps))

    return router
