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
# Approvals (v0.25.0)
from .approvals import (
    ApprovalEscalationSpec,
    ApprovalOutcomeSpec,
    ApprovalSpec,
)
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
    GrantCheck,
    LogicalOperator,
    RoleCheck,
    ViaBinding,
    ViaCondition,
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
    BulkConfig,
    BulkFormat,
    Constraint,
    ConstraintKind,
    DomainSpec,
    EntitySpec,
    ExampleRecord,
    GraphEdgeSpec,
    GraphNodeSpec,
    PermissionKind,
    PermissionRule,
    PolicyEffect,
    ScopeRule,
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

# Shared Enums (v0.25.0)
from .enums import (
    EnumSpec,
    EnumValueSpec,
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
    FlowContextVar,
    StepKind,
    StepPrefill,
    StepTransition,
    TransitionEvent,
)

# Expressions (v0.29.0 Typed Expression Language)
from .expressions import (
    BinaryExpr as ExprBinaryExpr,
)
from .expressions import (
    BinaryOp as ExprBinaryOp,
)
from .expressions import (
    DurationLiteral as ExprDurationLiteral,
)
from .expressions import (
    Expr,
    ExprType,
)
from .expressions import (
    FieldRef as ExprFieldRef,
)
from .expressions import (
    FuncCall as ExprFuncCall,
)
from .expressions import (
    IfExpr as ExprIfExpr,
)
from .expressions import (
    InExpr as ExprInExpr,
)
from .expressions import (
    Literal as ExprLiteral,
)
from .expressions import (
    UnaryExpr as ExprUnaryExpr,
)
from .expressions import (
    UnaryOp as ExprUnaryOp,
)

# Feedback Widget
from .feedback_widget import (
    FEEDBACK_REPORT_FIELDS,
    FeedbackWidgetSpec,
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

# Fitness (Agent-Led Fitness v1 — per-entity repr_fields)
from .fitness_repr import (
    FitnessSpec,
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

# Grants (v0.42.0 Runtime RBAC)
from .grants import (
    GrantApprovalMode,
    GrantExpiryMode,
    GrantRelationSpec,
    GrantSchemaSpec,
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
    AuthSpec,
    AuthType,
    ErrorAction,
    ErrorStrategy,
    Expression,
    HttpMethod,
    HttpRequestSpec,
    IntegrationAction,
    IntegrationMapping,
    IntegrationSpec,
    IntegrationSync,
    MappingRule,
    MappingTriggerSpec,
    MappingTriggerType,
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

# Islands (UI Islands)
from .islands import (
    IslandEventSpec,
    IslandPropSpec,
    IslandSpec,
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

# Lifecycle (ADR-0020)
from .lifecycle import (
    LifecycleSpec,
    LifecycleStateSpec,
    LifecycleTransitionSpec,
)

# LLM - Large Language Model (v0.21.0 - Issue #33)
from .llm import (
    AI_JOB_FIELDS,
    ArtifactKind,
    ArtifactRefSpec,
    ArtifactStore,
    LLMConfigSpec,
    LLMIntentSpec,
    LLMModelSpec,
    LLMProvider,
    LLMTriggerEvent,
    LLMTriggerSpec,
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

# Source locations (v0.31.0)
from .location import SourceLocation

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

# Notifications (v0.34.0)
from .notifications import (
    NotificationChannel,
    NotificationPreference,
    NotificationRecipient,
    NotificationSpec,
    NotificationTrigger,
)

# Runtime Parameters (v0.44.0)
from .params import ParamConstraints, ParamRef, ParamSpec

# Personas (v0.8.5)
from .personas import (
    PersonaSpec,
)

# PII annotations (v0.61.0)
from .pii import (
    PIIAnnotation,
    PIICategory,
    PIISensitivity,
)

# Predicate Algebra (Scope row-level security)
from .predicates import (
    BoolComposite,
    BoolOp,
    ColumnCheck,
    CompOp,
    Contradiction,
    ExistsBinding,
    ExistsCheck,
    PathCheck,
    ScopePredicate,
    Tautology,
    UserAttrCheck,
    ValueRef,
)

# Process Workflows (v0.23.0)
from .process import (
    CompensationSpec,
    EffectAction,
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
    StepEffect,
)
from .process import RetryBackoff as ProcessRetryBackoff
from .process import StepKind as ProcessStepKind

# Questions (v0.41.0 Convergent BDD)
from .questions import (
    QuestionSpec,
    QuestionStatus,
)

# Rhythms (v0.39.0 Longitudinal UX Evaluation)
from .rhythm import (
    Gap,
    GapsReport,
    GapsSummary,
    LifecycleReport,
    LifecycleStep,
    PhaseKind,
    PhaseSpec,
    RhythmSpec,
    SceneDimensionScore,
    SceneEvaluation,
    SceneSpec,
)

# Rules (v0.41.0 Convergent BDD)
from .rules import (
    RuleKind,
    RuleOrigin,
    RuleSpec,
    RuleStatus,
)

# Scenarios (v0.8.5)
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

# Seed Templates (v0.38.0)
from .seed import (
    SeedFieldTemplate,
    SeedStrategy,
    SeedTemplateSpec,
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

# SLA (v0.25.0)
from .sla import (
    BusinessHoursSpec,
    SLABreachActionSpec,
    SLAConditionSpec,
    SLASpec,
    SLATierSpec,
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
    StoryCondition,
    StoryException,
    StorySpec,
    StoryStatus,
    StoryTrigger,
)

# Subprocessor declarations (v0.61.0)
from .subprocessors import (
    ConsentCategory,
    DataCategory,
    LegalBasis,
    SubprocessorSpec,
)

# Surfaces
from .surfaces import (
    BusinessPriority,
    Outcome,
    OutcomeKind,
    RelatedDisplayMode,
    RelatedGroup,
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

# ThemeSpec YAML (v0.25.0 Declarative Theme)
from .themespec import (
    AttentionMapSpec,
    AttentionRule,
    ColorMode,
    DensityEnum,
    FontStackSpec,
    ImagerySpec,
    ImageryVocabulary,
    LayoutCompositionSpec,
    PaletteSpec,
    SemanticColorOverrides,
    ShadowPreset,
    ShapePreset,
    ShapeSpec,
    SpacingSpec,
    SurfaceCompositionRule,
    ThemeMetaSpec,
    ThemeSpecYAML,
    TypographyRatioPreset,
    TypographySpec,
    VisualTreatment,
)

# Triples (v0.50.0 IR Triple Enrichment)
from .triples import (
    ActionTriple,
    SurfaceActionTriple,
    SurfaceFieldTriple,
    VerifiableTriple,
    WidgetKind,
)

# UX Semantic Layer
from .ux import (
    AttentionSignal,
    BulkActionSpec,
    EmptyMessages,
    PersonaVariant,
    SignalLevel,
    SortSpec,
    UXSpec,
)

# Views (v0.25.0, v0.34.0 date-range reporting)
from .views import (
    TimeBucket,
    ViewFieldSpec,
    ViewSpec,
)

# Webhooks (v0.25.0)
from .webhooks import (
    WebhookAuthMethod,
    WebhookAuthSpec,
    WebhookEvent,
    WebhookPayloadSpec,
    WebhookRetrySpec,
    WebhookSpec,
)

# Workspaces
from .workspaces import (
    BucketRef,
    ContextSelectorSpec,
    DisplayMode,
    NavGroupSpec,
    NavItemIR,
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
    # PII (v0.61.0)
    "PIIAnnotation",
    "PIICategory",
    "PIISensitivity",
    # Subprocessors (v0.61.0)
    "ConsentCategory",
    "DataCategory",
    "LegalBasis",
    "SubprocessorSpec",
    # Conditions
    "ComparisonOperator",
    "LogicalOperator",
    "ConditionValue",
    "FunctionCall",
    "GrantCheck",
    "RoleCheck",
    "Comparison",
    "ConditionExpr",
    "ViaBinding",
    "ViaCondition",
    # Domain
    "BulkConfig",
    "BulkFormat",
    "ConstraintKind",
    "Constraint",
    "AuthContext",
    "VisibilityRule",
    "PolicyEffect",
    "PermissionKind",
    "PermissionRule",
    "AuditConfig",
    "AccessSpec",
    "ScopeRule",
    "ExampleRecord",
    "GraphEdgeSpec",
    "GraphNodeSpec",
    "EntitySpec",
    "DomainSpec",
    # UX
    "SignalLevel",
    "AttentionSignal",
    "BulkActionSpec",
    "EmptyMessages",
    "PersonaVariant",
    "SortSpec",
    "UXSpec",
    # Surfaces
    "BusinessPriority",
    "RelatedDisplayMode",
    "RelatedGroup",
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
    "BucketRef",
    "DisplayMode",
    "NavGroupSpec",
    "ContextSelectorSpec",
    "NavItemIR",
    "WorkspaceAccessLevel",
    "WorkspaceAccessSpec",
    "WorkspaceRegion",
    "WorkspaceSpec",
    # Experiences
    "FlowContextVar",
    "StepPrefill",
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
    "AuthSpec",
    "AuthType",
    "ErrorAction",
    "ErrorStrategy",
    "Expression",
    "HttpMethod",
    "HttpRequestSpec",
    "IntegrationAction",
    "IntegrationMapping",
    "MappingRule",
    "MappingTriggerSpec",
    "MappingTriggerType",
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
    # Source locations
    "SourceLocation",
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
    # Lifecycle (ADR-0020)
    "LifecycleSpec",
    "LifecycleStateSpec",
    "LifecycleTransitionSpec",
    # Fitness (Agent-Led Fitness v1)
    "FitnessSpec",
    # Personas (v0.8.5)
    "PersonaSpec",
    # Triples (v0.50.0 IR Triple Enrichment)
    "ActionTriple",
    "SurfaceActionTriple",
    "SurfaceFieldTriple",
    "VerifiableTriple",
    "WidgetKind",
    # Predicate Algebra (Scope row-level security)
    "BoolComposite",
    "BoolOp",
    "ColumnCheck",
    "CompOp",
    "Contradiction",
    "ExistsBinding",
    "ExistsCheck",
    "PathCheck",
    "ScopePredicate",
    "Tautology",
    "UserAttrCheck",
    "ValueRef",
    # Process Workflows (v0.23.0)
    "CompensationSpec",
    "EffectAction",
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
    "StepEffect",
    # Scenarios (v0.8.5)
    "DemoFixture",
    "PersonaScenarioEntry",
    "ScenarioSpec",
    # Security (v0.11.0)
    "SecurityConfig",
    "SecurityProfile",
    # Rules (v0.41.0 Convergent BDD)
    "RuleKind",
    "RuleOrigin",
    "RuleSpec",
    "RuleStatus",
    # Grants (v0.42.0 Runtime RBAC)
    "GrantApprovalMode",
    "GrantExpiryMode",
    "GrantRelationSpec",
    "GrantSchemaSpec",
    # Questions (v0.41.0 Convergent BDD)
    "QuestionSpec",
    "QuestionStatus",
    # Stories (v0.12.0 Behaviour Layer, v0.22.0 DSL syntax)
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
    "AI_JOB_FIELDS",
    "ArtifactKind",
    "ArtifactRefSpec",
    "ArtifactStore",
    "LLMConfigSpec",
    "LLMIntentSpec",
    "LLMModelSpec",
    "LLMProvider",
    "LLMTriggerEvent",
    "LLMTriggerSpec",
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
    # ThemeSpec YAML (v0.25.0 Declarative Theme)
    "AttentionMapSpec",
    "AttentionRule",
    "ColorMode",
    "DensityEnum",
    "FontStackSpec",
    "ImagerySpec",
    "ImageryVocabulary",
    "LayoutCompositionSpec",
    "PaletteSpec",
    "SemanticColorOverrides",
    "ShadowPreset",
    "ShapePreset",
    "ShapeSpec",
    "SpacingSpec",
    "SurfaceCompositionRule",
    "ThemeMetaSpec",
    "ThemeSpecYAML",
    "TypographyRatioPreset",
    "TypographySpec",
    "VisualTreatment",
    # Feedback Widget
    "FEEDBACK_REPORT_FIELDS",
    "FeedbackWidgetSpec",
    # Shared Enums (v0.25.0)
    "EnumSpec",
    "EnumValueSpec",
    # Views (v0.25.0, v0.34.0 date-range)
    "TimeBucket",
    "ViewFieldSpec",
    "ViewSpec",
    # Runtime Parameters (v0.44.0)
    "ParamConstraints",
    "ParamRef",
    "ParamSpec",
    # Notifications (v0.34.0)
    "NotificationChannel",
    "NotificationPreference",
    "NotificationRecipient",
    "NotificationSpec",
    "NotificationTrigger",
    # Webhooks (v0.25.0)
    "WebhookAuthMethod",
    "WebhookAuthSpec",
    "WebhookEvent",
    "WebhookPayloadSpec",
    "WebhookRetrySpec",
    "WebhookSpec",
    # Approvals (v0.25.0)
    "ApprovalEscalationSpec",
    "ApprovalOutcomeSpec",
    "ApprovalSpec",
    # Rhythms (v0.39.0 Longitudinal UX Evaluation)
    "Gap",
    "GapsReport",
    "GapsSummary",
    "LifecycleReport",
    "LifecycleStep",
    "PhaseKind",
    "PhaseSpec",
    "RhythmSpec",
    "SceneDimensionScore",
    "SceneEvaluation",
    "SceneSpec",
    # Seed Templates (v0.38.0)
    "SeedFieldTemplate",
    "SeedStrategy",
    "SeedTemplateSpec",
    # SLA (v0.25.0)
    "BusinessHoursSpec",
    "SLABreachActionSpec",
    "SLAConditionSpec",
    "SLASpec",
    "SLATierSpec",
    # Islands (UI Islands)
    "IslandEventSpec",
    "IslandPropSpec",
    "IslandSpec",
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
