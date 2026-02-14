"""Tests for the Multi-Tenancy detection agent (MT-01 through MT-07)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dazzle.core.ir import FieldTypeKind
from dazzle.core.ir.governance import TenancyMode
from dazzle.sentinel.agents.multi_tenancy import MultiTenancyAgent
from dazzle.sentinel.models import AgentId, Severity

from .conftest import (
    make_appspec,
    make_entity,
    make_field,
    mock_entity,
    pk_field,
    ref_field,
    str_field,
)


@pytest.fixture
def agent() -> MultiTenancyAgent:
    return MultiTenancyAgent()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tenancy(
    mode: TenancyMode = TenancyMode.SHARED_SCHEMA,
    partition_key: str = "tenant_id",
    excluded: list[str] | None = None,
    topic_namespace: object | None = None,
) -> MagicMock:
    isolation = MagicMock()
    isolation.mode = mode
    isolation.partition_key = partition_key
    isolation.topic_namespace = topic_namespace
    t = MagicMock()
    t.isolation = isolation
    t.entities_excluded = excluded or []
    return t


# =============================================================================
# MT-01  Missing partition key field
# =============================================================================


class TestMT01MissingPartitionKey:
    def test_flags_entity_without_partition_key(self, agent: MultiTenancyAgent) -> None:
        entity = make_entity("Task", [pk_field(), str_field("title")])
        tenancy = _tenancy()
        findings = agent.mt_01_missing_partition_key(make_appspec([entity], tenancy=tenancy))
        assert len(findings) == 1
        assert findings[0].severity == Severity.CRITICAL
        assert "tenant_id" in findings[0].title

    def test_passes_when_field_present(self, agent: MultiTenancyAgent) -> None:
        entity = make_entity(
            "Task",
            [pk_field(), str_field("title"), make_field("tenant_id", FieldTypeKind.UUID)],
        )
        tenancy = _tenancy()
        assert agent.mt_01_missing_partition_key(make_appspec([entity], tenancy=tenancy)) == []

    def test_skips_excluded_entities(self, agent: MultiTenancyAgent) -> None:
        entity = make_entity("Config", [pk_field()])
        tenancy = _tenancy(excluded=["Config"])
        assert agent.mt_01_missing_partition_key(make_appspec([entity], tenancy=tenancy)) == []

    def test_no_tenancy(self, agent: MultiTenancyAgent) -> None:
        assert agent.mt_01_missing_partition_key(make_appspec()) == []

    def test_non_shared_schema_skipped(self, agent: MultiTenancyAgent) -> None:
        entity = make_entity("Task", [pk_field()])
        tenancy = _tenancy(mode=TenancyMode.DATABASE_PER_TENANT)
        assert agent.mt_01_missing_partition_key(make_appspec([entity], tenancy=tenancy)) == []


# =============================================================================
# MT-02  Ref chain missing tenant field
# =============================================================================


class TestMT02RefChainMissingTenant:
    def test_flags_ref_to_tenant_scoped_entity(self, agent: MultiTenancyAgent) -> None:
        order = make_entity(
            "Order",
            [pk_field(), make_field("tenant_id", FieldTypeKind.UUID)],
        )
        line_item = make_entity(
            "LineItem",
            [pk_field(), ref_field("order", "Order")],
        )
        tenancy = _tenancy()
        findings = agent.mt_02_ref_chain_missing_tenant(
            make_appspec([order, line_item], tenancy=tenancy)
        )
        assert len(findings) == 1
        assert "LineItem" in findings[0].title

    def test_passes_when_both_have_key(self, agent: MultiTenancyAgent) -> None:
        order = make_entity(
            "Order",
            [pk_field(), make_field("tenant_id", FieldTypeKind.UUID)],
        )
        line_item = make_entity(
            "LineItem",
            [
                pk_field(),
                ref_field("order", "Order"),
                make_field("tenant_id", FieldTypeKind.UUID),
            ],
        )
        tenancy = _tenancy()
        assert (
            agent.mt_02_ref_chain_missing_tenant(make_appspec([order, line_item], tenancy=tenancy))
            == []
        )

    def test_no_tenancy(self, agent: MultiTenancyAgent) -> None:
        assert agent.mt_02_ref_chain_missing_tenant(make_appspec()) == []


# =============================================================================
# MT-03  Singleton in multi-tenant app
# =============================================================================


class TestMT03SingletonInMultiTenant:
    def test_flags_singleton(self, agent: MultiTenancyAgent) -> None:
        entity = make_entity("AppConfig", is_singleton=True)
        tenancy = _tenancy()
        findings = agent.mt_03_singleton_in_multi_tenant(make_appspec([entity], tenancy=tenancy))
        assert len(findings) == 1
        assert findings[0].severity == Severity.MEDIUM

    def test_passes_non_singleton(self, agent: MultiTenancyAgent) -> None:
        entity = make_entity("Task")
        tenancy = _tenancy()
        assert agent.mt_03_singleton_in_multi_tenant(make_appspec([entity], tenancy=tenancy)) == []

    def test_no_tenancy(self, agent: MultiTenancyAgent) -> None:
        entity = make_entity("AppConfig", is_singleton=True)
        assert agent.mt_03_singleton_in_multi_tenant(make_appspec([entity])) == []


# =============================================================================
# MT-04  No tenant root entity
# =============================================================================


class TestMT04NoTenantRoot:
    def test_flags_missing_root(self, agent: MultiTenancyAgent) -> None:
        entity = make_entity("Task")
        tenancy = _tenancy()
        findings = agent.mt_04_no_tenant_root(make_appspec([entity], tenancy=tenancy))
        assert len(findings) == 1
        assert findings[0].severity == Severity.HIGH

    def test_passes_with_root(self, agent: MultiTenancyAgent) -> None:
        entity = make_entity("Tenant", is_tenant_root=True)
        tenancy = _tenancy()
        assert agent.mt_04_no_tenant_root(make_appspec([entity], tenancy=tenancy)) == []

    def test_no_tenancy(self, agent: MultiTenancyAgent) -> None:
        assert agent.mt_04_no_tenant_root(make_appspec()) == []


# =============================================================================
# MT-05  Cross-tenant data product without anonymization
# =============================================================================


class TestMT05CrossTenantNoAnonymization:
    def _data_products(self, products: list) -> MagicMock:
        dp = MagicMock()
        dp.products = products
        return dp

    def _product(
        self, name: str, cross_tenant: bool = True, transforms: list | None = None
    ) -> MagicMock:
        p = MagicMock()
        p.name = name
        p.cross_tenant = cross_tenant
        p.transforms = transforms or []
        return p

    def test_flags_cross_tenant_without_anonymization(self, agent: MultiTenancyAgent) -> None:
        product = self._product("analytics", transforms=[])
        appspec = make_appspec(data_products=self._data_products([product]))
        findings = agent.mt_05_cross_tenant_no_anonymization(appspec)
        assert len(findings) == 1
        assert findings[0].severity == Severity.HIGH

    def test_passes_with_pseudonymise(self, agent: MultiTenancyAgent) -> None:
        from dazzle.core.ir.governance import DataProductTransform

        product = self._product("analytics", transforms=[DataProductTransform.PSEUDONYMISE])
        appspec = make_appspec(data_products=self._data_products([product]))
        assert agent.mt_05_cross_tenant_no_anonymization(appspec) == []

    def test_skips_non_cross_tenant(self, agent: MultiTenancyAgent) -> None:
        product = self._product("internal", cross_tenant=False)
        appspec = make_appspec(data_products=self._data_products([product]))
        assert agent.mt_05_cross_tenant_no_anonymization(appspec) == []

    def test_no_data_products(self, agent: MultiTenancyAgent) -> None:
        assert agent.mt_05_cross_tenant_no_anonymization(make_appspec()) == []


# =============================================================================
# MT-06  Visibility rules without partition key
# =============================================================================


class TestMT06VisibilityWithoutPartition:
    def _visibility_rule(self, condition: str) -> MagicMock:
        rule = MagicMock()
        rule.condition = condition
        rule.context = MagicMock()
        rule.context.value = "authenticated"
        return rule

    def test_flags_visibility_ignoring_partition(self, agent: MultiTenancyAgent) -> None:
        access = MagicMock()
        access.visibility = [self._visibility_rule("created_by = current_user")]
        access.permissions = []
        entity = mock_entity("Task", access=access)
        tenancy = _tenancy()
        findings = agent.mt_06_visibility_without_partition(make_appspec([entity], tenancy=tenancy))
        assert len(findings) == 1

    def test_passes_when_partition_referenced(self, agent: MultiTenancyAgent) -> None:
        access = MagicMock()
        access.visibility = [self._visibility_rule("tenant_id = current_tenant")]
        access.permissions = []
        entity = mock_entity("Task", access=access)
        tenancy = _tenancy()
        assert (
            agent.mt_06_visibility_without_partition(make_appspec([entity], tenancy=tenancy)) == []
        )

    def test_no_visibility_rules(self, agent: MultiTenancyAgent) -> None:
        access = MagicMock()
        access.visibility = []
        access.permissions = []
        entity = mock_entity("Task", access=access)
        tenancy = _tenancy()
        assert (
            agent.mt_06_visibility_without_partition(make_appspec([entity], tenancy=tenancy)) == []
        )


# =============================================================================
# MT-07  Shared topic namespace with strict tenancy
# =============================================================================


class TestMT07SharedTopicStrictTenancy:
    def test_flags_shared_topic_with_strict(self, agent: MultiTenancyAgent) -> None:
        from dazzle.core.ir.governance import TopicNamespaceMode

        tenancy = _tenancy(
            mode=TenancyMode.SCHEMA_PER_TENANT,
            topic_namespace=TopicNamespaceMode.SHARED,
        )
        findings = agent.mt_07_shared_topic_strict_tenancy(make_appspec(tenancy=tenancy))
        assert len(findings) == 1

    def test_passes_namespace_per_tenant(self, agent: MultiTenancyAgent) -> None:
        from dazzle.core.ir.governance import TopicNamespaceMode

        tenancy = _tenancy(
            mode=TenancyMode.SCHEMA_PER_TENANT,
            topic_namespace=TopicNamespaceMode.NAMESPACE_PER_TENANT,
        )
        assert agent.mt_07_shared_topic_strict_tenancy(make_appspec(tenancy=tenancy)) == []

    def test_passes_shared_schema(self, agent: MultiTenancyAgent) -> None:
        from dazzle.core.ir.governance import TopicNamespaceMode

        tenancy = _tenancy(
            mode=TenancyMode.SHARED_SCHEMA,
            topic_namespace=TopicNamespaceMode.SHARED,
        )
        assert agent.mt_07_shared_topic_strict_tenancy(make_appspec(tenancy=tenancy)) == []


# =============================================================================
# Full agent run
# =============================================================================


class TestMultiTenancyAgentRun:
    def test_agent_id(self, agent: MultiTenancyAgent) -> None:
        assert agent.agent_id == AgentId.MT

    def test_has_7_heuristics(self, agent: MultiTenancyAgent) -> None:
        assert len(agent.get_heuristics()) == 7

    def test_heuristic_ids(self, agent: MultiTenancyAgent) -> None:
        ids = [meta.heuristic_id for meta, _ in agent.get_heuristics()]
        assert ids == [f"MT-0{i}" for i in range(1, 8)]
