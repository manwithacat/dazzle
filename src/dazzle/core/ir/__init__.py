"""
DAZZLE Intermediate Representation (IR) types.

This package contains all IR type definitions for the DAZZLE DSL.
Types are organized into logical submodules for maintainability.

All types are re-exported from this package for backward compatibility.
"""

# Archetypes (v0.7.1, v0.10.3)
# Fields
# App Specification
from .appspec import (
    AppSpec,
)
from .archetype import (
    ArchetypeKind,
    ArchetypeSpec,
)

# Computed Fields
from .computed import (
    AggregateCall,
    AggregateFunction,
    ArithmeticExpr,
    ArithmeticOperator,
    ComputedExpr,
    ComputedFieldSpec,
    FieldReference,
    LiteralValue,
)

# Conditions
from .conditions import (
    Comparison,
    ComparisonOperator,
    ConditionExpr,
    ConditionValue,
    FunctionCall,
    LogicalOperator,
    RoleCheck,
)

# Date Expressions (v0.10.2)
from .dates import (
    DateArithmeticExpr,
    DateArithmeticOp,
    DateExpr,
    DateLiteral,
    DateLiteralKind,
    DurationLiteral,
)

# Demo Data Blueprint (v0.12.0)
from .demo_blueprint import (
    BlueprintContainer,
    DemoDataBlueprint,
    EntityBlueprint,
    FieldPattern,
    FieldStrategy,
    PersonaBlueprint,
    TenantBlueprint,
)

# Domain
from .domain import (
    AccessSpec,
    AuthContext,
    Constraint,
    ConstraintKind,
    DomainSpec,
    EntitySpec,
    ExampleRecord,
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

# Eventing (v0.18.0 Event-First Architecture)
from .eventing import (
    EventFieldSpec,
    EventHandlerSpec,
    EventModelSpec,
    EventSpec,
    EventTriggerKind,
    ProjectionAction,
    ProjectionHandlerSpec,
    ProjectionSpec,
    PublishSpec,
    SubscribeSpec,
    TopicSpec,
)

# HLESS - High-Level Event Semantics (v0.19.0)
from .hless import (
    DerivationLineage,
    DerivationType,
    ExpectedOutcome,
    HLESSMode,
    HLESSPragma,
    HLESSViolation,
    IdempotencyStrategy,
    IdempotencyType,
    OutcomeCondition,
    RebuildStrategy,
    RecordKind,
    SchemaCompatibility,
    SideEffectPolicy,
    StreamSchema,
    StreamSpec,
    TimeSemantics,
    WindowSpec,
    WindowType,
    get_default_idempotency,
)
from .hless_validator import (
    HLESSValidator,
    ValidationResult,
    validate_stream,
    validate_streams_with_cross_references,
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
    RelationshipBehavior,
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

# Invariants
from .invariant import (
    ComparisonExpr,
    DurationExpr,
    DurationUnit,
    InvariantExpr,
    InvariantFieldRef,
    InvariantLiteral,
    InvariantSpec,
    LogicalExpr,
    NotExpr,
)
from .invariant import (
    ComparisonOperator as InvariantComparisonOperator,
)
from .invariant import (
    LogicalOperator as InvariantLogicalOperator,
)

# Layout Engine
from .layout import (
    AttentionSignalKind,
    LayoutArchetype,  # Backward compat alias for Stage
    LayoutPlan,
    LayoutSignal,
    LayoutSurface,
    PersonaLayout,
    Stage,
    UXLayouts,
    WorkspaceLayout,
)

# Messaging Channels (v0.9.0)
from .messaging import (
    AssetKind,
    AssetSpec,
    ChannelConfigSpec,
    ChannelKind,
    ChannelSpec,
    DeliveryMode,
    DocumentFormat,
    DocumentSpec,
    EntityEvent,
    MappingSpec,
    MatchPatternKind,
    MatchPatternSpec,
    MessageFieldSpec,
    MessageSpec,
    ProviderConfigSpec,
    ReceiveActionKind,
    ReceiveActionSpec,
    ReceiveMappingSpec,
    ReceiveOperationSpec,
    SendOperationSpec,
    SendTriggerKind,
    SendTriggerSpec,
    TemplateAttachmentSpec,
    TemplateSpec,
    ThrottleExceedAction,
    ThrottleScope,
    ThrottleSpec,
)

# Module-level IR
from .module import (
    AppConfigSpec,
    ModuleFragment,
    ModuleIR,
)

# Personas (v0.8.5 Dazzle Bar)
from .personas import (
    PersonaSpec,
)

# Scenarios (v0.8.5 Dazzle Bar)
from .scenarios import (
    DemoFixture,
    PersonaScenarioEntry,
    ScenarioSpec,
)

# Security (v0.11.0)
from .security import (
    SecurityConfig,
    SecurityProfile,
)

# Services (External APIs and Domain Services)
from .services import (
    APISpec,
    AuthKind,
    AuthProfile,
    DomainServiceKind,
    DomainServiceSpec,
    ServiceFieldSpec,
    StubLanguage,
)

# SiteSpec (v0.16.0 Public Site Shell)
from .sitespec import (
    AuthEntrySpec,
    AuthPageMode,
    AuthPageSpec,
    AuthPagesSpec,
    AuthProvider,
    BrandSpec,
    ContentFormat,
    ContentSourceSpec,
    CTASpec,
    FAQItem,
    FeatureItem,
    FooterColumnSpec,
    FooterSpec,
    IntegrationsSpec,
    LayoutSpec,
    LegalPageSpec,
    LegalPagesSpec,
    LogoItem,
    LogoMode,
    LogoSpec,
    MediaKind,
    MediaSpec,
    NavItemSpec,
    NavSpec,
    PageKind,
    PageSpec,
    PricingTier,
    SectionKind,
    SectionSpec,
    SiteSpec,
    StatItem,
    StepItem,
    TestimonialItem,
    ThemeKind,
    create_default_sitespec,
)

# State Machines (v0.7.0)
from .state_machine import (
    AutoTransitionSpec,
    StateMachineSpec,
    StateTransition,
    TimeUnit,
    TransitionGuard,
    TransitionTrigger,
)

# Stories (v0.12.0 Behaviour Layer)
from .stories import (
    StoriesContainer,
    StorySpec,
    StoryStatus,
    StoryTrigger,
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

# Test Design (v0.13.0)
from .test_design import (
    TestDesignAction,
    TestDesignSpec,
    TestDesignStatus,
    TestDesignStep,
    TestDesignTrigger,
    TestGap,
    TestGapAnalysis,
    TestGapCategory,
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
    # Archetypes (v0.7.1, v0.10.3)
    "ArchetypeKind",
    "ArchetypeSpec",
    # Fields
    "FieldTypeKind",
    "FieldType",
    "FieldModifier",
    "FieldSpec",
    "RelationshipBehavior",
    # Conditions
    "ComparisonOperator",
    "LogicalOperator",
    "ConditionValue",
    "FunctionCall",
    "RoleCheck",
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
    "ExampleRecord",
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
    # Services (External APIs and Domain Services)
    "APISpec",
    "AuthKind",
    "AuthProfile",
    "DomainServiceKind",
    "DomainServiceSpec",
    "ServiceFieldSpec",
    "StubLanguage",
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
    "Stage",
    "LayoutArchetype",  # Backward compat alias for Stage
    "LayoutSurface",
    "LayoutPlan",
    "UXLayouts",
    # Module
    "AppConfigSpec",
    "ModuleFragment",
    "ModuleIR",
    # AppSpec
    "AppSpec",
    # State Machines
    "TimeUnit",
    "TransitionTrigger",
    "TransitionGuard",
    "AutoTransitionSpec",
    "StateTransition",
    "StateMachineSpec",
    # Computed Fields
    "AggregateFunction",
    "ArithmeticOperator",
    "FieldReference",
    "AggregateCall",
    "ArithmeticExpr",
    "LiteralValue",
    "ComputedExpr",
    "ComputedFieldSpec",
    # Date Expressions (v0.10.2)
    "DateLiteralKind",
    "DateLiteral",
    "DateArithmeticOp",
    "DurationLiteral",
    "DateArithmeticExpr",
    "DateExpr",
    # Invariants
    "InvariantComparisonOperator",
    "InvariantLogicalOperator",
    "DurationUnit",
    "InvariantFieldRef",
    "InvariantLiteral",
    "DurationExpr",
    "ComparisonExpr",
    "LogicalExpr",
    "NotExpr",
    "InvariantExpr",
    "InvariantSpec",
    # Personas (v0.8.5 Dazzle Bar)
    "PersonaSpec",
    # Scenarios (v0.8.5 Dazzle Bar)
    "DemoFixture",
    "PersonaScenarioEntry",
    "ScenarioSpec",
    # Security (v0.11.0)
    "SecurityConfig",
    "SecurityProfile",
    # Stories (v0.12.0 Behaviour Layer)
    "StoriesContainer",
    "StorySpec",
    "StoryStatus",
    "StoryTrigger",
    # Demo Data Blueprint (v0.12.0)
    "BlueprintContainer",
    "DemoDataBlueprint",
    "EntityBlueprint",
    "FieldPattern",
    "FieldStrategy",
    "PersonaBlueprint",
    "TenantBlueprint",
    # Messaging Channels (v0.9.0)
    "AssetKind",
    "AssetSpec",
    "ChannelConfigSpec",
    "ChannelKind",
    "ChannelSpec",
    "DeliveryMode",
    "DocumentFormat",
    "DocumentSpec",
    "EntityEvent",
    "MatchPatternKind",
    "MatchPatternSpec",
    "MappingSpec",
    "MessageFieldSpec",
    "MessageSpec",
    "ProviderConfigSpec",
    "ReceiveActionKind",
    "ReceiveActionSpec",
    "ReceiveMappingSpec",
    "ReceiveOperationSpec",
    "SendOperationSpec",
    "SendTriggerKind",
    "SendTriggerSpec",
    "TemplateAttachmentSpec",
    "TemplateSpec",
    "ThrottleExceedAction",
    "ThrottleScope",
    "ThrottleSpec",
    # Test Design (v0.13.0)
    "TestDesignAction",
    "TestDesignSpec",
    "TestDesignStatus",
    "TestDesignStep",
    "TestDesignTrigger",
    "TestGap",
    "TestGapAnalysis",
    "TestGapCategory",
    # Eventing (v0.18.0 Event-First Architecture)
    "EventFieldSpec",
    "EventHandlerSpec",
    "EventModelSpec",
    "EventSpec",
    "EventTriggerKind",
    "ProjectionAction",
    "ProjectionHandlerSpec",
    "ProjectionSpec",
    "PublishSpec",
    "SubscribeSpec",
    "TopicSpec",
    # HLESS - High-Level Event Semantics (v0.19.0)
    "DerivationLineage",
    "DerivationType",
    "ExpectedOutcome",
    "HLESSMode",
    "HLESSPragma",
    "HLESSValidator",
    "HLESSViolation",
    "IdempotencyStrategy",
    "IdempotencyType",
    "OutcomeCondition",
    "RebuildStrategy",
    "RecordKind",
    "SchemaCompatibility",
    "SideEffectPolicy",
    "StreamSchema",
    "StreamSpec",
    "TimeSemantics",
    "ValidationResult",
    "WindowSpec",
    "WindowType",
    "get_default_idempotency",
    "validate_stream",
    "validate_streams_with_cross_references",
    # SiteSpec (v0.16.0 Public Site Shell)
    "AuthEntrySpec",
    "AuthPageMode",
    "AuthPagesSpec",
    "AuthPageSpec",
    "AuthProvider",
    "BrandSpec",
    "ContentFormat",
    "ContentSourceSpec",
    "CTASpec",
    "FAQItem",
    "FeatureItem",
    "FooterColumnSpec",
    "FooterSpec",
    "IntegrationsSpec",
    "LayoutSpec",
    "LegalPagesSpec",
    "LegalPageSpec",
    "LogoItem",
    "LogoMode",
    "LogoSpec",
    "MediaKind",
    "MediaSpec",
    "NavItemSpec",
    "NavSpec",
    "PageKind",
    "PageSpec",
    "PricingTier",
    "SectionKind",
    "SectionSpec",
    "SiteSpec",
    "StatItem",
    "StepItem",
    "TestimonialItem",
    "ThemeKind",
    "create_default_sitespec",
]
