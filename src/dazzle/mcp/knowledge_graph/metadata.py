"""
Knowledge Graph metadata mixin — aliases, seed metadata, concept/inference lookup.

Provides alias management, seed metadata key-value store, bulk deletion
by metadata key, and concept/inference lookup for the unified KG.
"""

from __future__ import annotations

from .models import Entity


class KnowledgeGraphMetadata:
    """Mixin providing alias management, seed metadata, and concept/inference lookup."""

    # =========================================================================
    # Alias Management
    # =========================================================================

    def create_alias(self, alias: str, canonical_id: str) -> None:
        """Create an alias mapping to a canonical entity ID."""
        conn = self._get_connection()  # type: ignore[attr-defined]
        try:
            conn.execute(
                "INSERT OR REPLACE INTO aliases (alias, canonical_id) VALUES (?, ?)",
                (alias, canonical_id),
            )
            conn.commit()
        finally:
            self._close_connection(conn)  # type: ignore[attr-defined]

    def resolve_alias(self, alias: str) -> str | None:
        """Resolve an alias to its canonical entity ID, or None if not found."""
        conn = self._get_connection()  # type: ignore[attr-defined]
        try:
            row = conn.execute(
                "SELECT canonical_id FROM aliases WHERE alias = ?", (alias,)
            ).fetchone()
            return row["canonical_id"] if row else None
        finally:
            self._close_connection(conn)  # type: ignore[attr-defined]

    def clear_aliases(self) -> int:
        """Delete all aliases. Returns number deleted."""
        conn = self._get_connection()  # type: ignore[attr-defined]
        try:
            cursor = conn.execute("DELETE FROM aliases")
            conn.commit()
            return int(cursor.rowcount)
        finally:
            self._close_connection(conn)  # type: ignore[attr-defined]

    # =========================================================================
    # Seed Metadata
    # =========================================================================

    def set_seed_meta(self, key: str, value: str) -> None:
        """Set a seed metadata key-value pair."""
        conn = self._get_connection()  # type: ignore[attr-defined]
        try:
            conn.execute(
                "INSERT OR REPLACE INTO seed_meta (key, value) VALUES (?, ?)",
                (key, value),
            )
            conn.commit()
        finally:
            self._close_connection(conn)  # type: ignore[attr-defined]

    def get_seed_meta(self, key: str) -> str | None:
        """Get a seed metadata value by key."""
        conn = self._get_connection()  # type: ignore[attr-defined]
        try:
            row = conn.execute("SELECT value FROM seed_meta WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else None
        finally:
            self._close_connection(conn)  # type: ignore[attr-defined]

    # =========================================================================
    # Bulk Operations
    # =========================================================================

    def delete_by_metadata_key(self, key: str, value: str) -> int:
        """Delete all entities where metadata contains key=value. Returns count deleted."""
        conn = self._get_connection()  # type: ignore[attr-defined]
        try:
            # Use JSON extraction to match metadata field
            cursor = conn.execute(
                "DELETE FROM entities WHERE json_extract(metadata, ?) = ?",
                (f"$.{key}", value),
            )
            conn.commit()
            return int(cursor.rowcount)
        finally:
            self._close_connection(conn)  # type: ignore[attr-defined]

    # =========================================================================
    # Concept & Inference Lookup (for unified KG queries)
    # =========================================================================

    def lookup_concept(self, term: str) -> Entity | None:
        """
        Look up a concept or pattern by name, checking aliases first.

        Args:
            term: Concept name (e.g., "entity", "wizard", "crud")

        Returns:
            Entity if found (concept or pattern), None otherwise
        """
        normalized = term.lower().replace(" ", "_").replace("-", "_")

        # Try alias resolution first
        canonical_id = self.resolve_alias(normalized)
        if canonical_id:
            entity: Entity | None = self.get_entity(canonical_id)  # type: ignore[attr-defined]
            if entity:
                return entity

        # Try direct concept lookup
        entity = self.get_entity(f"concept:{normalized}")  # type: ignore[attr-defined]
        if entity:
            return entity

        # Try pattern lookup
        entity = self.get_entity(f"pattern:{normalized}")  # type: ignore[attr-defined]
        if entity:
            return entity

        return None

    def lookup_inference_matches(
        self,
        query: str,
        limit: int = 20,
    ) -> list[Entity]:
        """
        Find inference entries whose triggers match the query.

        Searches inference entities by matching query words against
        the triggers stored in metadata.

        Args:
            query: Search text
            limit: Maximum results

        Returns:
            List of matching inference entities
        """
        query_lower = query.lower()
        query_words = set(query_lower.split())

        # Get all inference entities
        inference_entities = self.list_entities(entity_type="inference", limit=500)  # type: ignore[attr-defined]

        matches: list[Entity] = []
        for entity in inference_entities:
            triggers = entity.metadata.get("triggers", [])
            if not triggers:
                continue

            # Check trigger matching (same logic as _matches_triggers)
            matched = False
            for trigger in triggers:
                trigger_lower = trigger.lower()
                if trigger_lower in query_lower:
                    matched = True
                    break
                trigger_words = set(trigger_lower.split())
                if query_words & trigger_words:
                    matched = True
                    break

            if matched:
                matches.append(entity)
                if len(matches) >= limit:
                    break

        return matches
