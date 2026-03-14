"""Tests for API route registration ordering.

Ensures that static paths are registered before parameterized paths at the
same depth, preventing FastAPI from matching path params like {id} against
literal segments like "create".
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dazzle_back.specs.endpoint import EndpointSpec, HttpMethod

pytest.importorskip("fastapi")

from dazzle_back.runtime.route_generator import RouteGenerator  # noqa: E402


def _make_endpoint(name: str, method: HttpMethod, path: str) -> EndpointSpec:
    return EndpointSpec(
        name=name,
        service=name,
        method=method,
        path=path,
    )


class TestRouteOrdering:
    """Verify that generate_all_routes sorts static paths before dynamic."""

    def test_static_path_registered_before_dynamic(self) -> None:
        """GET /users/export should be registered before GET /users/{id}."""
        endpoints = [
            _make_endpoint("get_user", HttpMethod.GET, "/users/{id}"),
            _make_endpoint("export_users", HttpMethod.GET, "/users/export"),
        ]

        service = MagicMock()
        service.execute = MagicMock()

        gen = RouteGenerator(
            services={"get_user": service, "export_users": service},
            models={},
        )

        # Track registration order
        registered: list[str] = []

        def tracking_add_route(endpoint: EndpointSpec, *args, **kwargs):  # type: ignore[no-untyped-def]
            registered.append(endpoint.path)

        gen._add_route = tracking_add_route  # type: ignore[assignment]
        gen.generate_all_routes(endpoints)

        assert registered.index("/users/export") < registered.index("/users/{id}")

    def test_deeper_paths_registered_first(self) -> None:
        """/users/{id}/notes should come before /users/{id}."""
        endpoints = [
            _make_endpoint("get_user", HttpMethod.GET, "/users/{id}"),
            _make_endpoint("user_notes", HttpMethod.GET, "/users/{id}/notes"),
        ]

        service = MagicMock()
        gen = RouteGenerator(
            services={"get_user": service, "user_notes": service},
            models={},
        )

        registered: list[str] = []

        def tracking_add_route(endpoint: EndpointSpec, *args, **kwargs):  # type: ignore[no-untyped-def]
            registered.append(endpoint.path)

        gen._add_route = tracking_add_route  # type: ignore[assignment]
        gen.generate_all_routes(endpoints)

        assert registered.index("/users/{id}/notes") < registered.index("/users/{id}")

    def test_original_order_preserved_for_equal_specificity(self) -> None:
        """Endpoints with equal specificity keep their relative order."""
        endpoints = [
            _make_endpoint("list_users", HttpMethod.GET, "/users"),
            _make_endpoint("list_tasks", HttpMethod.GET, "/tasks"),
        ]

        service = MagicMock()
        gen = RouteGenerator(
            services={"list_users": service, "list_tasks": service},
            models={},
        )

        registered: list[str] = []

        def tracking_add_route(endpoint: EndpointSpec, *args, **kwargs):  # type: ignore[no-untyped-def]
            registered.append(endpoint.path)

        gen._add_route = tracking_add_route  # type: ignore[assignment]
        gen.generate_all_routes(endpoints)

        assert registered == ["/users", "/tasks"]
