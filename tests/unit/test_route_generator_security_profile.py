"""Regression guard for #1196.

Generated entity routes must be rate-limit-wrapped by the active security
profile's API limit. The wrap reads from the `rate_limit.limits` module-level
singleton (set by `apply_rate_limiting(app, profile)` at server boot); on the
`basic` profile (or when slowapi is absent) the limiter is a `_NoOpLimiter`
stub, so the wrap is a no-op there.
"""

from types import SimpleNamespace

import pytest

from dazzle.http.runtime import rate_limit as _rl
from dazzle.http.runtime.route_generator import RouteGenerator
from dazzle.http.specs.endpoint import HttpMethod


def test_security_profile_defaults_to_basic() -> None:
    gen = RouteGenerator(services={}, models={})
    assert gen.security_profile == "basic"


def test_security_profile_accepts_override() -> None:
    gen = RouteGenerator(services={}, models={}, security_profile="standard")
    assert gen.security_profile == "standard"


def test_add_route_wraps_handler_with_active_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_add_route` must wrap every handler with `limits.limiter.limit(api_limit)`
    so generated routes honour the active profile's throttling."""
    calls: list[str] = []

    class _RecordingLimiter:
        def limit(self, spec: str):
            calls.append(spec)
            return lambda fn: fn

    monkeypatch.setattr(_rl.limits, "limiter", _RecordingLimiter())
    monkeypatch.setattr(_rl.limits, "api_limit", "42/minute")

    gen = RouteGenerator(services={}, models={}, security_profile="standard")
    endpoint = SimpleNamespace(
        method=HttpMethod.GET,
        path="/_t1196",
        name="t1196",
        description="t",
        tags=[],
        require_roles=None,
        deny_roles=None,
    )
    gen._add_route(endpoint, lambda: {})
    assert calls == ["42/minute"]
