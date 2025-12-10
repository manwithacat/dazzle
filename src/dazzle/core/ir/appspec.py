"""
Application specification types for DAZZLE IR.

This module contains the top-level AppSpec that represents
a complete, linked application definition.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .archetype import ArchetypeSpec
from .domain import DomainSpec, EntitySpec
from .e2e import FixtureSpec, FlowPriority, FlowSpec
from .experiences import ExperienceSpec
from .fields import FieldType
from .foreign_models import ForeignModelSpec
from .integrations import IntegrationSpec
from .layout import UXLayouts
from .services import APISpec, DomainServiceSpec
from .surfaces import SurfaceSpec
from .tests import TestSpec
from .workspaces import WorkspaceSpec


class AppSpec(BaseModel):
    """
    Complete application specification.

    This is the root of the IR tree and represents a fully merged,
    linked application definition.

    Attributes:
        name: Application name
        title: Human-readable title
        version: Version string
        archetypes: List of archetype specifications (v0.7.1)
        domain: Domain specification (entities)
        surfaces: List of surface specifications
        workspaces: List of workspace specifications
        experiences: List of experience specifications
        apis: List of external API specifications
        domain_services: List of domain service specifications (v0.5.0)
        foreign_models: List of foreign model specifications
        integrations: List of integration specifications
        tests: API-focused test specifications
        e2e_flows: E2E user journey flows (semantic E2E testing)
        fixtures: Test fixtures for E2E testing
        metadata: Additional metadata
        ux: Semantic layout engine configuration
    """

    name: str
    title: str | None = None
    version: str = "0.1.0"
    archetypes: list[ArchetypeSpec] = Field(default_factory=list)  # v0.7.1
    domain: DomainSpec
    surfaces: list[SurfaceSpec] = Field(default_factory=list)
    workspaces: list[WorkspaceSpec] = Field(default_factory=list)  # UX extension (old)
    experiences: list[ExperienceSpec] = Field(default_factory=list)
    apis: list[APISpec] = Field(default_factory=list)
    domain_services: list[DomainServiceSpec] = Field(default_factory=list)  # v0.5.0
    foreign_models: list[ForeignModelSpec] = Field(default_factory=list)
    integrations: list[IntegrationSpec] = Field(default_factory=list)
    tests: list[TestSpec] = Field(default_factory=list)
    e2e_flows: list[FlowSpec] = Field(default_factory=list)  # Semantic E2E flows (v0.3.2)
    fixtures: list[FixtureSpec] = Field(default_factory=list)  # Test fixtures (v0.3.2)
    metadata: dict[str, Any] = Field(default_factory=dict)
    ux: UXLayouts | None = None  # Semantic layout engine (v0.3)

    model_config = ConfigDict(frozen=True)

    def get_entity(self, name: str) -> EntitySpec | None:
        """Get entity by name."""
        return self.domain.get_entity(name)

    def get_archetype(self, name: str) -> ArchetypeSpec | None:
        """Get archetype by name."""
        for archetype in self.archetypes:
            if archetype.name == name:
                return archetype
        return None

    def get_surface(self, name: str) -> SurfaceSpec | None:
        """Get surface by name."""
        for surface in self.surfaces:
            if surface.name == name:
                return surface
        return None

    def get_workspace(self, name: str) -> WorkspaceSpec | None:
        """Get workspace by name."""
        for workspace in self.workspaces:
            if workspace.name == name:
                return workspace
        return None

    def get_experience(self, name: str) -> ExperienceSpec | None:
        """Get experience by name."""
        for experience in self.experiences:
            if experience.name == name:
                return experience
        return None

    def get_api(self, name: str) -> APISpec | None:
        """Get external API by name."""
        for api in self.apis:
            if api.name == name:
                return api
        return None

    def get_domain_service(self, name: str) -> DomainServiceSpec | None:
        """Get domain service by name."""
        for service in self.domain_services:
            if service.name == name:
                return service
        return None

    def get_test(self, name: str) -> TestSpec | None:
        """Get test by name."""
        for test in self.tests:
            if test.name == name:
                return test
        return None

    def get_foreign_model(self, name: str) -> ForeignModelSpec | None:
        """Get foreign model by name."""
        for fm in self.foreign_models:
            if fm.name == name:
                return fm
        return None

    def get_integration(self, name: str) -> IntegrationSpec | None:
        """Get integration by name."""
        for integration in self.integrations:
            if integration.name == name:
                return integration
        return None

    def get_flow(self, flow_id: str) -> FlowSpec | None:
        """Get E2E flow by ID."""
        for flow in self.e2e_flows:
            if flow.id == flow_id:
                return flow
        return None

    def get_fixture(self, fixture_id: str) -> FixtureSpec | None:
        """Get fixture by ID."""
        for fixture in self.fixtures:
            if fixture.id == fixture_id:
                return fixture
        return None

    def get_flows_by_entity(self, entity: str) -> list[FlowSpec]:
        """Get all E2E flows for a given entity."""
        return [f for f in self.e2e_flows if f.entity == entity]

    def get_flows_by_priority(self, priority: FlowPriority) -> list[FlowSpec]:
        """Get all E2E flows with given priority."""
        return [f for f in self.e2e_flows if f.priority == priority]

    @property
    def type_catalog(self) -> dict[str, list[FieldType]]:
        """
        Extract catalog of all field types used in the application.

        Returns a mapping of field names to the types they use across
        all entities and foreign models. Useful for:
        - Stack generators building type mappings
        - Detecting type inconsistencies (same field name, different types)
        - Schema evolution analysis

        Returns:
            Dict mapping field names to list of FieldType objects
        """
        catalog: dict[str, list[FieldType]] = {}

        # Collect from entities
        for entity in self.domain.entities:
            for field in entity.fields:
                if field.name not in catalog:
                    catalog[field.name] = []
                # Only add if not already present (avoid duplicates)
                if field.type not in catalog[field.name]:
                    catalog[field.name].append(field.type)

        # Collect from foreign models
        for foreign_model in self.foreign_models:
            for field in foreign_model.fields:
                if field.name not in catalog:
                    catalog[field.name] = []
                if field.type not in catalog[field.name]:
                    catalog[field.name].append(field.type)

        return catalog

    def get_field_type_conflicts(self) -> list[str]:
        """
        Detect fields with the same name but different types.

        Returns:
            List of warning messages about type conflicts
        """
        conflicts = []
        for field_name, types in self.type_catalog.items():
            if len(types) > 1:
                type_descriptions = [
                    f"{t.kind.value}"
                    + (
                        f"({t.max_length})"
                        if t.max_length
                        else f"({t.precision},{t.scale})"
                        if t.precision
                        else f"[{','.join(t.enum_values)}]"
                        if t.enum_values
                        else f" {t.ref_entity}"
                        if t.ref_entity
                        else ""
                    )
                    for t in types
                ]
                conflicts.append(
                    f"Field '{field_name}' has inconsistent types: {', '.join(type_descriptions)}"
                )
        return conflicts
