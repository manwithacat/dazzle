"""
Demo data seeder for Dazzle Bar (v0.8.5).

Seeds demo data into the database with scenario and persona awareness.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from .generator import DemoDataGenerator
from .loader import DemoDataLoader

if TYPE_CHECKING:
    from pathlib import Path

    from dazzle_dnr_back.runtime.repository import DatabaseManager, SQLiteRepository
    from dazzle_dnr_back.specs import BackendSpec


class DemoDataSeeder:
    """
    Seeds demo data into the database.

    Supports:
    - Loading from files or inline DSL demo blocks
    - Faker-based generation from entity schemas
    - Per-persona fixture support
    - Reference resolution between entities
    """

    def __init__(
        self,
        backend_spec: BackendSpec,
        db_manager: DatabaseManager,
        repositories: dict[str, SQLiteRepository[Any]],
        project_root: Path | None = None,
        seed: int | None = None,
    ) -> None:
        """
        Initialize the seeder.

        Args:
            backend_spec: Backend specification with entity definitions
            db_manager: Database manager instance
            repositories: Dictionary of repositories by entity name
            project_root: Root directory for resolving paths
            seed: Random seed for reproducible data generation
        """
        self.backend_spec = backend_spec
        self.db_manager = db_manager
        self.repositories = repositories
        self.generator = DemoDataGenerator(seed=seed)
        self.loader = DemoDataLoader(project_root=project_root)

        # Build entity lookup
        self._entity_lookup = {e.name: e for e in backend_spec.entities}

    def reset(self) -> None:
        """
        Clear all data from the database.

        Truncates all entity tables while preserving schema.
        """
        with self.db_manager.connection() as conn:
            for entity in self.backend_spec.entities:
                try:
                    conn.execute(f"DELETE FROM {entity.name}")
                except Exception:
                    # Table might not exist yet
                    pass

    async def seed_from_data(
        self,
        data: dict[str, list[dict[str, Any]]],
    ) -> dict[str, int]:
        """
        Seed the database with provided data.

        Args:
            data: Dictionary mapping entity names to lists of records

        Returns:
            Dictionary mapping entity names to count of created records
        """
        counts: dict[str, int] = {}

        for entity_name, records in data.items():
            entity = self._entity_lookup.get(entity_name)
            if not entity:
                continue

            repo = self.repositories.get(entity_name)
            if not repo:
                continue

            created_count = 0
            for record in records:
                # Add ID if not present
                if "id" not in record:
                    record["id"] = str(uuid.uuid4())

                try:
                    await repo.create(record)
                    created_count += 1
                except Exception:
                    # Skip failed records
                    pass

            counts[entity_name] = created_count

        return counts

    async def seed_generated(
        self,
        entity_counts: dict[str, int] | None = None,
        default_count: int = 10,
    ) -> dict[str, int]:
        """
        Seed the database with generated data.

        Args:
            entity_counts: Dictionary mapping entity names to desired counts
            default_count: Default count for entities not specified

        Returns:
            Dictionary mapping entity names to count of created records
        """
        entity_counts = entity_counts or {}
        counts: dict[str, int] = {}

        # Generate and seed entities in order (to handle references)
        for entity in self.backend_spec.entities:
            entity_name = entity.name
            count = entity_counts.get(entity_name, default_count)

            repo = self.repositories.get(entity_name)
            if not repo:
                continue

            # Generate entities
            records = self.generator.generate_entities(entity, count)

            # Add IDs and create
            created_count = 0
            for record in records:
                record["id"] = str(uuid.uuid4())

                try:
                    await repo.create(record)
                    created_count += 1
                except Exception:
                    # Skip failed records
                    pass

            counts[entity_name] = created_count

        return counts

    async def seed_scenario(
        self,
        scenario_id: str,
        persona_id: str | None = None,
        seed_script: str | None = None,
        seed_data_path: str | None = None,
        inline_demo: dict[str, list[dict[str, Any]]] | None = None,
        entity_counts: dict[str, int] | None = None,
        default_count: int = 10,
    ) -> dict[str, int]:
        """
        Seed the database for a scenario.

        Uses the following precedence:
        1. Per-persona seed_script (if provided)
        2. Scenario seed_data_path (if provided)
        3. Inline demo block (if provided)
        4. Faker generation from entity schemas

        Args:
            scenario_id: Scenario identifier
            persona_id: Current persona ID
            seed_script: Path to per-persona seed script
            seed_data_path: Path to scenario-level seed data
            inline_demo: Inline demo data from DSL
            entity_counts: Entity counts for generated data
            default_count: Default count for generation

        Returns:
            Dictionary mapping entity names to count of created records
        """
        # Load demo data from available sources
        demo_data = self.loader.load_scenario_data(
            scenario_id=scenario_id,
            persona_id=persona_id,
            seed_script=seed_script,
            seed_data_path=seed_data_path,
            inline_demo=inline_demo,
        )

        if demo_data:
            # Seed from loaded data
            return await self.seed_from_data(demo_data)
        else:
            # Generate data
            return await self.seed_generated(
                entity_counts=entity_counts,
                default_count=default_count,
            )

    async def regenerate(
        self,
        entity_counts: dict[str, int] | None = None,
        default_count: int = 10,
    ) -> dict[str, int]:
        """
        Reset and regenerate demo data.

        Args:
            entity_counts: Dictionary mapping entity names to desired counts
            default_count: Default count for entities not specified

        Returns:
            Dictionary mapping entity names to count of created records
        """
        self.reset()
        return await self.seed_generated(
            entity_counts=entity_counts,
            default_count=default_count,
        )
