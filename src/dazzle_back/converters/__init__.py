"""
AppSpec to Backend Spec Converters

Converts Dazzle AppSpec (IR) to backend specification types.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dazzle.core import ir

if TYPE_CHECKING:
    from dazzle_back.specs.backend_spec import BackendSpec
from dazzle_back.converters.entity_converter import convert_entities
from dazzle_back.converters.surface_converter import convert_surfaces_to_services
from dazzle_back.specs.channel import ChannelSpec, SendOperationSpec


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


def convert_appspec_to_backend(appspec: ir.AppSpec) -> BackendSpec:
    """Convert AppSpec to BackendSpec.

    Only used by the GraphQL subsystem which still requires BackendSpec.
    All other code paths now use AppSpec directly.
    """
    from dazzle_back.specs.backend_spec import BackendSpec

    entities = convert_entities(appspec.domain.entities)
    services, endpoints = convert_surfaces_to_services(appspec.surfaces, appspec.domain)
    channels = _convert_channels(appspec.channels)

    return BackendSpec(
        name=appspec.name,
        version=appspec.version,
        description=appspec.title,
        entities=entities,
        services=services,
        endpoints=endpoints,
        channels=channels,
        workspaces=appspec.workspaces,
        surfaces=appspec.surfaces,
        personas=appspec.personas,
        audit_trail=appspec.audit_trail,
    )


__all__ = [
    "_convert_channels",
    "convert_appspec_to_backend",
    "convert_entities",
    "convert_surfaces_to_services",
]
