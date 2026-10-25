"""#1854: the server side of ``POST`` / ``GET /feedbackreports``.

The generated create route runs ``FeedbackCreateInterceptor`` ahead of
injection, validation and the insert: identity is stamped from the session
(payload ignored), caps and a per-user rate limit are enforced, and an
``Idempotency-Key`` replay answers 200 + ``Idempotent-Replayed: true`` from
the stored row — including the unique-violation race, which used to 500.
The generated list route runs ``feedback_list_filters`` for ``status`` comma
lists and ``since``.
"""

from __future__ import annotations

import functools
from typing import Any
from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")

from fastapi import HTTPException  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from dazzle.http.runtime.auth import AuthContext  # noqa: E402
from dazzle.http.runtime.feedback_policy import (  # noqa: E402
    CONTEXT_MAX_BYTES,
    DESCRIPTION_MAX_CHARS,
    SCREENSHOT_MAX_BYTES,
    FeedbackCreateInterceptor,
    FeedbackRateLimiter,
    enforce_caps,
    feedback_list_filters,
    parse_since,
    resolve_idempotency_key,
    stamp_identity,
)
from dazzle.http.runtime.handlers.list_handlers import create_list_handler  # noqa: E402
from dazzle.http.runtime.handlers.write_handlers import create_create_handler  # noqa: E402
from dazzle.http.runtime.repository import ConstraintViolationError  # noqa: E402
from dazzle.http.specs.auth import (  # noqa: E402
    AccessOperationKind,
    EntityAccessSpec,
    PermissionRuleSpec,
)
from tests.unit.helpers.crud_routes import (  # noqa: E402
    RecordingService,
    crud_route_client,
    signed_in,
)


class _ReportCreate(BaseModel):
    """Mirror of the generated FeedbackReport create schema (the fields that matter)."""

    category: str
    severity: str = "minor"
    description: str
    page_url: str | None = None
    surface: str | None = None
    review_session: str | None = None
    anchor: dict[str, Any] | None = None
    context: dict[str, Any] | None = None
    page_snapshot: str | None = None
    console_errors: str | None = None
    screenshot_data: str | None = None
    reported_by: str | None = None
    persona: str | None = None
    idempotency_key: str | None = None


class _ReportStore(RecordingService):
    """A service that stores creates and answers idempotency lookups.

    ``race_on_key`` makes the create for that key raise the unique violation
    the repository raises when two inserts race, while the row is "already
    there" for the lookup that follows.
    """

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict[str, Any]] = []
        self.race_on_key: str | None = None
        self.creates = 0

    async def execute(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        op = kwargs.get("operation")
        if op == "list":
            key = (kwargs.get("filters") or {}).get("idempotency_key")
            items = [r for r in self.rows if key and r.get("idempotency_key") == key]
            return {"items": items, "total": len(items), "page": 1, "page_size": 1}
        if op == "create":
            self.creates += 1
            data = kwargs["data"].model_dump()
            if self.race_on_key and data.get("idempotency_key") == self.race_on_key:
                self.rows.append({"id": "raced", **data})
                raise ConstraintViolationError(
                    "A feedback report with this idempotency key already exists",
                    field="idempotency_key",
                    constraint_type="unique",
                )
            row = {"id": f"row-{self.creates}", **data}
            self.rows.append(row)
            return row
        return {"ok": True}


_ACCESS = EntityAccessSpec(
    permissions=[
        PermissionRuleSpec(operation=AccessOperationKind.CREATE, personas=["teacher"]),
        PermissionRuleSpec(operation=AccessOperationKind.LIST, personas=["teacher"]),
    ]
)


def _client(
    service: Any,
    *,
    auth: AuthContext | None = None,
    interceptor: FeedbackCreateInterceptor | None = None,
) -> Any:
    factory = functools.partial(
        create_create_handler,
        create_interceptor=interceptor or FeedbackCreateInterceptor(limiter=FeedbackRateLimiter()),
    )
    return crud_route_client(
        factory,
        auth=auth or signed_in("role_teacher"),
        service=service,
        access=_ACCESS,
        entity_name="FeedbackReport",
        input_schema=_ReportCreate,
        method="POST",
        path="/feedbackreports",
    )


_PAYLOAD = {
    "category": "ux",
    "severity": "minor",
    "description": "The save button hides behind the drawer",
    "page_url": "https://app.example.test/app/tasks",
    "surface": "task_list",
    "anchor": {"dz_anchor": "task_list/main/row-1/save", "css": "#save"},
    # Spoofed identity — the server must ignore these.
    "reported_by": "mallory@example.test",
    "persona": "super_admin",
}


# ---------------------------------------------------------------------------
# The policy pieces
# ---------------------------------------------------------------------------


class TestRateLimiter:
    def test_minute_window(self) -> None:
        now = [1_000.0]
        limiter = FeedbackRateLimiter(per_minute=2, per_day=10, clock=lambda: now[0])
        assert limiter.check("u") is None
        assert limiter.check("u") is None
        wait = limiter.check("u")
        assert wait is not None and 1 <= wait <= 61
        now[0] += 61
        assert limiter.check("u") is None

    def test_day_window(self) -> None:
        now = [0.0]
        limiter = FeedbackRateLimiter(per_minute=100, per_day=3, clock=lambda: now[0])
        for _ in range(3):
            assert limiter.check("u") is None
            now[0] += 120
        wait = limiter.check("u")
        assert wait is not None and wait > 60
        assert limiter.check("other") is None  # keys are independent


class TestCaps:
    def test_description(self) -> None:
        with pytest.raises(HTTPException) as info:
            enforce_caps({"description": "x" * (DESCRIPTION_MAX_CHARS + 1)})
        assert info.value.status_code == 422
        assert "description" in str(info.value.detail)

    def test_context_total(self) -> None:
        big = "y" * (CONTEXT_MAX_BYTES // 2)
        enforce_caps({"page_snapshot": big})  # alone it fits
        with pytest.raises(HTTPException, match="limit is"):
            enforce_caps({"page_snapshot": big, "console_errors": big, "anchor": {"a": "b"}})

    def test_screenshot(self) -> None:
        with pytest.raises(HTTPException) as info:
            enforce_caps({"screenshot_data": "z" * (SCREENSHOT_MAX_BYTES + 1)})
        assert "screenshot_data" in str(info.value.detail)


class TestStampAndKey:
    def test_stamp_overwrites_payload(self) -> None:
        body = {"reported_by": "mallory", "persona": "super_admin"}
        stamp_identity(
            body, {"reported_by", "persona"}, user_email="ada@x.test", user_roles=["role_teacher"]
        )
        assert body == {"reported_by": "ada@x.test", "persona": "teacher"}

    def test_stamp_only_declared_fields(self) -> None:
        body = {"persona": "x"}
        stamp_identity(body, {"description"}, user_email="a@b", user_roles=[])
        assert body == {"persona": "x"}

    def test_key_precedence_header_then_legacy_then_body(self) -> None:
        class _Req:
            def __init__(self, headers: dict[str, str]) -> None:
                self.headers = headers

        assert (
            resolve_idempotency_key(
                _Req({"Idempotency-Key": "h", "X-Idempotency-Key": "x"}), {"idempotency_key": "b"}
            )
            == "h"
        )
        assert (
            resolve_idempotency_key(_Req({"X-Idempotency-Key": "x"}), {"idempotency_key": "b"})
            == "x"
        )
        assert resolve_idempotency_key(_Req({}), {"idempotency_key": " b "}) == "b"
        assert resolve_idempotency_key(_Req({}), {}) is None


class TestListFilters:
    def test_status_comma_list_becomes_in(self) -> None:
        out = feedback_list_filters(
            {"status": "new,triaged,bogus"}, {"status": "new,triaged,bogus", "surface": "x"}
        )
        assert out == {"surface": "x", "status__in": ["new", "triaged"]}

    def test_single_status_is_left_alone(self) -> None:
        assert feedback_list_filters({"status": "new"}, {"status": "new"}) == {"status": "new"}

    def test_since(self) -> None:
        out = feedback_list_filters({"since": "2026-10-01T09:00:00Z"}, {})
        assert out["created_at__gte"].isoformat() == "2026-10-01T09:00:00+00:00"
        assert parse_since("2026-10-01").isoformat() == "2026-10-01T00:00:00+00:00"

    def test_bad_since_is_422(self) -> None:
        with pytest.raises(HTTPException) as info:
            feedback_list_filters({"since": "yesterday"}, {})
        assert info.value.status_code == 422


# ---------------------------------------------------------------------------
# POST /feedbackreports through the generated create route
# ---------------------------------------------------------------------------


class TestCreateRoute:
    def test_identity_is_stamped_from_the_session_not_the_payload(self) -> None:
        service = _ReportStore()
        client = _client(service)
        resp = client.post("/feedbackreports", json=_PAYLOAD)
        assert resp.status_code == 200, resp.text
        created = next(c for c in service.calls if c.get("operation") == "create")["data"]
        assert created.reported_by == "u@example.com"
        assert created.persona == "teacher"

    def test_replay_by_header_answers_the_stored_row(self) -> None:
        service = _ReportStore()
        client = _client(service)
        first = client.post("/feedbackreports", json=_PAYLOAD, headers={"Idempotency-Key": "k-1"})
        assert first.status_code == 200
        assert "Idempotent-Replayed" not in first.headers
        second = client.post("/feedbackreports", json=_PAYLOAD, headers={"Idempotency-Key": "k-1"})
        assert second.status_code == 200
        assert second.headers["Idempotent-Replayed"] == "true"
        assert second.json()["id"] == first.json()["id"]
        assert service.creates == 1  # the replay never reached the insert

    def test_replay_by_body_field(self) -> None:
        service = _ReportStore()
        client = _client(service)
        body = {**_PAYLOAD, "idempotency_key": "k-2"}
        assert client.post("/feedbackreports", json=body).status_code == 200
        replay = client.post("/feedbackreports", json=body)
        assert replay.status_code == 200
        assert replay.headers["Idempotent-Replayed"] == "true"
        assert service.creates == 1

    def test_different_payload_under_the_same_key_is_422(self) -> None:
        service = _ReportStore()
        client = _client(service)
        client.post("/feedbackreports", json=_PAYLOAD, headers={"Idempotency-Key": "k-3"})
        other = client.post(
            "/feedbackreports",
            json={**_PAYLOAD, "description": "something else"},
            headers={"Idempotency-Key": "k-3"},
        )
        assert other.status_code == 422
        assert "different payload" in other.text
        assert service.creates == 1

    def test_unique_violation_race_is_a_replay_not_a_500(self) -> None:
        service = _ReportStore()
        service.race_on_key = "k-4"
        client = _client(service)
        resp = client.post("/feedbackreports", json=_PAYLOAD, headers={"Idempotency-Key": "k-4"})
        assert resp.status_code == 200, resp.text
        assert resp.headers["Idempotent-Replayed"] == "true"
        assert resp.json()["id"] == "raced"

    def test_caps_are_422_before_the_insert(self) -> None:
        service = _ReportStore()
        client = _client(service)
        resp = client.post(
            "/feedbackreports", json={**_PAYLOAD, "description": "x" * (DESCRIPTION_MAX_CHARS + 1)}
        )
        assert resp.status_code == 422
        assert "description" in resp.text
        assert service.creates == 0

    def test_rate_limit_answers_429_with_retry_after(self) -> None:
        service = _ReportStore()
        limiter = FeedbackRateLimiter(per_minute=2, per_day=100, clock=lambda: 5_000.0)
        client = _client(service, interceptor=FeedbackCreateInterceptor(limiter=limiter))
        assert client.post("/feedbackreports", json=_PAYLOAD).status_code == 200
        assert client.post("/feedbackreports", json=_PAYLOAD).status_code == 200
        third = client.post("/feedbackreports", json=_PAYLOAD)
        assert third.status_code == 429
        assert int(third.headers["Retry-After"]) >= 1
        assert service.creates == 2

    def test_anonymous_is_refused_before_the_policy_runs(self) -> None:
        """The auth wrapper refuses an anonymous create as before (401 with the
        real auth dependency; 403 from this persona-permit fixture). The policy
        never stamps an empty identity into the table."""
        service = _ReportStore()
        client = _client(service, auth=AuthContext(user=None, is_authenticated=False, roles=[]))
        resp = client.post("/feedbackreports", json=_PAYLOAD)
        assert resp.status_code in (401, 403), resp.text
        assert service.creates == 0


class TestListRoute:
    def test_filters_reach_the_data_layer(self) -> None:
        service = RecordingService()
        factory = functools.partial(
            create_list_handler,
            filter_hook=feedback_list_filters,
            filter_fields=["status", "page_url", "surface", "review_session"],
        )
        client = crud_route_client(
            factory,
            auth=signed_in("role_teacher"),
            service=service,
            access=_ACCESS,
            entity_name="FeedbackReport",
            path="/feedbackreports",
        )
        resp = client.get(
            "/feedbackreports",
            params={
                "status": "new,triaged",
                "since": "2026-10-01T00:00:00Z",
                "page_url": "https://app.example.test/app/tasks",
                "surface": "task_list",
                "review_session": "2026-10-25-ab12",
            },
        )
        assert resp.status_code == 200, resp.text
        filters = next(c for c in service.calls if c.get("operation") == "list")["filters"]
        assert filters["status__in"] == ["new", "triaged"]
        assert filters["created_at__gte"].isoformat() == "2026-10-01T00:00:00+00:00"
        assert filters["page_url"] == "https://app.example.test/app/tasks"
        assert filters["surface"] == "task_list"
        assert filters["review_session"] == "2026-10-25-ab12"


# ---------------------------------------------------------------------------
# The generator threads the registries into the generated routes
# ---------------------------------------------------------------------------


class TestRouteGeneratorRegistries:
    def _generator(self) -> Any:
        from dazzle.http.runtime.route_generator import RouteGenerator

        return RouteGenerator(
            services={"svc": _ReportStore()},
            models={"FeedbackReport": _ReportCreate},
            schemas={"FeedbackReport": {"create": _ReportCreate}},
        )

    @staticmethod
    def _spec(kind: str) -> Any:
        from dazzle.http.specs import DomainOperation, OperationKind, ServiceSpec

        return ServiceSpec(
            name="svc",
            domain_operation=DomainOperation(kind=OperationKind(kind), entity="FeedbackReport"),
        )

    def test_defaults_are_empty(self) -> None:
        generator = self._generator()
        assert generator.entity_create_interceptors == {}
        assert generator.entity_list_filter_hooks == {}

    def test_create_route_receives_the_registered_interceptor(self) -> None:
        from dazzle.http.specs import EndpointSpec, HttpMethod

        generator = self._generator()
        interceptor = FeedbackCreateInterceptor(limiter=FeedbackRateLimiter())
        generator.entity_create_interceptors["FeedbackReport"] = interceptor
        endpoint = EndpointSpec(
            name="create", service="svc", method=HttpMethod.POST, path="/feedbackreports"
        )
        with patch(
            "dazzle.http.runtime.route_generator.create_create_handler",
            wraps=create_create_handler,
        ) as spy:
            generator.generate_route(endpoint, self._spec("create"))
        assert spy.call_args.kwargs["create_interceptor"] is interceptor

    def test_list_route_receives_the_registered_hook(self) -> None:
        from dazzle.http.specs import EndpointSpec, HttpMethod

        generator = self._generator()
        generator.entity_list_filter_hooks["FeedbackReport"] = feedback_list_filters
        endpoint = EndpointSpec(
            name="list", service="svc", method=HttpMethod.GET, path="/feedbackreports"
        )
        with patch(
            "dazzle.http.runtime.route_generator.create_list_handler",
            wraps=create_list_handler,
        ) as spy:
            generator.generate_route(endpoint, self._spec("list"))
        assert spy.call_args.kwargs["filter_hook"] is feedback_list_filters

    def test_other_entities_get_neither(self) -> None:
        from dazzle.http.specs import (
            DomainOperation,
            EndpointSpec,
            HttpMethod,
            OperationKind,
            ServiceSpec,
        )

        generator = self._generator()
        generator.services["other"] = _ReportStore()
        generator.models["Task"] = _ReportCreate
        generator.schemas["Task"] = {"create": _ReportCreate}
        generator.entity_create_interceptors["FeedbackReport"] = FeedbackCreateInterceptor()
        endpoint = EndpointSpec(name="c", service="other", method=HttpMethod.POST, path="/tasks")
        spec = ServiceSpec(
            name="other", domain_operation=DomainOperation(kind=OperationKind.CREATE, entity="Task")
        )
        with patch(
            "dazzle.http.runtime.route_generator.create_create_handler",
            wraps=create_create_handler,
        ) as spy:
            generator.generate_route(endpoint, spec)
        assert spy.call_args.kwargs["create_interceptor"] is None
