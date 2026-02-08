"""Unit tests for exception handlers — JSON serialization of validation errors."""

from __future__ import annotations

import json
from typing import Annotated, Any
from unittest.mock import MagicMock

import pytest
from pydantic import AfterValidator, BaseModel, ValidationError


def _check_enum(v: str) -> str:
    if v not in ["low", "high"]:
        raise ValueError(f"Value '{v}' is not valid. Allowed: low, high")
    return v


class _FakeModel(BaseModel):
    priority: Annotated[str, AfterValidator(_check_enum)] = "low"


class TestValidationErrorHandler:
    """Test that validation_error_handler produces JSON-serializable responses."""

    @pytest.fixture
    def handler(self) -> Any:
        """Extract the validation_error_handler from register_exception_handlers."""
        from dazzle_back.runtime.exception_handlers import register_exception_handlers

        app = MagicMock()
        handlers: dict[type, Any] = {}

        def capture_handler(exc_class: type) -> Any:
            def decorator(fn: Any) -> Any:
                handlers[exc_class] = fn
                return fn

            return decorator

        app.exception_handler = capture_handler
        register_exception_handlers(app)
        return handlers[ValidationError]

    @pytest.mark.asyncio
    async def test_enum_validation_error_serializable(self, handler: Any) -> None:
        """ValueError from AfterValidator must not crash JSON serialization."""
        try:
            _FakeModel(priority="medium")
            pytest.fail("Should have raised ValidationError")
        except ValidationError as exc:
            response = await handler(MagicMock(), exc)

        assert response.status_code == 422
        body = json.loads(response.body)
        assert body["type"] == "validation_error"
        assert isinstance(body["detail"], list)
        assert len(body["detail"]) == 1
        err = body["detail"][0]
        assert err["type"] == "value_error"
        assert "priority" in err["loc"]
        # ctx.error should be a string, not a raw ValueError
        assert isinstance(err["ctx"]["error"], str)
        assert "Allowed: low, high" in err["ctx"]["error"]

    @pytest.mark.asyncio
    async def test_standard_validation_error_serializable(self, handler: Any) -> None:
        """Standard Pydantic required-field errors should also serialize cleanly."""

        class _Required(BaseModel):
            name: str

        try:
            _Required()  # type: ignore[call-arg]
            pytest.fail("Should have raised ValidationError")
        except ValidationError as exc:
            response = await handler(MagicMock(), exc)

        assert response.status_code == 422
        body = json.loads(response.body)
        assert body["type"] == "validation_error"
        assert len(body["detail"]) >= 1
        # Ensure the whole body is JSON-serializable (no crash)
        json.dumps(body)
