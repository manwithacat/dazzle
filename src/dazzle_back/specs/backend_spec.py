"""
BackendSpec - Main backend specification aggregate.

This is the root type that contains all backend specifications.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from dazzle_back.specs.auth import AuthRuleSpec, RoleSpec, TenancyRuleSpec
from dazzle_back.specs.channel import ChannelSpec, MessageSpec
from dazzle_back.specs.endpoint import EndpointSpec
from dazzle_back.specs.entity import EntitySpec
from dazzle_back.specs.service import ServiceSpec


class BackendSpec(BaseModel):
    """
    Complete backend specification.

    This is the aggregate root for all backend specifications, containing:
    - Entities (domain models)
    - Services (domain operations)
    - Endpoints (HTTP/RPC mappings)
    - Roles (authorization)
    - Auth rules (authentication)
    - Tenancy rules (multi-tenancy)

    Example:
        BackendSpec(
            name="invoice_system",
            version="1.0.0",
            entities=[
                EntitySpec(name="Client", fields=[...]),
                EntitySpec(name="Invoice", fields=[...]),
            ],
            services=[
                ServiceSpec(name="create_invoice", ...),
            ],
            endpoints=[
                EndpointSpec(name="create_invoice_endpoint", service="create_invoice", ...),
            ],
            roles=[
                RoleSpec(name="admin", permissions=["*"]),
            ]
        )
    """

    # Metadata
    name: str = Field(description="Backend name")
    version: str = Field(default="1.0.0", description="Backend version")
    description: str | None = Field(default=None, description="Backend description")

    # Core specifications
    entities: list[EntitySpec] = Field(default_factory=list, description="Entity specifications")
    services: list[ServiceSpec] = Field(default_factory=list, description="Service specifications")
    endpoints: list[EndpointSpec] = Field(
        default_factory=list, description="Endpoint specifications"
    )

    # Messaging (v0.9)
    channels: list[ChannelSpec] = Field(
        default_factory=list, description="Messaging channel specifications"
    )
    messages: list[MessageSpec] = Field(
        default_factory=list, description="Message type specifications"
    )

    # Authorization
    roles: list[RoleSpec] = Field(default_factory=list, description="Role definitions")
    default_auth: AuthRuleSpec | None = Field(
        default=None, description="Default auth rule for all endpoints"
    )

    # Multi-tenancy
    tenancy: TenancyRuleSpec = Field(
        default_factory=TenancyRuleSpec, description="Tenancy configuration"
    )

    # Additional metadata
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    model_config = ConfigDict(frozen=True)

    # =========================================================================
    # Query methods
    # =========================================================================

    def get_entity(self, name: str) -> EntitySpec | None:
        """Get entity by name."""
        for entity in self.entities:
            if entity.name == name:
                return entity
        return None

    def get_service(self, name: str) -> ServiceSpec | None:
        """Get service by name."""
        for service in self.services:
            if service.name == name:
                return service
        return None

    def get_endpoint(self, name: str) -> EndpointSpec | None:
        """Get endpoint by name."""
        for endpoint in self.endpoints:
            if endpoint.name == name:
                return endpoint
        return None

    def get_role(self, name: str) -> RoleSpec | None:
        """Get role by name."""
        for role in self.roles:
            if role.name == name:
                return role
        return None

    def get_endpoints_for_service(self, service_name: str) -> list[EndpointSpec]:
        """Get all endpoints that invoke a given service."""
        return [ep for ep in self.endpoints if ep.service == service_name]

    def get_services_for_entity(self, entity_name: str) -> list[ServiceSpec]:
        """Get all services that operate on a given entity."""
        return [svc for svc in self.services if svc.domain_operation.entity == entity_name]

    def get_channel(self, name: str) -> ChannelSpec | None:
        """Get channel by name."""
        for channel in self.channels:
            if channel.name == name:
                return channel
        return None

    def get_message(self, name: str) -> MessageSpec | None:
        """Get message type by name."""
        for message in self.messages:
            if message.name == name:
                return message
        return None

    def get_messages_for_channel(self, channel_name: str) -> list[MessageSpec]:
        """Get all message types associated with a channel."""
        return [msg for msg in self.messages if msg.channel == channel_name]

    # =========================================================================
    # Validation
    # =========================================================================

    def validate_references(self) -> list[str]:
        """
        Validate all references between specs.

        Returns list of error messages (empty if valid).
        """
        errors = []

        # Check that endpoint services exist
        for endpoint in self.endpoints:
            if not self.get_service(endpoint.service):
                errors.append(
                    f"Endpoint '{endpoint.name}' references unknown service '{endpoint.service}'"
                )

        # Check that service entities exist
        for service in self.services:
            if service.domain_operation.entity:
                if not self.get_entity(service.domain_operation.entity):
                    errors.append(
                        f"Service '{service.name}' references unknown entity '{service.domain_operation.entity}'"
                    )

        # Check that relation targets exist
        for entity in self.entities:
            for relation in entity.relations:
                if not self.get_entity(relation.to_entity):
                    errors.append(
                        f"Entity '{entity.name}' relation '{relation.name}' references unknown entity '{relation.to_entity}'"
                    )

        # Check that ref field targets exist
        for entity in self.entities:
            for field in entity.fields:
                if field.type.kind == "ref" and field.type.ref_entity:
                    if not self.get_entity(field.type.ref_entity):
                        errors.append(
                            f"Entity '{entity.name}' field '{field.name}' references unknown entity '{field.type.ref_entity}'"
                        )

        return errors

    # =========================================================================
    # Stats
    # =========================================================================

    @property
    def stats(self) -> dict[str, int]:
        """Get statistics about this backend spec."""
        return {
            "entities": len(self.entities),
            "services": len(self.services),
            "endpoints": len(self.endpoints),
            "roles": len(self.roles),
            "crud_services": sum(1 for svc in self.services if svc.is_crud),
            "custom_services": sum(1 for svc in self.services if not svc.is_crud),
            "channels": len(self.channels),
            "messages": len(self.messages),
        }
