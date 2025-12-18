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
from .eventing import (
    EventModelSpec,
    ProjectionSpec,
    SubscribeSpec,
)
from .experiences import ExperienceSpec
from .fields import FieldType
from .foreign_models import ForeignModelSpec
from .governance import (
    DataProductsSpec,
    InterfacesSpec,
    PoliciesSpec,
    TenancySpec,
)
from .hless import (
    HLESSMode,
    HLESSPragma,
    StreamSpec,
)
from .integrations import IntegrationSpec
from .layout import UXLayouts
from .llm import (
    LLMConfigSpec,
    LLMIntentSpec,
    LLMModelSpec,
)
from .messaging import (
    AssetSpec,
    ChannelSpec,
    DocumentSpec,
    MessageSpec,
    TemplateSpec,
)
from .personas import PersonaSpec
from .process import (
    ProcessSpec,
    ScheduleSpec,
)
from .scenarios import ScenarioSpec
from .security import SecurityConfig
from .services import APISpec, DomainServiceSpec
from .stories import StorySpec
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
    personas: list[PersonaSpec] = Field(default_factory=list)  # v0.8.5 Dazzle Bar
    scenarios: list[ScenarioSpec] = Field(default_factory=list)  # v0.8.5 Dazzle Bar
    # Stories (v0.22.0 DSL syntax)
    stories: list[StorySpec] = Field(default_factory=list)
    # Messaging Channels (v0.9.0)
    messages: list[MessageSpec] = Field(default_factory=list)
    channels: list[ChannelSpec] = Field(default_factory=list)
    assets: list[AssetSpec] = Field(default_factory=list)
    documents: list[DocumentSpec] = Field(default_factory=list)
    templates: list[TemplateSpec] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    ux: UXLayouts | None = None  # Semantic layout engine (v0.3)
    security: SecurityConfig | None = None  # Security configuration (v0.11.0)
    # Event-First Architecture (v0.18.0)
    event_model: EventModelSpec | None = None
    subscriptions: list[SubscribeSpec] = Field(default_factory=list)
    projections: list[ProjectionSpec] = Field(default_factory=list)
    # HLESS - High-Level Event Semantics (v0.19.0)
    streams: list[StreamSpec] = Field(default_factory=list)
    hless_mode: HLESSMode = Field(default=HLESSMode.STRICT)
    hless_pragma: HLESSPragma | None = None
    # Governance sections (v0.18.0 Event-First Architecture - Issue #25)
    policies: PoliciesSpec | None = None
    tenancy: TenancySpec | None = None
    interfaces: InterfacesSpec | None = None
    data_products: DataProductsSpec | None = None
    # LLM Jobs as First-Class Events (v0.21.0 - Issue #33)
    llm_config: LLMConfigSpec | None = None
    llm_models: list[LLMModelSpec] = Field(default_factory=list)
    llm_intents: list[LLMIntentSpec] = Field(default_factory=list)
    # Process Workflows (v0.23.0)
    processes: list[ProcessSpec] = Field(default_factory=list)
    schedules: list[ScheduleSpec] = Field(default_factory=list)

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

    def get_persona(self, persona_id: str) -> PersonaSpec | None:
        """Get persona by ID."""
        for persona in self.personas:
            if persona.id == persona_id:
                return persona
        return None

    def get_scenario(self, scenario_id: str) -> ScenarioSpec | None:
        """Get scenario by ID."""
        for scenario in self.scenarios:
            if scenario.id == scenario_id:
                return scenario
        return None

    # Story getters (v0.22.0)

    def get_story(self, story_id: str) -> StorySpec | None:
        """Get story by ID."""
        for story in self.stories:
            if story.story_id == story_id:
                return story
        return None

    def get_stories_by_actor(self, actor: str) -> list[StorySpec]:
        """Get all stories for a given actor/persona."""
        return [s for s in self.stories if s.actor == actor]

    def get_stories_by_entity(self, entity_name: str) -> list[StorySpec]:
        """Get all stories involving a specific entity."""
        return [s for s in self.stories if entity_name in s.scope]

    # Messaging getters (v0.9.0)

    def get_message(self, name: str) -> MessageSpec | None:
        """Get message schema by name."""
        for message in self.messages:
            if message.name == name:
                return message
        return None

    def get_channel(self, name: str) -> ChannelSpec | None:
        """Get channel by name."""
        for channel in self.channels:
            if channel.name == name:
                return channel
        return None

    def get_asset(self, name: str) -> AssetSpec | None:
        """Get asset by name."""
        for asset in self.assets:
            if asset.name == name:
                return asset
        return None

    def get_document(self, name: str) -> DocumentSpec | None:
        """Get document by name."""
        for document in self.documents:
            if document.name == name:
                return document
        return None

    def get_template(self, name: str) -> TemplateSpec | None:
        """Get template by name."""
        for template in self.templates:
            if template.name == name:
                return template
        return None

    # HLESS getters (v0.19.0)

    def get_stream(self, name: str) -> StreamSpec | None:
        """Get stream by name."""
        for stream in self.streams:
            if stream.name == name:
                return stream
        return None

    # LLM getters (v0.21.0 - Issue #33)

    def get_llm_model(self, name: str) -> LLMModelSpec | None:
        """Get LLM model by name."""
        for model in self.llm_models:
            if model.name == name:
                return model
        return None

    def get_llm_intent(self, name: str) -> LLMIntentSpec | None:
        """Get LLM intent by name."""
        for intent in self.llm_intents:
            if intent.name == name:
                return intent
        return None

    # Process getters (v0.23.0)

    def get_process(self, name: str) -> ProcessSpec | None:
        """Get process by name."""
        for process in self.processes:
            if process.name == name:
                return process
        return None

    def get_schedule(self, name: str) -> ScheduleSpec | None:
        """Get schedule by name."""
        for schedule in self.schedules:
            if schedule.name == name:
                return schedule
        return None

    def get_processes_by_story(self, story_id: str) -> list[ProcessSpec]:
        """Get all processes that implement a specific story."""
        return [p for p in self.processes if story_id in p.implements]

    def get_schedules_by_story(self, story_id: str) -> list[ScheduleSpec]:
        """Get all schedules that implement a specific story."""
        return [s for s in self.schedules if story_id in s.implements]

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
