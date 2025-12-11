"""
Scenario specification types for DAZZLE IR.

This module contains scenario definitions for the Dazzle Bar
developer overlay. Scenarios represent different demo states
with per-persona configurations.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PersonaScenarioEntry(BaseModel):
    """
    Per-persona configuration within a scenario.

    Defines how a specific persona should experience a scenario,
    including their starting route and any persona-specific fixtures.

    Attributes:
        persona_id: Reference to the persona this entry configures
        start_route: Route to navigate to when this persona activates the scenario
        seed_script: Optional path to persona-specific fixture JSON file
    """

    persona_id: str
    start_route: str
    seed_script: str | None = None

    model_config = ConfigDict(frozen=True)


class DemoFixture(BaseModel):
    """
    Inline demo fixture for an entity.

    Represents demo data defined directly in DSL rather than external files.

    Attributes:
        entity: Entity name this fixture applies to
        records: List of record dictionaries with field values
    """

    entity: str
    records: list[dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


class ScenarioSpec(BaseModel):
    """
    A demo scenario with per-persona configurations.

    Scenarios allow developers to switch between different demo states
    (e.g., "empty state", "busy term", "error conditions") with
    persona-specific routing and fixtures.

    Attributes:
        id: Unique identifier for the scenario
        name: Human-readable scenario name
        description: Optional description of what this scenario demonstrates
        persona_entries: Per-persona configurations within this scenario
        seed_data_path: Optional path to global seed data JSON file
        demo_fixtures: Inline demo data defined in DSL
    """

    id: str
    name: str
    description: str | None = None
    persona_entries: list[PersonaScenarioEntry] = Field(default_factory=list)
    seed_data_path: str | None = None
    demo_fixtures: list[DemoFixture] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)

    def get_persona_entry(self, persona_id: str) -> PersonaScenarioEntry | None:
        """Get the scenario entry for a specific persona."""
        for entry in self.persona_entries:
            if entry.persona_id == persona_id:
                return entry
        return None

    def get_start_route(self, persona_id: str) -> str | None:
        """Get the starting route for a persona in this scenario."""
        entry = self.get_persona_entry(persona_id)
        return entry.start_route if entry else None

    def __str__(self) -> str:
        return f"Scenario({self.id}: {self.name})"
