"""
Base external API adapter interface.

Provides a unified interface for wrapping external REST APIs (HMRC, banks,
accounting platforms, etc.) for use in the GraphQL BFF layer.

The adapter pattern handles:
- Authentication (OAuth, API keys, etc.)
- Rate limiting and throttling
- Retry logic with exponential backoff
- Response normalization
- Error handling and mapping

Example:
    class HmrcAdapter(BaseExternalAdapter[HmrcConfig]):
        \"\"\"Adapter for HMRC VAT API.\"\"\"

        @property
        def service_name(self) -> str:
            return "hmrc"

        async def get_vat_obligations(
            self, vrn: str, *, ctx: GraphQLContext
        ) -> AdapterResult[list[VatObligation]]:
            return await self._get(
                f"/organisations/vat/{vrn}/obligations",
                response_type=list[VatObligation],
            )
"""

from __future__ import annotations

import asyncio
import builtins
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Generic, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable

    from dazzle_dnr_back.graphql.context import GraphQLContext

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================


@dataclass(frozen=True)
class RetryConfig:
    """Configuration for retry behavior.

    Attributes:
        max_retries: Maximum number of retry attempts (default: 3)
        initial_delay: Initial delay between retries in seconds (default: 1.0)
        max_delay: Maximum delay between retries in seconds (default: 30.0)
        exponential_base: Base for exponential backoff (default: 2.0)
        retry_on: HTTP status codes that should trigger a retry
    """

    max_retries: int = 3
    initial_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0
    retry_on: frozenset[int] = field(default_factory=lambda: frozenset({429, 500, 502, 503, 504}))


@dataclass(frozen=True)
class RateLimitConfig:
    """Configuration for rate limiting.

    Attributes:
        requests_per_second: Maximum requests per second (default: 10)
        burst_limit: Maximum burst size (default: 20)
    """

    requests_per_second: float = 10.0
    burst_limit: int = 20


@dataclass
class AdapterConfig:
    """Base configuration for external API adapters.

    Attributes:
        base_url: Base URL for the API
        timeout: Request timeout in seconds
        retry: Retry configuration
        rate_limit: Rate limit configuration
        headers: Default headers to include in all requests
        auth_type: Authentication type (api_key, oauth, bearer, none)
    """

    base_url: str
    timeout: float = 30.0
    retry: RetryConfig = field(default_factory=RetryConfig)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    headers: dict[str, str] = field(default_factory=dict)
    auth_type: str = "bearer"


# Type variable for adapter configuration
ConfigT = TypeVar("ConfigT", bound=AdapterConfig)

# Type variable for response data
T = TypeVar("T")


# =============================================================================
# Response Types
# =============================================================================


@dataclass
class AdapterResponse(Generic[T]):
    """Successful response from an external API.

    Attributes:
        data: The parsed response data
        raw_response: Raw response body (for debugging)
        status_code: HTTP status code
        headers: Response headers
        latency_ms: Request latency in milliseconds
    """

    data: T
    raw_response: bytes | None = None
    status_code: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    latency_ms: float = 0.0


@dataclass
class PaginatedResponse(Generic[T]):
    """Paginated response from an external API.

    Attributes:
        items: List of items on this page
        total: Total number of items (if known)
        page: Current page number (1-indexed)
        page_size: Number of items per page
        has_next: Whether there are more pages
        next_cursor: Cursor for next page (for cursor-based pagination)
    """

    items: list[T]
    total: int | None = None
    page: int = 1
    page_size: int = 20
    has_next: bool = False
    next_cursor: str | None = None


# =============================================================================
# Error Types
# =============================================================================


class AdapterError(Exception):
    """Base exception for adapter errors.

    All adapter errors should inherit from this class to enable
    unified error handling in the GraphQL layer.
    """

    def __init__(
        self,
        message: str,
        *,
        service_name: str = "unknown",
        status_code: int | None = None,
        retry_after: float | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.service_name = service_name
        self.status_code = status_code
        self.retry_after = retry_after
        self.details = details or {}

    def __str__(self) -> str:
        parts = [self.args[0]]
        if self.status_code:
            parts.append(f"(status: {self.status_code})")
        if self.service_name != "unknown":
            parts.append(f"[{self.service_name}]")
        return " ".join(parts)


class ApiError(AdapterError):
    """Error returned by the external API.

    Represents errors like 4xx/5xx responses with error bodies.
    """

    pass


class AuthenticationError(AdapterError):
    """Authentication or authorization failure.

    Represents 401/403 errors or token expiration.
    """

    pass


class RateLimitError(AdapterError):
    """Rate limit exceeded.

    The `retry_after` attribute indicates when to retry.
    """

    pass


class TimeoutError(AdapterError):
    """Request timed out."""

    pass


class ValidationError(AdapterError):
    """Request validation failed.

    Used when the adapter detects invalid input before
    making the external request.
    """

    pass


# =============================================================================
# Result Type
# =============================================================================


class AdapterResultStatus(Enum):
    """Status of an adapter operation."""

    SUCCESS = "success"
    ERROR = "error"


@dataclass
class AdapterResult(Generic[T]):
    """Result of an adapter operation.

    Uses a Result pattern to represent success or failure without
    raising exceptions. This allows callers to handle errors explicitly.

    Example:
        result = await adapter.get_vat_obligations(vrn)
        if result.is_success:
            obligations = result.data
        else:
            logger.error(f"Failed: {result.error}")
    """

    status: AdapterResultStatus
    _data: T | None = None
    _error: AdapterError | None = None
    _response: AdapterResponse[T] | None = None

    @property
    def is_success(self) -> bool:
        """Check if the operation succeeded."""
        return self.status == AdapterResultStatus.SUCCESS

    @property
    def is_error(self) -> bool:
        """Check if the operation failed."""
        return self.status == AdapterResultStatus.ERROR

    @property
    def data(self) -> T:
        """Get the result data. Raises if operation failed."""
        if self._data is None:
            raise ValueError("No data available - operation failed")
        return self._data

    @property
    def error(self) -> AdapterError:
        """Get the error. Raises if operation succeeded."""
        if self._error is None:
            raise ValueError("No error - operation succeeded")
        return self._error

    @property
    def response(self) -> AdapterResponse[T] | None:
        """Get the full response if available."""
        return self._response

    @classmethod
    def success(cls, data: T, response: AdapterResponse[T] | None = None) -> AdapterResult[T]:
        """Create a successful result."""
        return cls(
            status=AdapterResultStatus.SUCCESS,
            _data=data,
            _response=response,
        )

    @classmethod
    def failure(cls, error: AdapterError) -> AdapterResult[T]:
        """Create a failed result."""
        return cls(
            status=AdapterResultStatus.ERROR,
            _error=error,
        )

    def unwrap(self) -> T:
        """Unwrap the result, raising the error if failed."""
        if self.is_error:
            raise self.error
        return self.data

    def unwrap_or(self, default: T) -> T:
        """Unwrap the result, returning default if failed."""
        if self.is_error:
            return default
        return self.data

    def map(self, fn: Callable[[T], T]) -> AdapterResult[T]:
        """Map over the success value."""
        if self.is_success:
            return AdapterResult.success(fn(self.data))
        return self  # type: ignore


# =============================================================================
# Base Adapter
# =============================================================================


class BaseExternalAdapter(ABC, Generic[ConfigT]):
    """Base class for external API adapters.

    Subclasses should implement:
    - service_name property
    - API-specific methods using _get, _post, etc.

    The base class provides:
    - Retry logic with exponential backoff
    - Rate limiting
    - Error handling and normalization
    - Request/response logging

    Example:
        class HmrcAdapter(BaseExternalAdapter[HmrcConfig]):
            @property
            def service_name(self) -> str:
                return "hmrc"

            async def get_vat_obligations(self, vrn: str) -> AdapterResult[list]:
                return await self._get(f"/vat/{vrn}/obligations")
    """

    def __init__(self, config: ConfigT) -> None:
        """Initialize the adapter with configuration.

        Args:
            config: Adapter-specific configuration
        """
        self.config = config
        self._last_request_time: float = 0.0
        self._request_count: int = 0

    @property
    @abstractmethod
    def service_name(self) -> str:
        """Name of the external service (for logging and errors)."""
        ...

    # -------------------------------------------------------------------------
    # HTTP Methods
    # -------------------------------------------------------------------------

    async def _get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        ctx: GraphQLContext | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Make a GET request to the external API.

        Args:
            path: API endpoint path (appended to base_url)
            params: Query parameters
            headers: Additional headers
            ctx: GraphQL context (for tenant/user info)

        Returns:
            AdapterResult with parsed JSON response or error
        """
        return await self._request("GET", path, params=params, headers=headers, ctx=ctx)

    async def _post(
        self,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        data: bytes | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        ctx: GraphQLContext | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Make a POST request to the external API.

        Args:
            path: API endpoint path
            json: JSON body (will be serialized)
            data: Raw body data
            params: Query parameters
            headers: Additional headers
            ctx: GraphQL context

        Returns:
            AdapterResult with parsed JSON response or error
        """
        return await self._request(
            "POST", path, json=json, data=data, params=params, headers=headers, ctx=ctx
        )

    async def _put(
        self,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        data: bytes | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        ctx: GraphQLContext | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Make a PUT request to the external API."""
        return await self._request(
            "PUT", path, json=json, data=data, params=params, headers=headers, ctx=ctx
        )

    async def _delete(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        ctx: GraphQLContext | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Make a DELETE request to the external API."""
        return await self._request("DELETE", path, params=params, headers=headers, ctx=ctx)

    async def _patch(
        self,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        data: bytes | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        ctx: GraphQLContext | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Make a PATCH request to the external API."""
        return await self._request(
            "PATCH", path, json=json, data=data, params=params, headers=headers, ctx=ctx
        )

    # -------------------------------------------------------------------------
    # Core Request Logic
    # -------------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        data: bytes | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        ctx: GraphQLContext | None = None,
    ) -> AdapterResult[dict[str, Any]]:
        """Make an HTTP request with retry and rate limiting.

        This is the core request method that handles:
        - Rate limiting
        - Retry with exponential backoff
        - Error mapping
        - Logging

        Args:
            method: HTTP method
            path: API endpoint path
            json: JSON body
            data: Raw body
            params: Query parameters
            headers: Additional headers
            ctx: GraphQL context

        Returns:
            AdapterResult with response or error
        """
        # Apply rate limiting
        await self._apply_rate_limit()

        # Build URL
        url = f"{self.config.base_url.rstrip('/')}/{path.lstrip('/')}"

        # Build headers
        request_headers = dict(self.config.headers)
        if headers:
            request_headers.update(headers)

        # Add authentication
        auth_header = await self._get_auth_header(ctx)
        if auth_header:
            request_headers.update(auth_header)

        # Retry loop
        retry_config = self.config.retry
        last_error: AdapterError | None = None

        for attempt in range(retry_config.max_retries + 1):
            try:
                start_time = time.monotonic()
                response = await self._make_http_request(
                    method=method,
                    url=url,
                    json_body=json,
                    data=data,
                    params=params,
                    headers=request_headers,
                )
                latency_ms = (time.monotonic() - start_time) * 1000

                # Log successful request
                logger.debug(
                    f"[{self.service_name}] {method} {path} -> {response.status_code} "
                    f"({latency_ms:.1f}ms)"
                )

                return AdapterResult.success(
                    response.data,
                    response=AdapterResponse(
                        data=response.data,
                        status_code=response.status_code,
                        headers=response.headers,
                        latency_ms=latency_ms,
                    ),
                )

            except AdapterError as e:
                last_error = e
                e.service_name = self.service_name

                # Check if we should retry
                if isinstance(e, RateLimitError | TimeoutError):
                    should_retry = attempt < retry_config.max_retries
                elif e.status_code and e.status_code in retry_config.retry_on:
                    should_retry = attempt < retry_config.max_retries
                else:
                    # Don't retry auth errors or validation errors
                    should_retry = False

                if should_retry:
                    delay = self._calculate_retry_delay(attempt, retry_config)
                    if isinstance(e, RateLimitError) and e.retry_after:
                        delay = max(delay, e.retry_after)

                    logger.warning(
                        f"[{self.service_name}] {method} {path} failed "
                        f"(attempt {attempt + 1}), retrying in {delay:.1f}s: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"[{self.service_name}] {method} {path} failed: {e}")
                    return AdapterResult.failure(e)

        # All retries exhausted
        if last_error:
            return AdapterResult.failure(last_error)

        return AdapterResult.failure(
            ApiError("Request failed after retries", service_name=self.service_name)
        )

    async def _make_http_request(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
        data: bytes | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> AdapterResponse[dict[str, Any]]:
        """Actually make the HTTP request.

        This method should be overridden by subclasses that need
        custom HTTP client behavior. The default implementation
        uses httpx if available, falling back to urllib.

        Args:
            method: HTTP method
            url: Full URL
            json_body: JSON body
            data: Raw body
            params: Query parameters
            headers: Headers

        Returns:
            AdapterResponse with parsed data

        Raises:
            AdapterError: On HTTP or parsing errors
        """
        import importlib.util

        # Try to use httpx for async support
        if importlib.util.find_spec("httpx") is not None:
            return await self._make_httpx_request(
                method, url, json_body=json_body, data=data, params=params, headers=headers
            )

        # Fallback to aiohttp
        if importlib.util.find_spec("aiohttp") is not None:
            return await self._make_aiohttp_request(
                method, url, json_body=json_body, data=data, params=params, headers=headers
            )

        # Final fallback to urllib (sync, wrapped in executor)
        return await self._make_urllib_request(
            method, url, json_body=json_body, data=data, params=params, headers=headers
        )

    async def _make_httpx_request(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
        data: bytes | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> AdapterResponse[dict[str, Any]]:
        """Make request using httpx."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.request(
                    method,
                    url,
                    json=json_body,
                    content=data,
                    params=params,
                    headers=headers,
                )

                return self._process_response(
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    body=response.content,
                )

        except httpx.TimeoutException as e:
            raise TimeoutError(
                f"Request timed out after {self.config.timeout}s",
                service_name=self.service_name,
            ) from e
        except httpx.RequestError as e:
            raise ApiError(
                f"Request failed: {e}",
                service_name=self.service_name,
            ) from e

    async def _make_aiohttp_request(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
        data: bytes | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> AdapterResponse[dict[str, Any]]:
        """Make request using aiohttp."""
        import aiohttp

        try:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(
                    method,
                    url,
                    json=json_body,
                    data=data,
                    params=params,
                    headers=headers,
                ) as response:
                    body = await response.read()
                    return self._process_response(
                        status_code=response.status,
                        headers=dict(response.headers),
                        body=body,
                    )

        except builtins.TimeoutError as e:
            raise TimeoutError(
                f"Request timed out after {self.config.timeout}s",
                service_name=self.service_name,
            ) from e
        except aiohttp.ClientError as e:
            raise ApiError(
                f"Request failed: {e}",
                service_name=self.service_name,
            ) from e

    async def _make_urllib_request(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
        data: bytes | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> AdapterResponse[dict[str, Any]]:
        """Make request using urllib (sync fallback)."""
        import json as json_module
        import urllib.error
        import urllib.parse
        import urllib.request

        # Build URL with params
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"

        # Build request body
        body_data: bytes | None = None
        if json_body:
            body_data = json_module.dumps(json_body).encode()
            headers = headers or {}
            headers["Content-Type"] = "application/json"
        elif data:
            body_data = data

        # Create request
        request = urllib.request.Request(
            url,
            data=body_data,
            headers=headers or {},
            method=method,
        )

        # Execute in thread pool
        loop = asyncio.get_event_loop()
        try:

            def do_request() -> tuple[int, dict[str, str], bytes]:
                try:
                    with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
                        return (
                            response.status,
                            dict(response.headers),
                            response.read(),
                        )
                except urllib.error.HTTPError as e:
                    return (e.code, dict(e.headers), e.read())

            status, resp_headers, body = await loop.run_in_executor(None, do_request)
            return self._process_response(
                status_code=status,
                headers=resp_headers,
                body=body,
            )

        except TimeoutError as e:
            raise TimeoutError(
                f"Request timed out after {self.config.timeout}s",
                service_name=self.service_name,
            ) from e

    def _process_response(
        self,
        *,
        status_code: int,
        headers: dict[str, str],
        body: bytes,
    ) -> AdapterResponse[dict[str, Any]]:
        """Process HTTP response and handle errors.

        Args:
            status_code: HTTP status code
            headers: Response headers
            body: Response body

        Returns:
            AdapterResponse with parsed data

        Raises:
            AdapterError: On error status codes
        """
        import json as json_module

        # Parse JSON body
        try:
            data = json_module.loads(body) if body else {}
        except json_module.JSONDecodeError:
            data = {"raw": body.decode(errors="replace")}

        # Handle error status codes
        if status_code == 401:
            raise AuthenticationError(
                data.get("message", "Authentication required"),
                status_code=status_code,
                details=data,
            )
        elif status_code == 403:
            raise AuthenticationError(
                data.get("message", "Access denied"),
                status_code=status_code,
                details=data,
            )
        elif status_code == 429:
            retry_after = None
            if "Retry-After" in headers:
                try:
                    retry_after = float(headers["Retry-After"])
                except ValueError:
                    pass
            raise RateLimitError(
                data.get("message", "Rate limit exceeded"),
                status_code=status_code,
                retry_after=retry_after,
                details=data,
            )
        elif status_code >= 400:
            raise ApiError(
                data.get("message", f"API error: {status_code}"),
                status_code=status_code,
                details=data,
            )

        return AdapterResponse(
            data=data,
            raw_response=body,
            status_code=status_code,
            headers=headers,
        )

    # -------------------------------------------------------------------------
    # Rate Limiting
    # -------------------------------------------------------------------------

    async def _apply_rate_limit(self) -> None:
        """Apply rate limiting before making a request."""
        rate_limit = self.config.rate_limit
        min_interval = 1.0 / rate_limit.requests_per_second

        now = time.monotonic()
        elapsed = now - self._last_request_time

        if elapsed < min_interval:
            await asyncio.sleep(min_interval - elapsed)

        self._last_request_time = time.monotonic()

    def _calculate_retry_delay(self, attempt: int, config: RetryConfig) -> float:
        """Calculate delay for retry with exponential backoff."""
        delay = config.initial_delay * (config.exponential_base**attempt)
        return min(delay, config.max_delay)

    # -------------------------------------------------------------------------
    # Authentication
    # -------------------------------------------------------------------------

    async def _get_auth_header(self, ctx: GraphQLContext | None) -> dict[str, str] | None:
        """Get authentication header for requests.

        Override this method to implement custom authentication.
        The default implementation supports bearer tokens from context.

        Args:
            ctx: GraphQL context

        Returns:
            Dict with Authorization header or None
        """
        if self.config.auth_type == "none":
            return None

        # Default: look for token in context
        if ctx and ctx.session:
            token = ctx.session.get(f"{self.service_name}_token")
            if token:
                return {"Authorization": f"Bearer {token}"}

        return None

    # -------------------------------------------------------------------------
    # Health Check
    # -------------------------------------------------------------------------

    async def health_check(self) -> bool:
        """Check if the external service is healthy.

        Override this method to implement service-specific health checks.

        Returns:
            True if healthy, False otherwise
        """
        return True


__all__ = [
    "AdapterConfig",
    "AdapterError",
    "AdapterResponse",
    "AdapterResult",
    "ApiError",
    "AuthenticationError",
    "BaseExternalAdapter",
    "PaginatedResponse",
    "RateLimitConfig",
    "RateLimitError",
    "RetryConfig",
    "TimeoutError",
    "ValidationError",
]
