"""
External API Call Tracker.

Instruments outbound API calls to track:
- Latency and response times
- Success/error rates
- Request/response sizes
- Costs (for metered APIs like OpenAI, Stripe)

Usage:
    # As context manager
    async with api_tracker.track("stripe", "/v1/charges", "POST") as ctx:
        response = await httpx.post(url, json=data)
        ctx.set_response(response.status_code, len(response.content))

    # As decorator
    @api_tracker.traced("openai", "/v1/chat/completions")
    async def call_openai(prompt: str) -> str:
        ...

    # With cost tracking
    async with api_tracker.track("openai", "/v1/chat/completions", "POST") as ctx:
        response = await openai.chat.completions.create(...)
        ctx.set_cost(calculate_token_cost(response.usage))
"""

from __future__ import annotations

import functools
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar
from uuid import uuid4

from dazzle_back.runtime.ops_database import ApiCallRecord, OpsDatabase

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable

    from dazzle_back.events.bus import EventBus

P = ParamSpec("P")
R = TypeVar("R")


@dataclass
class ApiCostConfig:
    """Cost configuration for an API provider."""

    provider: str
    # Cost per request (flat rate)
    cost_per_request_cents: float = 0.0
    # Cost per KB of request data
    cost_per_kb_request_cents: float = 0.0
    # Cost per KB of response data
    cost_per_kb_response_cents: float = 0.0
    # Custom cost calculator (e.g., for token-based pricing)
    custom_calculator: Callable[[dict[str, Any]], float] | None = None


# Default cost configurations for common providers
DEFAULT_COST_CONFIGS: dict[str, ApiCostConfig] = {
    "stripe": ApiCostConfig(
        provider="stripe",
        # Stripe charges per transaction, not API call
        cost_per_request_cents=0.0,
    ),
    "openai": ApiCostConfig(
        provider="openai",
        # OpenAI uses token-based pricing - use custom calculator
        cost_per_request_cents=0.0,
    ),
    "twilio": ApiCostConfig(
        provider="twilio",
        # Twilio charges per SMS/call, tracked separately
        cost_per_request_cents=0.0,
    ),
    "sendgrid": ApiCostConfig(
        provider="sendgrid",
        # SendGrid charges per email
        cost_per_request_cents=0.0,
    ),
    "hmrc": ApiCostConfig(
        provider="hmrc",
        # HMRC MTD is free
        cost_per_request_cents=0.0,
    ),
    "companies_house": ApiCostConfig(
        provider="companies_house",
        # Companies House API is free
        cost_per_request_cents=0.0,
    ),
}


@dataclass
class TrackingContext:
    """Context for a tracked API call."""

    service_name: str
    endpoint: str
    method: str
    tenant_id: str | None = None
    start_time: float = field(default_factory=time.monotonic)
    status_code: int | None = None
    request_size_bytes: int | None = None
    response_size_bytes: int | None = None
    error_message: str | None = None
    cost_cents: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def set_request_size(self, size: int) -> None:
        """Set request body size in bytes."""
        self.request_size_bytes = size

    def set_response(
        self,
        status_code: int,
        response_size: int | None = None,
    ) -> None:
        """Set response status and size."""
        self.status_code = status_code
        self.response_size_bytes = response_size

    def set_error(self, message: str) -> None:
        """Set error message."""
        self.error_message = message
        if self.status_code is None:
            self.status_code = 0  # Connection error

    def set_cost(self, cost_cents: float) -> None:
        """Set the cost of this API call in cents."""
        self.cost_cents = cost_cents

    def add_metadata(self, key: str, value: Any) -> None:
        """Add metadata to the tracking context."""
        self.metadata[key] = value

    @property
    def latency_ms(self) -> float:
        """Get latency in milliseconds."""
        return (time.monotonic() - self.start_time) * 1000


class ApiTracker:
    """
    Tracks external API calls with latency, errors, and costs.

    Thread-safe and async-compatible. Emits events for SSE streaming.
    """

    def __init__(
        self,
        ops_db: OpsDatabase,
        event_bus: EventBus | None = None,
        cost_configs: dict[str, ApiCostConfig] | None = None,
    ):
        """
        Initialize API tracker.

        Args:
            ops_db: Operations database for storage
            event_bus: Optional event bus for SSE streaming
            cost_configs: Cost configurations by provider name
        """
        self.ops_db = ops_db
        self.event_bus = event_bus
        self.cost_configs = {**DEFAULT_COST_CONFIGS, **(cost_configs or {})}

    def configure_cost(self, config: ApiCostConfig) -> None:
        """Add or update cost configuration for a provider."""
        self.cost_configs[config.provider] = config

    @asynccontextmanager
    async def track(
        self,
        service_name: str,
        endpoint: str,
        method: str = "GET",
        tenant_id: str | None = None,
    ) -> AsyncGenerator[TrackingContext, None]:
        """
        Track an API call using context manager.

        Args:
            service_name: Name of the external service (e.g., "stripe", "openai")
            endpoint: API endpoint path
            method: HTTP method
            tenant_id: Optional tenant ID for scoping

        Yields:
            TrackingContext for setting response details

        Example:
            async with tracker.track("stripe", "/v1/charges", "POST") as ctx:
                response = await client.post(url, json=data)
                ctx.set_response(response.status_code, len(response.content))
        """
        ctx = TrackingContext(
            service_name=service_name,
            endpoint=endpoint,
            method=method,
            tenant_id=tenant_id,
        )

        try:
            yield ctx
        except Exception as e:
            ctx.set_error(str(e))
            raise
        finally:
            await self._record(ctx)

    def traced(
        self,
        service_name: str,
        endpoint: str,
        method: str = "GET",
        tenant_id: str | None = None,
    ) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
        """
        Decorator to track an async function as an API call.

        Args:
            service_name: Name of the external service
            endpoint: API endpoint path
            method: HTTP method
            tenant_id: Optional tenant ID

        Returns:
            Decorator function

        Example:
            @tracker.traced("openai", "/v1/chat/completions", "POST")
            async def call_openai(prompt: str) -> str:
                ...
        """

        def decorator(
            func: Callable[P, Awaitable[R]],
        ) -> Callable[P, Awaitable[R]]:
            @functools.wraps(func)
            async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                async with self.track(service_name, endpoint, method, tenant_id) as ctx:
                    try:
                        result = await func(*args, **kwargs)
                        # Try to extract status from result if it's a response
                        if hasattr(result, "status_code"):
                            ctx.set_response(result.status_code)
                        else:
                            ctx.set_response(200)  # Assume success
                        return result
                    except Exception as e:
                        ctx.set_error(str(e))
                        raise

            return wrapper

        return decorator

    async def _record(self, ctx: TrackingContext) -> None:
        """Record the API call to the database and emit event."""
        # Calculate cost if not set and we have a config
        if ctx.cost_cents is None:
            cost_config = self.cost_configs.get(ctx.service_name)
            if cost_config:
                ctx.cost_cents = self._calculate_cost(ctx, cost_config)

        # Create record
        record = ApiCallRecord(
            id=str(uuid4()),
            service_name=ctx.service_name,
            endpoint=ctx.endpoint,
            method=ctx.method,
            status_code=ctx.status_code,
            latency_ms=ctx.latency_ms,
            request_size_bytes=ctx.request_size_bytes,
            response_size_bytes=ctx.response_size_bytes,
            error_message=ctx.error_message,
            cost_cents=ctx.cost_cents,
            metadata=ctx.metadata,
            called_at=datetime.now(UTC),
            tenant_id=ctx.tenant_id,
        )

        # Store in database
        self.ops_db.record_api_call(record)

        # Emit event for SSE
        if self.event_bus:
            await self._emit_event(record)

    def _calculate_cost(
        self,
        ctx: TrackingContext,
        config: ApiCostConfig,
    ) -> float:
        """Calculate cost for an API call."""
        cost = config.cost_per_request_cents

        if ctx.request_size_bytes and config.cost_per_kb_request_cents:
            cost += (ctx.request_size_bytes / 1024) * config.cost_per_kb_request_cents

        if ctx.response_size_bytes and config.cost_per_kb_response_cents:
            cost += (ctx.response_size_bytes / 1024) * config.cost_per_kb_response_cents

        if config.custom_calculator:
            cost += config.custom_calculator(ctx.metadata)

        return cost

    async def _emit_event(self, record: ApiCallRecord) -> None:
        """Emit API call event for SSE streaming."""
        if not self.event_bus:
            return

        try:
            from dazzle_back.events.envelope import EventEnvelope

            envelope = EventEnvelope.create(
                event_type="ops.api_call.completed",
                key=record.service_name,
                payload={
                    "id": record.id,
                    "service_name": record.service_name,
                    "endpoint": record.endpoint,
                    "method": record.method,
                    "status_code": record.status_code,
                    "latency_ms": record.latency_ms,
                    "error_message": record.error_message,
                    "cost_cents": record.cost_cents,
                    "called_at": record.called_at.isoformat(),
                    "tenant_id": record.tenant_id,
                },
                headers={"tenant_id": record.tenant_id} if record.tenant_id else {},
            )
            await self.event_bus.publish("ops.api_call", envelope)
        except Exception:
            pass  # Don't fail on event emission


# =============================================================================
# HTTPX Integration
# =============================================================================


class TrackedHttpxClient:
    """
    HTTPX client wrapper that automatically tracks API calls.

    Usage:
        client = TrackedHttpxClient(tracker, "stripe", tenant_id="tenant_123")
        response = await client.post("/v1/charges", json=data)
    """

    def __init__(
        self,
        tracker: ApiTracker,
        service_name: str,
        base_url: str = "",
        tenant_id: str | None = None,
        **httpx_kwargs: Any,
    ):
        """
        Initialize tracked HTTPX client.

        Args:
            tracker: ApiTracker instance
            service_name: Name of the external service
            base_url: Base URL for all requests
            tenant_id: Optional tenant ID for scoping
            **httpx_kwargs: Additional kwargs for httpx.AsyncClient
        """
        try:
            import httpx
        except ImportError:
            raise RuntimeError("httpx required for TrackedHttpxClient")

        self.tracker = tracker
        self.service_name = service_name
        self.base_url = base_url
        self.tenant_id = tenant_id
        self._client = httpx.AsyncClient(base_url=base_url, **httpx_kwargs)

    async def request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> Any:
        """Make a tracked HTTP request."""
        import httpx

        async with self.tracker.track(
            self.service_name,
            url,
            method,
            self.tenant_id,
        ) as ctx:
            # Track request size
            if "json" in kwargs:
                import json

                ctx.set_request_size(len(json.dumps(kwargs["json"]).encode()))
            elif "content" in kwargs:
                content = kwargs["content"]
                if isinstance(content, bytes):
                    ctx.set_request_size(len(content))
                elif isinstance(content, str):
                    ctx.set_request_size(len(content.encode()))

            try:
                response = await self._client.request(method, url, **kwargs)
                ctx.set_response(response.status_code, len(response.content))
                return response
            except httpx.TimeoutException as e:
                ctx.set_error(f"Timeout: {e}")
                raise
            except httpx.HTTPError as e:
                ctx.set_error(str(e))
                raise

    async def get(self, url: str, **kwargs: Any) -> Any:
        """Make a tracked GET request."""
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> Any:
        """Make a tracked POST request."""
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> Any:
        """Make a tracked PUT request."""
        return await self.request("PUT", url, **kwargs)

    async def patch(self, url: str, **kwargs: Any) -> Any:
        """Make a tracked PATCH request."""
        return await self.request("PATCH", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> Any:
        """Make a tracked DELETE request."""
        return await self.request("DELETE", url, **kwargs)

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> TrackedHttpxClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.aclose()


# =============================================================================
# OpenAI Token Cost Calculator
# =============================================================================


def create_openai_cost_calculator(
    model_costs: dict[str, tuple[float, float]] | None = None,
) -> Callable[[dict[str, Any]], float]:
    """
    Create a cost calculator for OpenAI API calls.

    Args:
        model_costs: Dict of model -> (input_cost_per_1k_tokens, output_cost_per_1k_tokens)
                    in cents. Defaults to current GPT-4 pricing.

    Returns:
        Cost calculator function for use with ApiCostConfig
    """
    # Default costs in cents per 1K tokens (as of 2024)
    default_costs = {
        "gpt-4-turbo": (1.0, 3.0),  # $0.01/$0.03 per 1K
        "gpt-4": (3.0, 6.0),  # $0.03/$0.06 per 1K
        "gpt-3.5-turbo": (0.05, 0.15),  # $0.0005/$0.0015 per 1K
        "claude-3-opus": (1.5, 7.5),  # $0.015/$0.075 per 1K
        "claude-3-sonnet": (0.3, 1.5),  # $0.003/$0.015 per 1K
        "claude-3-haiku": (0.025, 0.125),  # $0.00025/$0.00125 per 1K
    }
    costs = {**default_costs, **(model_costs or {})}

    def calculator(metadata: dict[str, Any]) -> float:
        model = str(metadata.get("model", "gpt-3.5-turbo"))
        input_tokens = int(metadata.get("input_tokens", 0))
        output_tokens = int(metadata.get("output_tokens", 0))

        input_cost, output_cost = costs.get(model, (0.1, 0.3))

        total: float = (input_tokens / 1000) * input_cost + (output_tokens / 1000) * output_cost
        return total

    return calculator


# =============================================================================
# Convenience Functions
# =============================================================================


def configure_openai_tracking(tracker: ApiTracker) -> None:
    """Configure cost tracking for OpenAI API calls."""
    tracker.configure_cost(
        ApiCostConfig(
            provider="openai",
            custom_calculator=create_openai_cost_calculator(),
        )
    )


def configure_anthropic_tracking(tracker: ApiTracker) -> None:
    """Configure cost tracking for Anthropic API calls."""
    tracker.configure_cost(
        ApiCostConfig(
            provider="anthropic",
            custom_calculator=create_openai_cost_calculator(
                {
                    "claude-3-opus-20240229": (1.5, 7.5),
                    "claude-3-sonnet-20240229": (0.3, 1.5),
                    "claude-3-haiku-20240307": (0.025, 0.125),
                    "claude-3-5-sonnet-20241022": (0.3, 1.5),
                }
            ),
        )
    )
