"""
Module-level IR types for DAZZLE.

This module contains module fragment and module IR definitions
representing parser output for single DSL files.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .domain import EntitySpec
from .e2e import FixtureSpec, FlowSpec
from .experiences import ExperienceSpec
from .foreign_models import ForeignModelSpec
from .integrations import IntegrationSpec
from .services import APISpec
from .surfaces import SurfaceSpec
from .tests import TestSpec
from .workspaces import WorkspaceSpec


class ModuleFragment(BaseModel):
    """
    Parsed fragments from a single module.

    This is the output of parsing a single DSL file.

    Attributes:
        entities: Entities defined in this module
        surfaces: Surfaces defined in this module
        workspaces: Workspaces defined in this module
        experiences: Experiences defined in this module
        apis: External APIs defined in this module
        foreign_models: Foreign models defined in this module
        integrations: Integrations defined in this module
        tests: Tests defined in this module
        e2e_flows: E2E flow specifications defined in this module
        fixtures: Test fixtures defined in this module
    """

    entities: list[EntitySpec] = Field(default_factory=list)
    surfaces: list[SurfaceSpec] = Field(default_factory=list)
    workspaces: list[WorkspaceSpec] = Field(default_factory=list)  # UX extension
    experiences: list[ExperienceSpec] = Field(default_factory=list)
    apis: list[APISpec] = Field(default_factory=list)
    foreign_models: list[ForeignModelSpec] = Field(default_factory=list)
    integrations: list[IntegrationSpec] = Field(default_factory=list)
    tests: list[TestSpec] = Field(default_factory=list)
    e2e_flows: list[FlowSpec] = Field(default_factory=list)  # Semantic E2E flows (v0.3.2)
    fixtures: list[FixtureSpec] = Field(default_factory=list)  # Test fixtures (v0.3.2)

    model_config = ConfigDict(frozen=True)


class ModuleIR(BaseModel):
    """
    Complete IR for a single module (file).

    Attributes:
        name: Module name (e.g., "vat_tools.core")
        file: Source file path
        app_name: App name (if declared in this module)
        app_title: App title (if declared in this module)
        uses: List of module names this module depends on
        fragment: Parsed DSL fragments
    """

    name: str
    file: Path
    app_name: str | None = None
    app_title: str | None = None
    uses: list[str] = Field(default_factory=list)
    fragment: ModuleFragment = Field(default_factory=ModuleFragment)

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)  # for Path
