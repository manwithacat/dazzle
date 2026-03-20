"""
Authentication runtime for Dazzle Backend (PostgreSQL-only).

Provides session-based authentication with cookie management,
two-factor authentication, and JWT token endpoints.
"""

from .crypto import hash_password, verify_password
from .dependencies import (
    create_auth_dependency,
    create_deny_dependency,
    create_optional_auth_dependency,
)
from .events import (
    AUTH_USER_LOGGED_IN,
    AUTH_USER_PASSWORD_CHANGED,
    AUTH_USER_REGISTERED,
    emit_user_logged_in,
    emit_user_password_changed,
    emit_user_registered,
)
from .middleware import AuthMiddleware
from .models import (
    AuthContext,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SessionRecord,
    TokenRequest,
    TokenRevokeRequest,
    TwoFactorSetupRequest,
    TwoFactorVerifyRequest,
    UserRecord,
)
from .routes import create_auth_routes
from .routes_2fa import create_2fa_routes
from .routes_jwt import create_jwt_auth_routes
from .store import AuthStore, TwoFactorMixin

__all__ = [
    "AUTH_USER_LOGGED_IN",
    "AUTH_USER_PASSWORD_CHANGED",
    "AUTH_USER_REGISTERED",
    "AuthContext",
    "AuthMiddleware",
    "AuthStore",
    "TwoFactorMixin",
    "ChangePasswordRequest",
    "ForgotPasswordRequest",
    "LoginRequest",
    "RefreshTokenRequest",
    "RegisterRequest",
    "ResetPasswordRequest",
    "SessionRecord",
    "TokenRequest",
    "TokenRevokeRequest",
    "TwoFactorSetupRequest",
    "TwoFactorVerifyRequest",
    "UserRecord",
    "create_2fa_routes",
    "create_auth_dependency",
    "create_auth_routes",
    "create_deny_dependency",
    "create_jwt_auth_routes",
    "create_optional_auth_dependency",
    "emit_user_logged_in",
    "emit_user_password_changed",
    "emit_user_registered",
    "hash_password",
    "verify_password",
]
