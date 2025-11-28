"""
BackendSpec type definitions.

This module exports all backend specification types.
"""

from dazzle_dnr_back.specs.auth import (
    AuthRuleSpec,
    PermissionSpec,
    RoleSpec,
    TenancyRuleSpec,
)
from dazzle_dnr_back.specs.backend_spec import BackendSpec
from dazzle_dnr_back.specs.endpoint import (
    EndpointSpec,
    HttpMethod,
    RateLimitSpec,
)
from dazzle_dnr_back.specs.entity import (
    EntitySpec,
    EnumType,
    FieldSpec,
    FieldType,
    RefType,
    RelationKind,
    RelationSpec,
    ScalarType,
    ValidatorKind,
    ValidatorSpec,
)
from dazzle_dnr_back.specs.service import (
    BusinessRuleSpec,
    DomainOperation,
    EffectSpec,
    OperationKind,
    SchemaFieldSpec,
    SchemaSpec,
    ServiceSpec,
)

__all__ = [
    # Entity types
    "EntitySpec",
    "FieldSpec",
    "RelationSpec",
    "RelationKind",
    "ValidatorSpec",
    "ValidatorKind",
    "ScalarType",
    "EnumType",
    "RefType",
    "FieldType",
    # Service types
    "ServiceSpec",
    "SchemaSpec",
    "SchemaFieldSpec",
    "DomainOperation",
    "OperationKind",
    "EffectSpec",
    "BusinessRuleSpec",
    # Endpoint types
    "EndpointSpec",
    "HttpMethod",
    "RateLimitSpec",
    # Auth types
    "AuthRuleSpec",
    "TenancyRuleSpec",
    "PermissionSpec",
    "RoleSpec",
    # Main spec
    "BackendSpec",
]
