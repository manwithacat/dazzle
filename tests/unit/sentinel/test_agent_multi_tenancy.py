"""Tests for the Multi-Tenancy detection agent (MT-01 to MT-04, MT-06, MT-07).

One table: each case builds an AppSpec, runs one heuristic and pins the exact
findings (see ``assert_findings``). Agent identity, heuristic order and the
clean-spec run live in ``test_registry.py``.
"""

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest

from dazzle.core.ir import FieldTypeKind
from dazzle.core.ir.governance import TenancyMode, TopicNamespaceMode
from dazzle.sentinel.agents.multi_tenancy import MultiTenancyAgent
from dazzle.sentinel.models import Severity

from .conftest import (
    assert_findings,
    make_appspec,
    make_entity,
    make_field,
    mock_entity,
    pk_field,
    ref_field,
    str_field,
)

# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _tenancy(
    mode: TenancyMode = TenancyMode.SHARED_SCHEMA,
    excluded: list[str] | None = None,
    topic_namespace: object | None = None,
) -> MagicMock:
    isolation = MagicMock()
    isolation.mode = mode
    isolation.partition_key = "tenant_id"
    isolation.topic_namespace = topic_namespace
    t = MagicMock()
    t.isolation = isolation
    t.entities_excluded = excluded or []
    return t


def _tenanted(*entities: Any, **tenancy_kw: Any) -> Any:
    return make_appspec(list(entities), tenancy=_tenancy(**tenancy_kw))


def _tenant_id() -> Any:
    return make_field("tenant_id", FieldTypeKind.UUID)


def _order_and_line_item(*, line_item_keyed: bool) -> Any:
    order = make_entity("Order", [pk_field(), _tenant_id()])
    line_fields = [pk_field(), ref_field("order", "Order")]
    if line_item_keyed:
        line_fields.append(_tenant_id())
    return _tenanted(order, make_entity("LineItem", line_fields))


def _visibility(*conditions: str) -> Any:
    access = MagicMock()
    access.visibility = []
    for condition in conditions:
        rule = MagicMock()
        rule.condition = condition
        rule.context = MagicMock()
        rule.context.value = "authenticated"
        access.visibility.append(rule)
    access.permissions = []
    return _tenanted(mock_entity("Task", access=access))


def _topics(mode: TenancyMode, namespace: TopicNamespaceMode) -> Any:
    return make_appspec(tenancy=_tenancy(mode=mode, topic_namespace=namespace))


# ---------------------------------------------------------------------------
# Heuristic table
# ---------------------------------------------------------------------------

CASES = [
    # MT-01  shared-schema entity without the partition key field
    pytest.param(
        "mt_01_missing_partition_key",
        lambda: _tenanted(make_entity("Task", [pk_field(), str_field("title")])),
        [{"heuristic_id": "MT-01", "severity": Severity.CRITICAL, "title_has": "tenant_id"}],
        id="MT-01-flags-entity-without-partition-key",
    ),
    pytest.param(
        "mt_01_missing_partition_key",
        lambda: _tenanted(make_entity("Task", [pk_field(), str_field("title"), _tenant_id()])),
        [],
        id="MT-01-partition-key-present",
    ),
    pytest.param(
        "mt_01_missing_partition_key",
        lambda: _tenanted(make_entity("Config", [pk_field()]), excluded=["Config"]),
        [],
        id="MT-01-skips-excluded-entity",
    ),
    pytest.param("mt_01_missing_partition_key", make_appspec, [], id="MT-01-no-tenancy"),
    pytest.param(
        "mt_01_missing_partition_key",
        lambda: _tenanted(make_entity("Task", [pk_field()]), mode=TenancyMode.DATABASE_PER_TENANT),
        [],
        id="MT-01-skips-non-shared-schema",
    ),
    # MT-02  ref to a tenant-scoped entity from an entity without the key
    pytest.param(
        "mt_02_ref_chain_missing_tenant",
        lambda: _order_and_line_item(line_item_keyed=False),
        [{"heuristic_id": "MT-02", "title_has": "LineItem"}],
        id="MT-02-flags-unkeyed-ref-to-tenant-entity",
    ),
    pytest.param(
        "mt_02_ref_chain_missing_tenant",
        lambda: _order_and_line_item(line_item_keyed=True),
        [],
        id="MT-02-both-keyed",
    ),
    pytest.param("mt_02_ref_chain_missing_tenant", make_appspec, [], id="MT-02-no-tenancy"),
    # MT-03  singleton in a multi-tenant app
    pytest.param(
        "mt_03_singleton_in_multi_tenant",
        lambda: _tenanted(make_entity("AppConfig", is_singleton=True)),
        [{"heuristic_id": "MT-03", "severity": Severity.MEDIUM}],
        id="MT-03-flags-singleton",
    ),
    pytest.param(
        "mt_03_singleton_in_multi_tenant",
        lambda: _tenanted(make_entity("Task")),
        [],
        id="MT-03-non-singleton",
    ),
    pytest.param(
        "mt_03_singleton_in_multi_tenant",
        lambda: make_appspec([make_entity("AppConfig", is_singleton=True)]),
        [],
        id="MT-03-no-tenancy",
    ),
    # MT-04  no tenant-root entity
    pytest.param(
        "mt_04_no_tenant_root",
        lambda: _tenanted(make_entity("Task")),
        [{"heuristic_id": "MT-04", "severity": Severity.HIGH}],
        id="MT-04-flags-missing-root",
    ),
    pytest.param(
        "mt_04_no_tenant_root",
        lambda: _tenanted(make_entity("Tenant", is_tenant_root=True)),
        [],
        id="MT-04-root-present",
    ),
    pytest.param("mt_04_no_tenant_root", make_appspec, [], id="MT-04-no-tenancy"),
    # MT-06  visibility rule that ignores the partition key
    pytest.param(
        "mt_06_visibility_without_partition",
        lambda: _visibility("created_by = current_user"),
        [{"heuristic_id": "MT-06"}],
        id="MT-06-flags-visibility-ignoring-partition",
    ),
    pytest.param(
        "mt_06_visibility_without_partition",
        lambda: _visibility("tenant_id = current_tenant"),
        [],
        id="MT-06-partition-referenced",
    ),
    pytest.param(
        "mt_06_visibility_without_partition", _visibility, [], id="MT-06-no-visibility-rules"
    ),
    # MT-07  shared topic namespace under strict (schema-per-tenant) isolation
    pytest.param(
        "mt_07_shared_topic_strict_tenancy",
        lambda: _topics(TenancyMode.SCHEMA_PER_TENANT, TopicNamespaceMode.SHARED),
        [{"heuristic_id": "MT-07"}],
        id="MT-07-flags-shared-topic-with-strict-tenancy",
    ),
    pytest.param(
        "mt_07_shared_topic_strict_tenancy",
        lambda: _topics(TenancyMode.SCHEMA_PER_TENANT, TopicNamespaceMode.NAMESPACE_PER_TENANT),
        [],
        id="MT-07-namespace-per-tenant",
    ),
    pytest.param(
        "mt_07_shared_topic_strict_tenancy",
        lambda: _topics(TenancyMode.SHARED_SCHEMA, TopicNamespaceMode.SHARED),
        [],
        id="MT-07-shared-schema",
    ),
]


@pytest.mark.parametrize(("heuristic", "build", "expected"), CASES)
def test_heuristic(
    heuristic: str, build: Callable[[], Any], expected: list[dict[str, Any]]
) -> None:
    assert_findings(getattr(MultiTenancyAgent(), heuristic)(build()), expected)
