"""Tests for external API adapter interface and error normalization."""

from __future__ import annotations

from typing import Any

import pytest

from dazzle_back.graphql.adapters.base import (
    AdapterConfig,
    AdapterError,
    AdapterResponse,
    AdapterResult,
    ApiError,
    AuthenticationError,
    BaseExternalAdapter,
    PaginatedResponse,
    RateLimitConfig,
    RateLimitError,
    RetryConfig,
    TimeoutError,
    ValidationError,
)
from dazzle_back.graphql.adapters.errors import (
    ErrorCategory,
    ErrorSeverity,
    NormalizedError,
    normalize_error,
    normalize_hmrc_error,
)

# =============================================================================
# Test Configuration Classes
# =============================================================================


class TestRetryConfig:
    """Tests for RetryConfig."""

    def test_default_values(self) -> None:
        """Test default retry configuration."""
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.initial_delay == 1.0
        assert config.max_delay == 30.0
        assert config.exponential_base == 2.0
        assert 429 in config.retry_on
        assert 500 in config.retry_on

    def test_custom_values(self) -> None:
        """Test custom retry configuration."""
        config = RetryConfig(
            max_retries=5,
            initial_delay=0.5,
            max_delay=60.0,
            exponential_base=3.0,
            retry_on=frozenset({503}),
        )
        assert config.max_retries == 5
        assert config.initial_delay == 0.5
        assert config.max_delay == 60.0
        assert config.exponential_base == 3.0
        assert 503 in config.retry_on
        assert 429 not in config.retry_on

    def test_immutable(self) -> None:
        """Test retry config is frozen."""
        from dataclasses import FrozenInstanceError

        config = RetryConfig()
        with pytest.raises(FrozenInstanceError):
            config.max_retries = 10  # type: ignore


class TestRateLimitConfig:
    """Tests for RateLimitConfig."""

    def test_default_values(self) -> None:
        """Test default rate limit configuration."""
        config = RateLimitConfig()
        assert config.requests_per_second == 10.0
        assert config.burst_limit == 20

    def test_custom_values(self) -> None:
        """Test custom rate limit configuration."""
        config = RateLimitConfig(requests_per_second=5.0, burst_limit=10)
        assert config.requests_per_second == 5.0
        assert config.burst_limit == 10


class TestAdapterConfig:
    """Tests for AdapterConfig."""

    def test_required_fields(self) -> None:
        """Test adapter config with only required fields."""
        config = AdapterConfig(base_url="https://api.example.com")
        assert config.base_url == "https://api.example.com"
        assert config.timeout == 30.0
        assert config.auth_type == "bearer"
        assert isinstance(config.retry, RetryConfig)
        assert isinstance(config.rate_limit, RateLimitConfig)

    def test_all_fields(self) -> None:
        """Test adapter config with all fields."""
        config = AdapterConfig(
            base_url="https://api.example.com",
            timeout=60.0,
            retry=RetryConfig(max_retries=5),
            rate_limit=RateLimitConfig(requests_per_second=5.0),
            headers={"X-Custom": "header"},
            auth_type="api_key",
        )
        assert config.timeout == 60.0
        assert config.retry.max_retries == 5
        assert config.rate_limit.requests_per_second == 5.0
        assert config.headers["X-Custom"] == "header"
        assert config.auth_type == "api_key"


# =============================================================================
# Test Response Types
# =============================================================================


class TestAdapterResponse:
    """Tests for AdapterResponse."""

    def test_basic_response(self) -> None:
        """Test basic response creation."""
        response: AdapterResponse[dict[str, str]] = AdapterResponse(data={"key": "value"})
        assert response.data == {"key": "value"}
        assert response.status_code == 200
        assert response.latency_ms == 0.0

    def test_full_response(self) -> None:
        """Test response with all fields."""
        response = AdapterResponse(
            data={"result": "success"},
            raw_response=b'{"result": "success"}',
            status_code=201,
            headers={"Content-Type": "application/json"},
            latency_ms=123.45,
        )
        assert response.status_code == 201
        assert response.headers["Content-Type"] == "application/json"
        assert response.latency_ms == 123.45
        assert response.raw_response == b'{"result": "success"}'


class TestPaginatedResponse:
    """Tests for PaginatedResponse."""

    def test_basic_pagination(self) -> None:
        """Test basic paginated response."""
        response: PaginatedResponse[str] = PaginatedResponse(items=["a", "b", "c"])
        assert len(response.items) == 3
        assert response.page == 1
        assert response.page_size == 20
        assert response.has_next is False

    def test_full_pagination(self) -> None:
        """Test paginated response with all fields."""
        response = PaginatedResponse(
            items=[1, 2, 3],
            total=100,
            page=2,
            page_size=3,
            has_next=True,
            next_cursor="cursor-abc",
        )
        assert response.total == 100
        assert response.page == 2
        assert response.has_next is True
        assert response.next_cursor == "cursor-abc"


# =============================================================================
# Test Error Types
# =============================================================================


class TestAdapterError:
    """Tests for AdapterError and subclasses."""

    def test_basic_error(self) -> None:
        """Test basic adapter error."""
        error = AdapterError("Something went wrong")
        assert str(error) == "Something went wrong"
        assert error.service_name == "unknown"
        assert error.status_code is None

    def test_error_with_details(self) -> None:
        """Test error with all details."""
        error = AdapterError(
            "Request failed",
            service_name="hmrc",
            status_code=500,
            retry_after=30.0,
            details={"code": "SERVER_ERROR"},
        )
        assert "Request failed" in str(error)
        assert "500" in str(error)
        assert "[hmrc]" in str(error)
        assert error.retry_after == 30.0
        assert error.details["code"] == "SERVER_ERROR"

    def test_api_error(self) -> None:
        """Test ApiError."""
        error = ApiError("API returned error", status_code=400)
        assert isinstance(error, AdapterError)
        assert error.status_code == 400

    def test_authentication_error(self) -> None:
        """Test AuthenticationError."""
        error = AuthenticationError("Token expired", status_code=401)
        assert isinstance(error, AdapterError)
        assert error.status_code == 401

    def test_rate_limit_error(self) -> None:
        """Test RateLimitError."""
        error = RateLimitError("Rate limit exceeded", retry_after=60.0)
        assert isinstance(error, AdapterError)
        assert error.retry_after == 60.0

    def test_timeout_error(self) -> None:
        """Test TimeoutError."""
        error = TimeoutError("Request timed out")
        assert isinstance(error, AdapterError)

    def test_validation_error(self) -> None:
        """Test ValidationError."""
        error = ValidationError("Invalid input", details={"fields": {"vrn": ["Invalid format"]}})
        assert isinstance(error, AdapterError)
        assert "vrn" in error.details["fields"]


# =============================================================================
# Test AdapterResult
# =============================================================================


class TestAdapterResult:
    """Tests for AdapterResult result type."""

    def test_success_result(self) -> None:
        """Test successful result."""
        result = AdapterResult.success({"data": "value"})
        assert result.is_success
        assert not result.is_error
        assert result.data == {"data": "value"}

    def test_failure_result(self) -> None:
        """Test failed result."""
        error = ApiError("Failed")
        result: AdapterResult[dict[str, Any]] = AdapterResult.failure(error)
        assert result.is_error
        assert not result.is_success
        assert result.error is error

    def test_unwrap_success(self) -> None:
        """Test unwrap on success."""
        result = AdapterResult.success(42)
        assert result.unwrap() == 42

    def test_unwrap_failure(self) -> None:
        """Test unwrap on failure raises."""
        error = ApiError("Failed")
        result: AdapterResult[int] = AdapterResult.failure(error)
        with pytest.raises(ApiError):
            result.unwrap()

    def test_unwrap_or(self) -> None:
        """Test unwrap_or with default."""
        success = AdapterResult.success(42)
        assert success.unwrap_or(0) == 42

        failure: AdapterResult[int] = AdapterResult.failure(ApiError("Failed"))
        assert failure.unwrap_or(0) == 0

    def test_map_success(self) -> None:
        """Test map on success."""
        result = AdapterResult.success(10)
        mapped = result.map(lambda x: x * 2)
        assert mapped.data == 20

    def test_map_failure(self) -> None:
        """Test map on failure returns same error."""
        error = ApiError("Failed")
        result: AdapterResult[int] = AdapterResult.failure(error)
        mapped = result.map(lambda x: x * 2)
        assert mapped.is_error
        assert mapped.error is error

    def test_data_raises_on_failure(self) -> None:
        """Test accessing data on failure raises."""
        result: AdapterResult[int] = AdapterResult.failure(ApiError("Failed"))
        with pytest.raises(ValueError, match="No data available"):
            _ = result.data

    def test_error_raises_on_success(self) -> None:
        """Test accessing error on success raises."""
        result = AdapterResult.success(42)
        with pytest.raises(ValueError, match="No error"):
            _ = result.error


# =============================================================================
# Test NormalizedError
# =============================================================================


class TestNormalizedError:
    """Tests for NormalizedError."""

    def test_basic_error(self) -> None:
        """Test basic normalized error."""
        error = NormalizedError(
            code="TEST_ERROR",
            category=ErrorCategory.INTERNAL,
            severity=ErrorSeverity.ERROR,
            user_message="Something went wrong",
            developer_message="Detailed error info",
            service_name="test",
        )
        assert error.code == "TEST_ERROR"
        assert error.category == ErrorCategory.INTERNAL
        assert error.severity == ErrorSeverity.ERROR
        assert error.user_message == "Something went wrong"
        assert error.service_name == "test"

    def test_to_graphql_extensions(self) -> None:
        """Test converting to GraphQL extensions."""
        error = NormalizedError(
            code="AUTH_REQUIRED",
            category=ErrorCategory.AUTHENTICATION,
            severity=ErrorSeverity.WARNING,
            user_message="Please log in",
            developer_message="No auth token",
            service_name="api",
            status_code=401,
            retry_after=60.0,
            request_id="req-123",
            field_errors={"email": ["Invalid format"]},
        )
        extensions = error.to_graphql_extensions()

        assert extensions["code"] == "AUTH_REQUIRED"
        assert extensions["category"] == "authentication"
        assert extensions["service"] == "api"
        assert extensions["statusCode"] == 401
        assert extensions["retryAfter"] == 60.0
        assert extensions["requestId"] == "req-123"
        assert extensions["fieldErrors"]["email"] == ["Invalid format"]

    def test_to_log_dict(self) -> None:
        """Test converting to log dict."""
        error = NormalizedError(
            code="TEST_ERROR",
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.INFO,
            user_message="Invalid input",
            developer_message="Field validation failed",
            service_name="test",
        )
        log_dict = error.to_log_dict()

        assert log_dict["error_code"] == "TEST_ERROR"
        assert log_dict["category"] == "validation"
        assert log_dict["severity"] == "info"
        assert log_dict["service_name"] == "test"
        assert "timestamp" in log_dict


# =============================================================================
# Test Error Normalization
# =============================================================================


class TestNormalizeError:
    """Tests for normalize_error function."""

    def test_normalize_auth_error_401(self) -> None:
        """Test normalizing 401 authentication error."""
        error = AuthenticationError("Token expired", service_name="api", status_code=401)
        normalized = normalize_error(error)

        assert normalized.category == ErrorCategory.AUTHENTICATION
        assert "API_AUTHENTICATION_REQUIRED" in normalized.code
        assert "log in" in normalized.user_message.lower()

    def test_normalize_auth_error_403(self) -> None:
        """Test normalizing 403 authorization error."""
        error = AuthenticationError("Access denied", service_name="api", status_code=403)
        normalized = normalize_error(error)

        assert normalized.category == ErrorCategory.AUTHORIZATION
        assert "ACCESS_DENIED" in normalized.code
        assert "permission" in normalized.user_message.lower()

    def test_normalize_rate_limit_error(self) -> None:
        """Test normalizing rate limit error."""
        error = RateLimitError("Too many requests", service_name="api", retry_after=30.0)
        normalized = normalize_error(error)

        assert normalized.category == ErrorCategory.RATE_LIMIT
        assert normalized.retry_after == 30.0
        assert "30" in normalized.user_message

    def test_normalize_timeout_error(self) -> None:
        """Test normalizing timeout error."""
        error = TimeoutError("Request timed out", service_name="api")
        normalized = normalize_error(error)

        assert normalized.category == ErrorCategory.TIMEOUT
        assert "TIMEOUT" in normalized.code
        assert "too long" in normalized.user_message.lower()

    def test_normalize_validation_error(self) -> None:
        """Test normalizing validation error."""
        error = ValidationError(
            "Invalid input",
            service_name="api",
            details={"fields": {"email": ["Invalid format"]}},
        )
        normalized = normalize_error(error)

        assert normalized.category == ErrorCategory.VALIDATION
        assert normalized.severity == ErrorSeverity.INFO
        assert "email" in normalized.field_errors

    def test_normalize_api_error_404(self) -> None:
        """Test normalizing 404 error."""
        error = ApiError("Not found", service_name="api", status_code=404)
        normalized = normalize_error(error)

        assert normalized.category == ErrorCategory.NOT_FOUND
        assert "not found" in normalized.user_message.lower()

    def test_normalize_api_error_500(self) -> None:
        """Test normalizing 500 error."""
        error = ApiError("Server error", service_name="api", status_code=500)
        normalized = normalize_error(error)

        assert normalized.category == ErrorCategory.EXTERNAL_SERVICE
        assert normalized.severity == ErrorSeverity.ERROR

    def test_normalize_unknown_error(self) -> None:
        """Test normalizing unknown exception."""
        error = ValueError("Something unexpected")
        normalized = normalize_error(error, service_name="test")

        assert normalized.category == ErrorCategory.INTERNAL
        assert normalized.severity == ErrorSeverity.ERROR
        assert "unexpected" in normalized.user_message.lower()

    def test_normalize_with_request_id(self) -> None:
        """Test normalizing with request ID."""
        error = ApiError("Failed", service_name="api")
        normalized = normalize_error(error, request_id="req-123")

        assert normalized.request_id == "req-123"


class TestNormalizeHmrcError:
    """Tests for HMRC-specific error normalization."""

    def test_invalid_vrn(self) -> None:
        """Test normalizing HMRC INVALID_VRN error."""
        error = ApiError(
            "Invalid VRN",
            service_name="hmrc",
            status_code=400,
            details={"code": "INVALID_VRN"},
        )
        normalized = normalize_hmrc_error(error)

        assert normalized.code == "HMRC_INVALID_VRN"
        assert normalized.category == ErrorCategory.VALIDATION
        assert "Invalid VAT registration number" in normalized.user_message

    def test_vrn_not_found(self) -> None:
        """Test normalizing HMRC VRN_NOT_FOUND error."""
        error = ApiError(
            "VRN not found",
            service_name="hmrc",
            status_code=404,
            details={"code": "VRN_NOT_FOUND"},
        )
        normalized = normalize_hmrc_error(error)

        assert normalized.code == "HMRC_VRN_NOT_FOUND"
        assert normalized.category == ErrorCategory.NOT_FOUND

    def test_forbidden(self) -> None:
        """Test normalizing HMRC FORBIDDEN error."""
        error = ApiError(
            "Access denied",
            service_name="hmrc",
            status_code=403,
            details={"code": "FORBIDDEN"},
        )
        normalized = normalize_hmrc_error(error)

        assert normalized.code == "HMRC_FORBIDDEN"
        assert normalized.category == ErrorCategory.AUTHORIZATION

    def test_unknown_hmrc_code(self) -> None:
        """Test normalizing unknown HMRC error code."""
        error = ApiError(
            "Unknown error",
            service_name="hmrc",
            status_code=500,
            details={"code": "UNKNOWN_CODE", "message": "Custom message"},
        )
        normalized = normalize_hmrc_error(error)

        assert normalized.code == "HMRC_UNKNOWN_CODE"
        assert normalized.category == ErrorCategory.EXTERNAL_SERVICE
        assert "Custom message" in normalized.user_message

    def test_no_code(self) -> None:
        """Test normalizing HMRC error without code."""
        error = ApiError("Generic error", service_name="hmrc", status_code=500)
        normalized = normalize_hmrc_error(error)

        assert normalized.code == "HMRC_ERROR"
        assert normalized.category == ErrorCategory.EXTERNAL_SERVICE


# =============================================================================
# Test BaseExternalAdapter
# =============================================================================


class MockAdapter(BaseExternalAdapter[AdapterConfig]):
    """Mock adapter for testing."""

    @property
    def service_name(self) -> str:
        return "mock"


class TestBaseExternalAdapter:
    """Tests for BaseExternalAdapter."""

    def test_adapter_creation(self) -> None:
        """Test creating an adapter."""
        config = AdapterConfig(base_url="https://api.example.com")
        adapter = MockAdapter(config)

        assert adapter.service_name == "mock"
        assert adapter.config.base_url == "https://api.example.com"

    def test_calculate_retry_delay(self) -> None:
        """Test retry delay calculation."""
        config = AdapterConfig(
            base_url="https://api.example.com",
            retry=RetryConfig(initial_delay=1.0, exponential_base=2.0, max_delay=30.0),
        )
        adapter = MockAdapter(config)

        # First retry: 1.0 * 2^0 = 1.0
        assert adapter._calculate_retry_delay(0, config.retry) == 1.0

        # Second retry: 1.0 * 2^1 = 2.0
        assert adapter._calculate_retry_delay(1, config.retry) == 2.0

        # Third retry: 1.0 * 2^2 = 4.0
        assert adapter._calculate_retry_delay(2, config.retry) == 4.0

        # Max delay cap
        assert adapter._calculate_retry_delay(10, config.retry) == 30.0

    async def test_health_check_default(self) -> None:
        """Test default health check returns True."""
        config = AdapterConfig(base_url="https://api.example.com")
        adapter = MockAdapter(config)

        result = await adapter.health_check()
        assert result is True

    def test_process_response_success(self) -> None:
        """Test processing successful response."""
        config = AdapterConfig(base_url="https://api.example.com")
        adapter = MockAdapter(config)

        response = adapter._process_response(
            status_code=200,
            headers={"Content-Type": "application/json"},
            body=b'{"result": "success"}',
        )

        assert response.status_code == 200
        assert response.data == {"result": "success"}

    def test_process_response_401(self) -> None:
        """Test processing 401 response raises AuthenticationError."""
        config = AdapterConfig(base_url="https://api.example.com")
        adapter = MockAdapter(config)

        with pytest.raises(AuthenticationError) as exc:
            adapter._process_response(
                status_code=401,
                headers={},
                body=b'{"message": "Unauthorized"}',
            )
        assert exc.value.status_code == 401

    def test_process_response_403(self) -> None:
        """Test processing 403 response raises AuthenticationError."""
        config = AdapterConfig(base_url="https://api.example.com")
        adapter = MockAdapter(config)

        with pytest.raises(AuthenticationError) as exc:
            adapter._process_response(
                status_code=403,
                headers={},
                body=b'{"message": "Forbidden"}',
            )
        assert exc.value.status_code == 403

    def test_process_response_429(self) -> None:
        """Test processing 429 response raises RateLimitError."""
        config = AdapterConfig(base_url="https://api.example.com")
        adapter = MockAdapter(config)

        with pytest.raises(RateLimitError) as exc:
            adapter._process_response(
                status_code=429,
                headers={"Retry-After": "60"},
                body=b'{"message": "Rate limited"}',
            )
        assert exc.value.retry_after == 60.0

    def test_process_response_500(self) -> None:
        """Test processing 500 response raises ApiError."""
        config = AdapterConfig(base_url="https://api.example.com")
        adapter = MockAdapter(config)

        with pytest.raises(ApiError) as exc:
            adapter._process_response(
                status_code=500,
                headers={},
                body=b'{"message": "Internal error"}',
            )
        assert exc.value.status_code == 500

    def test_process_response_invalid_json(self) -> None:
        """Test processing response with invalid JSON."""
        config = AdapterConfig(base_url="https://api.example.com")
        adapter = MockAdapter(config)

        response = adapter._process_response(status_code=200, headers={}, body=b"not json")

        # Should still return a response with raw content
        assert "raw" in response.data
