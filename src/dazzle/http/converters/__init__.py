"""
AppSpec to Backend Spec Converters

Converts Dazzle AppSpec (IR) to backend specification types.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dazzle.core import ir

if TYPE_CHECKING:
    from dazzle.http.specs.backend_spec import BackendSpec
from dazzle.http.converters.entity_converter import convert_entities
from dazzle.http.converters.surface_converter import convert_surfaces_to_services


def convert_appspec_to_backend(appspec: ir.AppSpec) -> BackendSpec:
    """Convert AppSpec to BackendSpec.

    Most code paths use AppSpec directly.
    """
    from dazzle.http.specs.backend_spec import BackendSpec

    entities = convert_entities(appspec.domain.entities)
    services, endpoints = convert_surfaces_to_services(appspec.surfaces, appspec.domain)

    return BackendSpec(
        name=appspec.name,
        version=appspec.version,
        description=appspec.title,
        entities=entities,
        services=services,
        endpoints=endpoints,
        workspaces=appspec.workspaces,
        surfaces=appspec.surfaces,
        personas=appspec.personas,
        audit_trail=appspec.audit_trail,
    )


__all__ = [
    "convert_appspec_to_backend",
    "convert_entities",
    "convert_surfaces_to_services",
]
