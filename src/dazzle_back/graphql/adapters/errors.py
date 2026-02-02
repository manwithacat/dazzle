"""
Error normalization for external API responses.

Provides a unified error model that normalizes different error formats
from external APIs (HMRC, banks, Xero, etc.) into a consistent structure
for the GraphQL layer.

This enables:
- Consistent error messages for clients
- Structured error details for debugging
- Error categorization for handling logic
- Localized error messages

Example:
    try:
        result = await hmrc_adapter.get_vat_obligations(vrn)
    except AdapterError as e:
        normalized = normalize_error(e)
        raise GraphQLError(
            normalized.user_message,
            extensions=normalized.to_graphql_extensions(),
        )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dazzle_back.graphql.adapters.base import (
        AdapterError,
        ApiError,
        AuthenticationError,
        RateLimitError,
        TimeoutError,
        ValidationError,
    )


class ErrorCategory(Enum):
    """High-level error categories for routing and handling.

    These categories help determine how to handle errors:
    - AUTHENTICATION: Redirect to login, refresh token
    - AUTHORIZATION: Show forbidden message
    - VALIDATION: Show field-level errors
    - RATE_LIMIT: Implement backoff, show retry message
    - TIMEOUT: Retry or show timeout message
    - NOT_FOUND: Show 404-style message
    - EXTERNAL_SERVICE: Show service unavailable
    - INTERNAL: Log and show generic error
    """

    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    VALIDATION = "validation"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    NOT_FOUND = "not_found"
    EXTERNAL_SERVICE = "external_service"
    INTERNAL = "internal"


class ErrorSeverity(Enum):
    """Error severity for logging and alerting.

    - INFO: Expected errors (validation, not found)
    - WARNING: Recoverable errors (rate limits, timeouts)
    - ERROR: Unexpected errors that need attention
    - CRITICAL: System-level errors requiring immediate action
    """

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class NormalizedError:
    """Normalized error structure for GraphQL layer.

    Provides a consistent error format regardless of the source API,
    with both user-facing messages and developer details.

    Attributes:
        code: Machine-readable error code (e.g., "HMRC_VAT_INVALID_VRN")
        category: High-level error category
        severity: Error severity for logging
        user_message: Safe message to show to end users
        developer_message: Detailed message for debugging
        service_name: Name of the external service
        status_code: HTTP status code if applicable
        details: Structured error details
        timestamp: When the error occurred
        request_id: Request ID for tracing
        retry_after: Seconds until retry is allowed (for rate limits)
        field_errors: Field-level validation errors
    """

    code: str
    category: ErrorCategory
    severity: ErrorSeverity
    user_message: str
    developer_message: str
    service_name: str
    status_code: int | None = None
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    request_id: str | None = None
    retry_after: float | None = None
    field_errors: dict[str, list[str]] = field(default_factory=dict)

    def to_graphql_extensions(self) -> dict[str, Any]:
        """Convert to GraphQL error extensions.

        Returns a dict suitable for use as GraphQL error extensions,
        providing structured error info to clients.

        Returns:
            Dict with error details for GraphQL extensions
        """
        extensions: dict[str, Any] = {
            "code": self.code,
            "category": self.category.value,
            "service": self.service_name,
        }

        if self.status_code:
            extensions["statusCode"] = self.status_code

        if self.retry_after:
            extensions["retryAfter"] = self.retry_after

        if self.field_errors:
            extensions["fieldErrors"] = self.field_errors

        if self.request_id:
            extensions["requestId"] = self.request_id

        return extensions

    def to_log_dict(self) -> dict[str, Any]:
        """Convert to dict for structured logging.

        Returns:
            Dict with all error details for logging
        """
        return {
            "error_code": self.code,
            "category": self.category.value,
            "severity": self.severity.value,
            "user_message": self.user_message,
            "developer_message": self.developer_message,
            "service_name": self.service_name,
            "status_code": self.status_code,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
            "request_id": self.request_id,
            "retry_after": self.retry_after,
            "field_errors": self.field_errors,
        }


# =============================================================================
# Error Normalization Functions
# =============================================================================


def normalize_error(
    error: Exception,
    *,
    service_name: str | None = None,
    request_id: str | None = None,
) -> NormalizedError:
    """Normalize any exception to a NormalizedError.

    This function handles:
    - AdapterError and its subclasses
    - Standard exceptions
    - Unknown exceptions

    Args:
        error: The exception to normalize
        service_name: Override service name
        request_id: Request ID for tracing

    Returns:
        NormalizedError with consistent structure
    """
    from dazzle_back.graphql.adapters.base import (
        AdapterError,
        ApiError,
        AuthenticationError,
        RateLimitError,
        TimeoutError,
        ValidationError,
    )

    # Handle AdapterError subclasses
    if isinstance(error, AuthenticationError):
        return _normalize_auth_error(error, service_name, request_id)
    elif isinstance(error, RateLimitError):
        return _normalize_rate_limit_error(error, service_name, request_id)
    elif isinstance(error, TimeoutError):
        return _normalize_timeout_error(error, service_name, request_id)
    elif isinstance(error, ValidationError):
        return _normalize_validation_error(error, service_name, request_id)
    elif isinstance(error, ApiError):
        return _normalize_api_error(error, service_name, request_id)
    elif isinstance(error, AdapterError):
        return _normalize_adapter_error(error, service_name, request_id)
    else:
        return _normalize_unknown_error(error, service_name, request_id)


def _normalize_auth_error(
    error: AuthenticationError,
    service_name: str | None,
    request_id: str | None,
) -> NormalizedError:
    """Normalize authentication errors."""

    svc = service_name or error.service_name
    status = error.status_code or 401

    if status == 401:
        code = f"{svc.upper()}_AUTHENTICATION_REQUIRED"
        user_msg = "Authentication required. Please log in and try again."
        category = ErrorCategory.AUTHENTICATION
    else:
        code = f"{svc.upper()}_ACCESS_DENIED"
        user_msg = "You don't have permission to access this resource."
        category = ErrorCategory.AUTHORIZATION

    return NormalizedError(
        code=code,
        category=category,
        severity=ErrorSeverity.WARNING,
        user_message=user_msg,
        developer_message=str(error),
        service_name=svc,
        status_code=status,
        details=error.details,
        request_id=request_id,
    )


def _normalize_rate_limit_error(
    error: RateLimitError,
    service_name: str | None,
    request_id: str | None,
) -> NormalizedError:
    """Normalize rate limit errors."""

    svc = service_name or error.service_name

    if error.retry_after:
        user_msg = f"Too many requests. Please try again in {int(error.retry_after)} seconds."
    else:
        user_msg = "Too many requests. Please try again later."

    return NormalizedError(
        code=f"{svc.upper()}_RATE_LIMIT_EXCEEDED",
        category=ErrorCategory.RATE_LIMIT,
        severity=ErrorSeverity.WARNING,
        user_message=user_msg,
        developer_message=str(error),
        service_name=svc,
        status_code=429,
        details=error.details,
        request_id=request_id,
        retry_after=error.retry_after,
    )


def _normalize_timeout_error(
    error: TimeoutError,
    service_name: str | None,
    request_id: str | None,
) -> NormalizedError:
    """Normalize timeout errors."""

    svc = service_name or error.service_name

    return NormalizedError(
        code=f"{svc.upper()}_TIMEOUT",
        category=ErrorCategory.TIMEOUT,
        severity=ErrorSeverity.WARNING,
        user_message=f"The {svc} service is taking too long to respond. Please try again.",
        developer_message=str(error),
        service_name=svc,
        status_code=504,
        details=error.details,
        request_id=request_id,
    )


def _normalize_validation_error(
    error: ValidationError,
    service_name: str | None,
    request_id: str | None,
) -> NormalizedError:
    """Normalize validation errors."""

    svc = service_name or error.service_name

    # Extract field errors if present
    field_errors: dict[str, list[str]] = {}
    if "fields" in error.details:
        for field_name, messages in error.details["fields"].items():
            if isinstance(messages, list):
                field_errors[field_name] = messages
            else:
                field_errors[field_name] = [str(messages)]

    return NormalizedError(
        code=f"{svc.upper()}_VALIDATION_ERROR",
        category=ErrorCategory.VALIDATION,
        severity=ErrorSeverity.INFO,
        user_message="Please check your input and try again.",
        developer_message=str(error),
        service_name=svc,
        status_code=400,
        details=error.details,
        request_id=request_id,
        field_errors=field_errors,
    )


def _normalize_api_error(
    error: ApiError,
    service_name: str | None,
    request_id: str | None,
) -> NormalizedError:
    """Normalize general API errors."""

    svc = service_name or error.service_name
    status = error.status_code or 500

    # Determine category and severity based on status
    if status == 404:
        category = ErrorCategory.NOT_FOUND
        severity = ErrorSeverity.INFO
        user_msg = "The requested resource was not found."
        code = f"{svc.upper()}_NOT_FOUND"
    elif 400 <= status < 500:
        category = ErrorCategory.EXTERNAL_SERVICE
        severity = ErrorSeverity.WARNING
        user_msg = f"The {svc} service returned an error. Please try again."
        code = f"{svc.upper()}_CLIENT_ERROR"
    else:
        category = ErrorCategory.EXTERNAL_SERVICE
        severity = ErrorSeverity.ERROR
        user_msg = f"The {svc} service is temporarily unavailable. Please try again later."
        code = f"{svc.upper()}_SERVER_ERROR"

    return NormalizedError(
        code=code,
        category=category,
        severity=severity,
        user_message=user_msg,
        developer_message=str(error),
        service_name=svc,
        status_code=status,
        details=error.details,
        request_id=request_id,
    )


def _normalize_adapter_error(
    error: AdapterError,
    service_name: str | None,
    request_id: str | None,
) -> NormalizedError:
    """Normalize generic adapter errors."""

    svc = service_name or error.service_name

    return NormalizedError(
        code=f"{svc.upper()}_ERROR",
        category=ErrorCategory.EXTERNAL_SERVICE,
        severity=ErrorSeverity.ERROR,
        user_message=f"An error occurred with the {svc} service. Please try again.",
        developer_message=str(error),
        service_name=svc,
        status_code=error.status_code,
        details=error.details,
        request_id=request_id,
        retry_after=error.retry_after,
    )


def _normalize_unknown_error(
    error: Exception,
    service_name: str | None,
    request_id: str | None,
) -> NormalizedError:
    """Normalize unknown exceptions."""
    svc = service_name or "unknown"

    return NormalizedError(
        code=f"{svc.upper()}_INTERNAL_ERROR",
        category=ErrorCategory.INTERNAL,
        severity=ErrorSeverity.ERROR,
        user_message="An unexpected error occurred. Please try again.",
        developer_message=f"{type(error).__name__}: {error}",
        service_name=svc,
        status_code=500,
        details={"exception_type": type(error).__name__},
        request_id=request_id,
    )


# =============================================================================
# Service-Specific Error Mapping
# =============================================================================


# HMRC error code mappings
HMRC_ERROR_CODES: dict[str, tuple[str, ErrorCategory]] = {
    "INVALID_VRN": ("Invalid VAT registration number", ErrorCategory.VALIDATION),
    "VRN_NOT_FOUND": ("VAT registration not found", ErrorCategory.NOT_FOUND),
    "DATE_RANGE_TOO_LARGE": ("Date range exceeds allowed limit", ErrorCategory.VALIDATION),
    "FORBIDDEN": ("Access denied to this VAT registration", ErrorCategory.AUTHORIZATION),
    "NOT_SIGNED_UP_TO_MTD": ("Not enrolled for Making Tax Digital", ErrorCategory.VALIDATION),
    "INVALID_DATE_FROM": ("Invalid 'from' date", ErrorCategory.VALIDATION),
    "INVALID_DATE_TO": ("Invalid 'to' date", ErrorCategory.VALIDATION),
    "INVALID_DATE_RANGE": ("Invalid date range", ErrorCategory.VALIDATION),
    "INVALID_STATUS": ("Invalid obligation status", ErrorCategory.VALIDATION),
}


def normalize_hmrc_error(
    error: ApiError,
    request_id: str | None = None,
) -> NormalizedError:
    """Normalize HMRC-specific error responses.

    HMRC returns errors in a specific format:
    {
        "code": "INVALID_VRN",
        "message": "The provided VRN is invalid"
    }

    Args:
        error: The ApiError from HMRC
        request_id: Request ID for tracing

    Returns:
        NormalizedError with HMRC-specific handling
    """

    details = error.details or {}
    hmrc_code = details.get("code", "")

    if hmrc_code in HMRC_ERROR_CODES:
        user_msg, category = HMRC_ERROR_CODES[hmrc_code]
        severity = (
            ErrorSeverity.INFO if category == ErrorCategory.VALIDATION else ErrorSeverity.WARNING
        )
    else:
        user_msg = details.get("message", "An error occurred with HMRC")
        category = ErrorCategory.EXTERNAL_SERVICE
        severity = ErrorSeverity.ERROR

    return NormalizedError(
        code=f"HMRC_{hmrc_code}" if hmrc_code else "HMRC_ERROR",
        category=category,
        severity=severity,
        user_message=user_msg,
        developer_message=str(error),
        service_name="hmrc",
        status_code=error.status_code,
        details=details,
        request_id=request_id,
    )


__all__ = [
    "ErrorCategory",
    "ErrorSeverity",
    "NormalizedError",
    "normalize_error",
    "normalize_hmrc_error",
]
