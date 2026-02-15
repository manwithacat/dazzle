"""Performance & Resource detection agent (PR-01 through PR-08)."""

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

# Relationship field kinds that trigger additional queries.
_RELATIONSHIP_KINDS = frozenset({"ref", "has_many", "has_one"})

# Threshold: entity with this many relationship fields is an N+1 risk.
_N_PLUS_1_THRESHOLD = 3

# Threshold: entity with this many total fields is "large".
_LARGE_ENTITY_FIELDS = 10

# Threshold: surface references beyond this count is "hot entity".
_HOT_ENTITY_SURFACES = 4


class PerformanceResourceAgent(DetectionAgent):
    """Detect performance and resource risks in the application spec."""

    @property
    def agent_id(self) -> AgentId:
        return AgentId.PR

    # ------------------------------------------------------------------
    # PR-01: N+1 risk on list surface
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="PR-01",
        category="performance",
        subcategory="query",
        title="N+1 risk on list surface",
    )
    def n_plus_1_list_surface(self, appspec: AppSpec) -> list[Finding]:
        """Flag list surfaces backed by entities with many relationship fields.

        ``ref`` fields are excluded from the count because the runtime
        auto-detects them at compile time and adds eager loading.  Only
        ``has_many`` and ``has_one`` relationships still carry N+1 risk.
        """
        findings: list[Finding] = []
        for surface in appspec.surfaces:
            if getattr(surface, "mode", None) is None:
                continue
            mode_val = surface.mode if isinstance(surface.mode, str) else surface.mode.value
            if mode_val != "list":
                continue
            entity_name = getattr(surface, "entity_ref", None) or getattr(surface, "entity", None)
            if not entity_name:
                continue
            entity = appspec.get_entity(entity_name)
            if entity is None:
                continue
            # Only count relationship fields NOT covered by auto-eager-load.
            # ref fields get auto-included at compile time; has_many/has_one do not.
            rel_fields = [
                f
                for f in entity.fields
                if f.type.kind.value in _RELATIONSHIP_KINDS and f.type.kind.value != "ref"
            ]
            if len(rel_fields) < _N_PLUS_1_THRESHOLD:
                continue
            field_names = [f.name for f in rel_fields]
            findings.append(
                Finding(
                    agent=AgentId.PR,
                    heuristic_id="PR-01",
                    category="performance",
                    subcategory="query",
                    severity=Severity.HIGH,
                    confidence=Confidence.LIKELY,
                    title=(f"List surface '{surface.name}' on entity '{entity_name}' has N+1 risk"),
                    description=(
                        f"Surface '{surface.name}' renders a list of "
                        f"'{entity_name}' which has {len(rel_fields)} "
                        f"relationship fields ({', '.join(field_names)}). "
                        f"Each row may trigger additional queries to resolve "
                        f"these references."
                    ),
                    evidence=[
                        Evidence(
                            evidence_type="ir_pattern",
                            location=f"surface:{surface.name}",
                            snippet=f"mode: list, entity: {entity_name}",
                            context=f"Relationship fields: {field_names}",
                        ),
                    ],
                    remediation=Remediation(
                        summary=(
                            "Add eager loading hints or create a view that "
                            "pre-joins the relationships."
                        ),
                        effort=RemediationEffort.MEDIUM,
                    ),
                    surface_name=surface.name,
                    entity_name=entity_name,
                    construct_type="surface",
                ),
            )
        return findings

    # ------------------------------------------------------------------
    # PR-02: Ref field without index constraint
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="PR-02",
        category="performance",
        subcategory="index",
        title="Ref field without index constraint",
    )
    def ref_without_index(self, appspec: AppSpec) -> list[Finding]:
        """Flag ref fields on entities that have no index constraint covering them."""
        from dazzle.core.ir import FieldTypeKind

        findings: list[Finding] = []
        for entity in appspec.domain.entities:
            indexed_fields: set[str] = set()
            constraints = getattr(entity, "constraints", None) or []
            for c in constraints:
                kind = c.kind if isinstance(c.kind, str) else c.kind.value
                if kind == "index":
                    indexed_fields.update(c.fields)

            for field in entity.fields:
                if field.type.kind != FieldTypeKind.REF:
                    continue
                if field.name in indexed_fields:
                    continue
                findings.append(
                    Finding(
                        agent=AgentId.PR,
                        heuristic_id="PR-02",
                        category="performance",
                        subcategory="index",
                        severity=Severity.MEDIUM,
                        confidence=Confidence.LIKELY,
                        title=(f"Ref field '{entity.name}.{field.name}' has no index"),
                        description=(
                            f"Entity '{entity.name}' has a ref field "
                            f"'{field.name}' (-> {field.type.ref_entity}) "
                            f"without an index constraint. Joins and lookups "
                            f"on this field will require full table scans."
                        ),
                        evidence=[
                            Evidence(
                                evidence_type="ir_pattern",
                                location=f"entity:{entity.name}",
                                snippet=f"field: {field.name} ref {field.type.ref_entity}",
                                context=f"Indexed fields: {sorted(indexed_fields) or '(none)'}",
                            ),
                        ],
                        remediation=Remediation(
                            summary=(f"Add an index constraint on '{entity.name}.{field.name}'."),
                            effort=RemediationEffort.SMALL,
                        ),
                        entity_name=entity.name,
                        construct_type="entity",
                    ),
                )
        return findings

    # ------------------------------------------------------------------
    # PR-03: Process with ALLOW overlap policy
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="PR-03",
        category="performance",
        subcategory="concurrency",
        title="Process with ALLOW overlap policy",
    )
    def process_allow_overlap(self, appspec: AppSpec) -> list[Finding]:
        """Flag processes that allow unbounded concurrent runs."""
        from dazzle.core.ir.process import OverlapPolicy

        findings: list[Finding] = []
        for process in appspec.processes:
            if process.overlap_policy != OverlapPolicy.ALLOW:
                continue
            findings.append(
                Finding(
                    agent=AgentId.PR,
                    heuristic_id="PR-03",
                    category="performance",
                    subcategory="concurrency",
                    severity=Severity.MEDIUM,
                    confidence=Confidence.LIKELY,
                    title=(f"Process '{process.name}' allows unbounded concurrent runs"),
                    description=(
                        f"Process '{process.name}' uses overlap_policy "
                        f"'allow', meaning multiple instances can run "
                        f"simultaneously. Under burst load this may exhaust "
                        f"worker slots and database connections."
                    ),
                    evidence=[
                        Evidence(
                            evidence_type="config_value",
                            location=f"process:{process.name}",
                            snippet="overlap_policy: allow",
                        ),
                    ],
                    remediation=Remediation(
                        summary=(
                            f"Use 'skip' or 'queue' overlap policy for process '{process.name}'."
                        ),
                        effort=RemediationEffort.SMALL,
                    ),
                    construct_type="process",
                ),
            )
        return findings

    # ------------------------------------------------------------------
    # PR-04: High event topic retention
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="PR-04",
        category="performance",
        subcategory="storage",
        title="High event topic retention",
    )
    def high_topic_retention(self, appspec: AppSpec) -> list[Finding]:
        """Flag event topics with retention exceeding 90 days."""
        findings: list[Finding] = []
        if appspec.event_model is None:
            return findings
        for topic in appspec.event_model.topics:
            if topic.retention_days <= 90:
                continue
            findings.append(
                Finding(
                    agent=AgentId.PR,
                    heuristic_id="PR-04",
                    category="performance",
                    subcategory="storage",
                    severity=Severity.LOW,
                    confidence=Confidence.POSSIBLE,
                    title=(f"Topic '{topic.name}' retains events for {topic.retention_days} days"),
                    description=(
                        f"Topic '{topic.name}' has retention_days="
                        f"{topic.retention_days}, exceeding 90 days. "
                        f"Long retention increases storage cost and may "
                        f"slow consumer catch-up on replay."
                    ),
                    evidence=[
                        Evidence(
                            evidence_type="config_value",
                            location=f"topic:{topic.name}",
                            snippet=f"retention_days: {topic.retention_days}",
                        ),
                    ],
                    remediation=Remediation(
                        summary=f"Review retention for topic '{topic.name}'.",
                        effort=RemediationEffort.TRIVIAL,
                    ),
                    construct_type="topic",
                ),
            )
        return findings

    # ------------------------------------------------------------------
    # PR-05: Large entity in list surface
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="PR-05",
        category="performance",
        subcategory="payload",
        title="Large entity in list surface",
    )
    def large_entity_list_surface(self, appspec: AppSpec) -> list[Finding]:
        """Flag list surfaces backed by entities with many fields.

        When a surface uses ``view_ref`` (a projection view), the runtime
        only SELECTs the view's columns — so we count view fields instead
        of entity fields.
        """
        findings: list[Finding] = []
        for surface in appspec.surfaces:
            if getattr(surface, "mode", None) is None:
                continue
            mode_val = surface.mode if isinstance(surface.mode, str) else surface.mode.value
            if mode_val != "list":
                continue
            entity_name = getattr(surface, "entity_ref", None) or getattr(surface, "entity", None)
            if not entity_name:
                continue
            entity = appspec.get_entity(entity_name)
            if entity is None:
                continue

            # If the surface has a view_ref, use the view's field count
            # instead of the entity's — the runtime projects only those columns.
            view_ref = getattr(surface, "view_ref", None)
            if view_ref:
                view = appspec.get_view(view_ref)
                if view is not None:
                    field_count = len(view.fields)
                else:
                    field_count = len(entity.fields)
            else:
                field_count = len(entity.fields)

            if field_count < _LARGE_ENTITY_FIELDS:
                continue
            findings.append(
                Finding(
                    agent=AgentId.PR,
                    heuristic_id="PR-05",
                    category="performance",
                    subcategory="payload",
                    severity=Severity.MEDIUM,
                    confidence=Confidence.POSSIBLE,
                    title=(
                        f"List surface '{surface.name}' renders "
                        f"{field_count}-field entity '{entity_name}'"
                    ),
                    description=(
                        f"Surface '{surface.name}' renders a list of "
                        f"'{entity_name}' which has {field_count} fields. "
                        f"Large entities in list mode may transfer "
                        f"unnecessary data. Consider using a view or "
                        f"selecting only needed columns."
                    ),
                    evidence=[
                        Evidence(
                            evidence_type="ir_pattern",
                            location=f"surface:{surface.name}",
                            snippet=f"entity: {entity_name}, fields: {field_count}",
                        ),
                    ],
                    remediation=Remediation(
                        summary="Create a view or limit fields in the surface.",
                        effort=RemediationEffort.SMALL,
                    ),
                    surface_name=surface.name,
                    entity_name=entity_name,
                    construct_type="surface",
                ),
            )
        return findings

    # ------------------------------------------------------------------
    # PR-06: Synchronous transaction execution
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="PR-06",
        category="performance",
        subcategory="blocking",
        title="Synchronous transaction execution",
    )
    def sync_transaction(self, appspec: AppSpec) -> list[Finding]:
        """Flag transactions using synchronous execution."""
        from dazzle.core.ir.ledgers import TransactionExecution

        findings: list[Finding] = []
        for txn in appspec.transactions:
            if txn.execution != TransactionExecution.SYNC:
                continue
            findings.append(
                Finding(
                    agent=AgentId.PR,
                    heuristic_id="PR-06",
                    category="performance",
                    subcategory="blocking",
                    severity=Severity.MEDIUM,
                    confidence=Confidence.LIKELY,
                    title=f"Transaction '{txn.name}' uses synchronous execution",
                    description=(
                        f"Transaction '{txn.name}' has execution='sync', "
                        f"which blocks the caller until the transfer "
                        f"completes. Under load this may exhaust request "
                        f"threads. Consider async execution for non-critical "
                        f"transfers."
                    ),
                    evidence=[
                        Evidence(
                            evidence_type="config_value",
                            location=f"transaction:{txn.name}",
                            snippet="execution: sync",
                        ),
                    ],
                    remediation=Remediation(
                        summary=f"Consider async execution for '{txn.name}'.",
                        effort=RemediationEffort.SMALL,
                    ),
                    construct_type="transaction",
                ),
            )
        return findings

    # ------------------------------------------------------------------
    # PR-07: Heavily surfaced entity
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="PR-07",
        category="performance",
        subcategory="hot_path",
        title="Heavily surfaced entity",
    )
    def heavily_surfaced_entity(self, appspec: AppSpec) -> list[Finding]:
        """Flag entities referenced by many surfaces."""
        findings: list[Finding] = []
        entity_surface_count: dict[str, int] = {}
        for surface in appspec.surfaces:
            entity_name = getattr(surface, "entity_ref", None) or getattr(surface, "entity", None)
            if entity_name:
                entity_surface_count[entity_name] = entity_surface_count.get(entity_name, 0) + 1

        for entity_name, count in sorted(entity_surface_count.items()):
            if count < _HOT_ENTITY_SURFACES:
                continue
            findings.append(
                Finding(
                    agent=AgentId.PR,
                    heuristic_id="PR-07",
                    category="performance",
                    subcategory="hot_path",
                    severity=Severity.MEDIUM,
                    confidence=Confidence.POSSIBLE,
                    title=(f"Entity '{entity_name}' is referenced by {count} surfaces"),
                    description=(
                        f"Entity '{entity_name}' is referenced by {count} "
                        f"surfaces, making it a hot-path entity. Ensure "
                        f"proper indexing, caching, and query optimization "
                        f"for this entity."
                    ),
                    evidence=[
                        Evidence(
                            evidence_type="ir_pattern",
                            location=f"entity:{entity_name}",
                            context=f"Referenced by {count} surfaces",
                        ),
                    ],
                    remediation=Remediation(
                        summary=(f"Add indexes and consider read replicas for '{entity_name}'."),
                        effort=RemediationEffort.MEDIUM,
                    ),
                    entity_name=entity_name,
                    construct_type="entity",
                ),
            )
        return findings

    # ------------------------------------------------------------------
    # PR-08: Process without explicit timeout
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="PR-08",
        category="performance",
        subcategory="timeout",
        title="Process without explicit timeout",
    )
    def process_default_timeout(self, appspec: AppSpec) -> list[Finding]:
        """Flag processes using the default 24-hour timeout."""
        findings: list[Finding] = []
        for process in appspec.processes:
            # Default is 86400 (24h). If a process uses exactly that, it
            # likely wasn't explicitly configured.
            if process.timeout_seconds != 86400:
                continue
            if not process.steps:
                continue
            findings.append(
                Finding(
                    agent=AgentId.PR,
                    heuristic_id="PR-08",
                    category="performance",
                    subcategory="timeout",
                    severity=Severity.LOW,
                    confidence=Confidence.POSSIBLE,
                    title=(f"Process '{process.name}' uses default 24h timeout"),
                    description=(
                        f"Process '{process.name}' has {len(process.steps)} "
                        f"steps but uses the default 24-hour timeout. "
                        f"An explicit timeout avoids zombie workflows and "
                        f"wasted resources."
                    ),
                    evidence=[
                        Evidence(
                            evidence_type="config_value",
                            location=f"process:{process.name}",
                            snippet=f"timeout_seconds: {process.timeout_seconds} (default)",
                        ),
                    ],
                    remediation=Remediation(
                        summary=f"Set an explicit timeout for process '{process.name}'.",
                        effort=RemediationEffort.TRIVIAL,
                    ),
                    construct_type="process",
                ),
            )
        return findings
