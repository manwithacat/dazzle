"""
Authentication runtime for Dazzle Backend (PostgreSQL-only).

Provides session-based authentication with cookie management, two-factor
sign-in with a step-up API (DD-014), and JWT token endpoints.
"""

# #1772: the public RLS binder for app-owned DB connections (custom routes /
# renderers), next to the #933 custom-route helpers. Lives in the rls_bind leaf.
from dazzle.http.runtime.rls_bind import (
    RBAC_DENY,
    RlsBinding,
    bind_rls,
    bind_rls_context,
    resolve_rls_gucs,
)

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
from .middleware import AuthMiddleware
from .models import (
    AuthContext,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SecondFactorProof,
    SessionRecord,
    TokenRequest,
    TokenRevokeRequest,
    UserRecord,
    effective_roles_of,
    principal_of,
)
from .routes import create_auth_routes
from .routes_jwt import create_jwt_auth_routes
from .second_factor import require_second_factor
from .store import AuthStore

__all__ = [
    "AUTH_USER_EMAIL_VERIFIED",
    "AUTH_USER_LOGGED_IN",
    "AUTH_USER_PASSWORD_CHANGED",
    "AUTH_USER_REGISTERED",
    "AuthContext",
    "effective_roles_of",
    "principal_of",
    "AuthMiddleware",
    "AuthStore",
    "ChangePasswordRequest",
    "ForgotPasswordRequest",
    "LoginRequest",
    "RefreshTokenRequest",
    "RegisterRequest",
    "ResetPasswordRequest",
    "SecondFactorProof",
    "SessionRecord",
    "TokenRequest",
    "TokenRevokeRequest",
    "UserRecord",
    "create_auth_dependency",
    "create_auth_routes",
    "create_deny_dependency",
    "create_email_verification_routes",
    "create_jwt_auth_routes",
    "create_optional_auth_dependency",
    "current_auth",
    "current_user",
    "current_user_id",
    "register_auth_store",
    "require_auth",
    "require_second_factor",
    "RBAC_DENY",
    "RlsBinding",
    "bind_rls",
    "bind_rls_context",
    "resolve_rls_gucs",
    "emit_user_email_verified",
    "emit_user_logged_in",
    "emit_user_password_changed",
    "emit_user_registered",
    "hash_password",
    "verify_password",
]
