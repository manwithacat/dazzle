"""Shared fixtures for Sentinel tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from dazzle.core.ir import (
    EntitySpec,
    FieldModifier,
    FieldSpec,
    FieldType,
    FieldTypeKind,
)

# ---------------------------------------------------------------------------
# Field helpers
# ---------------------------------------------------------------------------


def make_field(
    name: str,
    kind: FieldTypeKind = FieldTypeKind.STR,
    *,
    modifiers: list[FieldModifier] | None = None,
    ref_entity: str | None = None,
    max_length: int | None = None,
    relationship_behavior: object | None = None,
) -> FieldSpec:
    ft = FieldType(
        kind=kind,
        ref_entity=ref_entity,
        max_length=max_length,
        relationship_behavior=relationship_behavior,
    )
    return FieldSpec(
        name=name,
        type=ft,
        modifiers=modifiers or [],
    )


def pk_field(name: str = "id") -> FieldSpec:
    return make_field(name, FieldTypeKind.UUID, modifiers=[FieldModifier.PK])


def str_field(name: str, *, required: bool = False, unique: bool = False) -> FieldSpec:
    mods: list[FieldModifier] = []
    if required:
        mods.append(FieldModifier.REQUIRED)
    if unique:
        mods.append(FieldModifier.UNIQUE)
    return make_field(name, FieldTypeKind.STR, modifiers=mods, max_length=200)


def ref_field(name: str, target: str) -> FieldSpec:
    return make_field(name, FieldTypeKind.REF, ref_entity=target)


# ---------------------------------------------------------------------------
# Entity helpers
# ---------------------------------------------------------------------------


def make_entity(
    name: str,
    fields: list[FieldSpec] | None = None,
    *,
    access: object | None = None,
    audit: object | None = None,
    state_machine: object | None = None,
    is_singleton: bool = False,
    is_tenant_root: bool = False,
    computed_fields: list | None = None,
    invariants: list | None = None,
) -> EntitySpec:
    return EntitySpec(
        name=name,
        title=name,
        fields=fields or [pk_field()],
        access=access,
        audit=audit,
        state_machine=state_machine,
        is_singleton=is_singleton,
        is_tenant_root=is_tenant_root,
        computed_fields=computed_fields or [],
        invariants=invariants or [],
    )


# ---------------------------------------------------------------------------
# Mock entity helper (for entities with mock sub-objects)
# ---------------------------------------------------------------------------


def mock_entity(
    name: str,
    fields: list[FieldSpec] | None = None,
    *,
    access: object | None = None,
    audit: object | None = None,
    state_machine: object | None = None,
    is_singleton: bool = False,
    is_tenant_root: bool = False,
    computed_fields: list | None = None,
    invariants: list | None = None,
    primary_key: object | None = ...,  # sentinel default
) -> MagicMock:
    """Build a duck-typed EntitySpec mock for tests that need MagicMock sub-objects
    (invariants, computed_fields, state_machine with mock guards, etc.)."""
    f = fields or [pk_field()]
    e = MagicMock()
    e.name = name
    e.title = name
    e.fields = f
    e.access = access
    e.audit = audit
    e.state_machine = state_machine
    e.is_singleton = is_singleton
    e.is_tenant_root = is_tenant_root
    e.computed_fields = computed_fields or []
    e.invariants = invariants or []
    # primary_key: find first PK field, or None
    if primary_key is ...:
        pk = next((fld for fld in f if fld.is_primary_key), None)
        e.primary_key = pk
    else:
        e.primary_key = primary_key
    # get_field helper
    field_map = {fld.name: fld for fld in f}
    e.get_field = lambda n, m=field_map: m.get(n)
    return e


# ---------------------------------------------------------------------------
# AppSpec mock helper
# ---------------------------------------------------------------------------


def make_appspec(
    entities: list[EntitySpec] | None = None,
    *,
    surfaces: list | None = None,
    stories: list | None = None,
    processes: list | None = None,
    personas: list | None = None,
    policies: object | None = None,
    tenancy: object | None = None,
    security: object | None = None,
    ledgers: list | None = None,
    webhooks: list | None = None,
    slas: list | None = None,
    approvals: list | None = None,
    experiences: list | None = None,
    enums: list | None = None,
    schedules: list | None = None,
    tests: list | None = None,
    data_products: object | None = None,
    # New fields for ID/DS/PR/OP agents
    apis: list | None = None,
    domain_services: list | None = None,
    foreign_models: list | None = None,
    integrations: list | None = None,
    channels: list | None = None,
    interfaces: object | None = None,
    transactions: list | None = None,
    llm_config: object | None = None,
    llm_models: list | None = None,
    llm_intents: list | None = None,
    event_model: object | None = None,
    views: list | None = None,
) -> Any:
    """Build a duck-typed AppSpec-like object for sentinel agent testing.

    Uses a MagicMock with pre-set attributes so that Pydantic validation
    is bypassed — the sentinel agents only read attributes from the AppSpec
    and never deserialise it.
    """
    entity_list = entities or [make_entity("Task")]
    entity_map = {e.name: e for e in entity_list}

    spec = MagicMock()
    spec.name = "test_app"
    spec.title = "Test App"
    spec.version = "0.1.0"
    spec.domain.entities = entity_list
    spec.surfaces = surfaces or []
    spec.stories = stories or []
    spec.processes = processes or []
    spec.personas = personas or []
    spec.policies = policies
    spec.tenancy = tenancy
    spec.security = security
    spec.ledgers = ledgers or []
    spec.webhooks = webhooks or []
    spec.slas = slas or []
    spec.approvals = approvals or []
    spec.experiences = experiences or []
    spec.enums = enums or []
    spec.schedules = schedules or []
    spec.tests = tests or []
    spec.data_products = data_products
    # New fields for ID/DS/PR/OP agents
    spec.apis = apis or []
    spec.domain_services = domain_services or []
    spec.foreign_models = foreign_models or []
    spec.integrations = integrations or []
    spec.channels = channels or []
    spec.interfaces = interfaces
    spec.transactions = transactions or []
    spec.llm_config = llm_config
    spec.llm_models = llm_models or []
    spec.llm_intents = llm_intents or []
    spec.event_model = event_model

    # Views (v0.25.0)
    view_list = views or []
    view_map = {v.name: v for v in view_list}
    spec.views = view_list

    # Implement get_entity(name) for agents that look up entities
    spec.get_entity = lambda name, m=entity_map: m.get(name)
    # Implement get_view(name) for agents that look up views
    spec.get_view = lambda name, m=view_map: m.get(name)

    return spec


# ---------------------------------------------------------------------------
# Standard fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def simple_entity() -> EntitySpec:
    return make_entity(
        "Task",
        [pk_field(), str_field("title", required=True)],
    )


@pytest.fixture
def simple_appspec(simple_entity: EntitySpec) -> Any:
    return make_appspec([simple_entity])
