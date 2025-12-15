"""
Module-level IR types for DAZZLE.

This module contains module fragment and module IR definitions
representing parser output for single DSL files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .archetype import ArchetypeSpec
from .domain import EntitySpec
from .e2e import FixtureSpec, FlowSpec
from .eventing import (
    EventModelSpec,
    ProjectionSpec,
    SubscribeSpec,
)
from .experiences import ExperienceSpec
from .foreign_models import ForeignModelSpec
from .integrations import IntegrationSpec
from .messaging import (
    AssetSpec,
    ChannelSpec,
    DocumentSpec,
    MessageSpec,
    TemplateSpec,
)
from .personas import PersonaSpec
from .scenarios import ScenarioSpec
from .services import APISpec, DomainServiceSpec
from .surfaces import SurfaceSpec
from .tests import TestSpec
from .workspaces import WorkspaceSpec


class AppConfigSpec(BaseModel):
    """
    Application-level configuration (v0.9.5).

    Parsed from the optional app config block:
        app MyApp "My Application":
          description: "..."
          multi_tenant: true
          audit_trail: true
          security_profile: standard

    Attributes:
        description: Human-readable description of the app
        multi_tenant: Whether the app supports multi-tenancy
        audit_trail: Whether to enable audit trail on all entities
        security_profile: Security profile level (basic, standard, strict)
        features: Additional feature flags as key-value pairs
    """

    description: str | None = None
    multi_tenant: bool = False
    audit_trail: bool = False
    security_profile: str = "basic"  # basic | standard | strict
    features: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)


class ModuleFragment(BaseModel):
    """
    Parsed fragments from a single module.

    This is the output of parsing a single DSL file.

    Attributes:
        archetypes: Archetypes defined in this module (v0.7.1)
        entities: Entities defined in this module
        surfaces: Surfaces defined in this module
        workspaces: Workspaces defined in this module
        experiences: Experiences defined in this module
        apis: External APIs defined in this module
        domain_services: Domain services defined in this module (v0.5.0)
        foreign_models: Foreign models defined in this module
        integrations: Integrations defined in this module
        tests: Tests defined in this module
        e2e_flows: E2E flow specifications defined in this module
        fixtures: Test fixtures defined in this module
    """

    archetypes: list[ArchetypeSpec] = Field(default_factory=list)  # v0.7.1
    entities: list[EntitySpec] = Field(default_factory=list)
    surfaces: list[SurfaceSpec] = Field(default_factory=list)
    workspaces: list[WorkspaceSpec] = Field(default_factory=list)  # UX extension
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
    # Messaging Channels (v0.9.0)
    messages: list[MessageSpec] = Field(default_factory=list)
    channels: list[ChannelSpec] = Field(default_factory=list)
    assets: list[AssetSpec] = Field(default_factory=list)
    documents: list[DocumentSpec] = Field(default_factory=list)
    templates: list[TemplateSpec] = Field(default_factory=list)
    # Event-First Architecture (v0.18.0)
    event_model: EventModelSpec | None = None
    subscriptions: list[SubscribeSpec] = Field(default_factory=list)
    projections: list[ProjectionSpec] = Field(default_factory=list)
    # Publish directives are stored on entities, not here

    model_config = ConfigDict(frozen=True)


class ModuleIR(BaseModel):
    """
    Complete IR for a single module (file).

    Attributes:
        name: Module name (e.g., "vat_tools.core")
        file: Source file path
        app_name: App name (if declared in this module)
        app_title: App title (if declared in this module)
        app_config: App-level configuration (v0.9.5)
        uses: List of module names this module depends on
        fragment: Parsed DSL fragments
    """

    name: str
    file: Path
    app_name: str | None = None
    app_title: str | None = None
    app_config: AppConfigSpec | None = None  # v0.9.5
    uses: list[str] = Field(default_factory=list)
    fragment: ModuleFragment = Field(default_factory=ModuleFragment)

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)  # for Path
