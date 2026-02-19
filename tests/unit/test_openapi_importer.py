"""Tests for OpenAPI to pack TOML importer."""

from __future__ import annotations

from dazzle.api_kb.openapi_importer import import_from_openapi, scaffold_blank


def test_scaffold_blank_basic() -> None:
    """scaffold_blank generates valid TOML template."""
    result = scaffold_blank("Acme", "payments", "acme_payments")

    assert "[pack]" in result
    assert 'name = "acme_payments"' in result
    assert 'provider = "Acme"' in result
    assert 'category = "payments"' in result
    assert "ACME_API_KEY" in result


def test_scaffold_blank_has_sections() -> None:
    """scaffold_blank includes all expected sections."""
    result = scaffold_blank("Test", "api", "test_api")

    assert "[pack]" in result
    assert "[auth]" in result
    assert "[env_vars]" in result
    # Operations and models are commented out
    assert "# [operations]" in result
    assert "# [foreign_models" in result


def test_import_from_openapi_minimal() -> None:
    """import_from_openapi handles minimal spec."""
    spec = {
        "openapi": "3.0.0",
        "info": {
            "title": "Pet Store",
            "version": "1.0.0",
            "description": "A pet store API",
        },
        "servers": [{"url": "https://api.petstore.io/v1"}],
        "paths": {},
    }

    result = import_from_openapi(spec)

    assert "[pack]" in result
    assert 'provider = "Pet Store"' in result
    assert 'base_url = "https://api.petstore.io/v1"' in result
    assert 'version = "1.0.0"' in result


def test_import_from_openapi_operations() -> None:
    """import_from_openapi extracts operations from paths."""
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "TestAPI", "version": "1.0"},
        "paths": {
            "/pets": {
                "get": {
                    "operationId": "listPets",
                    "summary": "List all pets",
                },
                "post": {
                    "operationId": "createPet",
                    "summary": "Create a pet",
                },
            },
        },
    }

    result = import_from_openapi(spec)

    assert "[operations]" in result
    assert "list_pets" in result
    assert "create_pet" in result
    assert 'method = "GET"' in result
    assert 'method = "POST"' in result


def test_import_from_openapi_schemas() -> None:
    """import_from_openapi extracts foreign models from schemas."""
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "TestAPI", "version": "1.0"},
        "paths": {},
        "components": {
            "schemas": {
                "Pet": {
                    "type": "object",
                    "required": ["name"],
                    "description": "A pet in the store",
                    "properties": {
                        "id": {"type": "integer"},
                        "name": {"type": "string", "maxLength": 100},
                        "status": {"type": "string"},
                    },
                },
            },
        },
    }

    result = import_from_openapi(spec)

    assert "[foreign_models.Pet]" in result
    assert 'description = "A pet in the store"' in result
    assert "[foreign_models.Pet.fields]" in result
    assert 'type = "int"' in result
    assert 'type = "str(100)"' in result


def test_import_from_openapi_api_key_auth() -> None:
    """import_from_openapi extracts API key auth."""
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "TestAPI", "version": "1.0"},
        "paths": {},
        "components": {
            "securitySchemes": {
                "apiKey": {
                    "type": "apiKey",
                    "name": "X-API-Key",
                    "in": "header",
                },
            },
        },
    }

    result = import_from_openapi(spec)

    assert "[auth]" in result
    assert 'type = "api_key"' in result
    assert 'header = "X-API-Key"' in result


def test_import_from_openapi_bearer_auth() -> None:
    """import_from_openapi extracts bearer auth."""
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "TestAPI", "version": "1.0"},
        "paths": {},
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                },
            },
        },
    }

    result = import_from_openapi(spec)

    assert 'type = "bearer"' in result
