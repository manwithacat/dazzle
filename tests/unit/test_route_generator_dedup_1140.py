"""#1140: backstop dedup in generate_all_routes.

When the same `(method, path)` appears twice in the `endpoints` list
(AegisMark's AssessmentEvent was visited twice because it was
referenced from both an `analytics:` block and regular workspace
surfaces), the generator must emit it exactly once.

This is a defence-in-depth — `convert_surfaces_to_services` already
dedupes (covered by `test_route_conflict_dedup.py`), but `endpoints`
is assembled from multiple sources and a future upstream change could
re-introduce the duplicate. The backstop catches it regardless of
which source double-visited.
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")

from dazzle.http.runtime.route_generator import RouteGenerator  # noqa: E402
from dazzle.http.specs import EndpointSpec, HttpMethod  # noqa: E402


def _generator() -> RouteGenerator:
    return RouteGenerator(
        services={},
        models={},
        schemas={},
        entity_access_specs={},
        auth_dep=None,
        optional_auth_dep=None,
    )


def test_duplicate_method_path_emitted_once() -> None:
    """Two endpoints with identical (method, path) → exactly one
    `generate_route` call."""
    generator = _generator()
    a = EndpointSpec(
        name="list_events_a",
        service="svc",
        method=HttpMethod.GET,
        path="/assessmentevents",
    )
    b = EndpointSpec(
        name="list_events_b",
        service="svc",
        method=HttpMethod.GET,
        path="/assessmentevents",
    )

    with patch.object(generator, "generate_route") as spy:
        generator.generate_all_routes([a, b], service_specs={})

    assert spy.call_count == 1


def test_duplicate_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    """The second copy logs at WARNING — silent dedup would mask the
    upstream bug; a warning gives operators a trail back to the cause."""
    generator = _generator()
    a = EndpointSpec(
        name="post_events_a",
        service="svc",
        method=HttpMethod.POST,
        path="/assessmentevents",
    )
    b = EndpointSpec(
        name="post_events_b",
        service="svc",
        method=HttpMethod.POST,
        path="/assessmentevents",
    )

    with (
        patch.object(generator, "generate_route"),
        caplog.at_level(logging.WARNING, logger="dazzle.http.runtime.route_generator"),
    ):
        generator.generate_all_routes([a, b], service_specs={})

    matches = [r for r in caplog.records if "duplicate CRUD endpoint" in r.message]
    assert matches, (
        f"expected duplicate-endpoint WARNING, got {[r.message for r in caplog.records]}"
    )


def test_different_methods_same_path_both_emitted() -> None:
    """GET and POST at the same path are distinct operations — both
    must emit. The dedup key is (method, path), not just path."""
    generator = _generator()
    get = EndpointSpec(name="list", service="svc", method=HttpMethod.GET, path="/things")
    post = EndpointSpec(name="create", service="svc", method=HttpMethod.POST, path="/things")

    with patch.object(generator, "generate_route") as spy:
        generator.generate_all_routes([get, post], service_specs={})

    assert spy.call_count == 2


def test_claimed_routes_still_skipped_even_with_dedup() -> None:
    """Claimed-routes filtering and dedup compose: a claimed endpoint
    that appears twice still results in zero `generate_route` calls."""
    generator = _generator()
    a = EndpointSpec(name="list_a", service="svc", method=HttpMethod.GET, path="/overridden")
    b = EndpointSpec(name="list_b", service="svc", method=HttpMethod.GET, path="/overridden")

    with patch.object(generator, "generate_route") as spy:
        generator.generate_all_routes(
            [a, b], service_specs={}, claimed_routes={("GET", "/overridden")}
        )

    assert spy.call_count == 0
