"""
Adapter examples and guides for GraphQL BFF layer.

Contains example code for implementing external API adapters.
"""

from __future__ import annotations

# Available adapter patterns
ADAPTERS = [
    {
        "name": "BaseExternalAdapter",
        "category": "base",
        "description": "Abstract base class for all external API adapters",
        "features": [
            "Automatic retry with exponential backoff",
            "Rate limiting (token bucket)",
            "Multi-HTTP-client support (httpx, aiohttp, urllib)",
            "Request/response logging",
            "Health check endpoint",
        ],
        "import": "from dazzle_dnr_back.graphql.adapters import BaseExternalAdapter",
    },
    {
        "name": "AdapterResult",
        "category": "result_type",
        "description": "Result type for explicit success/failure handling",
        "features": [
            "is_success/is_failure properties",
            "unwrap() and unwrap_or() methods",
            "map() for transformations",
            "No exception throwing for expected errors",
        ],
        "import": "from dazzle_dnr_back.graphql.adapters import AdapterResult",
    },
    {
        "name": "NormalizedError",
        "category": "error_handling",
        "description": "Unified error format for GraphQL responses",
        "features": [
            "Error categories (auth, validation, rate_limit, etc.)",
            "Severity levels (info, warning, error, critical)",
            "User-safe messages",
            "Developer details for debugging",
            "GraphQL extensions format",
        ],
        "import": "from dazzle_dnr_back.graphql.adapters import normalize_error, NormalizedError",
    },
]

# Service patterns for external APIs
SERVICE_PATTERNS = [
    {
        "name": "HMRC VAT API",
        "type": "government",
        "example_methods": ["get_vat_obligations", "submit_vat_return"],
        "auth": "OAuth2 Bearer Token",
        "rate_limit": "4 requests/second",
    },
    {
        "name": "Payment Provider",
        "type": "payment",
        "example_methods": ["create_payment", "get_payment_status", "refund"],
        "auth": "API Key",
        "rate_limit": "Varies by provider",
    },
    {
        "name": "Email Service",
        "type": "communication",
        "example_methods": ["send_email", "get_delivery_status"],
        "auth": "API Key",
        "rate_limit": "Provider-specific",
    },
    {
        "name": "CRM Integration",
        "type": "crm",
        "example_methods": ["get_contact", "update_contact", "create_lead"],
        "auth": "OAuth2 or API Key",
        "rate_limit": "Provider-specific",
    },
]

# Implementation guides for different service types
ADAPTER_GUIDES = {
    "hmrc": {
        "service": "HMRC VAT API",
        "description": "UK tax authority API for VAT submissions",
        "base_url": "https://api.service.hmrc.gov.uk",
        "auth_type": "OAuth2 Bearer Token",
        "rate_limit": "4 requests per second",
        "error_codes": [
            "INVALID_VRN",
            "VRN_NOT_FOUND",
            "DATE_RANGE_TOO_LARGE",
            "FORBIDDEN",
            "NOT_SIGNED_UP_TO_MTD",
        ],
        "example": '''from dazzle_dnr_back.graphql.adapters import (
    BaseExternalAdapter,
    AdapterConfig,
    RetryConfig,
    RateLimitConfig,
    AdapterResult,
)

class HMRCAdapter(BaseExternalAdapter[AdapterConfig]):
    """Adapter for HMRC VAT API."""

    def __init__(self, bearer_token: str):
        config = AdapterConfig(
            base_url="https://api.service.hmrc.gov.uk",
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {bearer_token}",
                "Accept": "application/vnd.hmrc.1.0+json",
            },
            retry=RetryConfig(max_retries=3, base_delay=1.0),
            rate_limit=RateLimitConfig(requests_per_second=4),
        )
        super().__init__(config)

    async def get_vat_obligations(
        self, vrn: str, from_date: str, to_date: str
    ) -> AdapterResult[list[dict]]:
        """Fetch VAT obligations for a business."""
        return await self._get(
            f"/organisations/vat/{vrn}/obligations",
            params={"from": from_date, "to": to_date, "status": "O"},
        )''',
    },
    "payment": {
        "service": "Payment Provider",
        "description": "Generic payment processing integration",
        "auth_type": "API Key",
        "example": '''from dazzle_dnr_back.graphql.adapters import (
    BaseExternalAdapter,
    AdapterConfig,
    AdapterResult,
)

class PaymentAdapter(BaseExternalAdapter[AdapterConfig]):
    """Adapter for payment provider API."""

    def __init__(self, api_key: str, sandbox: bool = True):
        base_url = "https://sandbox.provider.com" if sandbox else "https://api.provider.com"
        config = AdapterConfig(
            base_url=base_url,
            headers={"X-API-Key": api_key},
            timeout=30.0,
        )
        super().__init__(config)

    async def create_payment(
        self, amount: int, currency: str, description: str
    ) -> AdapterResult[dict]:
        """Create a new payment."""
        return await self._post(
            "/payments",
            json={"amount": amount, "currency": currency, "description": description},
        )

    async def get_payment(self, payment_id: str) -> AdapterResult[dict]:
        """Get payment status."""
        return await self._get(f"/payments/{payment_id}")''',
    },
    "generic": {
        "service": "Generic External API",
        "description": "Template for any external API integration",
        "example": '''from dazzle_dnr_back.graphql.adapters import (
    BaseExternalAdapter,
    AdapterConfig,
    RetryConfig,
    AdapterResult,
)

class MyServiceAdapter(BaseExternalAdapter[AdapterConfig]):
    """Adapter for My Service API."""

    def __init__(self, api_key: str):
        config = AdapterConfig(
            base_url="https://api.myservice.com",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
            retry=RetryConfig(max_retries=3),
        )
        super().__init__(config)

    async def get_resource(self, id: str) -> AdapterResult[dict]:
        """Fetch a resource by ID."""
        return await self._get(f"/resources/{id}")

    async def create_resource(self, data: dict) -> AdapterResult[dict]:
        """Create a new resource."""
        return await self._post("/resources", json=data)

    async def update_resource(self, id: str, data: dict) -> AdapterResult[dict]:
        """Update an existing resource."""
        return await self._put(f"/resources/{id}", json=data)

# Usage in GraphQL resolver:
async def resolve_resource(info, id: str):
    adapter = MyServiceAdapter(api_key=get_api_key())
    result = await adapter.get_resource(id)

    if result.is_success:
        return result.data

    # Handle error
    normalized = normalize_error(result.error)
    raise GraphQLError(normalized.user_message, extensions=normalized.to_graphql_extensions())''',
    },
}
