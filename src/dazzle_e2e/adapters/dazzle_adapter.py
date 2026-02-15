"""
Dazzle Runtime Adapter for E2E Testing.

Provides test infrastructure for DNR-based applications.
"""

import logging
from typing import Any

import httpx

from dazzle.core.ir import FixtureSpec
from dazzle_e2e.adapters.base import BaseAdapter

logger = logging.getLogger(__name__)


class DazzleAdapter(BaseAdapter):
    """
    Adapter for Dazzle Runtime applications.

    Uses the /__test__/* endpoints for test operations.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:3000",
        api_url: str = "http://localhost:8000",
        timeout: float = 30.0,
    ) -> None:
        """
        Initialize the DNR adapter.

        Args:
            base_url: Frontend URL (default: http://localhost:3000)
            api_url: API URL (default: http://localhost:8000)
            timeout: HTTP request timeout in seconds
        """
        super().__init__(base_url, api_url)
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._fixture_ids: dict[str, str] = {}  # fixture_id -> created entity ID

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def seed(self, fixtures: list[FixtureSpec]) -> dict[str, Any]:
        """
        Seed test fixtures via /__test__/seed endpoint.

        Args:
            fixtures: List of fixtures to seed

        Returns:
            Dict mapping fixture IDs to created entity data
        """
        client = await self._get_client()

        # Convert fixtures to API format
        fixture_data = [
            {
                "id": fixture.id,
                "entity": fixture.entity,
                "data": fixture.data,
                "refs": fixture.refs,
            }
            for fixture in fixtures
        ]

        response = await client.post(
            f"{self.api_url}/__test__/seed",
            json={"fixtures": fixture_data},
        )
        response.raise_for_status()

        return response.json()

    async def reset(self) -> None:
        """
        Reset test data via /__test__/reset endpoint.
        """
        client = await self._get_client()

        response = await client.post(f"{self.api_url}/__test__/reset")
        response.raise_for_status()

    async def snapshot(self) -> dict[str, list[dict[str, Any]]]:
        """
        Get database snapshot via /__test__/snapshot endpoint.

        Returns:
            Dict mapping entity names to list of records
        """
        client = await self._get_client()

        response = await client.get(f"{self.api_url}/__test__/snapshot")
        response.raise_for_status()

        return response.json()

    async def get_entities(self, entity: str) -> list[dict[str, Any]]:
        """
        Get all instances of an entity via API.

        Args:
            entity: Entity name

        Returns:
            List of entity records
        """
        client = await self._get_client()

        # Try standard REST endpoint first
        response = await client.get(f"{self.api_url}/{entity.lower()}")

        if response.status_code == 200:
            data = response.json()
            # Handle both list and paginated responses
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "items" in data:
                return data["items"]
            elif isinstance(data, dict) and "data" in data:
                return data["data"]

        # Fall back to snapshot
        snapshot = await self.snapshot()
        return snapshot.get(entity, [])

    async def get_entity(self, entity: str, entity_id: str) -> dict[str, Any] | None:
        """
        Get a specific entity instance.

        Args:
            entity: Entity name
            entity_id: Entity instance ID

        Returns:
            Entity record or None
        """
        client = await self._get_client()

        response = await client.get(f"{self.api_url}/{entity.lower()}/{entity_id}")

        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            return None

        response.raise_for_status()
        return None

    async def authenticate(
        self,
        username: str | None = None,
        password: str | None = None,
        role: str | None = None,
    ) -> dict[str, Any]:
        """
        Authenticate via DNR auth endpoint.

        Args:
            username: Username (defaults to test user)
            password: Password (defaults to test password)
            role: Optional role for test user

        Returns:
            Auth context with session info
        """
        client = await self._get_client()

        # Use test credentials if not provided
        auth_data = {
            "username": username or f"test_{role or 'user'}",
            "password": password or "test_password",
        }

        if role:
            auth_data["role"] = role

        response = await client.post(
            f"{self.api_url}/auth/login",
            json=auth_data,
        )

        if response.status_code == 200:
            return response.json()

        # If auth fails, try test endpoint
        response = await client.post(
            f"{self.api_url}/__test__/authenticate",
            json=auth_data,
        )
        response.raise_for_status()

        return response.json()

    async def logout(self) -> None:
        """Log out via DNR auth endpoint."""
        client = await self._get_client()

        await client.post(f"{self.api_url}/auth/logout")

    async def get_current_user(self) -> dict[str, Any] | None:
        """
        Get the current authenticated user's info.

        Returns:
            User info dict or None if not authenticated
        """
        client = await self._get_client()

        try:
            response = await client.get(f"{self.api_url}/auth/me")
            if response.status_code == 200:
                return response.json()
        except Exception:
            logger.debug("Failed to get current user info", exc_info=True)

        return None

    async def create_test_user(
        self,
        email: str,
        password: str,
        display_name: str | None = None,
        persona: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a test user via /__test__/create_user endpoint.

        Args:
            email: User email
            password: User password
            display_name: Optional display name
            persona: Optional persona/role

        Returns:
            Created user data
        """
        client = await self._get_client()

        user_data: dict[str, Any] = {
            "email": email,
            "password": password,
        }
        if display_name:
            user_data["display_name"] = display_name
        if persona:
            user_data["persona"] = persona

        response = await client.post(
            f"{self.api_url}/__test__/create_user",
            json=user_data,
        )
        response.raise_for_status()

        return response.json()

    async def login_as(
        self,
        email: str,
        password: str,
    ) -> dict[str, Any]:
        """
        Login via API and return session info.

        Args:
            email: User email
            password: User password

        Returns:
            Session info dict with cookies/token
        """
        client = await self._get_client()

        response = await client.post(
            f"{self.api_url}/auth/login",
            json={"email": email, "password": password},
        )
        response.raise_for_status()

        result = response.json()

        # Store cookies from response
        result["cookies"] = dict(response.cookies)

        return result

    def resolve_view_url(self, view_id: str) -> str:
        """
        Resolve a view ID to a DNR URL.

        DNR uses path-based routing.

        Args:
            view_id: View identifier

        Returns:
            Full URL for the view
        """
        # Runtime uses path-based routing
        parts = view_id.split("_")
        if len(parts) == 1:
            return f"{self.base_url}/{parts[0]}"
        elif parts[-1] == "list":
            return f"{self.base_url}/{parts[0]}"
        elif parts[-1] == "create":
            return f"{self.base_url}/{parts[0]}/create"
        elif parts[-1] == "detail":
            return f"{self.base_url}/{parts[0]}/{{id}}"
        elif parts[-1] == "edit":
            return f"{self.base_url}/{parts[0]}/{{id}}/edit"
        else:
            # Dashboard/workspace routes
            return f"{self.base_url}/{view_id.replace('_', '/')}"

    # =========================================================================
    # Synchronous Methods (for CLI usage)
    # =========================================================================

    def seed_sync(self, fixtures: list[FixtureSpec]) -> dict[str, Any]:
        """Synchronous version of seed for CLI usage."""
        fixture_data = [
            {
                "id": fixture.id,
                "entity": fixture.entity,
                "data": fixture.data,
                "refs": getattr(fixture, "refs", {}),
            }
            for fixture in fixtures
        ]

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.api_url}/__test__/seed",
                json={"fixtures": fixture_data},
            )
            response.raise_for_status()
            result = response.json()

        # Store created entity IDs for fixture_ref resolution
        created = result.get("created", {})
        for fixture in fixtures:
            if fixture.id in created:
                entity_data = created[fixture.id]
                if isinstance(entity_data, dict) and "id" in entity_data:
                    self._fixture_ids[fixture.id] = entity_data["id"]

        return result

    def reset_sync(self) -> None:
        """Synchronous version of reset for CLI usage."""
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(f"{self.api_url}/__test__/reset")
            response.raise_for_status()

    def snapshot_sync(self) -> dict[str, list[dict[str, Any]]]:
        """Synchronous version of snapshot for CLI usage."""
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(f"{self.api_url}/__test__/snapshot")
            response.raise_for_status()
            return response.json()

    def authenticate_sync(
        self,
        username: str | None = None,
        password: str | None = None,
        role: str | None = None,
    ) -> dict[str, Any]:
        """Synchronous version of authenticate for CLI usage."""
        auth_data = {
            "username": username or f"test_{role or 'user'}",
            "password": password or "test_password",
        }

        if role:
            auth_data["role"] = role

        with httpx.Client(timeout=self.timeout) as client:
            # Try regular auth first
            response = client.post(
                f"{self.api_url}/auth/login",
                json=auth_data,
            )

            if response.status_code == 200:
                return response.json()

            # Fall back to test endpoint
            response = client.post(
                f"{self.api_url}/__test__/authenticate",
                json=auth_data,
            )
            response.raise_for_status()
            return response.json()

    def get_entity_count_sync(self, entity: str) -> int:
        """Get entity count synchronously for assertions."""
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(f"{self.api_url}/__test__/entity/{entity}/count")

            if response.status_code == 200:
                data = response.json()
                return data.get("count", 0)

            # Fall back to snapshot
            response = client.get(f"{self.api_url}/__test__/snapshot")
            if response.status_code == 200:
                snapshot = response.json()
                entities = snapshot.get("entities", {})
                return len(entities.get(entity, []))

            return 0
