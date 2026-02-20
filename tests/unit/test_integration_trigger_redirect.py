"""Tests for integration trigger htmx redirect behavior (#341).

When a manual trigger is invoked via htmx (HX-Request header), the handler
should return an HX-Redirect to the entity detail page instead of raw JSON.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from starlette.testclient import TestClient

_TEST_UUID = "00000000-0000-4000-8000-000000000001"
_TEST_UUID_2 = "00000000-0000-4000-8000-000000000002"


def _make_minimal_app_with_trigger(
    entity_name: str = "Company",
    integration_name: str = "companies_house",
    mapping_name: str = "fetch_company",
) -> Any:
    """Create a minimal FastAPI app with a manual trigger route."""
    from fastapi import FastAPI, Request
    from starlette.responses import JSONResponse, Response

    from dazzle.core.strings import to_api_plural

    app = FastAPI()
    slug = to_api_plural(entity_name)

    # Build a mock executor
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.message = "OK"
    mock_result.mapped_fields = {"data_source": "companies_house"}
    executor = AsyncMock()
    executor.execute_manual = AsyncMock(return_value=mock_result)

    # Build a mock repository
    repo = AsyncMock()
    repo.read = AsyncMock(return_value={"id": _TEST_UUID, "name": "Acme"})
    repositories = {entity_name: repo}

    async def handler(entity_id: str, request: Request) -> Any:
        from uuid import UUID

        r = repositories.get(entity_name)
        if not r:
            return JSONResponse({"error": "not found"}, status_code=404)
        entity_data = await r.read(UUID(entity_id))
        if not entity_data:
            return JSONResponse({"error": "not found"}, status_code=404)
        data = dict(entity_data) if isinstance(entity_data, dict) else {}
        result = await executor.execute_manual(
            integration_name,
            mapping_name,
            data,
            entity_name=entity_name,
            entity_id=entity_id,
        )

        is_htmx = request.headers.get("HX-Request") == "true"
        if is_htmx:
            detail_url = f"/{slug}/{entity_id}"
            return Response(status_code=200, headers={"HX-Redirect": detail_url})

        return {
            "success": result.success,
            "message": result.message if hasattr(result, "message") else "",
            "mapped_fields": result.mapped_fields or {},
        }

    app.post(f"/{slug}/{{entity_id}}/integrations/{integration_name}/{mapping_name}")(handler)
    return app, executor


class TestIntegrationTriggerRedirect:
    """Test manual trigger returns HX-Redirect for htmx requests."""

    def test_htmx_request_returns_hx_redirect(self) -> None:
        """htmx POST returns HX-Redirect to detail page."""
        app, _executor = _make_minimal_app_with_trigger()
        client = TestClient(app)

        resp = client.post(
            f"/companies/{_TEST_UUID}/integrations/companies_house/fetch_company",
            headers={"HX-Request": "true"},
        )

        assert resp.status_code == 200
        assert resp.headers.get("HX-Redirect") == f"/companies/{_TEST_UUID}"

    def test_non_htmx_request_returns_json(self) -> None:
        """Regular POST returns JSON response."""
        app, _executor = _make_minimal_app_with_trigger()
        client = TestClient(app)

        resp = client.post(
            f"/companies/{_TEST_UUID}/integrations/companies_house/fetch_company",
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "mapped_fields" in data

    def test_htmx_redirect_uses_correct_slug(self) -> None:
        """Redirect URL uses the plural entity slug."""
        app, _ = _make_minimal_app_with_trigger(entity_name="Person")
        client = TestClient(app)

        resp = client.post(
            f"/people/{_TEST_UUID_2}/integrations/companies_house/fetch_company",
            headers={"HX-Request": "true"},
        )

        assert resp.headers.get("HX-Redirect") == f"/people/{_TEST_UUID_2}"
