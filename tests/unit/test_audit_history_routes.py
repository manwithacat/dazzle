"""Tests for #956 cycle 11 — audit-history HTMX fragment route.

Cycle 9 built `render_audit_history_region`. Cycle 11 wraps it in
a FastAPI route at ``/_dazzle/audit-history/{entity_type}/{entity_id}``
that the cycle-11 detail-view template includes via HTMX.

These tests verify:

  * The route renders the cycle-9 region helper's output via
    HTMLResponse (200 + valid HTML)
  * Personas extracted from the auth context flow into the loader's
    RBAC check (denied viewer → empty state in HTML)
  * The `role_` prefix is stripped during persona extraction
    (matches `_normalize_role` in route_generator)
  * The auth-less variant works (anonymous viewer = `[]` personas →
    deny on restricted blocks, empty state)
  * `_extract_personas` defends against missing user / unauthenticated
    contexts
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from dazzle_back.runtime.audit_history_routes import (
    _extract_personas,
    create_audit_history_routes,
)

# ---------------------------------------------------------------------------
# Fixtures — minimal AuditSpec / AuditService stubs
# ---------------------------------------------------------------------------


@dataclass
class _ShowTo:
    kind: str = "persona"
    personas: list[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.personas is None:
            self.personas = []


@dataclass
class _AuditSpec:
    entity: str
    track: list[str] = None  # type: ignore[assignment]
    show_to: _ShowTo = None  # type: ignore[assignment]
    retention_days: int = 0

    def __post_init__(self):
        if self.track is None:
            self.track = []
        if self.show_to is None:
            self.show_to = _ShowTo()


def _row(at, field_name, *, before, after, by="user-1", op="update"):
    return {
        "at": at,
        "entity_type": "Manuscript",
        "entity_id": "abc",
        "field_name": field_name,
        "operation": op,
        "before_value": json.dumps(before) if before is not None else None,
        "after_value": json.dumps(after) if after is not None else None,
        "by_user_id": by,
    }


class _StubAuditService:
    def __init__(self, rows: Any) -> None:
        self._rows = rows

    async def list(self, **kwargs: Any) -> Any:
        return self._rows


def _make_app(*, audit_service, audits, auth_dep=None):
    app = FastAPI()
    router = create_audit_history_routes(
        audit_service=audit_service,
        audits=audits,
        auth_dep=auth_dep,
    )
    app.include_router(router)
    return app


# ---------------------------------------------------------------------------
# _extract_personas
# ---------------------------------------------------------------------------


class TestExtractPersonas:
    def test_none_context(self):
        assert _extract_personas(None) == []

    def test_unauthenticated(self):
        ctx = SimpleNamespace(is_authenticated=False, user=None)
        assert _extract_personas(ctx) == []

    def test_user_none_with_authenticated_flag(self):
        ctx = SimpleNamespace(is_authenticated=True, user=None)
        assert _extract_personas(ctx) == []

    def test_string_roles(self):
        user = SimpleNamespace(roles=["teacher", "marker"])
        ctx = SimpleNamespace(is_authenticated=True, user=user)
        assert _extract_personas(ctx) == ["teacher", "marker"]

    def test_role_prefix_stripped(self):
        user = SimpleNamespace(roles=["role_teacher"])
        ctx = SimpleNamespace(is_authenticated=True, user=user)
        assert _extract_personas(ctx) == ["teacher"]

    def test_object_roles_with_name_attr(self):
        role = SimpleNamespace(name="teacher")
        user = SimpleNamespace(roles=[role])
        ctx = SimpleNamespace(is_authenticated=True, user=user)
        assert _extract_personas(ctx) == ["teacher"]

    def test_empty_roles(self):
        user = SimpleNamespace(roles=[])
        ctx = SimpleNamespace(is_authenticated=True, user=user)
        assert _extract_personas(ctx) == []


# ---------------------------------------------------------------------------
# Route — auth-less path (no auth_dep)
# ---------------------------------------------------------------------------


class TestAuthlessRoute:
    def test_returns_html_with_history(self):
        spec = _AuditSpec(entity="Manuscript", show_to=_ShowTo(personas=[]))
        # show_to=[] → deny by default for the anonymous viewer, so
        # this returns the empty-state HTML rather than the rows.
        # Verify the route at least renders valid HTML (200).
        app = _make_app(
            audit_service=_StubAuditService([_row("t1", "status", before="d", after="s")]),
            audits=[spec],
        )
        client = TestClient(app)
        resp = client.get("/_dazzle/audit-history/Manuscript/abc")
        assert resp.status_code == 200
        assert "dz-audit-history" in resp.text

    def test_returns_empty_state_when_unaudited(self):
        # Entity not in audits → empty-state markup.
        app = _make_app(
            audit_service=_StubAuditService([]),
            audits=[],
        )
        client = TestClient(app)
        resp = client.get("/_dazzle/audit-history/Manuscript/abc")
        assert resp.status_code == 200
        assert "No history yet" in resp.text


# ---------------------------------------------------------------------------
# Route — with auth_dep
# ---------------------------------------------------------------------------


def _auth_dep_factory(personas: list[str]):
    """Build a Depends-shaped callable that yields the given roles."""

    def dep():
        if not personas:
            return SimpleNamespace(is_authenticated=False, user=None)
        user = SimpleNamespace(id="user-x", roles=list(personas))
        return SimpleNamespace(is_authenticated=True, user=user)

    return dep


class TestAuthenticatedRoute:
    def test_allowed_persona_sees_rows(self):
        spec = _AuditSpec(entity="Manuscript", show_to=_ShowTo(personas=["teacher"]))
        app = _make_app(
            audit_service=_StubAuditService(
                [_row("t1", "status", before="draft", after="submitted")]
            ),
            audits=[spec],
            auth_dep=_auth_dep_factory(["teacher"]),
        )
        client = TestClient(app)
        resp = client.get("/_dazzle/audit-history/Manuscript/abc")
        assert resp.status_code == 200
        assert "draft" in resp.text
        assert "submitted" in resp.text

    def test_denied_persona_sees_empty_state(self):
        spec = _AuditSpec(entity="Manuscript", show_to=_ShowTo(personas=["admin"]))
        app = _make_app(
            audit_service=_StubAuditService(
                [_row("t1", "status", before="draft", after="submitted")]
            ),
            audits=[spec],
            auth_dep=_auth_dep_factory(["teacher"]),
        )
        client = TestClient(app)
        resp = client.get("/_dazzle/audit-history/Manuscript/abc")
        assert resp.status_code == 200
        # Importantly the disallowed values must NOT leak into the markup.
        assert "draft" not in resp.text
        assert "submitted" not in resp.text
        assert "No history yet" in resp.text

    def test_role_prefix_stripped_for_persona_match(self):
        # AuthContext carries `role_teacher`; DSL declares `teacher` —
        # the route's persona extractor strips the prefix so the gate
        # matches.
        spec = _AuditSpec(entity="Manuscript", show_to=_ShowTo(personas=["teacher"]))
        app = _make_app(
            audit_service=_StubAuditService(
                [_row("t1", "status", before="draft", after="submitted")]
            ),
            audits=[spec],
            auth_dep=_auth_dep_factory(["role_teacher"]),
        )
        client = TestClient(app)
        resp = client.get("/_dazzle/audit-history/Manuscript/abc")
        assert resp.status_code == 200
        assert "draft" in resp.text


# ---------------------------------------------------------------------------
# Route shape — prefix + path
# ---------------------------------------------------------------------------


class TestRouteShape:
    def test_returns_404_outside_prefix(self):
        app = _make_app(audit_service=_StubAuditService([]), audits=[])
        client = TestClient(app)
        # Wrong prefix → 404.
        resp = client.get("/api/audit-history/Manuscript/abc")
        assert resp.status_code == 404

    @pytest.mark.parametrize("entity_type", ["Manuscript", "Order", "TenantSettings"])
    def test_accepts_arbitrary_entity_types(self, entity_type):
        # Path is generic — the audit_spec lookup determines whether
        # the entity is actually audited; the route itself accepts
        # any path component.
        app = _make_app(audit_service=_StubAuditService([]), audits=[])
        client = TestClient(app)
        resp = client.get(f"/_dazzle/audit-history/{entity_type}/some-id")
        assert resp.status_code == 200
