"""#1228 Phase 3c slice 3c.iii — atomic-flow route registration tests.

Pins the wiring around ``execute_atomic_flow``:

1. ``build_input_model`` synthesises a Pydantic class from the flow's
   ``inputs:`` block; required vs optional propagated correctly; IR
   field-type kinds map to expected Python types.
2. ``build_atomic_flow_router`` registers one ``POST /api/atomic/<name>``
   per flow with prefix ``/api/atomic`` and tag ``atomic``.
3. End-to-end HTTP: a POST with the right body triggers the executor;
   the response includes the created UUIDs.
4. RBAC: when ``user_role_extractor`` says the caller lacks the
   required role, the handler returns 403.
5. AtomicFlowError translates to HTTP 400 with ``failed_at`` in the
   error detail.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.core import ir
from dazzle.http.runtime.atomic_flow_routes import (
    build_atomic_flow_router,
    build_input_model,
)


def _simple_flow() -> ir.AtomicFlowSpec:
    return ir.AtomicFlowSpec(
        name="onboard",
        label="Onboard",
        intent="Atomic onboarding test",
        permit_execute=["hr_admin"],
        inputs=[
            ir.FlowInput(
                name="legal_name",
                type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200),
                required=True,
            ),
            ir.FlowInput(
                name="started_at",
                type=ir.FieldType(kind=ir.FieldTypeKind.DATE),
                required=True,
            ),
            ir.FlowInput(
                name="optional_email",
                type=ir.FieldType(kind=ir.FieldTypeKind.EMAIL),
                required=False,
            ),
        ],
        steps=[
            ir.FlowCreate(
                entity="Person",
                assignments={
                    "legal_name": ir.FlowFieldValue(
                        kind=ir.FlowFieldValueKind.INPUT_REF,
                        input_name="legal_name",
                    ),
                    "started_at": ir.FlowFieldValue(
                        kind=ir.FlowFieldValueKind.INPUT_REF,
                        input_name="started_at",
                    ),
                },
            ),
        ],
    )


def _make_db(*, raise_on_execute: bool = False) -> MagicMock:
    cursor = MagicMock()
    if raise_on_execute:
        cursor.execute = MagicMock(side_effect=RuntimeError("DB exploded"))
    else:
        cursor.execute = MagicMock()
    conn = MagicMock()
    conn.cursor = MagicMock(return_value=cursor)
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=conn)
    ctx.__exit__ = MagicMock(return_value=False)
    db = MagicMock()
    db.placeholder = "%s"
    db.connection = MagicMock(return_value=ctx)
    return db


class TestInputModelGeneration:
    def test_required_field_is_required(self) -> None:
        flow = _simple_flow()
        Model = build_input_model(flow)
        # Pydantic raises on missing required.
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            Model()  # type: ignore[call-arg]

    def test_optional_field_defaults_to_none(self) -> None:
        flow = _simple_flow()
        Model = build_input_model(flow)
        instance = Model(legal_name="Alice", started_at=date(2026, 1, 1))  # type: ignore[call-arg]
        assert instance.optional_email is None  # type: ignore[attr-defined]

    def test_str_field_maps_to_str(self) -> None:
        flow = _simple_flow()
        Model = build_input_model(flow)
        assert Model.model_fields["legal_name"].annotation is str

    def test_date_field_maps_to_date(self) -> None:
        flow = _simple_flow()
        Model = build_input_model(flow)
        assert Model.model_fields["started_at"].annotation is date

    def test_model_name_derives_from_flow_name(self) -> None:
        flow = _simple_flow()
        Model = build_input_model(flow)
        assert Model.__name__ == "OnboardInput"


class TestRouterShape:
    def test_route_registered_with_correct_prefix_and_method(self) -> None:
        flow = _simple_flow()
        db = _make_db()
        router = build_atomic_flow_router([flow], db)
        paths_methods = {(r.path, m) for r in router.routes for m in getattr(r, "methods", set())}
        assert ("/api/atomic/onboard", "POST") in paths_methods

    def test_no_flows_yields_empty_router(self) -> None:
        db = _make_db()
        router = build_atomic_flow_router([], db)
        # Only built-in OpenAPI / docs routes, no /api/atomic/* paths.
        atomic_paths = [r.path for r in router.routes if r.path.startswith("/api/atomic/")]
        assert atomic_paths == []


class TestEndToEnd:
    def _app(self, flow: ir.AtomicFlowSpec, db: Any) -> FastAPI:  # type: ignore[name-defined]
        app = FastAPI()
        app.include_router(build_atomic_flow_router([flow], db))
        return app

    def test_successful_post_returns_created_ids(self) -> None:
        flow = _simple_flow()
        db = _make_db()
        client = TestClient(self._app(flow, db))
        resp = client.post(
            "/api/atomic/onboard",
            json={"legal_name": "Alice", "started_at": "2026-01-01"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "created" in body and "Person" in body["created"]
        # Should be a valid UUID string.
        UUID(body["created"]["Person"])

    def test_missing_required_input_returns_422(self) -> None:
        flow = _simple_flow()
        db = _make_db()
        client = TestClient(self._app(flow, db))
        resp = client.post("/api/atomic/onboard", json={})
        assert resp.status_code == 422  # Pydantic validation error

    def test_db_failure_translates_to_400_with_failed_at(self) -> None:
        flow = _simple_flow()
        db = _make_db(raise_on_execute=True)
        client = TestClient(self._app(flow, db))
        resp = client.post(
            "/api/atomic/onboard",
            json={"legal_name": "Alice", "started_at": "2026-01-01"},
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert detail["error"] == "atomic_flow_failed"
        assert detail["failed_at"] == "Person"


class TestRBAC:
    def _app_with_auth(
        self,
        flow: ir.AtomicFlowSpec,
        db: Any,  # type: ignore[name-defined]
        user_roles: list[str],
    ) -> FastAPI:
        app = FastAPI()

        async def fake_auth_dep() -> dict[str, Any]:
            return {"name": "test", "roles": user_roles}

        def extract_roles(user: dict[str, Any]) -> list[str]:
            return list(user.get("roles", []))

        app.include_router(
            build_atomic_flow_router(
                [flow],
                db,
                user_role_extractor=extract_roles,
                auth_dep=fake_auth_dep,
            )
        )
        return app

    def test_user_with_required_role_passes(self) -> None:
        flow = _simple_flow()  # requires "hr_admin"
        db = _make_db()
        client = TestClient(self._app_with_auth(flow, db, ["hr_admin"]))
        resp = client.post(
            "/api/atomic/onboard",
            json={"legal_name": "Alice", "started_at": "2026-01-01"},
        )
        assert resp.status_code == 200

    def test_user_without_required_role_gets_403(self) -> None:
        flow = _simple_flow()  # requires "hr_admin"
        db = _make_db()
        client = TestClient(self._app_with_auth(flow, db, ["reader"]))
        resp = client.post(
            "/api/atomic/onboard",
            json={"legal_name": "Alice", "started_at": "2026-01-01"},
        )
        assert resp.status_code == 403
        assert "hr_admin" in resp.json()["detail"]
