"""
DAZZLE Intermediate Representation (IR) types.

This package contains all IR type definitions for the DAZZLE DSL.
Types are organized into logical submodules for maintainability.

All types are re-exported from this package for backward compatibility.
"""

# Fields
# App Specification
from .appspec import (
    AppSpec,
)

# Conditions
from .conditions import (
    Comparison,
    ComparisonOperator,
    ConditionExpr,
    ConditionValue,
    FunctionCall,
    LogicalOperator,
)

# Domain
from .domain import (
    AccessSpec,
    AuthContext,
    Constraint,
    ConstraintKind,
    DomainSpec,
    EntitySpec,
    PermissionKind,
    PermissionRule,
    VisibilityRule,
)

# E2E Flows
from .e2e import (
    A11yRule,
    E2ETestSpec,
    FixtureSpec,
    FlowAssertion,
    FlowAssertionKind,
    FlowPrecondition,
    FlowPriority,
    FlowSpec,
    FlowStep,
    FlowStepKind,
    UsabilityRule,
)

# Experiences
from .experiences import (
    ExperienceSpec,
    ExperienceStep,
    StepKind,
    StepTransition,
    TransitionEvent,
)
from .fields import (
    FieldModifier,
    FieldSpec,
    FieldType,
    FieldTypeKind,
)

# Foreign Models
from .foreign_models import (
    ForeignConstraint,
    ForeignConstraintKind,
    ForeignModelSpec,
)

# Integrations
from .integrations import (
    Expression,
    IntegrationAction,
    IntegrationSpec,
    IntegrationSync,
    MappingRule,
    MatchRule,
    SyncMode,
)

# Layout Engine
from .layout import (
    AttentionSignalKind,
    LayoutArchetype,
    LayoutPlan,
    LayoutSignal,
    LayoutSurface,
    PersonaLayout,
    UXLayouts,
    WorkspaceLayout,
)

# Module-level IR
from .module import (
    ModuleFragment,
    ModuleIR,
)

# Services
from .services import (
    AuthKind,
    AuthProfile,
    ServiceSpec,
)

# Surfaces
from .surfaces import (
    Outcome,
    OutcomeKind,
    SurfaceAccessSpec,
    SurfaceAction,
    SurfaceElement,
    SurfaceMode,
    SurfaceSection,
    SurfaceSpec,
    SurfaceTrigger,
)

# Tests
from .tests import (
    TestAction,
    TestActionKind,
    TestAssertion,
    TestAssertionKind,
    TestComparisonOperator,
    TestSetupStep,
    TestSpec,
)

# UX Semantic Layer
from .ux import (
    AttentionSignal,
    PersonaVariant,
    SignalLevel,
    SortSpec,
    UXSpec,
)

# Workspaces
from .workspaces import (
    DisplayMode,
    WorkspaceRegion,
    WorkspaceSpec,
)

__all__ = [
    # Fields
    "FieldTypeKind",
    "FieldType",
    "FieldModifier",
    "FieldSpec",
    # Conditions
    "ComparisonOperator",
    "LogicalOperator",
    "ConditionValue",
    "FunctionCall",
    "Comparison",
    "ConditionExpr",
    # Domain
    "ConstraintKind",
    "Constraint",
    "AuthContext",
    "VisibilityRule",
    "PermissionKind",
    "PermissionRule",
    "AccessSpec",
    "EntitySpec",
    "DomainSpec",
    # UX
    "SignalLevel",
    "AttentionSignal",
    "PersonaVariant",
    "SortSpec",
    "UXSpec",
    # Surfaces
    "SurfaceMode",
    "SurfaceTrigger",
    "OutcomeKind",
    "Outcome",
    "SurfaceElement",
    "SurfaceSection",
    "SurfaceAction",
    "SurfaceAccessSpec",
    "SurfaceSpec",
    # Workspaces
    "DisplayMode",
    "WorkspaceRegion",
    "WorkspaceSpec",
    # Experiences
    "StepKind",
    "TransitionEvent",
    "StepTransition",
    "ExperienceStep",
    "ExperienceSpec",
    # Services
    "AuthKind",
    "AuthProfile",
    "ServiceSpec",
    # Foreign Models
    "ForeignConstraintKind",
    "ForeignConstraint",
    "ForeignModelSpec",
    # Integrations
    "Expression",
    "MappingRule",
    "IntegrationAction",
    "SyncMode",
    "MatchRule",
    "IntegrationSync",
    "IntegrationSpec",
    # Tests
    "TestActionKind",
    "TestAssertionKind",
    "TestComparisonOperator",
    "TestSetupStep",
    "TestAction",
    "TestAssertion",
    "TestSpec",
    # E2E
    "FlowPriority",
    "FlowStepKind",
    "FlowAssertionKind",
    "FlowAssertion",
    "FlowStep",
    "FlowPrecondition",
    "FlowSpec",
    "FixtureSpec",
    "UsabilityRule",
    "A11yRule",
    "E2ETestSpec",
    # Layout
    "AttentionSignalKind",
    "LayoutSignal",
    "WorkspaceLayout",
    "PersonaLayout",
    "LayoutArchetype",
    "LayoutSurface",
    "LayoutPlan",
    "UXLayouts",
    # Module
    "ModuleFragment",
    "ModuleIR",
    # AppSpec
    "AppSpec",
]
