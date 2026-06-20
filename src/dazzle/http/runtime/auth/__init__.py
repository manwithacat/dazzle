"""
Authentication runtime for Dazzle Backend (PostgreSQL-only).

Provides session-based authentication with cookie management,
two-factor authentication, and JWT token endpoints.
"""

from .crypto import hash_password, verify_password
from .current import (
    current_auth,
    current_user,
    current_user_id,
    register_auth_store,
    require_auth,
)
from .dependencies import (
    create_auth_dependency,
    create_deny_dependency,
    create_optional_auth_dependency,
)
from .email_verification_routes import create_email_verification_routes
from .events import (
    AUTH_USER_EMAIL_VERIFIED,
    AUTH_USER_LOGGED_IN,
    AUTH_USER_PASSWORD_CHANGED,
    AUTH_USER_REGISTERED,
    emit_user_email_verified,
    emit_user_logged_in,
    emit_user_password_changed,
    emit_user_registered,
)
from .join_request_routes import create_join_request_routes
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
    effective_roles_of,
)
from .routes import create_auth_routes
from .routes_2fa import create_2fa_routes
from .routes_jwt import create_jwt_auth_routes
from .store import AuthStore, TwoFactorMixin

__all__ = [
    "AUTH_USER_EMAIL_VERIFIED",
    "AUTH_USER_LOGGED_IN",
    "AUTH_USER_PASSWORD_CHANGED",
    "AUTH_USER_REGISTERED",
    "AuthContext",
    "effective_roles_of",
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
    "create_email_verification_routes",
    "create_join_request_routes",
    "create_jwt_auth_routes",
    "create_optional_auth_dependency",
    "current_auth",
    "current_user",
    "current_user_id",
    "register_auth_store",
    "require_auth",
    "emit_user_email_verified",
    "emit_user_logged_in",
    "emit_user_password_changed",
    "emit_user_registered",
    "hash_password",
    "verify_password",
]
