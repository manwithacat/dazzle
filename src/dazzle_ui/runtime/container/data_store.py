"""
In-memory data store for DNR container runtime.

Provides simple dict-based storage for entity data.
"""

from __future__ import annotations

from typing import Any


class DataStore:
    """Simple in-memory data store for entity collections."""

    def __init__(self) -> None:
        self._collections: dict[str, dict[str, Any]] = {}

    def get_collection(self, entity_name: str) -> dict[str, Any]:
        """Get or create collection for entity."""
        if entity_name not in self._collections:
            self._collections[entity_name] = {}
        return self._collections[entity_name]

    def clear(self) -> None:
        """Clear all collections."""
        self._collections.clear()

    def snapshot(self) -> dict[str, dict[str, Any]]:
        """Get a snapshot of all data."""
        return dict(self._collections)


# Global data store instance
data_store = DataStore()
