"""
Base Adapter for Dazzle E2E Testing.

Defines the interface that stack-specific adapters must implement.
"""

from abc import ABC, abstractmethod
from typing import Any

from dazzle.core.ir import FixtureSpec


class BaseAdapter(ABC):
    """
    Abstract base adapter for E2E testing.

    Stack-specific adapters (DNR, Django, Express, etc.) implement
    this interface to provide test infrastructure.
    """

    def __init__(self, base_url: str, api_url: str | None = None) -> None:
        """
        Initialize the adapter.

        Args:
            base_url: Base URL for the frontend (e.g., "http://localhost:3000")
            api_url: Optional API URL (e.g., "http://localhost:8000")
        """
        self.base_url = base_url.rstrip("/")
        self.api_url = (api_url or base_url).rstrip("/")

    @abstractmethod
    async def seed(self, fixtures: list[FixtureSpec]) -> dict[str, Any]:
        """
        Seed test fixtures into the database.

        Args:
            fixtures: List of fixtures to seed

        Returns:
            Dict mapping fixture IDs to created entity data (including IDs)
        """
        ...

    @abstractmethod
    async def reset(self) -> None:
        """
        Reset all test data.

        Clears the database to initial state.
        """
        ...

    @abstractmethod
    async def snapshot(self) -> dict[str, list[dict[str, Any]]]:
        """
        Get current database state.

        Returns:
            Dict mapping entity names to list of entity records
        """
        ...

    @abstractmethod
    async def get_entities(self, entity: str) -> list[dict[str, Any]]:
        """
        Get all instances of an entity.

        Args:
            entity: Entity name

        Returns:
            List of entity records
        """
        ...

    @abstractmethod
    async def get_entity(self, entity: str, entity_id: str) -> dict[str, Any] | None:
        """
        Get a specific entity instance.

        Args:
            entity: Entity name
            entity_id: Entity instance ID

        Returns:
            Entity record or None if not found
        """
        ...

    def resolve_view_url(self, view_id: str) -> str:
        """
        Resolve a view ID to a URL.

        Default implementation uses convention-based routing.
        Override for custom routing patterns.

        Args:
            view_id: View identifier (e.g., "task_list", "task_detail")

        Returns:
            Full URL for the view
        """
        # Convention: view_id maps to /{entity}/ or /{entity}/{action}
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
            return f"{self.base_url}/{'/'.join(parts)}"

    def resolve_action_url(self, action_id: str) -> str:
        """
        Resolve an action ID to an API endpoint.

        Args:
            action_id: Action identifier (e.g., "Task.create", "Task.delete")

        Returns:
            API endpoint URL
        """
        # Convention: Entity.action maps to /api/{entity}/{action}
        if "." in action_id:
            entity, action = action_id.split(".", 1)
            return f"{self.api_url}/api/{entity.lower()}/{action}"
        return f"{self.api_url}/api/{action_id}"

    async def authenticate(
        self,
        username: str | None = None,
        password: str | None = None,
        role: str | None = None,
    ) -> dict[str, Any]:
        """
        Authenticate for testing.

        Default implementation does nothing. Override for auth-enabled stacks.

        Args:
            username: Optional username
            password: Optional password
            role: Optional role for test user

        Returns:
            Auth context (e.g., {"token": "...", "user_id": "..."})
        """
        return {}

    async def logout(self) -> None:
        """
        Log out the current user.

        Default implementation does nothing. Override for auth-enabled stacks.
        """
        pass

    async def get_current_user(self) -> dict[str, Any] | None:
        """
        Get the current authenticated user's info.

        Default implementation returns None. Override for auth-enabled stacks.

        Returns:
            User info dict with at least 'email' and optionally 'persona', or None
        """
        return None
