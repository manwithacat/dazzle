"""
Rate limiting for Dazzle Backend applications.

Provides configurable rate limiting based on security profile using slowapi.

Usage in route modules::

    import dazzle.http.runtime.rate_limit as _rl

    @router.post("/login")
    @_rl.limits.limiter.limit(_rl.limits.auth_limit)
    async def login(request: Request, ...): ...
"""

import functools
import ipaddress
import logging
import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rate-limit key derivation (#1296)
# ---------------------------------------------------------------------------


def _is_loopback(host: str) -> bool:
    """True if *host* is an IPv4/IPv6 loopback address (127.0.0.0/8, ::1)."""
    if not host:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def make_rate_limit_key(trusted_proxies: int) -> Callable[..., str]:
    """Build the slowapi ``key_func`` used to bucket requests (#1296).

    Two behaviours the default ``slowapi.util.get_remote_address`` lacks:

    * **Exempt the framework's internal loopback self-fetch.** Since #1422 the
      page READ paths are in-process and no longer self-fetch; the only remaining
      internal self-fetch is the experience-form POST *fallback* (entities without
      an in-process create invoker), an internal HTTP call to
      ``http://127.0.0.1:{PORT}`` (Heroku/Railway single-dyno). That request
      arrives from a loopback address and carries **no** ``X-Forwarded-For``
      (``_sync_post`` sends only a Cookie). Without this, those self-fetches for
      all users share one bucket keyed on ``127.0.0.1`` → saturate → loopback 429.
      We give such requests a unique-per-request key so they never accumulate
      toward a limit. External traffic cannot forge a loopback origin (it arrives
      via the proxy with a real client IP + XFF), so this opens no abuse vector.
    * **Honor ``X-Forwarded-For`` behind trusted proxies.** With
      ``trusted_proxies > 0``, the real client IP is taken ``trusted_proxies``
      hops from the right of XFF (the entry the outermost trusted proxy added)
      so per-user limiting actually works behind Heroku/Cloudflare. Default 0
      preserves the spoofing-safe ``request.client.host`` behaviour.

    The returned callable takes ``request`` (slowapi passes it when the
    signature has a ``request`` parameter).
    """

    def key_func(request: Any) -> str:  # noqa: ANN401 — Starlette Request
        client = getattr(request, "client", None)
        host = getattr(client, "host", "") or ""
        xff = ""
        try:
            xff = request.headers.get("X-Forwarded-For", "") or ""
        except Exception:  # pragma: no cover — defensive
            xff = ""

        # Internal loopback self-fetch → unique key (effectively exempt).
        if _is_loopback(host) and not xff:
            return f"internal-loopback:{uuid.uuid4().hex}"

        # Trusted-proxy-aware real client IP.
        if trusted_proxies > 0 and xff:
            parts = [p.strip() for p in xff.split(",") if p.strip()]
            if len(parts) >= trusted_proxies:
                return parts[-trusted_proxies]

        return host or "anonymous"

    return key_func


def _resolve_trusted_proxies() -> int:
    """Number of trusted proxy hops from ``DAZZLE_RATE_LIMIT_TRUSTED_PROXIES``.

    0 (default) → no XFF trust (spoofing-safe). Set to 1 behind a single
    trusted proxy (Heroku router, Cloudflare); N for N chained trusted proxies.
    """
    raw = os.environ.get("DAZZLE_RATE_LIMIT_TRUSTED_PROXIES", "").strip()
    if not raw:
        return 0
    try:
        return max(0, int(raw))
    except ValueError:
        logger.warning("Invalid DAZZLE_RATE_LIMIT_TRUSTED_PROXIES=%r — ignoring (using 0)", raw)
        return 0


# #1298: per-limit env overrides. A project on `standard` can raise (or lower)
# any single limit per-deploy WITHOUT dropping to `basic` (which also disables
# CSP/HSTS/require-auth and opens CORS). Mirrors the DAZZLE_RATE_LIMIT_TRUSTED_PROXIES
# env knob (#1296). Maps env var → RateLimitConfig attribute.
_LIMIT_OVERRIDE_ENV = {
    "DAZZLE_RATE_LIMIT_API": "api_limit",
    "DAZZLE_RATE_LIMIT_AUTH": "auth_limit",
    "DAZZLE_RATE_LIMIT_UPLOAD": "upload_limit",
    "DAZZLE_RATE_LIMIT_2FA": "twofa_limit",
}

_VALID_RATE_PERIODS = frozenset({"second", "minute", "hour", "day"})


def _normalize_rate_string(value: str) -> str | None:
    """Return the canonical ``N/period`` form of ``value``, or None if invalid.

    Accepts a positive integer count, ``/``, and one of second/minute/hour/day
    (trailing ``s`` tolerated, e.g. ``300/minutes``; surrounding whitespace
    ignored). Returns the **canonical singular** form (``"300/minute"``) — never
    the raw input — so a tolerated-but-noncanonical value (``"300/minutes"``,
    ``" 60 / minute "``) is stored in a shape slowapi/limits definitely parses,
    rather than crashing at route-decoration time (the validator's whole point
    is to fail safe with a warn-and-ignore, not to launder a typo into a boot
    crash). Validates the single-rate shape the profiles use, not slowapi's full
    multi-rate grammar. No regex (ADR-0024 is parser-scoped, but a manual parse
    is clearer here anyway).
    """
    parts = value.split("/")
    if len(parts) != 2:
        return None
    count, period = parts[0].strip(), parts[1].strip().lower().rstrip("s")
    # `isascii()` guard: str.isdigit() also accepts non-ASCII digits (e.g.
    # Arabic-Indic "٣٠٠"), which would pass here but reach slowapi as a string
    # its parser may choke on at route-decoration time. Require plain ASCII.
    if not (count.isascii() and count.isdigit() and int(count) > 0):
        return None
    if period not in _VALID_RATE_PERIODS:
        return None
    return f"{int(count)}/{period}"


def _valid_rate_string(value: str) -> bool:
    """True if ``value`` is a parseable ``N/period`` rate string (see
    ``_normalize_rate_string``)."""
    return _normalize_rate_string(value) is not None


def _apply_env_limit_overrides(config: "RateLimitConfig", profile: str = "") -> None:
    """Override individual limits on ``config`` from env vars, in place.

    Each ``DAZZLE_RATE_LIMIT_*`` env var (see ``_LIMIT_OVERRIDE_ENV``) replaces
    the corresponding profile default when set to a valid ``N/period`` string.
    The stored value is the **canonical** form (``_normalize_rate_string``), not
    the raw env value. Invalid values are logged and ignored (the profile
    default stands). Empty / unset vars are no-ops. No effect on ``basic`` (the
    limiter is a no-op stub there regardless).

    ``profile`` is included in the override log so a security audit can see when
    a ``strict`` deploy has had its posture loosened by an env override — the
    override is deliberate (operator-set) so we don't clamp it, but we make it
    visible.
    """
    for env_var, attr in _LIMIT_OVERRIDE_ENV.items():
        raw = os.environ.get(env_var, "").strip()
        if not raw:
            continue
        normalized = _normalize_rate_string(raw)
        if normalized is None:
            logger.warning(
                "Invalid %s=%r — expected 'N/period' (e.g. '300/minute'); "
                "ignoring (using profile default)",
                env_var,
                raw,
            )
            continue
        setattr(config, attr, normalized)
        logger.info(
            "Rate-limit override on %s profile: %s=%s (from %s)",
            profile or "?",
            attr,
            normalized,
            env_var,
        )


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
    api_limit: str = "300/minute"  # #1298: matches the standard-profile default
    upload_limit: str = "10/minute"
    twofa_limit: str = "5/minute"


limits = _Limits()


def safe_limit(limit_str: str) -> Callable[[Any], Any]:
    """Apply rate limiting to a handler, robust to ``functools.partial``.

    slowapi's ``Limiter.limit()`` introspects ``handler.__name__`` to
    register the limit; ``functools.partial`` objects don't have
    ``__name__``, so a direct ``limits.limiter.limit(...)(partial_handler)``
    raises ``AttributeError`` at module-import time (#1251). The fix:
    copy ``__name__`` from the underlying callable onto the partial
    before applying the decorator. The no-partial path is a no-op.

    Deliberately NOT using ``functools.update_wrapper`` here:
    ``update_wrapper`` *also* sets ``__wrapped__`` on the partial, which
    causes FastAPI's ``add_api_route`` introspection to traverse past
    the partial to the underlying function — and then try to wire the
    pre-bound ``deps`` argument as a request parameter, breaking every
    partial-bound handler in the auth router. Just ``__name__`` is the
    surgical fix.

    Route auth-flow + 2FA handlers wrapped with ``partial(deps_fn, deps)``
    through this helper instead of calling ``_rl.limits.limiter.limit()``
    directly.

    Reproduced at #1251: this only bites when the real ``Limiter`` is
    active (security_profile ∈ {standard, strict}); ``_NoOpLimiter``
    ignores the partial entirely. The bug was latent on basic profile —
    #1235 surfaced it by propagating the DSL-declared profile.
    """
    decorator = limits.limiter.limit(limit_str)

    def wrap(handler: Any) -> Any:
        if isinstance(handler, functools.partial):
            handler.__name__ = handler.func.__name__  # type: ignore[attr-defined]
        return decorator(handler)

    return wrap


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
    # #1296: trusted proxy hops for X-Forwarded-For-aware client keying.
    # 0 = spoofing-safe request.client.host; 1 for Heroku/Cloudflare.
    trusted_proxies: int = 0


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
            # #1298: raised 60→300/minute. SSR list/workspace pages fan out
            # several client API XHRs per view (list data + filter-option
            # dropdowns + FTS/columns), so 60/minute self-429'd a *single*
            # user under normal navigation. 300/minute (~30-50 page views/min)
            # fits the current client-hydrated fan-out. Projects that need a
            # different value set DAZZLE_RATE_LIMIT_API (see
            # _apply_env_limit_overrides) instead of dropping to `basic`.
            api_limit="300/minute",
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


def apply_rate_limiting(app: "FastAPI", profile: str) -> None:
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
    # #1298: apply per-limit env overrides (e.g. DAZZLE_RATE_LIMIT_API=300/minute)
    # so a deploy can tune any single limit without dropping the whole profile.
    _apply_env_limit_overrides(config, profile)
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

    # #1252: `dazzle test dsl-run` issues many AUTH requests per persona
    # (LOGIN_VALID/LOGIN_INVALID/REDIRECT × N personas), enough to exhaust
    # standard/strict's 10-per-minute auth bucket mid-suite and produce
    # spurious HTTP 429s. The same trust boundary that already gates the
    # /__test__/* schema-wipe endpoints (DAZZLE_TEST_SECRET) bypasses the
    # rate limiter here — strictly smaller blast radius than the schema
    # endpoints the secret already unlocks.
    if os.environ.get("DAZZLE_TEST_SECRET"):
        logger.warning(
            "Test-harness bypass active — rate limiting disabled (profile=%s)",
            profile,
        )
        limits.limiter = _NoOpLimiter()
        return

    try:
        from slowapi import Limiter, _rate_limit_exceeded_handler
        from slowapi.errors import RateLimitExceeded
    except ImportError:
        logger.warning(
            "slowapi not installed — rate limiting disabled. Install with: pip install slowapi"
        )
        limits.limiter = _NoOpLimiter()
        app.state.rate_limit_config = RateLimitConfig()  # disabled
        return

    # #1296: resolve trusted-proxy hops + use a key_func that (a) exempts the
    # framework's internal loopback self-fetch and (b) honors X-Forwarded-For
    # behind trusted proxies. Replaces slowapi's get_remote_address (which keys
    # purely on request.client.host — collapsing all loopback self-fetches into
    # one bucket and ignoring XFF so real per-user limiting fails behind a proxy).
    config.trusted_proxies = _resolve_trusted_proxies()
    limits.limiter = Limiter(key_func=make_rate_limit_key(config.trusted_proxies))
    app.state.limiter = limits.limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

    logger.info(
        "Rate limiting enabled (profile=%s, trusted_proxies=%d)",
        profile,
        config.trusted_proxies,
    )
