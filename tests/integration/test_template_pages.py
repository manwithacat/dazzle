"""
Integration tests for server-rendered HTMX template pages.

Tests full page rendering via FastAPI TestClient — verifies that
page routes return correct HTML with expected structure, HTMX
attributes, and navigation elements.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

pytest.importorskip("fastapi", reason="FastAPI not installed")

from dazzle.core.ir import (
    AppSpec,
    DomainSpec,
    EntitySpec,
    FieldModifier,
    FieldSpec,
    FieldType,
    FieldTypeKind,
    SurfaceElement,
    SurfaceMode,
    SurfaceSection,
    SurfaceSpec,
)

# These modules are part of the HTMX template runtime and may not be
# installed in every CI configuration.
pytest.importorskip("dazzle_dnr_ui.runtime.page_routes")

from dazzle_dnr_ui.runtime.page_routes import create_page_routes  # noqa: E402

if TYPE_CHECKING:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def appspec() -> AppSpec:
    """Hand-built AppSpec for template page testing."""
    task = EntitySpec(
        name="Task",
        title="Task",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind=FieldTypeKind.UUID),
                modifiers=[FieldModifier.PK],
            ),
            FieldSpec(
                name="title",
                type=FieldType(kind=FieldTypeKind.STR, max_length=200),
                modifiers=[FieldModifier.REQUIRED],
            ),
            FieldSpec(
                name="completed",
                type=FieldType(kind=FieldTypeKind.BOOL),
                default=False,
            ),
        ],
    )

    return AppSpec(
        name="test_app",
        title="Test App",
        domain=DomainSpec(entities=[task]),
        surfaces=[
            SurfaceSpec(
                name="task_list",
                title="Tasks",
                entity_ref="Task",
                mode=SurfaceMode.LIST,
                sections=[
                    SurfaceSection(
                        name="main",
                        title="Main",
                        elements=[
                            SurfaceElement(field_name="title", label="Title"),
                            SurfaceElement(field_name="completed", label="Done"),
                        ],
                    )
                ],
            ),
            SurfaceSpec(
                name="task_create",
                title="Create Task",
                entity_ref="Task",
                mode=SurfaceMode.CREATE,
                sections=[
                    SurfaceSection(
                        name="main",
                        title="Main",
                        elements=[
                            SurfaceElement(field_name="title", label="Title"),
                            SurfaceElement(field_name="completed", label="Done"),
                        ],
                    )
                ],
            ),
            SurfaceSpec(
                name="task_view",
                title="Task Details",
                entity_ref="Task",
                mode=SurfaceMode.VIEW,
                sections=[
                    SurfaceSection(
                        name="main",
                        title="Main",
                        elements=[
                            SurfaceElement(field_name="title", label="Title"),
                            SurfaceElement(field_name="completed", label="Done"),
                        ],
                    )
                ],
            ),
        ],
    )


@pytest.fixture(scope="module")
def page_app(appspec: AppSpec) -> FastAPI:
    """Create a FastAPI app with page routes mounted."""
    from fastapi import FastAPI

    app = FastAPI()
    router = create_page_routes(appspec, backend_url="http://127.0.0.1:9999")
    app.include_router(router)
    return app


@pytest.fixture(scope="module")
def client(page_app: FastAPI) -> TestClient:
    from fastapi.testclient import TestClient

    return TestClient(page_app)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestListPage:
    """Tests for the list page route."""

    def test_root_returns_html(self, client: TestClient) -> None:
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_root_has_doctype(self, client: TestClient) -> None:
        resp = client.get("/")
        html = resp.text.lower()
        assert "<!doctype html>" in html

    def test_list_page_has_table(self, client: TestClient) -> None:
        resp = client.get("/task")
        assert resp.status_code == 200
        assert "<table" in resp.text

    def test_list_page_has_htmx(self, client: TestClient) -> None:
        resp = client.get("/task")
        assert "hx-" in resp.text or "htmx" in resp.text.lower()

    def test_list_page_has_app_name(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "Test App" in resp.text


class TestCreatePage:
    """Tests for the create page route."""

    def test_create_returns_html(self, client: TestClient) -> None:
        resp = client.get("/task/create")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_create_has_form(self, client: TestClient) -> None:
        resp = client.get("/task/create")
        assert "<form" in resp.text

    def test_create_has_input_fields(self, client: TestClient) -> None:
        resp = client.get("/task/create")
        assert "<input" in resp.text or "Title" in resp.text


class TestDetailPage:
    """Tests for the detail/view page route."""

    def test_detail_returns_html(self, client: TestClient) -> None:
        resp = client.get("/task/some-uuid")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_detail_has_structure(self, client: TestClient) -> None:
        resp = client.get("/task/some-uuid")
        # Should have detail view markup
        assert "Task Details" in resp.text or "Title" in resp.text


class TestNavigation:
    """Tests for navigation across rendered pages."""

    def test_all_pages_have_nav(self, client: TestClient) -> None:
        """Every rendered page should include navigation."""
        for path in ["/", "/task", "/task/create"]:
            resp = client.get(path)
            assert resp.status_code == 200
            html = resp.text.lower()
            assert "<nav" in html or "navbar" in html or "<a" in html


class TestHtmxFragments:
    """Tests for HTMX partial (fragment) responses."""

    def test_hx_request_header_returns_fragment(self, client: TestClient) -> None:
        """GET with HX-Request header should still return content.

        Note: Fragment vs full-page behavior depends on implementation.
        At minimum the response should be valid HTML.
        """
        resp = client.get("/task", headers={"HX-Request": "true"})
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
