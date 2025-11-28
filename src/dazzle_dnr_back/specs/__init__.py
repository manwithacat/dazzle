"""
BackendSpec type definitions.

This module exports all backend specification types.
"""

from dazzle_dnr_back.specs.entity import (
    EntitySpec,
    FieldSpec,
    RelationSpec,
    RelationKind,
    ValidatorSpec,
    ValidatorKind,
    ScalarType,
    EnumType,
    RefType,
    FieldType,
)
from dazzle_dnr_back.specs.service import (
    ServiceSpec,
    SchemaSpec,
    SchemaFieldSpec,
    DomainOperation,
    OperationKind,
    EffectSpec,
    BusinessRuleSpec,
)
from dazzle_dnr_back.specs.endpoint import (
    EndpointSpec,
    HttpMethod,
    RateLimitSpec,
)
from dazzle_dnr_back.specs.auth import (
    AuthRuleSpec,
    TenancyRuleSpec,
    PermissionSpec,
    RoleSpec,
)
from dazzle_dnr_back.specs.backend_spec import BackendSpec

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
