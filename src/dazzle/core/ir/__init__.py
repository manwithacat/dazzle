"""
DAZZLE Intermediate Representation (IR) types.

This package contains all IR type definitions for the DAZZLE DSL.
Types are organized into logical submodules for maintainability.

All types are re-exported from this package for backward compatibility.
"""

# Fidelity Scoring
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
    AuditConfig,
    AuthContext,
    Constraint,
    ConstraintKind,
    DomainSpec,
    EntitySpec,
    ExampleRecord,
    PermissionKind,
    PermissionRule,
    PolicyEffect,
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

# Email Events (v0.18.0 Phase F)
from .email import (
    BusinessReference,
    EmailAttachmentRef,
    EmailBouncedEvent,
    EmailFailedEvent,
    EmailProvider,
    EmailSendRequestedEvent,
    EmailSentEvent,
    NormalizedMailEvent,
    RawMailEvent,
    get_email_stream_definitions,
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

# Experiences
from .experiences import (
    ExperienceSpec,
    ExperienceStep,
    StepKind,
    StepTransition,
    TransitionEvent,
)
from .fidelity import (
    FidelityGap,
    FidelityGapCategory,
    FidelityReport,
    SurfaceFidelityScore,
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

# Governance (v0.18.0 Event-First Architecture - Issue #25)
from .governance import (
    ClassificationSpec,
    DataClassification,
    DataProductSpec,
    DataProductsSpec,
    DataProductTransform,
    ErasurePolicy,
    ErasureSpec,
    InterfaceAuthMethod,
    InterfaceEndpointSpec,
    InterfaceFormat,
    InterfaceSpec,
    InterfacesSpec,
    PoliciesSpec,
    RetentionPolicy,
    TenancyMode,
    TenancySpec,
    TenantIsolationSpec,
    TenantProvisioningSpec,
    TopicNamespaceMode,
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

# Ledgers (v0.24.0 TigerBeetle Integration)
from .ledgers import (
    AccountFlag,
    AccountType,
    AmountExpr,
    LedgerAccountRef,
    LedgerSpec,
    LedgerSyncSpec,
    SyncTrigger,
    TransactionExecution,
    TransactionPriority,
    TransactionSpec,
    TransferFlag,
    TransferSpec,
    ValidationRule,
)

# LLM - Large Language Model (v0.21.0 - Issue #33)
from .llm import (
    ArtifactKind,
    ArtifactRefSpec,
    ArtifactStore,
    LLMConfigSpec,
    LLMIntentSpec,
    LLMModelSpec,
    LLMProvider,
    LoggingPolicySpec,
    ModelTier,
    PIIAction,
    PIIPolicySpec,
    RetryBackoff,
    RetryPolicySpec,
)

# LLM Event Streams (v0.21.0 - Issue #33)
from .llm_events import (
    LLM_DERIVATION_STREAM,
    LLM_FACT_STREAM,
    LLM_INTENT_STREAM,
    LLM_OBSERVATION_STREAM,
    LLM_SCHEMAS,
    create_llm_derivation_stream,
    create_llm_fact_stream,
    create_llm_intent_stream,
    create_llm_observation_stream,
    get_all_llm_streams,
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

# Money Value Object (v0.20.0)
from .money import (
    CURRENCY_SCALES,
    DEFAULT_CURRENCY_SCALE,
    MONEY_FIELD_PATTERNS,
    Money,
    MoneyWithScale,
    from_money,
    get_currency_scale,
    is_money_field_name,
    money_from_dict,
    to_money,
)

# Personas (v0.8.5 Dazzle Bar)
from .personas import (
    PersonaSpec,
)

# Process Workflows (v0.23.0)
from .process import (
    CompensationSpec,
    FieldAssignment,
    HumanTaskOutcome,
    HumanTaskSpec,
    InputMapping,
    OverlapPolicy,
    ParallelFailurePolicy,
    ProcessEventEmission,
    ProcessInputField,
    ProcessOutputField,
    ProcessSpec,
    ProcessStepSpec,
    ProcessTriggerKind,
    ProcessTriggerSpec,
    RetryConfig,
    ScheduleSpec,
)
from .process import RetryBackoff as ProcessRetryBackoff
from .process import StepKind as ProcessStepKind

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

# Stories (v0.12.0 Behaviour Layer, v0.22.0 DSL syntax)
from .stories import (
    StoriesContainer,
    StoryCondition,
    StoryException,
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
    WorkspaceAccessLevel,
    WorkspaceAccessSpec,
    WorkspaceRegion,
    WorkspaceSpec,
)

__all__ = [
    # Fidelity Scoring
    "FidelityGap",
    "FidelityGapCategory",
    "FidelityReport",
    "SurfaceFidelityScore",
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
    "PolicyEffect",
    "PermissionKind",
    "PermissionRule",
    "AuditConfig",
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
    "WorkspaceAccessLevel",
    "WorkspaceAccessSpec",
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
    # Ledgers (v0.24.0 TigerBeetle Integration)
    "AccountFlag",
    "AccountType",
    "AmountExpr",
    "LedgerAccountRef",
    "LedgerSpec",
    "LedgerSyncSpec",
    "SyncTrigger",
    "TransactionExecution",
    "TransactionPriority",
    "TransactionSpec",
    "TransferFlag",
    "TransferSpec",
    "ValidationRule",
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
    # Process Workflows (v0.23.0)
    "CompensationSpec",
    "FieldAssignment",
    "HumanTaskOutcome",
    "HumanTaskSpec",
    "InputMapping",
    "OverlapPolicy",
    "ParallelFailurePolicy",
    "ProcessEventEmission",
    "ProcessInputField",
    "ProcessOutputField",
    "ProcessRetryBackoff",
    "ProcessSpec",
    "ProcessStepSpec",
    "ProcessStepKind",
    "ProcessTriggerKind",
    "ProcessTriggerSpec",
    "RetryConfig",
    "ScheduleSpec",
    # Scenarios (v0.8.5 Dazzle Bar)
    "DemoFixture",
    "PersonaScenarioEntry",
    "ScenarioSpec",
    # Security (v0.11.0)
    "SecurityConfig",
    "SecurityProfile",
    # Stories (v0.12.0 Behaviour Layer, v0.22.0 DSL syntax)
    "StoriesContainer",
    "StoryCondition",
    "StoryException",
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
    # Money Value Object (v0.20.0)
    "CURRENCY_SCALES",
    "DEFAULT_CURRENCY_SCALE",
    "MONEY_FIELD_PATTERNS",
    "Money",
    "MoneyWithScale",
    "from_money",
    "get_currency_scale",
    "is_money_field_name",
    "money_from_dict",
    "to_money",
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
    # LLM - Large Language Model (v0.21.0 - Issue #33)
    "ArtifactKind",
    "ArtifactRefSpec",
    "ArtifactStore",
    "LLMConfigSpec",
    "LLMIntentSpec",
    "LLMModelSpec",
    "LLMProvider",
    "LoggingPolicySpec",
    "ModelTier",
    "PIIAction",
    "PIIPolicySpec",
    "RetryBackoff",
    "RetryPolicySpec",
    # Governance (v0.18.0 Event-First Architecture - Issue #25)
    "ClassificationSpec",
    "DataClassification",
    "DataProductsSpec",
    "DataProductSpec",
    "DataProductTransform",
    "ErasurePolicy",
    "ErasureSpec",
    "InterfaceAuthMethod",
    "InterfaceEndpointSpec",
    "InterfaceFormat",
    "InterfacesSpec",
    "InterfaceSpec",
    "PoliciesSpec",
    "RetentionPolicy",
    "TenancyMode",
    "TenancySpec",
    "TenantIsolationSpec",
    "TenantProvisioningSpec",
    "TopicNamespaceMode",
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
