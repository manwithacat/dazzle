"""
Extracted query functions for AppSpec.

These are pure query functions that read from an AppSpec instance
without mutating it. AppSpec methods delegate to these functions,
so callers can use either ``appspec.get_entity(name)`` or
``appspec_queries.get_entity(appspec, name)`` interchangeably.

New code is encouraged to import from this module directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .approvals import ApprovalSpec
    from .appspec import AppSpec
    from .archetype import ArchetypeSpec
    from .domain import EntitySpec
    from .e2e import FixtureSpec, FlowPriority, FlowSpec
    from .enums import EnumSpec
    from .experiences import ExperienceSpec
    from .fields import FieldType
    from .foreign_models import ForeignModelSpec
    from .grants import GrantSchemaSpec
    from .hless import StreamSpec
    from .integrations import IntegrationSpec
    from .islands import IslandSpec
    from .ledgers import LedgerSpec, TransactionSpec
    from .llm import LLMIntentSpec, LLMModelSpec
    from .messaging import (
        AssetSpec,
        ChannelSpec,
        DocumentSpec,
        MessageSpec,
        TemplateSpec,
    )
    from .personas import PersonaSpec
    from .process import ProcessSpec, ScheduleSpec
    from .questions import QuestionSpec
    from .rules import RuleSpec
    from .scenarios import ScenarioSpec
    from .services import APISpec, DomainServiceSpec
    from .sla import SLASpec
    from .stories import StorySpec
    from .surfaces import SurfaceSpec
    from .tests import TestSpec
    from .triples import VerifiableTriple
    from .views import ViewSpec
    from .webhooks import WebhookSpec
    from .workspaces import WorkspaceSpec

__all__ = [
    # Simple lookups
    "get_entity",
    "get_archetype",
    "get_surface",
    "get_workspace",
    "get_experience",
    "get_api",
    "get_domain_service",
    "get_test",
    "get_foreign_model",
    "get_integration",
    "get_flow",
    "get_fixture",
    "get_persona",
    "get_scenario",
    "get_story",
    "get_rule",
    "get_question",
    "get_grant_schema",
    "get_message",
    "get_channel",
    "get_asset",
    "get_document",
    "get_template",
    "get_stream",
    "get_llm_model",
    "get_llm_intent",
    "get_process",
    "get_schedule",
    "get_ledger",
    "get_transaction",
    "get_enum",
    "get_view",
    "get_webhook",
    "get_approval",
    "get_sla",
    "get_island",
    # Filter / multi-result queries
    "get_flows_by_entity",
    "get_flows_by_priority",
    "get_stories_by_actor",
    "get_stories_by_entity",
    "get_rules_by_scope",
    "get_questions_blocking",
    "get_grant_schemas_by_scope",
    "get_triples_for_entity",
    "get_triples_for_persona",
    "get_triple",
    "get_processes_by_story",
    "get_schedules_by_story",
    "get_transactions_by_ledger",
    "get_ledgers_by_currency",
    # Analysis
    "type_catalog",
    "get_field_type_conflicts",
]


# ---------------------------------------------------------------------------
# Simple lookups by name / id
# ---------------------------------------------------------------------------


def get_entity(appspec: AppSpec, name: str) -> EntitySpec | None:
    """Get entity by name."""
    return appspec.domain.get_entity(name)


def get_archetype(appspec: AppSpec, name: str) -> ArchetypeSpec | None:
    """Get archetype by name."""
    for archetype in appspec.archetypes:
        if archetype.name == name:
            return archetype
    return None


def get_surface(appspec: AppSpec, name: str) -> SurfaceSpec | None:
    """Get surface by name."""
    for surface in appspec.surfaces:
        if surface.name == name:
            return surface
    return None


def get_workspace(appspec: AppSpec, name: str) -> WorkspaceSpec | None:
    """Get workspace by name."""
    for workspace in appspec.workspaces:
        if workspace.name == name:
            return workspace
    return None


def get_experience(appspec: AppSpec, name: str) -> ExperienceSpec | None:
    """Get experience by name."""
    for experience in appspec.experiences:
        if experience.name == name:
            return experience
    return None


def get_api(appspec: AppSpec, name: str) -> APISpec | None:
    """Get external API by name."""
    for api in appspec.apis:
        if api.name == name:
            return api
    return None


def get_domain_service(appspec: AppSpec, name: str) -> DomainServiceSpec | None:
    """Get domain service by name."""
    for service in appspec.domain_services:
        if service.name == name:
            return service
    return None


def get_test(appspec: AppSpec, name: str) -> TestSpec | None:
    """Get test by name."""
    for test in appspec.tests:
        if test.name == name:
            return test
    return None


def get_foreign_model(appspec: AppSpec, name: str) -> ForeignModelSpec | None:
    """Get foreign model by name."""
    for fm in appspec.foreign_models:
        if fm.name == name:
            return fm
    return None


def get_integration(appspec: AppSpec, name: str) -> IntegrationSpec | None:
    """Get integration by name."""
    for integration in appspec.integrations:
        if integration.name == name:
            return integration
    return None


def get_flow(appspec: AppSpec, flow_id: str) -> FlowSpec | None:
    """Get E2E flow by ID."""
    for flow in appspec.e2e_flows:
        if flow.id == flow_id:
            return flow
    return None


def get_fixture(appspec: AppSpec, fixture_id: str) -> FixtureSpec | None:
    """Get fixture by ID."""
    for fixture in appspec.fixtures:
        if fixture.id == fixture_id:
            return fixture
    return None


def get_persona(appspec: AppSpec, persona_id: str) -> PersonaSpec | None:
    """Get persona by ID."""
    for persona in appspec.personas:
        if persona.id == persona_id:
            return persona
    return None


def get_scenario(appspec: AppSpec, scenario_id: str) -> ScenarioSpec | None:
    """Get scenario by ID."""
    for scenario in appspec.scenarios:
        if scenario.id == scenario_id:
            return scenario
    return None


def get_story(appspec: AppSpec, story_id: str) -> StorySpec | None:
    """Get story by ID."""
    for story in appspec.stories:
        if story.story_id == story_id:
            return story
    return None


def get_rule(appspec: AppSpec, rule_id: str) -> RuleSpec | None:
    """Get rule by ID."""
    for rule in appspec.rules:
        if rule.rule_id == rule_id:
            return rule
    return None


def get_question(appspec: AppSpec, question_id: str) -> QuestionSpec | None:
    """Get question by ID."""
    for question in appspec.questions:
        if question.question_id == question_id:
            return question
    return None


def get_grant_schema(appspec: AppSpec, name: str) -> GrantSchemaSpec | None:
    """Get grant schema by name."""
    for schema in appspec.grant_schemas:
        if schema.name == name:
            return schema
    return None


def get_message(appspec: AppSpec, name: str) -> MessageSpec | None:
    """Get message schema by name."""
    for message in appspec.messages:
        if message.name == name:
            return message
    return None


def get_channel(appspec: AppSpec, name: str) -> ChannelSpec | None:
    """Get channel by name."""
    for channel in appspec.channels:
        if channel.name == name:
            return channel
    return None


def get_asset(appspec: AppSpec, name: str) -> AssetSpec | None:
    """Get asset by name."""
    for asset in appspec.assets:
        if asset.name == name:
            return asset
    return None


def get_document(appspec: AppSpec, name: str) -> DocumentSpec | None:
    """Get document by name."""
    for document in appspec.documents:
        if document.name == name:
            return document
    return None


def get_template(appspec: AppSpec, name: str) -> TemplateSpec | None:
    """Get template by name."""
    for template in appspec.templates:
        if template.name == name:
            return template
    return None


def get_stream(appspec: AppSpec, name: str) -> StreamSpec | None:
    """Get stream by name."""
    for stream in appspec.streams:
        if stream.name == name:
            return stream
    return None


def get_llm_model(appspec: AppSpec, name: str) -> LLMModelSpec | None:
    """Get LLM model by name."""
    for model in appspec.llm_models:
        if model.name == name:
            return model
    return None


def get_llm_intent(appspec: AppSpec, name: str) -> LLMIntentSpec | None:
    """Get LLM intent by name."""
    for intent in appspec.llm_intents:
        if intent.name == name:
            return intent
    return None


def get_process(appspec: AppSpec, name: str) -> ProcessSpec | None:
    """Get process by name."""
    for process in appspec.processes:
        if process.name == name:
            return process
    return None


def get_schedule(appspec: AppSpec, name: str) -> ScheduleSpec | None:
    """Get schedule by name."""
    for schedule in appspec.schedules:
        if schedule.name == name:
            return schedule
    return None


def get_ledger(appspec: AppSpec, name: str) -> LedgerSpec | None:
    """Get ledger by name."""
    for ledger in appspec.ledgers:
        if ledger.name == name:
            return ledger
    return None


def get_transaction(appspec: AppSpec, name: str) -> TransactionSpec | None:
    """Get transaction by name."""
    for transaction in appspec.transactions:
        if transaction.name == name:
            return transaction
    return None


def get_enum(appspec: AppSpec, name: str) -> EnumSpec | None:
    """Get shared enum by name."""
    for enum in appspec.enums:
        if enum.name == name:
            return enum
    return None


def get_view(appspec: AppSpec, name: str) -> ViewSpec | None:
    """Get view by name."""
    for view in appspec.views:
        if view.name == name:
            return view
    return None


def get_webhook(appspec: AppSpec, name: str) -> WebhookSpec | None:
    """Get webhook by name."""
    for webhook in appspec.webhooks:
        if webhook.name == name:
            return webhook
    return None


def get_approval(appspec: AppSpec, name: str) -> ApprovalSpec | None:
    """Get approval by name."""
    for approval in appspec.approvals:
        if approval.name == name:
            return approval
    return None


def get_sla(appspec: AppSpec, name: str) -> SLASpec | None:
    """Get SLA by name."""
    for sla in appspec.slas:
        if sla.name == name:
            return sla
    return None


def get_island(appspec: AppSpec, name: str) -> IslandSpec | None:
    """Get island by name."""
    for island in appspec.islands:
        if island.name == name:
            return island
    return None


# ---------------------------------------------------------------------------
# Filter / multi-result queries
# ---------------------------------------------------------------------------


def get_flows_by_entity(appspec: AppSpec, entity: str) -> list[FlowSpec]:
    """Get all E2E flows for a given entity."""
    return [f for f in appspec.e2e_flows if f.entity == entity]


def get_flows_by_priority(appspec: AppSpec, priority: FlowPriority) -> list[FlowSpec]:
    """Get all E2E flows with given priority."""
    return [f for f in appspec.e2e_flows if f.priority == priority]


def get_stories_by_actor(appspec: AppSpec, actor: str) -> list[StorySpec]:
    """Get all stories for a given actor/persona."""
    return [s for s in appspec.stories if s.actor == actor]


def get_stories_by_entity(appspec: AppSpec, entity_name: str) -> list[StorySpec]:
    """Get all stories involving a specific entity."""
    return [s for s in appspec.stories if entity_name in s.scope]


def get_rules_by_scope(appspec: AppSpec, entity_name: str) -> list[RuleSpec]:
    """Get all rules whose scope includes a specific entity."""
    return [r for r in appspec.rules if entity_name in r.scope]


def get_questions_blocking(appspec: AppSpec, artefact_id: str) -> list[QuestionSpec]:
    """Get all open questions that block a specific artefact."""
    return [q for q in appspec.questions if artefact_id in q.blocks]


def get_grant_schemas_by_scope(appspec: AppSpec, entity_name: str) -> list[GrantSchemaSpec]:
    """Get all grant schemas scoped to a specific entity."""
    return [s for s in appspec.grant_schemas if s.scope == entity_name]


def get_triples_for_entity(appspec: AppSpec, entity: str) -> list[VerifiableTriple]:
    """Get all triples for a given entity."""
    return appspec._triples_by_entity.get(entity, [])


def get_triples_for_persona(appspec: AppSpec, persona: str) -> list[VerifiableTriple]:
    """Get all triples for a given persona."""
    return appspec._triples_by_persona.get(persona, [])


def get_triple(
    appspec: AppSpec, entity: str, surface: str, persona: str
) -> VerifiableTriple | None:
    """Get a specific triple by entity, surface, and persona."""
    return appspec._triple_index.get((entity, surface, persona))


def get_processes_by_story(appspec: AppSpec, story_id: str) -> list[ProcessSpec]:
    """Get all processes that implement a specific story."""
    return [p for p in appspec.processes if story_id in p.implements]


def get_schedules_by_story(appspec: AppSpec, story_id: str) -> list[ScheduleSpec]:
    """Get all schedules that implement a specific story."""
    return [s for s in appspec.schedules if story_id in s.implements]


def get_transactions_by_ledger(appspec: AppSpec, ledger_name: str) -> list[TransactionSpec]:
    """Get all transactions that affect a specific ledger."""
    return [t for t in appspec.transactions if ledger_name in t.affected_ledgers]


def get_ledgers_by_currency(appspec: AppSpec, currency: str) -> list[LedgerSpec]:
    """Get all ledgers with a specific currency."""
    return [ledger for ledger in appspec.ledgers if ledger.currency == currency]


# ---------------------------------------------------------------------------
# Analysis / derived data
# ---------------------------------------------------------------------------


def type_catalog(appspec: AppSpec) -> dict[str, list[FieldType]]:
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
    catalog: dict[str, list[FieldType]] = {}

    # Collect from entities
    for entity in appspec.domain.entities:
        for field in entity.fields:
            if field.name not in catalog:
                catalog[field.name] = []
            if field.type not in catalog[field.name]:
                catalog[field.name].append(field.type)

    # Collect from foreign models
    for foreign_model in appspec.foreign_models:
        for field in foreign_model.fields:
            if field.name not in catalog:
                catalog[field.name] = []
            if field.type not in catalog[field.name]:
                catalog[field.name].append(field.type)

    return catalog


def get_field_type_conflicts(appspec: AppSpec) -> list[str]:
    """
    Detect fields with the same name but different types.

    Returns:
        List of warning messages about type conflicts
    """
    conflicts = []
    for field_name, types in type_catalog(appspec).items():
        if len(types) > 1:
            type_descriptions = [
                f"{t.kind.value}"
                + (
                    f"({t.max_length})"
                    if t.max_length
                    else f"({t.precision},{t.scale})"
                    if t.precision
                    else f"[{','.join(t.enum_values)}]"
                    if t.enum_values
                    else f" {t.ref_entity}"
                    if t.ref_entity
                    else ""
                )
                for t in types
            ]
            conflicts.append(
                f"Field '{field_name}' has inconsistent types: {', '.join(type_descriptions)}"
            )
    return conflicts
