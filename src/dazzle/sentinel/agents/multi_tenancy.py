"""Multi-Tenancy detection agent (MT-01 through MT-07)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dazzle.sentinel.agents.base import DetectionAgent, heuristic
from dazzle.sentinel.models import (
    AgentId,
    Confidence,
    Evidence,
    Finding,
    Remediation,
    RemediationEffort,
    Severity,
)

if TYPE_CHECKING:
    from dazzle.core.ir.appspec import AppSpec


class MultiTenancyAgent(DetectionAgent):
    """Detect multi-tenancy isolation gaps and configuration issues."""

    @property
    def agent_id(self) -> AgentId:
        return AgentId.MT

    # ------------------------------------------------------------------
    # MT-01: Missing partition key field
    # ------------------------------------------------------------------

    @heuristic(
        heuristic_id="MT-01",
        category="multi-tenancy",
        subcategory="partition-key",
        title="Missing partition key field",
    )
    def mt_01_missing_partition_key(self, appspec: AppSpec) -> list[Finding]:
        """Flag shared-schema entities that lack the configured partition key."""
        from dazzle.core.ir.governance import TenancyMode

        findings: list[Finding] = []
        tenancy = appspec.tenancy
        if tenancy is None:
            return findings
        if tenancy.isolation.mode != TenancyMode.SHARED_SCHEMA:
            return findings

        partition_key = tenancy.isolation.partition_key
        excluded = set(tenancy.entities_excluded)

        for entity in appspec.domain.entities:
            if entity.name in excluded:
                continue
            has_key = any(f.name == partition_key for f in entity.fields)
            if not has_key:
                findings.append(
                    Finding(
                        agent=AgentId.MT,
                        heuristic_id="MT-01",
                        category="multi-tenancy",
                        subcategory="partition-key",
                        severity=Severity.CRITICAL,
                        confidence=Confidence.CONFIRMED,
                        title=f"Entity '{entity.name}' missing partition key '{partition_key}'",
                        description=(
                            f"Tenancy mode is shared_schema with partition key "
                            f"'{partition_key}', but entity '{entity.name}' does not "
                            f"declare that field. Every query against this table will "
                            f"lack tenant isolation, risking cross-tenant data leakage."
                        ),
                        entity_name=entity.name,
                        construct_type="entity",
                        evidence=[
                            Evidence(
                                evidence_type="missing_construct",
                                location=f"entity {entity.name}",
                                context=(
                                    f"Expected field '{partition_key}' not found among "
                                    f"fields: {[f.name for f in entity.fields]}"
                                ),
                            ),
                        ],
                        remediation=Remediation(
                            summary=f"Add '{partition_key}' field to entity '{entity.name}'",
                            effort=RemediationEffort.SMALL,
                            guidance=(
                                f"Add a '{partition_key}' field of type 'ref Tenant' or "
                                f"'uuid required' to ensure every row is scoped to a tenant. "
                                f"Alternatively, add '{entity.name}' to tenancy.entities_excluded "
                                f"if this entity is intentionally global."
                            ),
                            dsl_example=(
                                f'entity {entity.name} "{entity.title or entity.name}":\n'
                                f"  {partition_key}: uuid required"
                            ),
                        ),
                    )
                )
        return findings

    # ------------------------------------------------------------------
    # MT-02: Ref chain missing tenant field
    # ------------------------------------------------------------------

    @heuristic(
        heuristic_id="MT-02",
        category="multi-tenancy",
        subcategory="ref-chain",
        title="Ref chain missing tenant field",
    )
    def mt_02_ref_chain_missing_tenant(self, appspec: AppSpec) -> list[Finding]:
        """Flag entities that reference a tenant-scoped entity but lack the partition key."""
        from dazzle.core.ir.fields import FieldTypeKind

        findings: list[Finding] = []
        tenancy = appspec.tenancy
        if tenancy is None:
            return findings

        partition_key = tenancy.isolation.partition_key

        # Build set of entity names that have the partition key field
        entities_with_key: set[str] = set()
        for entity in appspec.domain.entities:
            if any(f.name == partition_key for f in entity.fields):
                entities_with_key.add(entity.name)

        if not entities_with_key:
            return findings

        # Check entities that reference tenant-scoped entities
        for entity in appspec.domain.entities:
            if entity.name in entities_with_key:
                continue
            for field in entity.fields:
                if (
                    field.type.kind == FieldTypeKind.REF
                    and field.type.ref_entity in entities_with_key
                ):
                    findings.append(
                        Finding(
                            agent=AgentId.MT,
                            heuristic_id="MT-02",
                            category="multi-tenancy",
                            subcategory="ref-chain",
                            severity=Severity.HIGH,
                            confidence=Confidence.CONFIRMED,
                            title=(
                                f"Entity '{entity.name}' refs tenant-scoped "
                                f"'{field.type.ref_entity}' but lacks '{partition_key}'"
                            ),
                            description=(
                                f"Entity '{entity.name}' has a ref to "
                                f"'{field.type.ref_entity}' which carries the "
                                f"'{partition_key}' partition key, but '{entity.name}' "
                                f"itself does not. Joining across the reference without "
                                f"a local partition key makes tenant-scoped queries "
                                f"error-prone and may leak data."
                            ),
                            entity_name=entity.name,
                            construct_type="entity",
                            evidence=[
                                Evidence(
                                    evidence_type="ir_pattern",
                                    location=f"entity {entity.name}.{field.name}",
                                    snippet=f"ref {field.type.ref_entity}",
                                    context=(
                                        f"Field '{field.name}' references "
                                        f"'{field.type.ref_entity}' which has "
                                        f"'{partition_key}', but '{entity.name}' does not."
                                    ),
                                ),
                            ],
                            remediation=Remediation(
                                summary=(f"Add '{partition_key}' to entity '{entity.name}'"),
                                effort=RemediationEffort.SMALL,
                                guidance=(
                                    f"Propagate the partition key to '{entity.name}' so "
                                    f"queries can be scoped to a single tenant without "
                                    f"needing a join through '{field.type.ref_entity}'."
                                ),
                                dsl_example=(
                                    f'entity {entity.name} "{entity.title or entity.name}":\n'
                                    f"  {partition_key}: uuid required"
                                ),
                            ),
                        )
                    )
                    # One finding per entity is enough
                    break
        return findings

    # ------------------------------------------------------------------
    # MT-03: Singleton in multi-tenant app
    # ------------------------------------------------------------------

    @heuristic(
        heuristic_id="MT-03",
        category="multi-tenancy",
        subcategory="singleton",
        title="Singleton in multi-tenant app",
    )
    def mt_03_singleton_in_multi_tenant(self, appspec: AppSpec) -> list[Finding]:
        """Flag singleton entities in a multi-tenant app (ambiguous scope)."""
        findings: list[Finding] = []
        if appspec.tenancy is None:
            return findings

        for entity in appspec.domain.entities:
            if entity.is_singleton:
                findings.append(
                    Finding(
                        agent=AgentId.MT,
                        heuristic_id="MT-03",
                        category="multi-tenancy",
                        subcategory="singleton",
                        severity=Severity.MEDIUM,
                        confidence=Confidence.LIKELY,
                        title=f"Singleton entity '{entity.name}' in multi-tenant app",
                        description=(
                            f"Entity '{entity.name}' is marked as singleton "
                            f"(is_singleton=true) in an app with tenancy configured. "
                            f"It is ambiguous whether the singleton is global (one row "
                            f"total) or per-tenant (one row per tenant). This can lead "
                            f"to configuration bleed across tenants."
                        ),
                        entity_name=entity.name,
                        construct_type="entity",
                        evidence=[
                            Evidence(
                                evidence_type="ir_pattern",
                                location=f"entity {entity.name}",
                                context=("is_singleton=true combined with tenancy configuration"),
                            ),
                        ],
                        remediation=Remediation(
                            summary=(f"Clarify singleton scope for '{entity.name}'"),
                            effort=RemediationEffort.SMALL,
                            guidance=(
                                "If this singleton is per-tenant, add the partition key "
                                "field so each tenant gets its own row. If it is truly "
                                "global, add it to tenancy.entities_excluded to make the "
                                "intent explicit."
                            ),
                        ),
                    )
                )
        return findings

    # ------------------------------------------------------------------
    # MT-04: No tenant root entity
    # ------------------------------------------------------------------

    @heuristic(
        heuristic_id="MT-04",
        category="multi-tenancy",
        subcategory="tenant-root",
        title="No tenant root entity",
    )
    def mt_04_no_tenant_root(self, appspec: AppSpec) -> list[Finding]:
        """Flag tenancy configured but no entity marked as tenant root."""
        findings: list[Finding] = []
        if appspec.tenancy is None:
            return findings

        has_root = any(e.is_tenant_root for e in appspec.domain.entities)
        if not has_root:
            findings.append(
                Finding(
                    agent=AgentId.MT,
                    heuristic_id="MT-04",
                    category="multi-tenancy",
                    subcategory="tenant-root",
                    severity=Severity.HIGH,
                    confidence=Confidence.CONFIRMED,
                    title="No entity marked as tenant root",
                    description=(
                        "Tenancy is configured but no entity has "
                        "is_tenant_root=true. Without an explicit tenant root, "
                        "the runtime cannot determine which entity represents "
                        "a tenant, impacting provisioning, scoping, and "
                        "cascade-delete semantics."
                    ),
                    construct_type="tenancy",
                    evidence=[
                        Evidence(
                            evidence_type="missing_construct",
                            location="domain entities",
                            context=("Checked all entities; none have is_tenant_root=true"),
                        ),
                    ],
                    remediation=Remediation(
                        summary="Mark one entity as is_tenant_root=true",
                        effort=RemediationEffort.SMALL,
                        guidance=(
                            "Add 'is_tenant_root: true' to the entity that "
                            "represents a tenant (e.g. Organisation, Tenant, "
                            "Company). This entity becomes the root of the "
                            "tenant hierarchy."
                        ),
                        dsl_example=(
                            'entity Tenant "Tenant":\n'
                            "  is_tenant_root: true\n"
                            "  id: uuid pk\n"
                            "  name: str(200) required"
                        ),
                    ),
                )
            )
        return findings

    # ------------------------------------------------------------------
    # MT-05: Cross-tenant data product without anonymization
    # ------------------------------------------------------------------

    @heuristic(
        heuristic_id="MT-05",
        category="multi-tenancy",
        subcategory="data-product",
        title="Cross-tenant data product without anonymization",
    )
    def mt_05_cross_tenant_no_anonymization(self, appspec: AppSpec) -> list[Finding]:
        """Flag cross-tenant data products missing anonymization transforms."""
        from dazzle.core.ir.governance import DataProductTransform

        findings: list[Finding] = []
        if appspec.data_products is None:
            return findings

        anonymizing = {DataProductTransform.PSEUDONYMISE, DataProductTransform.AGGREGATE}

        for product in appspec.data_products.products:
            if not product.cross_tenant:
                continue
            applied = set(product.transforms)
            if not applied & anonymizing:
                findings.append(
                    Finding(
                        agent=AgentId.MT,
                        heuristic_id="MT-05",
                        category="multi-tenancy",
                        subcategory="data-product",
                        severity=Severity.HIGH,
                        confidence=Confidence.CONFIRMED,
                        title=(f"Cross-tenant data product '{product.name}' lacks anonymization"),
                        description=(
                            f"Data product '{product.name}' is marked "
                            f"cross_tenant=true but its transforms "
                            f"({[t.value for t in product.transforms]}) do not "
                            f"include 'pseudonymise' or 'aggregate'. Exposing "
                            f"raw tenant data across boundaries without "
                            f"anonymization risks regulatory non-compliance."
                        ),
                        construct_type="data_product",
                        evidence=[
                            Evidence(
                                evidence_type="config_value",
                                location=f"data_product {product.name}",
                                snippet=f"cross_tenant: true, transforms: {[t.value for t in product.transforms]}",
                                context=(
                                    "Neither pseudonymise nor aggregate is present "
                                    "in the transform pipeline."
                                ),
                            ),
                        ],
                        remediation=Remediation(
                            summary=(f"Add anonymization transform to '{product.name}'"),
                            effort=RemediationEffort.MEDIUM,
                            guidance=(
                                "Add 'pseudonymise' or 'aggregate' (or both) to the "
                                "transforms list so that tenant-specific identifiers "
                                "are removed before data crosses tenant boundaries."
                            ),
                            dsl_example=(
                                f"data_product {product.name}:\n"
                                f"  cross_tenant: true\n"
                                f"  transforms: [pseudonymise, aggregate]"
                            ),
                        ),
                    )
                )
        return findings

    # ------------------------------------------------------------------
    # MT-06: Visibility rules without partition key
    # ------------------------------------------------------------------

    @heuristic(
        heuristic_id="MT-06",
        category="multi-tenancy",
        subcategory="visibility",
        title="Visibility rules without partition key",
    )
    def mt_06_visibility_without_partition(self, appspec: AppSpec) -> list[Finding]:
        """Flag entities with visibility rules that never reference the partition key."""
        findings: list[Finding] = []
        tenancy = appspec.tenancy
        if tenancy is None:
            return findings

        partition_key = tenancy.isolation.partition_key

        for entity in appspec.domain.entities:
            if entity.access is None:
                continue
            if not entity.access.visibility:
                continue

            # Check if any visibility rule references the partition key
            references_key = False
            for rule in entity.access.visibility:
                if partition_key in str(rule.condition):
                    references_key = True
                    break

            if not references_key:
                rule_summaries = [
                    f"{r.context.value}: {r.condition}" for r in entity.access.visibility
                ]
                findings.append(
                    Finding(
                        agent=AgentId.MT,
                        heuristic_id="MT-06",
                        category="multi-tenancy",
                        subcategory="visibility",
                        severity=Severity.MEDIUM,
                        confidence=Confidence.LIKELY,
                        title=(
                            f"Visibility rules on '{entity.name}' ignore "
                            f"partition key '{partition_key}'"
                        ),
                        description=(
                            f"Entity '{entity.name}' defines visibility rules "
                            f"but none reference the partition key '{partition_key}'. "
                            f"Row-level security that does not account for tenant "
                            f"scoping may expose rows to users in other tenants."
                        ),
                        entity_name=entity.name,
                        construct_type="entity",
                        evidence=[
                            Evidence(
                                evidence_type="ir_pattern",
                                location=f"entity {entity.name}.access.visibility",
                                snippet=str(rule_summaries),
                                context=(
                                    f"None of the {len(entity.access.visibility)} "
                                    f"visibility rule(s) mention '{partition_key}'."
                                ),
                            ),
                        ],
                        remediation=Remediation(
                            summary=(
                                f"Add '{partition_key}' condition to visibility rules "
                                f"on '{entity.name}'"
                            ),
                            effort=RemediationEffort.SMALL,
                            guidance=(
                                f"Include a condition referencing '{partition_key}' "
                                f"(e.g., '{partition_key} = current_tenant') in the "
                                f"visibility rules to enforce tenant-level row filtering."
                            ),
                        ),
                    )
                )
        return findings

    # ------------------------------------------------------------------
    # MT-07: Shared topic namespace with strict tenancy
    # ------------------------------------------------------------------

    @heuristic(
        heuristic_id="MT-07",
        category="multi-tenancy",
        subcategory="topic-namespace",
        title="Shared topic namespace with strict tenancy",
    )
    def mt_07_shared_topic_strict_tenancy(self, appspec: AppSpec) -> list[Finding]:
        """Flag shared topic namespace when tenancy uses strict isolation."""
        from dazzle.core.ir.governance import TenancyMode, TopicNamespaceMode

        findings: list[Finding] = []
        tenancy = appspec.tenancy
        if tenancy is None:
            return findings

        strict_modes = {TenancyMode.SCHEMA_PER_TENANT, TenancyMode.DATABASE_PER_TENANT}
        if (
            tenancy.isolation.topic_namespace == TopicNamespaceMode.SHARED
            and tenancy.isolation.mode in strict_modes
        ):
            findings.append(
                Finding(
                    agent=AgentId.MT,
                    heuristic_id="MT-07",
                    category="multi-tenancy",
                    subcategory="topic-namespace",
                    severity=Severity.MEDIUM,
                    confidence=Confidence.CONFIRMED,
                    title="Shared topic namespace with strict tenancy isolation",
                    description=(
                        f"Tenancy isolation is '{tenancy.isolation.mode.value}' "
                        f"(strict) but the topic namespace is 'shared'. Database "
                        f"records are physically separated per tenant, yet events "
                        f"flow through shared topics. A consumer bug or missing "
                        f"filter could route events to the wrong tenant."
                    ),
                    construct_type="tenancy",
                    evidence=[
                        Evidence(
                            evidence_type="config_value",
                            location="tenancy.isolation",
                            snippet=(
                                f"mode: {tenancy.isolation.mode.value}, "
                                f"topic_namespace: {tenancy.isolation.topic_namespace.value}"
                            ),
                            context=(
                                "Strict DB isolation combined with shared event "
                                "topics creates an isolation mismatch."
                            ),
                        ),
                    ],
                    remediation=Remediation(
                        summary="Switch topic namespace to namespace_per_tenant",
                        effort=RemediationEffort.MEDIUM,
                        guidance=(
                            "Set 'topics: namespace_per_tenant' in the tenancy "
                            "block so each tenant's events flow through dedicated "
                            "topic namespaces, matching the strict DB isolation."
                        ),
                        dsl_example=(
                            "tenancy:\n"
                            f"  mode: {tenancy.isolation.mode.value}\n"
                            "  topics: namespace_per_tenant"
                        ),
                    ),
                )
            )
        return findings
