"""
Application specification types for DAZZLE IR.

This module contains the top-level AppSpec that represents
a complete, linked application definition.
"""

from functools import cached_property
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .analytics import AnalyticsSpec
from .approvals import ApprovalSpec
from .archetype import ArchetypeSpec
from .audit import AuditSpec
from .domain import DomainSpec, EntitySpec
from .e2e import FixtureSpec, FlowPriority, FlowSpec
from .enums import EnumSpec
from .eventing import (
    EventModelSpec,
    ProjectionSpec,
    SubscribeSpec,
)
from .experiences import ExperienceSpec
from .feedback_widget import FeedbackWidgetSpec
from .fields import FieldType
from .foreign_models import ForeignModelSpec
from .governance import (
    DataProductsSpec,
    InterfacesSpec,
    PoliciesSpec,
    TenancySpec,
)
from .grants import GrantSchemaSpec
from .hless import (
    HLESSMode,
    HLESSPragma,
    StreamSpec,
)
from .integrations import IntegrationSpec
from .islands import IslandSpec
from .jobs import JobSpec
from .layout import UXLayouts
from .ledgers import (
    LedgerSpec,
    TransactionSpec,
)
from .llm import (
    LLMConfigSpec,
    LLMIntentSpec,
    LLMModelSpec,
)
from .messaging import (
    AssetSpec,
    ChannelSpec,
    DocumentSpec,
    MessageSpec,
    TemplateSpec,
)
from .module import AppConfigSpec
from .notifications import NotificationSpec
from .params import ParamSpec
from .personas import PersonaSpec
from .process import (
    ProcessSpec,
    ScheduleSpec,
)
from .questions import QuestionSpec
from .rhythm import RhythmSpec
from .rules import RuleSpec
from .scenarios import ScenarioSpec
from .security import SecurityConfig
from .services import APISpec, DomainServiceSpec
from .sla import SLASpec
from .stories import StorySpec
from .subprocessors import SubprocessorSpec
from .surfaces import SurfaceSpec
from .tests import TestSpec
from .triples import VerifiableTriple
from .views import ViewSpec
from .webhooks import WebhookSpec
from .workspaces import WorkspaceSpec


class AppSpec(BaseModel):
    """
    Complete application specification.

    This is the root of the IR tree and represents a fully merged,
    linked application definition.

    Attributes:
        name: Application name
        title: Human-readable title
        version: Version string
        archetypes: List of archetype specifications (v0.7.1)
        domain: Domain specification (entities)
        surfaces: List of surface specifications
        workspaces: List of workspace specifications
        experiences: List of experience specifications
        apis: List of external API specifications
        domain_services: List of domain service specifications (v0.5.0)
        foreign_models: List of foreign model specifications
        integrations: List of integration specifications
        tests: API-focused test specifications
        e2e_flows: E2E user journey flows (semantic E2E testing)
        fixtures: Test fixtures for E2E testing
        metadata: Additional metadata
        ux: Semantic layout engine configuration
    """

    name: str
    title: str | None = None
    version: str = "0.1.0"
    archetypes: list[ArchetypeSpec] = Field(default_factory=list)  # v0.7.1
    domain: DomainSpec
    surfaces: list[SurfaceSpec] = Field(default_factory=list)
    workspaces: list[WorkspaceSpec] = Field(default_factory=list)  # UX extension (old)
    experiences: list[ExperienceSpec] = Field(default_factory=list)
    apis: list[APISpec] = Field(default_factory=list)
    domain_services: list[DomainServiceSpec] = Field(default_factory=list)  # v0.5.0
    foreign_models: list[ForeignModelSpec] = Field(default_factory=list)
    integrations: list[IntegrationSpec] = Field(default_factory=list)
    tests: list[TestSpec] = Field(default_factory=list)
    e2e_flows: list[FlowSpec] = Field(default_factory=list)  # Semantic E2E flows (v0.3.2)
    fixtures: list[FixtureSpec] = Field(default_factory=list)  # Test fixtures (v0.3.2)
    personas: list[PersonaSpec] = Field(default_factory=list)  # v0.8.5
    scenarios: list[ScenarioSpec] = Field(default_factory=list)  # v0.8.5
    # Stories (v0.22.0 DSL syntax)
    stories: list[StorySpec] = Field(default_factory=list)
    # Rules (v0.41.0 Convergent BDD)
    rules: list[RuleSpec] = Field(default_factory=list)
    # Questions (v0.41.0 Convergent BDD)
    questions: list[QuestionSpec] = Field(default_factory=list)
    # Messaging Channels (v0.9.0)
    messages: list[MessageSpec] = Field(default_factory=list)
    channels: list[ChannelSpec] = Field(default_factory=list)
    assets: list[AssetSpec] = Field(default_factory=list)
    documents: list[DocumentSpec] = Field(default_factory=list)
    templates: list[TemplateSpec] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    ux: UXLayouts | None = None  # Semantic layout engine (v0.3)
    security: SecurityConfig | None = None  # Security configuration (v0.11.0)
    # v0.61.43 (Phase B Patch 2): mirror the root module's app_config so
    # runtime consumers can read DSL-level theme / multi_tenant / etc.
    # without re-loading the source module.
    app_config: AppConfigSpec | None = None
    # Event-First Architecture (v0.18.0)
    event_model: EventModelSpec | None = None
    subscriptions: list[SubscribeSpec] = Field(default_factory=list)
    projections: list[ProjectionSpec] = Field(default_factory=list)
    # HLESS - High-Level Event Semantics (v0.19.0)
    streams: list[StreamSpec] = Field(default_factory=list)
    hless_mode: HLESSMode = Field(default=HLESSMode.STRICT)
    hless_pragma: HLESSPragma | None = None
    # Governance sections (v0.18.0 Event-First Architecture - Issue #25)
    policies: PoliciesSpec | None = None
    tenancy: TenancySpec | None = None
    interfaces: InterfacesSpec | None = None
    data_products: DataProductsSpec | None = None
    # LLM Jobs as First-Class Events (v0.21.0 - Issue #33)
    llm_config: LLMConfigSpec | None = None
    llm_models: list[LLMModelSpec] = Field(default_factory=list)
    llm_intents: list[LLMIntentSpec] = Field(default_factory=list)
    # Process Workflows (v0.23.0)
    processes: list[ProcessSpec] = Field(default_factory=list)
    schedules: list[ScheduleSpec] = Field(default_factory=list)
    # Ledgers (v0.24.0 TigerBeetle Integration)
    ledgers: list[LedgerSpec] = Field(default_factory=list)
    transactions: list[TransactionSpec] = Field(default_factory=list)
    # Shared Enums (v0.25.0)
    enums: list[EnumSpec] = Field(default_factory=list)
    # Views (v0.25.0)
    views: list[ViewSpec] = Field(default_factory=list)
    # Webhooks (v0.25.0)
    webhooks: list[WebhookSpec] = Field(default_factory=list)
    # Approvals (v0.25.0)
    approvals: list[ApprovalSpec] = Field(default_factory=list)
    # SLAs (v0.25.0)
    slas: list[SLASpec] = Field(default_factory=list)
    # Islands (UI Islands)
    islands: list[IslandSpec] = Field(default_factory=list)
    # Notifications (v0.34.0)
    notifications: list[NotificationSpec] = Field(default_factory=list)
    # Background Jobs (#953)
    jobs: list[JobSpec] = Field(default_factory=list)
    # Audit trail (#956)
    audits: list[AuditSpec] = Field(default_factory=list)
    # Rhythms (v0.39.0 Longitudinal UX Evaluation)
    rhythms: list[RhythmSpec] = Field(default_factory=list)
    # Grant Schemas (v0.42.0 Runtime RBAC)
    grant_schemas: list[GrantSchemaSpec] = Field(default_factory=list)
    # Runtime Parameters (v0.44.0)
    params: list[ParamSpec] = Field(default_factory=list)
    # Feedback Widget
    feedback_widget: FeedbackWidgetSpec | None = None
    # Global audit trail (v0.34.0) — when True, all entities are audited by default
    audit_trail: bool = False
    # FK graph built at link time (Task 5 predicate algebra).
    # Typed as Any to avoid circular import: FKGraph is a dataclass from ir.fk_graph
    # and importing it here would create import cycles with the linker.
    fk_graph: Any = None

    # Verifiable triples (v0.50.0 IR Triple Enrichment)
    triples: list[VerifiableTriple] = Field(default_factory=list)

    # Subprocessors (v0.61.0 Analytics / Privacy / Compliance)
    subprocessors: list[SubprocessorSpec] = Field(default_factory=list)

    # Analytics block (v0.61.0 Phase 3)
    analytics: AnalyticsSpec | None = None

    model_config = ConfigDict(frozen=True)

    # ------------------------------------------------------------------
    # Query methods — delegates to appspec_queries.py free functions.
    # Kept here for backward compatibility (100+ call sites).
    # ------------------------------------------------------------------

    def get_entity(self, name: str) -> EntitySpec | None:
        """Get entity by name."""
        from .appspec_queries import get_entity as _q

        return _q(self, name)

    def get_archetype(self, name: str) -> ArchetypeSpec | None:
        """Get archetype by name."""
        from .appspec_queries import get_archetype as _q

        return _q(self, name)

    def get_surface(self, name: str) -> SurfaceSpec | None:
        """Get surface by name."""
        from .appspec_queries import get_surface as _q

        return _q(self, name)

    def get_workspace(self, name: str) -> WorkspaceSpec | None:
        """Get workspace by name."""
        from .appspec_queries import get_workspace as _q

        return _q(self, name)

    def get_experience(self, name: str) -> ExperienceSpec | None:
        """Get experience by name."""
        from .appspec_queries import get_experience as _q

        return _q(self, name)

    def get_api(self, name: str) -> APISpec | None:
        """Get external API by name."""
        from .appspec_queries import get_api as _q

        return _q(self, name)

    def get_domain_service(self, name: str) -> DomainServiceSpec | None:
        """Get domain service by name."""
        from .appspec_queries import get_domain_service as _q

        return _q(self, name)

    def get_test(self, name: str) -> TestSpec | None:
        """Get test by name."""
        from .appspec_queries import get_test as _q

        return _q(self, name)

    def get_foreign_model(self, name: str) -> ForeignModelSpec | None:
        """Get foreign model by name."""
        from .appspec_queries import get_foreign_model as _q

        return _q(self, name)

    def get_integration(self, name: str) -> IntegrationSpec | None:
        """Get integration by name."""
        from .appspec_queries import get_integration as _q

        return _q(self, name)

    def get_flow(self, flow_id: str) -> FlowSpec | None:
        """Get E2E flow by ID."""
        from .appspec_queries import get_flow as _q

        return _q(self, flow_id)

    def get_fixture(self, fixture_id: str) -> FixtureSpec | None:
        """Get fixture by ID."""
        from .appspec_queries import get_fixture as _q

        return _q(self, fixture_id)

    def get_flows_by_entity(self, entity: str) -> list[FlowSpec]:
        """Get all E2E flows for a given entity."""
        from .appspec_queries import get_flows_by_entity as _q

        return _q(self, entity)

    def get_flows_by_priority(self, priority: FlowPriority) -> list[FlowSpec]:
        """Get all E2E flows with given priority."""
        from .appspec_queries import get_flows_by_priority as _q

        return _q(self, priority)

    def get_persona(self, persona_id: str) -> PersonaSpec | None:
        """Get persona by ID."""
        from .appspec_queries import get_persona as _q

        return _q(self, persona_id)

    def get_scenario(self, scenario_id: str) -> ScenarioSpec | None:
        """Get scenario by ID."""
        from .appspec_queries import get_scenario as _q

        return _q(self, scenario_id)

    # Story getters (v0.22.0)

    def get_story(self, story_id: str) -> StorySpec | None:
        """Get story by ID."""
        from .appspec_queries import get_story as _q

        return _q(self, story_id)

    def get_stories_by_actor(self, actor: str) -> list[StorySpec]:
        """Get all stories for a given actor/persona."""
        from .appspec_queries import get_stories_by_actor as _q

        return _q(self, actor)

    def get_stories_by_entity(self, entity_name: str) -> list[StorySpec]:
        """Get all stories involving a specific entity."""
        from .appspec_queries import get_stories_by_entity as _q

        return _q(self, entity_name)

    # Rule getters (v0.41.0 Convergent BDD)

    def get_rule(self, rule_id: str) -> RuleSpec | None:
        """Get rule by ID."""
        from .appspec_queries import get_rule as _q

        return _q(self, rule_id)

    def get_rules_by_scope(self, entity_name: str) -> list[RuleSpec]:
        """Get all rules whose scope includes a specific entity."""
        from .appspec_queries import get_rules_by_scope as _q

        return _q(self, entity_name)

    # Question getters (v0.41.0 Convergent BDD)

    def get_question(self, question_id: str) -> QuestionSpec | None:
        """Get question by ID."""
        from .appspec_queries import get_question as _q

        return _q(self, question_id)

    def get_questions_blocking(self, artefact_id: str) -> list[QuestionSpec]:
        """Get all open questions that block a specific artefact."""
        from .appspec_queries import get_questions_blocking as _q

        return _q(self, artefact_id)

    # Grant Schema getters (v0.42.0 Runtime RBAC)

    def get_grant_schema(self, name: str) -> GrantSchemaSpec | None:
        """Get grant schema by name."""
        from .appspec_queries import get_grant_schema as _q

        return _q(self, name)

    def get_grant_schemas_by_scope(self, entity_name: str) -> list[GrantSchemaSpec]:
        """Get all grant schemas scoped to a specific entity."""
        from .appspec_queries import get_grant_schemas_by_scope as _q

        return _q(self, entity_name)

    # Triple getters (v0.50.0 IR Triple Enrichment)

    @cached_property
    def _triple_index(self) -> dict[tuple[str, str, str], VerifiableTriple]:
        """Hash index for O(1) triple lookup by (entity, surface, persona)."""
        return {(t.entity, t.surface, t.persona): t for t in self.triples}

    @cached_property
    def _triples_by_entity(self) -> dict[str, list[VerifiableTriple]]:
        """Index triples by entity name."""
        idx: dict[str, list[VerifiableTriple]] = {}
        for t in self.triples:
            idx.setdefault(t.entity, []).append(t)
        return idx

    @cached_property
    def _triples_by_persona(self) -> dict[str, list[VerifiableTriple]]:
        """Index triples by persona ID."""
        idx: dict[str, list[VerifiableTriple]] = {}
        for t in self.triples:
            idx.setdefault(t.persona, []).append(t)
        return idx

    def get_triples_for_entity(self, entity: str) -> list[VerifiableTriple]:
        """Get all triples for a given entity."""
        from .appspec_queries import get_triples_for_entity as _q

        return _q(self, entity)

    def get_triples_for_persona(self, persona: str) -> list[VerifiableTriple]:
        """Get all triples for a given persona."""
        from .appspec_queries import get_triples_for_persona as _q

        return _q(self, persona)

    def get_triple(self, entity: str, surface: str, persona: str) -> VerifiableTriple | None:
        """Get a specific triple by entity, surface, and persona."""
        from .appspec_queries import get_triple as _q

        return _q(self, entity, surface, persona)

    # Messaging getters (v0.9.0)

    def get_message(self, name: str) -> MessageSpec | None:
        """Get message schema by name."""
        from .appspec_queries import get_message as _q

        return _q(self, name)

    def get_channel(self, name: str) -> ChannelSpec | None:
        """Get channel by name."""
        from .appspec_queries import get_channel as _q

        return _q(self, name)

    def get_asset(self, name: str) -> AssetSpec | None:
        """Get asset by name."""
        from .appspec_queries import get_asset as _q

        return _q(self, name)

    def get_document(self, name: str) -> DocumentSpec | None:
        """Get document by name."""
        from .appspec_queries import get_document as _q

        return _q(self, name)

    def get_template(self, name: str) -> TemplateSpec | None:
        """Get template by name."""
        from .appspec_queries import get_template as _q

        return _q(self, name)

    # HLESS getters (v0.19.0)

    def get_stream(self, name: str) -> StreamSpec | None:
        """Get stream by name."""
        from .appspec_queries import get_stream as _q

        return _q(self, name)

    # LLM getters (v0.21.0 - Issue #33)

    def get_llm_model(self, name: str) -> LLMModelSpec | None:
        """Get LLM model by name."""
        from .appspec_queries import get_llm_model as _q

        return _q(self, name)

    def get_llm_intent(self, name: str) -> LLMIntentSpec | None:
        """Get LLM intent by name."""
        from .appspec_queries import get_llm_intent as _q

        return _q(self, name)

    # Process getters (v0.23.0)

    def get_process(self, name: str) -> ProcessSpec | None:
        """Get process by name."""
        from .appspec_queries import get_process as _q

        return _q(self, name)

    def get_schedule(self, name: str) -> ScheduleSpec | None:
        """Get schedule by name."""
        from .appspec_queries import get_schedule as _q

        return _q(self, name)

    def get_processes_by_story(self, story_id: str) -> list[ProcessSpec]:
        """Get all processes that implement a specific story."""
        from .appspec_queries import get_processes_by_story as _q

        return _q(self, story_id)

    def get_schedules_by_story(self, story_id: str) -> list[ScheduleSpec]:
        """Get all schedules that implement a specific story."""
        from .appspec_queries import get_schedules_by_story as _q

        return _q(self, story_id)

    # Ledger getters (v0.24.0 TigerBeetle Integration)

    def get_ledger(self, name: str) -> LedgerSpec | None:
        """Get ledger by name."""
        from .appspec_queries import get_ledger as _q

        return _q(self, name)

    def get_transaction(self, name: str) -> TransactionSpec | None:
        """Get transaction by name."""
        from .appspec_queries import get_transaction as _q

        return _q(self, name)

    def get_transactions_by_ledger(self, ledger_name: str) -> list[TransactionSpec]:
        """Get all transactions that affect a specific ledger."""
        from .appspec_queries import get_transactions_by_ledger as _q

        return _q(self, ledger_name)

    def get_ledgers_by_currency(self, currency: str) -> list[LedgerSpec]:
        """Get all ledgers with a specific currency."""
        from .appspec_queries import get_ledgers_by_currency as _q

        return _q(self, currency)

    # Enum getters (v0.25.0)

    def get_enum(self, name: str) -> EnumSpec | None:
        """Get shared enum by name."""
        from .appspec_queries import get_enum as _q

        return _q(self, name)

    # View getters (v0.25.0)

    def get_view(self, name: str) -> ViewSpec | None:
        """Get view by name."""
        from .appspec_queries import get_view as _q

        return _q(self, name)

    # Webhook getters (v0.25.0)

    def get_webhook(self, name: str) -> WebhookSpec | None:
        """Get webhook by name."""
        from .appspec_queries import get_webhook as _q

        return _q(self, name)

    # Approval getters (v0.25.0)

    def get_approval(self, name: str) -> ApprovalSpec | None:
        """Get approval by name."""
        from .appspec_queries import get_approval as _q

        return _q(self, name)

    # SLA getters (v0.25.0)

    def get_sla(self, name: str) -> SLASpec | None:
        """Get SLA by name."""
        from .appspec_queries import get_sla as _q

        return _q(self, name)

    # Island getters

    def get_island(self, name: str) -> IslandSpec | None:
        """Get island by name."""
        from .appspec_queries import get_island as _q

        return _q(self, name)

    @property
    def type_catalog(self) -> dict[str, list[FieldType]]:
        """
        Extract catalog of all field types used in the application.

        Returns a mapping of field names to the types they use across
        all entities and foreign models. Useful for:
        - Stack generators building type mappings
        - Detecting type inconsistencies (same field name, different types)
        - Schema evolution analysis

        Returns:
            Dict mapping field names to list of FieldType objects
        """
        from .appspec_queries import type_catalog as _q

        return _q(self)

    def get_field_type_conflicts(self) -> list[str]:
        """
        Detect fields with the same name but different types.

        Returns:
            List of warning messages about type conflicts
        """
        from .appspec_queries import get_field_type_conflicts as _q

        return _q(self)
