"""
AppSpec to BackendSpec Converters

Converts Dazzle AppSpec (IR) to BackendSpec.
"""

from typing import Any

from dazzle.core import ir
from dazzle_back.converters.entity_converter import convert_entities
from dazzle_back.converters.surface_converter import convert_surfaces_to_services
from dazzle_back.specs import BackendSpec
from dazzle_back.specs.channel import ChannelSpec, SendOperationSpec


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

    # Convert channels (preserving trigger info in metadata)
    channels = _convert_channels(appspec.channels)

    # Build the BackendSpec
    return BackendSpec(
        name=appspec.name,
        version=appspec.version,
        description=appspec.title,
        entities=entities,
        services=services,
        endpoints=endpoints,
        channels=channels,
        workspaces=appspec.workspaces,
        personas=appspec.personas,
    )


def _convert_channels(ir_channels: list[ir.ChannelSpec]) -> list[ChannelSpec]:
    """Convert IR ChannelSpecs to BackendSpec ChannelSpecs.

    Trigger info from IR send operations is serialized into channel
    metadata under ``send_triggers`` so the runtime can wire entity
    lifecycle events to channel dispatches.
    """
    result: list[ChannelSpec] = []
    for ch in ir_channels:
        send_ops: list[SendOperationSpec] = []
        send_triggers: dict[str, dict[str, Any]] = {}

        for op in ch.send_operations:
            send_ops.append(
                SendOperationSpec(
                    name=op.name,
                    message=op.message_name,
                    template=op.options.get("template"),
                    subject_template=op.options.get("subject_template"),
                )
            )
            if op.trigger:
                trigger_data: dict[str, Any] = {"kind": str(op.trigger.kind)}
                if op.trigger.entity_name:
                    trigger_data["entity_name"] = op.trigger.entity_name
                if op.trigger.event:
                    trigger_data["event"] = str(op.trigger.event)
                if op.trigger.field_name:
                    trigger_data["field_name"] = op.trigger.field_name
                if op.trigger.field_value:
                    trigger_data["field_value"] = op.trigger.field_value
                if op.trigger.from_state:
                    trigger_data["from_state"] = op.trigger.from_state
                if op.trigger.to_state:
                    trigger_data["to_state"] = op.trigger.to_state
                send_triggers[op.name] = trigger_data

        metadata: dict[str, Any] = {}
        if send_triggers:
            metadata["send_triggers"] = send_triggers

        result.append(
            ChannelSpec(
                name=ch.name,
                kind=ch.kind.value,
                provider=ch.provider,
                send_operations=send_ops,
                metadata=metadata,
            )
        )
    return result


__all__ = [
    "convert_appspec_to_backend",
    "convert_entities",
    "convert_surfaces_to_services",
]
