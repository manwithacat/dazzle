"""
BackendSpec type definitions.

This module exports all backend specification types.
"""

from dazzle_back.specs.auth import (
    AccessAuthContext,
    AccessComparisonKind,
    AccessConditionSpec,
    AccessLogicalKind,
    AccessOperationKind,
    AccessPolicyEffect,
    AuthRuleSpec,
    EntityAccessSpec,
    PermissionRuleSpec,
    PermissionSpec,
    RoleSpec,
    TenancyRuleSpec,
    VisibilityRuleSpec,
)
from dazzle_back.specs.backend_spec import BackendSpec
from dazzle_back.specs.channel import (
    ChannelSpec,
    MessageFieldSpec,
    MessageSpec,
    ReceiveOperationSpec,
    SendOperationSpec,
)
from dazzle_back.specs.endpoint import (
    EndpointSpec,
    HttpMethod,
    RateLimitSpec,
)
from dazzle_back.specs.entity import (
    AggregateFunctionKind,
    ArithmeticOperatorKind,
    AutoTransitionSpec,
    ComputedExprSpec,
    ComputedFieldSpec,
    DurationUnitKind,
    EntitySpec,
    EnumType,
    FieldSpec,
    FieldType,
    InvariantComparisonKind,
    InvariantExprSpec,
    InvariantLogicalKind,
    InvariantSpec,
    RefType,
    RelationKind,
    RelationSpec,
    ScalarType,
    StateMachineSpec,
    StateTransitionSpec,
    TimeUnit,
    TransitionGuardSpec,
    TransitionTrigger,
    ValidatorKind,
    ValidatorSpec,
)
from dazzle_back.specs.service import (
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
    # Computed field types
    "AggregateFunctionKind",
    "ArithmeticOperatorKind",
    "ComputedExprSpec",
    "ComputedFieldSpec",
    # Invariant types
    "InvariantSpec",
    "InvariantExprSpec",
    "InvariantComparisonKind",
    "InvariantLogicalKind",
    "DurationUnitKind",
    # State machine types
    "StateMachineSpec",
    "StateTransitionSpec",
    "TransitionGuardSpec",
    "AutoTransitionSpec",
    "TimeUnit",
    "TransitionTrigger",
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
    # Entity access types (v0.7.0)
    "AccessConditionSpec",
    "AccessComparisonKind",
    "AccessLogicalKind",
    "AccessAuthContext",
    "AccessOperationKind",
    "AccessPolicyEffect",
    "VisibilityRuleSpec",
    "PermissionRuleSpec",
    "EntityAccessSpec",
    # Channel/Messaging types (v0.9)
    "ChannelSpec",
    "MessageSpec",
    "MessageFieldSpec",
    "SendOperationSpec",
    "ReceiveOperationSpec",
    # Main spec
    "BackendSpec",
]
