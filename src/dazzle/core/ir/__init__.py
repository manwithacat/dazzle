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
# Analytics (v0.61.0 Phase 3 + Phase 5)
from .aggregates import (
    AggregateExpr,
    AggregateFunc,
    AggregateRef,
    AggregateWindow,
    AggregateWindowKind,
    DerivedMetric,
    DerivedMetricExpr,
)
from .analytics import (
    AnalyticsConsentSpec,
    AnalyticsProviderInstance,
    AnalyticsSpec,
)
from .appspec import (
    AppSpec,
)
from .archetype import (
    ArchetypeKind,
    ArchetypeSpec,
)

# E2E Flows
# Audit trail (#956)
from .audit import (
    AuditShowTo,
    AuditSpec,
)

# List columns + page size (#1792)
from .columns import (
    COLUMN_WIDTH_UNITS,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    ColumnSpec,
    column_width_error,
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
    CALENDAR_PERIODS,
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
    AuthIdentitySpec,
    Constraint,
    ConstraintKind,
    DomainSpec,
    EntitySpec,
    ExampleRecord,
    GraphEdgeSpec,
    GraphNodeSpec,
    ManagedBy,
    MembershipSpec,
    PermissionKind,
    PermissionRule,
    PolicyEffect,
    ScopeRule,
    TemporalSpec,
    TenantHostSpec,
    VisibilityRule,
)
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
    TestComparisonOperator,
    UsabilityRule,
)
from .entity_events import EntityEvent

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
    ErasurePolicy,
    ErasureSpec,
    PoliciesSpec,
    RetentionPolicy,
    TenancyMode,
    TenancySpec,
    TenantIsolationSpec,
    TopicNamespaceMode,
)

# Grants (v0.42.0 Runtime RBAC)
from .grants import (
    GrantApprovalMode,
    GrantExpiryMode,
    GrantRelationSpec,
    GrantSchemaSpec,
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
    IslandSpec,
)

# Layout Engine
from .layout import AttentionSignalKind, Stage

# Lifecycle (ADR-0020)
from .lifecycle import (
    LifecycleSpec,
    LifecycleStateSpec,
    LifecycleTransitionSpec,
)

# LLM - Large Language Model (v0.21.0 - Issue #33)
from .llm import (
    AI_JOB_FIELDS,
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

# Source locations (v0.31.0)
from .location import SourceLocation

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

# Guided onboarding (#1106 follow-up, v0.71.0)
from .onboarding import (
    GuideCompleteOn,
    GuideCompleteOnKind,
    GuideOnComplete,
    GuideSpec,
    GuideStep,
    GuideStepKind,
    HintDismiss,
    HintSpec,
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

# Rhythms (v0.39.0 Longitudinal UX Evaluation)
from .rhythm import (
    Gap,
    GapsReport,
    GapsSummary,
    PhaseKind,
    PhaseSpec,
    RhythmSpec,
    SceneSpec,
)

# Scenarios (v0.8.5)
from .scenarios import (
    DemoFixture,
    PersonaScenarioEntry,
    ScenarioSpec,
)

# Full-text search (#954)
from .search import (
    SearchField,
    SearchSpec,
)

# Security (v0.11.0)
from .security import (
    SecurityConfig,
    SecurityProfile,
    TwoFactorConfig,
    TwoFactorMethod,
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
    PageKind,
    PageSpec,
    PricingTier,
    SectionKind,
    SectionSpec,
    SiteNavSpec,
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
    CompanionEntrySpec,
    CompanionPosition,
    CompanionSpec,
    CompanionStageSpec,
    FieldFormatSpec,
    OpenViaTarget,
    Outcome,
    OutcomeKind,
    PeekMode,
    RelatedDisplayMode,
    RelatedGroup,
    RowTransitions,
    SubtypePanelBranch,
    SubtypePanelSpec,
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

# Row-interpolating text templates (#1815)
from .text_template import (
    MAX_TEMPLATE_HOPS,
    TEXT_TEMPLATE_FILTERS,
    TemplatePlaceholder,
    TemplateSegment,
    TextTemplate,
    TextTemplateError,
    parse_template_path,
    parse_text_template,
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
    BreadcrumbCrumbSpec,
    BreadcrumbSpec,
    BulkActionSpec,
    EmptyMessages,
    PersonaVariant,
    SignalLevel,
    SortSpec,
    UXSpec,
)

# Views (v0.25.0, v0.34.0 date-range reporting)
from .views import (
    ViewFieldSpec,
    ViewSpec,
)

# Workspaces
from .workspaces import (
    BucketRef,
    CohortStripConfig,
    CohortStripLens,
    ComparisonOutlierSpec,
    CompositePrimaryPart,
    CompositePrimarySpec,
    ConfirmationItemSpec,
    ContextSelectorSpec,
    DayTimelineConfig,
    DeltaSpec,
    DisplayMode,
    EntityCardAction,
    EntityCardConfig,
    EntityCardSection,
    EntityCardSectionMode,
    LensAggregatePrimary,
    NavGroupSpec,
    NavItemIR,
    NavSpec,
    NoticeSpec,
    OverlaySeriesSpec,
    PipelineStageSpec,
    ReferenceBand,
    ReferenceLine,
    RowActionSpec,
    StatusListEntrySpec,
    ToneBandSpec,
    WhenEmpty,
    WorkspaceAccessLevel,
    WorkspaceAccessSpec,
    WorkspacePrimaryActionSpec,
    WorkspaceRegion,
    WorkspaceSpec,
)

__all__ = [
    # Aggregate expression IR (ADR-0024)
    "AggregateExpr",
    "AggregateFunc",
    "AggregateRef",
    "AggregateWindow",
    "AggregateWindowKind",
    "DerivedMetric",
    "DerivedMetricExpr",
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
    # Analytics (v0.61.0 Phase 3 + Phase 5)
    "AnalyticsConsentSpec",
    "AnalyticsProviderInstance",
    "AnalyticsSpec",
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
    "ConstraintKind",
    "Constraint",
    "ManagedBy",
    "AuthContext",
    "AuthIdentitySpec",
    "VisibilityRule",
    "PolicyEffect",
    "PermissionKind",
    "PermissionRule",
    "AuditConfig",
    "AccessSpec",
    "ScopeRule",
    "TemporalSpec",
    "TenantHostSpec",
    "MembershipSpec",
    "ExampleRecord",
    "GraphEdgeSpec",
    "GraphNodeSpec",
    "EntitySpec",
    "EntityEvent",
    "DomainSpec",
    # UX
    "SignalLevel",
    "AttentionSignal",
    "BulkActionSpec",
    "EmptyMessages",
    "PersonaVariant",
    "SortSpec",
    "UXSpec",
    "BreadcrumbCrumbSpec",
    "BreadcrumbSpec",
    "MAX_TEMPLATE_HOPS",
    "TEXT_TEMPLATE_FILTERS",
    "TemplatePlaceholder",
    "TemplateSegment",
    "TextTemplate",
    "TextTemplateError",
    "parse_template_path",
    "parse_text_template",
    # Surfaces
    "BusinessPriority",
    "RelatedDisplayMode",
    "RelatedGroup",
    "OpenViaTarget",
    "PeekMode",
    "RowTransitions",
    "SurfaceMode",
    "SurfaceTrigger",
    "OutcomeKind",
    "Outcome",
    "SubtypePanelBranch",
    "SubtypePanelSpec",
    "FieldFormatSpec",
    "ColumnSpec",
    "COLUMN_WIDTH_UNITS",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "column_width_error",
    "SurfaceElement",
    "SurfaceSection",
    "SurfaceAction",
    "CompanionSpec",
    "CompanionPosition",
    "CompanionEntrySpec",
    "CompanionStageSpec",
    "SurfaceAccessSpec",
    "SurfaceSpec",
    # Workspaces
    "BucketRef",
    "DisplayMode",
    "WhenEmpty",
    "NavSpec",
    "NavGroupSpec",
    "ContextSelectorSpec",
    "NavItemIR",
    "WorkspaceAccessLevel",
    "WorkspaceAccessSpec",
    "DeltaSpec",
    "CohortStripConfig",
    "CohortStripLens",
    "ComparisonOutlierSpec",
    "CompositePrimaryPart",
    "CompositePrimarySpec",
    "ConfirmationItemSpec",
    "LensAggregatePrimary",
    "DayTimelineConfig",
    "EntityCardConfig",
    "EntityCardSection",
    "EntityCardAction",
    "EntityCardSectionMode",
    "NoticeSpec",
    "OverlaySeriesSpec",
    "PipelineStageSpec",
    "ReferenceBand",
    "ReferenceLine",
    "RowActionSpec",
    "StatusListEntrySpec",
    "ToneBandSpec",
    "WorkspacePrimaryActionSpec",
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
    # E2E
    "TestComparisonOperator",
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
    "Stage",
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
    "CALENDAR_PERIODS",
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
    "TwoFactorConfig",
    "TwoFactorMethod",
    # Grants (v0.42.0 Runtime RBAC)
    "GrantApprovalMode",
    "GrantExpiryMode",
    "GrantRelationSpec",
    "GrantSchemaSpec",
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
    # Test Design (v0.13.0)
    "TestDesignAction",
    "TestDesignSpec",
    "TestDesignStatus",
    "TestDesignStep",
    "TestDesignTrigger",
    "TestGap",
    "TestGapAnalysis",
    "TestGapCategory",
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
    # LLM - Large Language Model (v0.21.0 - Issue #33)
    "AI_JOB_FIELDS",
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
    "ErasurePolicy",
    "ErasureSpec",
    "PoliciesSpec",
    "RetentionPolicy",
    "TenancyMode",
    "TenancySpec",
    "TenantIsolationSpec",
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
    # Guided onboarding (v0.71.0)
    "GuideCompleteOn",
    "GuideCompleteOnKind",
    "GuideOnComplete",
    "GuideSpec",
    "GuideStep",
    "GuideStepKind",
    "HintDismiss",
    "HintSpec",
    # Views (v0.25.0, v0.34.0 date-range)
    "ViewFieldSpec",
    "ViewSpec",
    # Runtime Parameters (v0.44.0)
    "ParamConstraints",
    "ParamRef",
    "ParamSpec",
    # Audit trail (#956)
    "AuditShowTo",
    "AuditSpec",
    # Full-text search (#954)
    "SearchField",
    "SearchSpec",
    # Rhythms (v0.39.0 Longitudinal UX Evaluation)
    "Gap",
    "GapsReport",
    "GapsSummary",
    "PhaseKind",
    "PhaseSpec",
    "RhythmSpec",
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
    "SiteNavSpec",
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
