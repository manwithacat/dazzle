"""API client helpers for E2E tests.

Provides HTTP clients for both the backend CRUD API and the Dazzle Bar control plane.
"""

from __future__ import annotations

from typing import Any

import httpx


class APIClient:
    """HTTP client for backend CRUD operations."""

    def __init__(self, base_url: str):
        """Initialize the API client.

        Args:
            base_url: Base URL for the backend API (e.g., http://localhost:8000)
        """
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(base_url=self.base_url, timeout=30.0)

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()

    def create(self, entity: str, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new entity record.

        Args:
            entity: Entity name (e.g., "Device", "Tester")
            data: Record data

        Returns:
            Created record with ID
        """
        response = self.client.post(f"/{entity.lower()}", json=data)
        response.raise_for_status()
        return response.json()

    def get(self, entity: str, entity_id: str) -> dict[str, Any]:
        """Get an entity record by ID.

        Args:
            entity: Entity name
            entity_id: Record ID

        Returns:
            Record data
        """
        response = self.client.get(f"/{entity.lower()}/{entity_id}")
        response.raise_for_status()
        return response.json()

    def get_all(self, entity: str) -> list[dict[str, Any]]:
        """Get all records for an entity.

        Args:
            entity: Entity name

        Returns:
            List of records
        """
        response = self.client.get(f"/{entity.lower()}")
        response.raise_for_status()
        return response.json()

    def update(self, entity: str, entity_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update an entity record.

        Args:
            entity: Entity name
            entity_id: Record ID
            data: Updated data

        Returns:
            Updated record
        """
        response = self.client.put(f"/{entity.lower()}/{entity_id}", json=data)
        response.raise_for_status()
        return response.json()

    def patch(self, entity: str, entity_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Partially update an entity record.

        Args:
            entity: Entity name
            entity_id: Record ID
            data: Partial data to update

        Returns:
            Updated record
        """
        response = self.client.patch(f"/{entity.lower()}/{entity_id}", json=data)
        response.raise_for_status()
        return response.json()

    def delete(self, entity: str, entity_id: str) -> None:
        """Delete an entity record.

        Args:
            entity: Entity name
            entity_id: Record ID
        """
        response = self.client.delete(f"/{entity.lower()}/{entity_id}")
        response.raise_for_status()

    def count(self, entity: str) -> int:
        """Get count of records for an entity.

        Args:
            entity: Entity name

        Returns:
            Number of records
        """
        records = self.get_all(entity)
        return len(records)


class ControlPlaneClient:
    """HTTP client for Dazzle Bar control plane API."""

    def __init__(self, base_url: str):
        """Initialize the control plane client.

        Args:
            base_url: Base URL for the backend (e.g., http://localhost:8000)
        """
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(base_url=self.base_url, timeout=30.0)

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()

    def get_state(self) -> dict[str, Any]:
        """Get the current Dazzle Bar state.

        Returns:
            State including personas, scenarios, current selections
        """
        response = self.client.get("/dazzle/dev/state")
        response.raise_for_status()
        return response.json()

    def set_persona(self, persona_id: str) -> dict[str, Any]:
        """Set the current persona.

        Args:
            persona_id: Persona identifier (e.g., "engineer", "tester", "manager")

        Returns:
            Updated state
        """
        response = self.client.post("/dazzle/dev/current_persona", json={"persona_id": persona_id})
        response.raise_for_status()
        return response.json()

    def set_scenario(self, scenario_id: str) -> dict[str, Any]:
        """Set the current scenario.

        Args:
            scenario_id: Scenario identifier

        Returns:
            Updated state
        """
        response = self.client.post(
            "/dazzle/dev/current_scenario", json={"scenario_id": scenario_id}
        )
        response.raise_for_status()
        return response.json()

    def reset_data(self) -> dict[str, Any]:
        """Reset all data in the database.

        Returns:
            Reset confirmation
        """
        response = self.client.post("/dazzle/dev/reset")
        response.raise_for_status()
        return response.json()

    def regenerate_data(self, entity_counts: dict[str, int] | None = None) -> dict[str, Any]:
        """Regenerate demo data.

        Args:
            entity_counts: Optional custom counts per entity

        Returns:
            Regeneration result with counts
        """
        payload = {}
        if entity_counts:
            payload["entity_counts"] = entity_counts
        response = self.client.post("/dazzle/dev/regenerate", json=payload)
        response.raise_for_status()
        return response.json()

    def get_personas(self) -> list[dict[str, Any]]:
        """Get available personas.

        Returns:
            List of persona definitions
        """
        state = self.get_state()
        return state.get("personas", [])

    def get_current_persona(self) -> dict[str, Any] | None:
        """Get the currently selected persona.

        Returns:
            Current persona or None
        """
        state = self.get_state()
        return state.get("current_persona")

    def inspect_entities(self) -> dict[str, Any]:
        """Get entity inspection data.

        Returns:
            Entity schemas and counts
        """
        response = self.client.get("/dazzle/dev/inspect/entities")
        response.raise_for_status()
        return response.json()
