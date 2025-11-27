"""
Tests for BackendSpec types.

Basic validation and construction tests to ensure specs work correctly.
"""

import pytest
from dazzle_dnr_back.specs import (
    BackendSpec,
    EntitySpec,
    FieldSpec,
    FieldType,
    ScalarType,
    ServiceSpec,
    EndpointSpec,
    HttpMethod,
    DomainOperation,
    OperationKind,
    SchemaSpec,
    AuthRuleSpec,
    RoleSpec,
)


def test_field_spec_creation():
    """Test creating a FieldSpec."""
    field = FieldSpec(
        name="email",
        type=FieldType(kind="scalar", scalar_type=ScalarType.EMAIL),
        required=True,
    )
    assert field.name == "email"
    assert field.type.scalar_type == ScalarType.EMAIL
    assert field.required is True


def test_entity_spec_creation():
    """Test creating an EntitySpec."""
    entity = EntitySpec(
        name="Client",
        label="Client",
        fields=[
            FieldSpec(
                name="name",
                type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                required=True,
            ),
            FieldSpec(
                name="email",
                type=FieldType(kind="scalar", scalar_type=ScalarType.EMAIL),
                required=True,
            ),
        ],
    )
    assert entity.name == "Client"
    assert len(entity.fields) == 2
    assert entity.get_field("name") is not None
    assert entity.get_field("nonexistent") is None


def test_service_spec_creation():
    """Test creating a ServiceSpec."""
    service = ServiceSpec(
        name="create_client",
        domain_operation=DomainOperation(
            kind=OperationKind.CREATE,
            entity="Client",
        ),
        inputs=SchemaSpec(),
        outputs=SchemaSpec(),
    )
    assert service.name == "create_client"
    assert service.is_crud is True
    assert service.target_entity == "Client"


def test_endpoint_spec_creation():
    """Test creating an EndpointSpec."""
    endpoint = EndpointSpec(
        name="create_client_endpoint",
        service="create_client",
        method=HttpMethod.POST,
        path="/api/clients",
    )
    assert endpoint.name == "create_client_endpoint"
    assert endpoint.method == HttpMethod.POST
    assert endpoint.full_path == "POST /api/clients"


def test_backend_spec_creation():
    """Test creating a complete BackendSpec."""
    spec = BackendSpec(
        name="test_backend",
        version="1.0.0",
        entities=[
            EntitySpec(
                name="Client",
                fields=[
                    FieldSpec(
                        name="name",
                        type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                    )
                ],
            )
        ],
        services=[
            ServiceSpec(
                name="list_clients",
                domain_operation=DomainOperation(
                    kind=OperationKind.LIST,
                    entity="Client",
                ),
                inputs=SchemaSpec(),
                outputs=SchemaSpec(),
            )
        ],
        endpoints=[
            EndpointSpec(
                name="list_clients_endpoint",
                service="list_clients",
                method=HttpMethod.GET,
                path="/api/clients",
            )
        ],
    )

    assert spec.name == "test_backend"
    assert len(spec.entities) == 1
    assert len(spec.services) == 1
    assert len(spec.endpoints) == 1

    # Test query methods
    assert spec.get_entity("Client") is not None
    assert spec.get_service("list_clients") is not None
    assert spec.get_endpoint("list_clients_endpoint") is not None

    # Test stats
    stats = spec.stats
    assert stats["entities"] == 1
    assert stats["services"] == 1
    assert stats["endpoints"] == 1
    assert stats["crud_services"] == 1


def test_backend_spec_validation():
    """Test BackendSpec reference validation."""
    # Valid spec
    spec = BackendSpec(
        name="valid_backend",
        entities=[
            EntitySpec(name="Client", fields=[])
        ],
        services=[
            ServiceSpec(
                name="list_clients",
                domain_operation=DomainOperation(
                    kind=OperationKind.LIST,
                    entity="Client",
                ),
                inputs=SchemaSpec(),
                outputs=SchemaSpec(),
            )
        ],
        endpoints=[
            EndpointSpec(
                name="list_endpoint",
                service="list_clients",
                method=HttpMethod.GET,
                path="/api/clients",
            )
        ],
    )
    errors = spec.validate_references()
    assert len(errors) == 0

    # Invalid spec: endpoint references non-existent service
    bad_spec = BackendSpec(
        name="invalid_backend",
        endpoints=[
            EndpointSpec(
                name="bad_endpoint",
                service="nonexistent_service",
                method=HttpMethod.GET,
                path="/api/bad",
            )
        ],
    )
    errors = bad_spec.validate_references()
    assert len(errors) > 0
    assert "nonexistent_service" in errors[0]


def test_immutability():
    """Test that specs are immutable (frozen)."""
    entity = EntitySpec(name="Test", fields=[])

    with pytest.raises((AttributeError, TypeError)):
        entity.name = "NewName"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
