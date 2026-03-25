"""
Rate limiting for Dazzle Backend applications.

Provides configurable rate limiting based on security profile using slowapi.

Usage in route modules::

    import dazzle_back.runtime.rate_limit as _rl

    @router.post("/login")
    @_rl.limits.limiter.limit(_rl.limits.auth_limit)
    async def login(request: Request, ...): ...
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)


class _NoOpLimiter:
    """Stub that makes @limiter.limit() a pass-through when slowapi is absent."""

    def limit(self, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        def decorator(func: Any) -> Any:
            return func

        return decorator


@dataclass
class _Limits:
    """Mutable container for rate-limit state.

    Attributes are set once by apply_rate_limiting() at startup.
    Using a dataclass avoids the ``global`` keyword — attribute
    assignment on an existing instance needs no global declaration.
    """

    limiter: Any = field(default_factory=_NoOpLimiter)
    auth_limit: str = "10/minute"
    api_limit: str = "60/minute"
    upload_limit: str = "10/minute"
    twofa_limit: str = "5/minute"


limits = _Limits()


@dataclass
class RateLimitConfig:
    """Per-profile rate limits for different endpoint categories.

    Limits are expressed as slowapi rate strings, e.g. "5/minute".
    A value of None means no limit for that category.
    """

    auth_limit: str | None = None  # login, register, forgot/reset password
    api_limit: str | None = None  # general API endpoints
    upload_limit: str | None = None  # file upload
    twofa_limit: str | None = None  # 2FA verification


def configure_rate_limits_for_profile(profile: str) -> RateLimitConfig:
    """Get rate limit configuration based on security profile.

    Args:
        profile: Security profile (basic, standard, strict)

    Returns:
        RateLimitConfig for the profile
    """
    if profile == "basic":
        # No rate limiting for internal/development use
        return RateLimitConfig()
    elif profile == "standard":
        return RateLimitConfig(
            auth_limit="10/minute",
            api_limit="60/minute",
            upload_limit="10/minute",
            twofa_limit="5/minute",
        )
    else:  # strict
        return RateLimitConfig(
            auth_limit="5/minute",
            api_limit="30/minute",
            upload_limit="5/minute",
            twofa_limit="3/minute",
        )


def apply_rate_limiting(app: FastAPI, profile: str) -> None:
    """Apply rate limiting to a FastAPI application.

    Creates a slowapi Limiter and stores it on app.state for use by
    endpoint decorators. On basic profile, no limiter is created.

    Also sets limit strings on the ``limits`` container (auth_limit, twofa_limit, etc.)
    so route modules can reference them via ``_rl.limits.auth_limit``.

    Args:
        app: FastAPI application instance
        profile: Security profile (basic, standard, strict)
    """
    # No global statement needed — attribute writes on existing instance
    config = configure_rate_limits_for_profile(profile)
    app.state.rate_limit_config = config

    # Publish limit strings on the limits container for route decorators
    if config.auth_limit:
        limits.auth_limit = config.auth_limit
    if config.api_limit:
        limits.api_limit = config.api_limit
    if config.upload_limit:
        limits.upload_limit = config.upload_limit
    if config.twofa_limit:
        limits.twofa_limit = config.twofa_limit

    # No rate limiting on basic profile
    if profile == "basic":
        limits.limiter = _NoOpLimiter()
        return

    try:
        from slowapi import Limiter, _rate_limit_exceeded_handler
        from slowapi.errors import RateLimitExceeded
        from slowapi.util import get_remote_address
    except ImportError:
        logger.warning(
            "slowapi not installed — rate limiting disabled. Install with: pip install slowapi"
        )
        limits.limiter = _NoOpLimiter()
        app.state.rate_limit_config = RateLimitConfig()  # disabled
        return

    limits.limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limits.limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

    logger.info("Rate limiting enabled (profile=%s)", profile)
