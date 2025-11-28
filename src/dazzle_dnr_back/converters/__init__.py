"""
AppSpec to BackendSpec Converters

Converts Dazzle AppSpec (IR) to BackendSpec.
"""

from dazzle.core import ir
from dazzle_dnr_back.converters.entity_converter import convert_entities
from dazzle_dnr_back.converters.surface_converter import convert_surfaces_to_services
from dazzle_dnr_back.specs import BackendSpec


def convert_appspec_to_backend(appspec: ir.AppSpec) -> BackendSpec:
    """
    Convert a complete Dazzle AppSpec to DNR BackendSpec.

    This is the main entry point for converting Dazzle's internal representation
    to the framework-agnostic BackendSpec.

    Args:
        appspec: Complete Dazzle application specification

    Returns:
        DNR BackendSpec with entities, services, and endpoints

    Example:
        >>> from dazzle.core.linker import build_appspec
        >>> appspec = build_appspec(modules, project_root)
        >>> backend_spec = convert_appspec_to_backend(appspec)
    """
    # Convert entities
    entities = convert_entities(appspec.domain.entities)

    # Convert surfaces to services and endpoints
    services, endpoints = convert_surfaces_to_services(
        appspec.surfaces,
        appspec.domain,
    )

    # Build the BackendSpec
    return BackendSpec(
        name=appspec.name,
        version=appspec.version,
        description=appspec.title,
        entities=entities,
        services=services,
        endpoints=endpoints,
    )


__all__ = [
    "convert_appspec_to_backend",
    "convert_entities",
    "convert_surfaces_to_services",
]
