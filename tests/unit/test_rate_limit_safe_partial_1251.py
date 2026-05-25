"""#1251 regression — `_rl.safe_limit` is robust to `functools.partial`.

At v0.71.x `ServerConfig.security_profile` silently stayed at "basic" so
the rate-limit decorators were `_NoOpLimiter` and the auth-routes partials
slipped through. #1235 (v0.72.8) fixed the propagation; the real slowapi
`Limiter` then introspected `handler.__name__` and raised AttributeError
on the partials at module-import time, breaking the entire `auth_routes`
subsystem registration.

`safe_limit` copies `__name__` from `partial.func` onto the partial via
`functools.update_wrapper` before applying the slowapi decorator. Tests
here pin both the partial-safe behaviour AND the no-op pass-through for
plain functions, so regressions surface immediately.
"""

from __future__ import annotations

from functools import partial
from typing import Any

import pytest


async def _plain_handler(deps: Any, request: Any) -> str:
    return "ok"


def test_safe_limit_routes_partial_through_underlying_name() -> None:
    """The pre-#1251 shape: `partial(handler, deps)` passed straight to
    `limiter.limit(...)` raised AttributeError because partials lack
    `__name__`. `safe_limit` copies the underlying function's `__name__`
    onto the partial first."""
    from dazzle.back.runtime import rate_limit as _rl

    handler = partial(_plain_handler, "fake-deps")
    assert not hasattr(handler, "__name__")  # partial has no __name__

    # safe_limit() should not raise on the partial.
    decorated = _rl.safe_limit("10/minute")(handler)

    # After safe_limit, the partial has gained the underlying func's name.
    assert getattr(handler, "__name__", None) == "_plain_handler"
    # The decorated callable must still be invocable (the _NoOpLimiter in
    # the test environment is a pass-through).
    assert decorated is not None


def test_safe_limit_does_not_set_wrapped_attribute() -> None:
    """`functools.update_wrapper` would set `__wrapped__` on the partial,
    which makes FastAPI's `add_api_route` traverse past the partial to
    the underlying function and try to wire the pre-bound `deps` argument
    as a request parameter — breaking every partial-bound auth handler.
    The fix uses bare `__name__` assignment instead. This test pins that
    `__wrapped__` is NOT set on the partial after safe_limit."""
    from dazzle.back.runtime import rate_limit as _rl

    handler = partial(_plain_handler, "fake-deps")
    _rl.safe_limit("10/minute")(handler)

    assert not hasattr(handler, "__wrapped__"), (
        "safe_limit must NOT set __wrapped__ on the partial — that would "
        "trigger FastAPI introspection into the underlying function and "
        "break partial-bound auth handlers (the regression that caused "
        "the v0.72.13 -> v0.72.14 development cycle in #1251)."
    )


def test_safe_limit_passes_through_plain_function_unchanged() -> None:
    """Non-partial handlers must flow through unchanged — safe_limit is
    additive only, no behavioural change for the common case."""
    from dazzle.back.runtime import rate_limit as _rl

    async def my_handler(request: Any) -> str:
        return "ok"

    decorated = _rl.safe_limit("10/minute")(my_handler)
    # Plain function already has __name__; safe_limit doesn't mangle it.
    assert my_handler.__name__ == "my_handler"
    assert decorated is not None


def test_safe_limit_survives_real_limiter_introspection() -> None:
    """Simulate the failure mode: a fake limiter whose `.limit()` decorator
    reads `handler.__name__` (the exact slowapi behaviour). With the
    plain partial this raises AttributeError; safe_limit must not.

    This is the load-bearing test — it pins the regression cause without
    requiring slowapi to be installed in the test env.
    """
    from dazzle.back.runtime import rate_limit as _rl

    introspections: list[str] = []

    class _StrictLimiter:
        """Mimics slowapi.Limiter.limit() reading handler.__name__."""

        def limit(self, _limit_str: str) -> Any:
            def decorator(handler: Any) -> Any:
                # The line that raises AttributeError on a raw partial.
                introspections.append(handler.__name__)
                return handler

            return decorator

    # Swap in the strict limiter for the duration of this test.
    saved = _rl.limits.limiter
    _rl.limits.limiter = _StrictLimiter()
    try:
        handler = partial(_plain_handler, "fake-deps")
        # Pre-#1251 would raise here. Post-fix this returns cleanly.
        _rl.safe_limit("10/minute")(handler)
        assert introspections == ["_plain_handler"], introspections
    finally:
        _rl.limits.limiter = saved


def test_safe_limit_raw_partial_without_helper_still_breaks() -> None:
    """Negative regression: the bare partial-vs-strict-limiter path still
    raises AttributeError — confirms the test infrastructure faithfully
    reproduces the v0.72.x boot failure when safe_limit is bypassed."""
    from dazzle.back.runtime import rate_limit as _rl

    class _StrictLimiter:
        def limit(self, _limit_str: str) -> Any:
            def decorator(handler: Any) -> Any:
                return handler.__name__  # noqa: B015 — read for the side effect

            return decorator

    saved = _rl.limits.limiter
    _rl.limits.limiter = _StrictLimiter()
    try:
        handler = partial(_plain_handler, "fake-deps")
        with pytest.raises(AttributeError, match="__name__"):
            # Direct application without safe_limit — the pre-fix code path.
            _rl.limits.limiter.limit("10/minute")(handler)
    finally:
        _rl.limits.limiter = saved
