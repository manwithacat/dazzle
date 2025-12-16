"""
AsyncAPI schema generation from AppSpec.

Generates AsyncAPI 3.0 specifications from DAZZLE AppSpec event model,
including all topics, events, and subscriptions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dazzle.core.ir import AppSpec, EntitySpec
    from dazzle.core.ir.eventing import EventSpec, TopicSpec


def generate_asyncapi(spec: AppSpec) -> dict[str, Any]:
    """
    Generate AsyncAPI 3.0 specification from AppSpec.

    Args:
        spec: The application specification

    Returns:
        AsyncAPI 3.0 specification as a dictionary
    """
    asyncapi: dict[str, Any] = {
        "asyncapi": "3.0.0",
        "info": {
            "title": f"{spec.name} Event API",
            "version": spec.version,
            "description": _build_description(spec),
        },
        "defaultContentType": "application/json",
        "servers": {
            "development": {
                "host": "localhost:9092",
                "protocol": "kafka",
                "description": "Development Kafka broker",
            }
        },
        "channels": {},
        "operations": {},
        "components": {
            "messages": {},
            "schemas": {},
        },
    }

    # Generate from event model if present
    if spec.event_model:
        _add_event_model(asyncapi, spec)

    # Generate from HLESS streams if present
    if spec.streams:
        _add_hless_streams(asyncapi, spec)

    # Add entity schemas for payloads
    for entity in spec.domain.entities:
        _add_entity_schema(asyncapi, entity)

    return asyncapi


def _build_description(spec: AppSpec) -> str:
    """Build description for the AsyncAPI spec."""
    parts = [spec.title or f"Event API for {spec.name}"]

    if spec.event_model:
        topic_count = len(spec.event_model.topics)
        event_count = len(spec.event_model.events)
        parts.append(f"\n\nTopics: {topic_count}, Events: {event_count}")

    if spec.streams:
        stream_count = len(spec.streams)
        parts.append(f"\n\nHLESS Streams: {stream_count}")

    return "".join(parts)


def _add_event_model(asyncapi: dict[str, Any], spec: AppSpec) -> None:
    """Add channels and messages from event model."""
    if not spec.event_model:
        return

    # Add channels for each topic
    for topic in spec.event_model.topics:
        _add_topic_channel(asyncapi, topic, spec)

    # Add messages for each event
    for event in spec.event_model.events:
        _add_event_message(asyncapi, event, spec)


def _add_topic_channel(asyncapi: dict[str, Any], topic: TopicSpec, spec: AppSpec) -> None:
    """Add a channel for a topic."""
    channel_name = f"app.{topic.name}"

    # Get all events for this topic
    events = spec.event_model.events_for_topic(topic.name) if spec.event_model else []
    message_refs = [{"$ref": f"#/components/messages/{event.name}"} for event in events]

    asyncapi["channels"][channel_name] = {
        "address": channel_name,
        "description": topic.description or f"Events for {topic.name}",
        "messages": {event.name: message_refs[i] for i, event in enumerate(events)},
        "bindings": {
            "kafka": {
                "partitions": 3,
                "replicas": 1,
                "topicConfiguration": {
                    "retention.ms": topic.retention_days * 24 * 60 * 60 * 1000,
                },
            }
        },
    }

    # Add publish operation
    asyncapi["operations"][f"publish_{topic.name}"] = {
        "action": "send",
        "channel": {"$ref": f"#/channels/{channel_name}"},
        "summary": f"Publish events to {topic.name}",
        "description": f"Publish events to the {channel_name} topic",
    }

    # Add subscribe operation
    asyncapi["operations"][f"subscribe_{topic.name}"] = {
        "action": "receive",
        "channel": {"$ref": f"#/channels/{channel_name}"},
        "summary": f"Subscribe to {topic.name} events",
        "description": f"Receive events from the {channel_name} topic",
    }


def _add_event_message(asyncapi: dict[str, Any], event: EventSpec, spec: AppSpec) -> None:
    """Add a message definition for an event."""
    message: dict[str, Any] = {
        "name": event.name,
        "title": event.name,
        "summary": event.description or f"{event.name} event",
        "contentType": "application/json",
        "headers": {
            "$ref": "#/components/schemas/EventHeaders",
        },
    }

    # Build payload schema
    if event.payload_entity:
        # Reference entity schema
        message["payload"] = {
            "$ref": f"#/components/schemas/{event.payload_entity}",
        }
    elif event.custom_fields:
        # Inline schema from custom fields
        message["payload"] = _build_custom_payload_schema(event)
    else:
        # Empty payload
        message["payload"] = {"type": "object"}

    # Add bindings
    message["bindings"] = {
        "kafka": {
            "key": {
                "type": "string",
                "description": "Partition key for ordering",
            }
        }
    }

    asyncapi["components"]["messages"][event.name] = message

    # Ensure headers schema exists
    if "EventHeaders" not in asyncapi["components"]["schemas"]:
        asyncapi["components"]["schemas"]["EventHeaders"] = {
            "type": "object",
            "properties": {
                "event_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "Unique event identifier",
                },
                "event_type": {
                    "type": "string",
                    "description": "Event type (e.g., app.orders.OrderCreated)",
                },
                "event_version": {
                    "type": "string",
                    "description": "Event schema version",
                },
                "correlation_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "Correlation ID for tracing",
                },
                "causation_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "ID of the event that caused this event",
                },
                "timestamp": {
                    "type": "string",
                    "format": "date-time",
                    "description": "Event timestamp",
                },
                "tenant_id": {
                    "type": "string",
                    "description": "Tenant identifier (if multi-tenant)",
                },
            },
            "required": ["event_id", "event_type", "timestamp"],
        }


def _build_custom_payload_schema(event: EventSpec) -> dict[str, Any]:
    """Build JSON Schema for custom event fields."""
    properties: dict[str, Any] = {}
    required: list[str] = []

    type_mapping = {
        "uuid": {"type": "string", "format": "uuid"},
        "str": {"type": "string"},
        "string": {"type": "string"},
        "int": {"type": "integer"},
        "integer": {"type": "integer"},
        "float": {"type": "number"},
        "number": {"type": "number"},
        "bool": {"type": "boolean"},
        "boolean": {"type": "boolean"},
        "datetime": {"type": "string", "format": "date-time"},
        "date": {"type": "string", "format": "date"},
        "json": {"type": "object"},
        "object": {"type": "object"},
        "array": {"type": "array"},
    }

    for field in event.custom_fields:
        field_schema = type_mapping.get(field.field_type.lower(), {"type": "string"}).copy()

        if field.description:
            field_schema["description"] = field.description

        properties[field.name] = field_schema

        if field.required:
            required.append(field.name)

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }

    if required:
        schema["required"] = required

    return schema


def _add_hless_streams(asyncapi: dict[str, Any], spec: AppSpec) -> None:
    """Add channels from HLESS streams."""
    from dazzle.core.ir.hless import RecordKind

    for stream in spec.streams:
        channel_name = stream.name

        # Determine channel description based on record kind
        kind_descriptions = {
            RecordKind.INTENT: "Intent stream - commands/requests",
            RecordKind.FACT: "Fact stream - verified outcomes",
            RecordKind.OBSERVATION: "Observation stream - raw external data",
            RecordKind.DERIVATION: "Derivation stream - computed data",
        }

        description = kind_descriptions.get(
            stream.record_kind, f"{stream.record_kind.value} stream"
        )

        asyncapi["channels"][channel_name] = {
            "address": channel_name,
            "description": description,
            "messages": {
                "record": {
                    "$ref": f"#/components/messages/{stream.name}Record",
                }
            },
            "bindings": {
                "kafka": {
                    "partitions": 3,
                    "replicas": 1,
                }
            },
        }

        # Add message for stream
        asyncapi["components"]["messages"][f"{stream.name}Record"] = {
            "name": f"{stream.name}Record",
            "title": f"{stream.name} Record",
            "summary": f"Record for {stream.name} ({stream.record_kind.value})",
            "contentType": "application/json",
            "headers": {"$ref": "#/components/schemas/HLESSHeaders"},
            "payload": {
                "type": "object",
                "description": f"Payload for {stream.name}",
            },
        }

        # Add operations
        asyncapi["operations"][f"publish_{stream.name}"] = {
            "action": "send",
            "channel": {"$ref": f"#/channels/{channel_name}"},
            "summary": f"Publish to {stream.name}",
        }

        asyncapi["operations"][f"subscribe_{stream.name}"] = {
            "action": "receive",
            "channel": {"$ref": f"#/channels/{channel_name}"},
            "summary": f"Subscribe to {stream.name}",
        }

    # Add HLESS headers schema
    if spec.streams and "HLESSHeaders" not in asyncapi["components"]["schemas"]:
        asyncapi["components"]["schemas"]["HLESSHeaders"] = {
            "type": "object",
            "properties": {
                "record_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "Unique record identifier",
                },
                "record_kind": {
                    "type": "string",
                    "enum": ["intent", "fact", "observation", "derivation"],
                    "description": "HLESS record classification",
                },
                "t_event": {
                    "type": "string",
                    "format": "date-time",
                    "description": "When the event occurred in reality",
                },
                "t_log": {
                    "type": "string",
                    "format": "date-time",
                    "description": "When the event was logged",
                },
                "t_process": {
                    "type": "string",
                    "format": "date-time",
                    "description": "When the event was processed",
                },
                "idempotency_key": {
                    "type": "string",
                    "description": "Key for idempotent processing",
                },
                "correlation_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "Correlation ID for tracing",
                },
            },
            "required": ["record_id", "record_kind", "t_log"],
        }


def _add_entity_schema(asyncapi: dict[str, Any], entity: EntitySpec) -> None:
    """Add JSON Schema for an entity (used as event payload)."""
    from dazzle.core.ir import FieldModifier

    properties: dict[str, Any] = {}
    required: list[str] = []

    type_mapping = {
        "uuid": {"type": "string", "format": "uuid"},
        "str": {"type": "string"},
        "text": {"type": "string"},
        "int": {"type": "integer"},
        "float": {"type": "number"},
        "decimal": {"type": "string", "format": "decimal"},
        "bool": {"type": "boolean"},
        "date": {"type": "string", "format": "date"},
        "datetime": {"type": "string", "format": "date-time"},
        "time": {"type": "string", "format": "time"},
        "json": {"type": "object"},
        "email": {"type": "string", "format": "email"},
        "url": {"type": "string", "format": "uri"},
        "phone": {"type": "string"},
        "money": {"type": "string", "format": "decimal"},
        "state": {"type": "string"},
        "image": {"type": "string", "format": "uri"},
        "file": {"type": "string", "format": "uri"},
        "ref": {"type": "string", "format": "uuid"},
    }

    for field in entity.fields:
        type_kind = field.type.kind.value
        prop_schema: dict[str, Any] = type_mapping.get(type_kind, {"type": "string"}).copy()

        if field.type.max_length:
            prop_schema["maxLength"] = field.type.max_length

        if field.type.enum_values:
            prop_schema["enum"] = field.type.enum_values

        if field.default is not None:
            # Convert default value to JSON-compatible type
            default_val = field.default
            if hasattr(default_val, "value"):
                default_val = default_val.value
            prop_schema["default"] = default_val

        properties[field.name] = prop_schema

        if FieldModifier.REQUIRED in field.modifiers and field.default is None:
            required.append(field.name)

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }

    if required:
        schema["required"] = required

    if entity.title:
        schema["description"] = entity.title

    asyncapi["components"]["schemas"][entity.name] = schema


def asyncapi_to_yaml(asyncapi: dict[str, Any]) -> str:
    """Convert AsyncAPI dict to YAML string."""
    try:
        import yaml

        return yaml.dump(asyncapi, default_flow_style=False, sort_keys=False)
    except ImportError:
        import json

        return json.dumps(asyncapi, indent=2)


def asyncapi_to_json(asyncapi: dict[str, Any]) -> str:
    """Convert AsyncAPI dict to JSON string."""
    import json

    return json.dumps(asyncapi, indent=2)
