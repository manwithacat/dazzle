"""
Event-First MCP tools for Phase H.

Provides semantic extraction, validation, diff, and inference tools
for event-driven architecture support.

Part of v0.18.0 Event-First Architecture (Issue #25, Phase H).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from dazzle.core import ir
from dazzle.core.fileset import discover_dsl_files
from dazzle.core.linker import build_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules

logger = logging.getLogger("dazzle.mcp.event_first")


# ============================================================================
# Semantic Extraction Tools
# ============================================================================


@dataclass
class SemanticExtraction:
    """Result of semantic extraction from AppSpec."""

    entities: list[dict[str, Any]] = field(default_factory=list)
    commands: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    projections: list[dict[str, Any]] = field(default_factory=list)
    tenancy_signals: list[dict[str, Any]] = field(default_factory=list)
    compliance_signals: list[dict[str, Any]] = field(default_factory=list)


def extract_semantics(appspec: ir.AppSpec) -> SemanticExtraction:
    """Extract semantic elements from an AppSpec.

    Returns structured information about:
    - Entities with their fields and relationships
    - Commands (mutations implied by surfaces)
    - Events (from HLESS streams and entity changes)
    - Projections (read models)
    - Tenancy signals (multi-tenant indicators)
    - Compliance signals (PII, financial data)
    """
    result = SemanticExtraction()

    # Extract entities
    for entity in appspec.domain.entities:
        # Extract relationships first
        relationships: list[dict[str, Any]] = []
        for rel_field in entity.fields:
            if hasattr(rel_field.type, "kind"):
                kind = rel_field.type.kind.value
                if kind in ("ref", "has_many", "has_one", "belongs_to", "embeds"):
                    relationships.append(
                        {
                            "field": rel_field.name,
                            "type": kind,
                            "target": rel_field.type.ref_entity,
                        }
                    )

        entity_info: dict[str, Any] = {
            "name": entity.name,
            "title": entity.title,
            "fields": [
                {
                    "name": f.name,
                    "type": f.type.kind.value if hasattr(f.type, "kind") else str(f.type),
                    "required": f.is_required,
                    "pk": f.is_primary_key,
                }
                for f in entity.fields
            ],
            "relationships": relationships,
            "has_state_machine": bool(entity.state_machine),
        }

        result.entities.append(entity_info)

    # Extract commands from surfaces
    for surface in appspec.surfaces:
        if surface.mode.value in ("create", "edit", "form") and surface.entity_ref:
            result.commands.append(
                {
                    "name": f"{surface.entity_ref}_{surface.mode.value}",
                    "entity": surface.entity_ref,
                    "type": surface.mode.value,
                    "source": f"surface:{surface.name}",
                }
            )

    # Extract events from HLESS streams
    if appspec.streams:
        for stream in appspec.streams:
            result.events.append(
                {
                    "stream": stream.name,
                    "record_kind": stream.record_kind.value if stream.record_kind else "unknown",
                    "partition_key": stream.partition_key,
                    "idempotency": stream.idempotency.strategy_type.value
                    if stream.idempotency
                    else None,
                }
            )

    # Infer events from entities (CRUD operations)
    for entity in appspec.domain.entities:
        for action in ["created", "updated", "deleted"]:
            result.events.append(
                {
                    "stream": f"app.{entity.name}.{action}",
                    "record_kind": "FACT",
                    "partition_key": "id",
                    "idempotency": "event_id",
                    "inferred": True,
                }
            )

    # Extract projections from AppSpec
    if appspec.projections:
        for proj in appspec.projections:
            result.projections.append(
                {
                    "name": proj.name,
                    "entity": proj.target_entity,
                    "source_topic": proj.source_topic,
                }
            )

    # Extract tenancy signals
    if appspec.tenancy:
        result.tenancy_signals.append(
            {
                "type": "explicit_config",
                "mode": appspec.tenancy.isolation.mode.value,
                "partition_key": appspec.tenancy.isolation.partition_key,
                "topic_namespace": appspec.tenancy.isolation.topic_namespace.value,
            }
        )

    # Check for tenant_id fields
    for entity in appspec.domain.entities:
        for f in entity.fields:
            if f.name == "tenant_id" or f.name.endswith("_tenant_id"):
                result.tenancy_signals.append(
                    {
                        "type": "field_indicator",
                        "entity": entity.name,
                        "field": f.name,
                    }
                )

    # Extract compliance signals from policies
    if appspec.policies:
        for cls in appspec.policies.classifications:
            result.compliance_signals.append(
                {
                    "type": "classification",
                    "entity": cls.entity,
                    "field": cls.field,
                    "classification": cls.classification.value,
                    "retention": cls.retention.value if cls.retention else None,
                }
            )

    # Infer compliance from field names
    pii_patterns = ["email", "phone", "ssn", "address", "name", "dob", "birth"]
    financial_patterns = ["amount", "total", "price", "cost", "balance", "payment"]

    for entity in appspec.domain.entities:
        for f in entity.fields:
            field_lower = f.name.lower()
            for pattern in pii_patterns:
                if pattern in field_lower:
                    result.compliance_signals.append(
                        {
                            "type": "inferred_pii",
                            "entity": entity.name,
                            "field": f.name,
                            "pattern": pattern,
                            "confidence": 0.8,
                        }
                    )
                    break

            for pattern in financial_patterns:
                if pattern in field_lower:
                    result.compliance_signals.append(
                        {
                            "type": "inferred_financial",
                            "entity": entity.name,
                            "field": f.name,
                            "pattern": pattern,
                            "confidence": 0.8,
                        }
                    )
                    break

    return result


# ============================================================================
# Validation Services
# ============================================================================


class ValidationSeverity(str, Enum):
    """Severity level for validation issues."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationIssue:
    """A validation issue found in the AppSpec."""

    code: str
    severity: ValidationSeverity
    message: str
    location: str | None = None
    suggestion: str | None = None


def validate_event_naming(appspec: ir.AppSpec) -> list[ValidationIssue]:
    """Validate event naming conventions.

    Checks:
    - Event names follow domain.entity.action pattern
    - Version numbers are valid
    - No reserved words used
    """
    issues: list[ValidationIssue] = []

    if not appspec.streams:
        return issues

    for stream in appspec.streams:
        # Check naming pattern
        parts = stream.name.split(".")
        if len(parts) < 2:
            issues.append(
                ValidationIssue(
                    code="E_EVENT_NAMING",
                    severity=ValidationSeverity.ERROR,
                    message=f"Stream '{stream.name}' should follow domain.entity[.action] pattern",
                    location=f"stream:{stream.name}",
                    suggestion="Use format like 'app.order.created' or 'office.mail.raw'",
                )
            )

        # Check for schema definitions
        if not stream.schemas:
            issues.append(
                ValidationIssue(
                    code="W_NO_SCHEMA",
                    severity=ValidationSeverity.WARNING,
                    message=f"Stream '{stream.name}' has no schema definitions",
                    location=f"stream:{stream.name}",
                    suggestion="Add schemas field for schema evolution support",
                )
            )

    return issues


def detect_idempotency_hazards(appspec: ir.AppSpec) -> list[ValidationIssue]:
    """Detect potential idempotency issues.

    Checks:
    - Consumers without idempotency strategy
    - External effects without idempotency keys
    - Non-deterministic operations in projections
    """
    issues: list[ValidationIssue] = []

    # Check HLESS streams - idempotency is required so this should always be present
    # But we still check in case of malformed specs
    if appspec.streams:
        for stream in appspec.streams:
            if not stream.idempotency:
                issues.append(
                    ValidationIssue(
                        code="W_NO_IDEMPOTENCY",
                        severity=ValidationSeverity.WARNING,
                        message=f"Stream '{stream.name}' has no idempotency strategy",
                        location=f"stream:{stream.name}",
                        suggestion="Add idempotency (event_id, source_dedup, provider_dedup)",
                    )
                )

    # Check subscriptions for idempotency
    for sub in appspec.subscriptions:
        # Subscriptions are assumed to need idempotency handling
        issues.append(
            ValidationIssue(
                code="I_SUBSCRIPTION_IDEMPOTENCY",
                severity=ValidationSeverity.INFO,
                message=f"Subscription '{sub.group_id}' should use inbox deduplication",
                location=f"subscription:{sub.group_id}",
                suggestion="Ensure handlers are idempotent or use inbox pattern",
            )
        )

    # Note: external_effect and idempotency_key are future IntegrationAction fields
    # For now, we skip external effect checking until the IR supports it

    return issues


def check_projection_necessity(appspec: ir.AppSpec) -> list[ValidationIssue]:
    """Check if projections are necessary and used.

    Warns about:
    - Projections that duplicate entity tables
    - Projections not referenced by any surface
    - Missing projections for complex queries
    """
    issues: list[ValidationIssue] = []

    if not appspec.projections:
        return issues

    # Get all surfaces to check projection usage
    surface_entities = {s.entity_ref for s in appspec.surfaces if s.entity_ref}

    for proj in appspec.projections:
        # Check if projection duplicates entity
        if proj.target_entity:
            entity = appspec.domain.get_entity(proj.target_entity)
            if entity and proj.target_entity.lower() == entity.name.lower():
                issues.append(
                    ValidationIssue(
                        code="W_PROJECTION_DUPLICATES_ENTITY",
                        severity=ValidationSeverity.WARNING,
                        message=f"Projection '{proj.name}' targets same table as entity",
                        location=f"projection:{proj.name}",
                        suggestion="Consider if projection adds value or use entity table directly",
                    )
                )

            # Check if projection is used
            if proj.target_entity not in surface_entities:
                issues.append(
                    ValidationIssue(
                        code="I_PROJECTION_NOT_USED",
                        severity=ValidationSeverity.INFO,
                        message=f"Projection '{proj.name}' entity not used in any surface",
                        location=f"projection:{proj.name}",
                        suggestion="Verify projection is needed or will be used by API",
                    )
                )

    return issues


def validate_event_first(appspec: ir.AppSpec) -> dict[str, Any]:
    """Run all event-first validations.

    Returns a structured validation report.
    """
    all_issues: list[ValidationIssue] = []

    all_issues.extend(validate_event_naming(appspec))
    all_issues.extend(detect_idempotency_hazards(appspec))
    all_issues.extend(check_projection_necessity(appspec))

    # Group by severity
    errors = [i for i in all_issues if i.severity == ValidationSeverity.ERROR]
    warnings = [i for i in all_issues if i.severity == ValidationSeverity.WARNING]
    infos = [i for i in all_issues if i.severity == ValidationSeverity.INFO]

    return {
        "valid": len(errors) == 0,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "info_count": len(infos),
        "issues": [
            {
                "code": i.code,
                "severity": i.severity.value,
                "message": i.message,
                "location": i.location,
                "suggestion": i.suggestion,
            }
            for i in all_issues
        ],
    }


# ============================================================================
# AppSpec Diff & Migration
# ============================================================================


@dataclass
class AppSpecDiff:
    """Difference between two AppSpec versions."""

    added_entities: list[str] = field(default_factory=list)
    removed_entities: list[str] = field(default_factory=list)
    modified_entities: list[dict[str, Any]] = field(default_factory=list)

    added_streams: list[str] = field(default_factory=list)
    removed_streams: list[str] = field(default_factory=list)
    modified_streams: list[dict[str, Any]] = field(default_factory=list)

    breaking_changes: list[str] = field(default_factory=list)
    migration_steps: list[str] = field(default_factory=list)


def diff_appspecs(old: ir.AppSpec, new: ir.AppSpec) -> AppSpecDiff:
    """Compare two AppSpecs and return the differences.

    Identifies:
    - Added/removed/modified entities
    - Added/removed/modified streams
    - Breaking changes
    - Required migration steps
    """
    diff = AppSpecDiff()

    # Entity comparison
    old_entities = {e.name: e for e in old.domain.entities}
    new_entities = {e.name: e for e in new.domain.entities}

    old_names = set(old_entities.keys())
    new_names = set(new_entities.keys())

    diff.added_entities = list(new_names - old_names)
    diff.removed_entities = list(old_names - new_names)

    # Check modified entities
    for name in old_names & new_names:
        old_e = old_entities[name]
        new_e = new_entities[name]

        old_fields = {f.name: f for f in old_e.fields}
        new_fields = {f.name: f for f in new_e.fields}

        added_fields = set(new_fields.keys()) - set(old_fields.keys())
        removed_fields = set(old_fields.keys()) - set(new_fields.keys())

        if added_fields or removed_fields:
            diff.modified_entities.append(
                {
                    "entity": name,
                    "added_fields": list(added_fields),
                    "removed_fields": list(removed_fields),
                }
            )

            # Removing required fields is breaking
            for field_name in removed_fields:
                if old_fields[field_name].is_required:
                    diff.breaking_changes.append(f"Removed required field '{name}.{field_name}'")
                    diff.migration_steps.append(
                        f"Migrate data from '{name}.{field_name}' before removal"
                    )

    # Stream comparison
    old_streams = {s.name: s for s in old.streams} if old.streams else {}
    new_streams = {s.name: s for s in new.streams} if new.streams else {}

    old_stream_names = set(old_streams.keys())
    new_stream_names = set(new_streams.keys())

    diff.added_streams = list(new_stream_names - old_stream_names)
    diff.removed_streams = list(old_stream_names - new_stream_names)

    # Removing streams with active consumers is breaking
    for stream_name in diff.removed_streams:
        diff.breaking_changes.append(f"Removed stream '{stream_name}'")
        diff.migration_steps.append(f"Ensure no consumers depend on '{stream_name}' before removal")

    # Check for entity removal (always breaking)
    for entity_name in diff.removed_entities:
        diff.breaking_changes.append(f"Removed entity '{entity_name}'")
        diff.migration_steps.append(f"Migrate or archive data from '{entity_name}' before removal")

    return diff


# ============================================================================
# Inference Rules
# ============================================================================


def infer_multi_tenancy(appspec: ir.AppSpec) -> dict[str, Any]:
    """Infer multi-tenancy requirements from AppSpec.

    Looks for:
    - tenant_id fields
    - Tenant entity
    - Organization/Company entities
    - User-to-tenant relationships

    Returns actionable suggestions for implementing multi-tenancy.
    """
    signals: list[dict[str, Any]] = []
    recommendation = "single_tenant"
    suggested_actions: list[dict[str, Any]] = []

    # Check for explicit tenancy config
    if appspec.tenancy:
        return {
            "mode": appspec.tenancy.isolation.mode.value,
            "signals": [{"type": "explicit_config", "confidence": 1.0}],
            "recommendation": appspec.tenancy.isolation.mode.value,
            "status": "configured",
            "suggested_actions": [],
        }

    # Check for tenant_id fields
    entities_with_tenant: list[str] = []
    for entity in appspec.domain.entities:
        for f in entity.fields:
            if f.name == "tenant_id":
                entities_with_tenant.append(entity.name)
                signals.append(
                    {
                        "type": "tenant_id_field",
                        "entity": entity.name,
                        "confidence": 0.9,
                    }
                )

    # Check for Tenant/Organization entity
    tenant_entity: str | None = None
    for entity in appspec.domain.entities:
        if entity.name.lower() in ("tenant", "organization", "company", "account"):
            tenant_entity = entity.name
            signals.append(
                {
                    "type": "tenant_entity",
                    "entity": entity.name,
                    "confidence": 0.85,
                }
            )

    # Determine recommendation
    if len(entities_with_tenant) > len(appspec.domain.entities) * 0.5:
        recommendation = "shared_schema"
    elif len(signals) > 0:
        recommendation = "consider_multi_tenant"

    # Build actionable suggestions
    if recommendation in ("consider_multi_tenant", "shared_schema"):
        # Find entities missing tenant_id that likely need it
        entities_needing_tenant = []
        # System-managed entities that typically don't need tenant scoping
        system_entities = {"auditlog", "systemevent", "notification", "log", "event"}

        for entity in appspec.domain.entities:
            # Skip if already has tenant_id
            if entity.name in entities_with_tenant:
                continue
            # Skip if this IS the tenant entity
            if tenant_entity and entity.name.lower() == tenant_entity.lower():
                continue
            # Skip system-managed entities
            if entity.name.lower() in system_entities:
                continue
            # Skip entities with 'log', 'event', 'audit' in name
            name_lower = entity.name.lower()
            if any(hint in name_lower for hint in ["log", "event", "audit", "history"]):
                continue

            entities_needing_tenant.append(entity.name)

        # Suggest adding tenancy config
        tenant_ref = tenant_entity or "Tenant"
        suggested_actions.append(
            {
                "action": "add_tenancy_config",
                "description": "Add tenancy configuration to your DSL",
                "dsl_snippet": """tenancy:
  mode: shared_schema
  partition_key: tenant_id
  provisioning:
    auto_create: true""",
                "priority": "high",
            }
        )

        # Suggest adding tenant_id to entities
        if entities_needing_tenant:
            suggested_actions.append(
                {
                    "action": "add_tenant_id_fields",
                    "description": f"Add tenant_id field to {len(entities_needing_tenant)} entities",
                    "entities": entities_needing_tenant,
                    "dsl_snippet": f"tenant_id: ref {tenant_ref} required",
                    "priority": "high",
                }
            )

        # Suggest creating tenant entity if none exists
        if not tenant_entity:
            suggested_actions.append(
                {
                    "action": "create_tenant_entity",
                    "description": "Create a Tenant entity to represent tenant accounts",
                    "dsl_snippet": """entity Tenant "Tenant":
  id: uuid pk
  name: str(200) required
  slug: str(100) unique required
  is_active: bool=true
  created_at: datetime auto_add""",
                    "priority": "medium",
                }
            )

    return {
        "mode": recommendation,
        "signals": signals,
        "entities_with_tenant_id": entities_with_tenant,
        "recommendation": recommendation,
        "tenant_entity": tenant_entity,
        "suggested_actions": suggested_actions,
    }


def infer_compliance_requirements(appspec: ir.AppSpec) -> dict[str, Any]:
    """Infer compliance requirements from AppSpec.

    Looks for:
    - PII fields (name, email, phone, address)
    - Financial fields (amount, price, payment)
    - Health data indicators
    - Geographic data
    """
    pii_fields: list[dict[str, Any]] = []
    financial_fields: list[dict[str, Any]] = []
    health_fields: list[dict[str, Any]] = []

    pii_patterns = {
        "name": 0.7,
        "email": 0.95,
        "phone": 0.9,
        "address": 0.85,
        "ssn": 0.99,
        "social_security": 0.99,
        "dob": 0.9,
        "birth": 0.85,
        "passport": 0.95,
        "driver_license": 0.95,
    }

    financial_patterns = {
        "amount": 0.8,
        "total": 0.75,
        "price": 0.8,
        "cost": 0.75,
        "balance": 0.85,
        "payment": 0.9,
        "credit": 0.8,
        "debit": 0.8,
        "account_number": 0.95,
        "card": 0.9,
        "iban": 0.95,
    }

    health_patterns = {
        "diagnosis": 0.95,
        "prescription": 0.9,
        "medical": 0.9,
        "health": 0.8,
        "patient": 0.85,
        "symptom": 0.9,
    }

    for entity in appspec.domain.entities:
        for f in entity.fields:
            field_lower = f.name.lower()

            for pattern, confidence in pii_patterns.items():
                if pattern in field_lower:
                    pii_fields.append(
                        {
                            "entity": entity.name,
                            "field": f.name,
                            "pattern": pattern,
                            "confidence": confidence,
                        }
                    )

            for pattern, confidence in financial_patterns.items():
                if pattern in field_lower:
                    financial_fields.append(
                        {
                            "entity": entity.name,
                            "field": f.name,
                            "pattern": pattern,
                            "confidence": confidence,
                        }
                    )

            for pattern, confidence in health_patterns.items():
                if pattern in field_lower:
                    health_fields.append(
                        {
                            "entity": entity.name,
                            "field": f.name,
                            "pattern": pattern,
                            "confidence": confidence,
                        }
                    )

    # Determine compliance frameworks
    frameworks: list[str] = []
    if pii_fields:
        frameworks.append("GDPR")
        if any(f["pattern"] in ("ssn", "social_security") for f in pii_fields):
            frameworks.append("CCPA")
    if financial_fields:
        frameworks.append("PCI-DSS")
    if health_fields:
        frameworks.append("HIPAA")

    return {
        "pii_fields": pii_fields,
        "financial_fields": financial_fields,
        "health_fields": health_fields,
        "recommended_frameworks": frameworks,
        "classification_suggestions": [
            {
                "entity": f["entity"],
                "field": f["field"],
                "classification": "pii_direct",
            }
            for f in pii_fields
            if f["confidence"] > 0.8
        ]
        + [
            {
                "entity": f["entity"],
                "field": f["field"],
                "classification": "financial_txn",
            }
            for f in financial_fields
            if f["confidence"] > 0.8
        ],
    }


def infer_analytics_intent(appspec: ir.AppSpec) -> dict[str, Any]:
    """Infer analytics requirements from AppSpec.

    Looks for:
    - Aggregate fields (count, sum, avg)
    - Time-series data
    - Reporting surfaces
    - Dashboard workspaces
    """
    signals: list[dict[str, Any]] = []
    recommended_products: list[dict[str, Any]] = []

    # Check for aggregate field patterns
    aggregate_patterns = ["count", "sum", "avg", "total", "metric", "stat"]
    for entity in appspec.domain.entities:
        for f in entity.fields:
            for pattern in aggregate_patterns:
                if pattern in f.name.lower():
                    signals.append(
                        {
                            "type": "aggregate_field",
                            "entity": entity.name,
                            "field": f.name,
                            "pattern": pattern,
                        }
                    )

    # Check for time-series data
    for entity in appspec.domain.entities:
        has_timestamp = any(
            f.name in ("created_at", "timestamp", "recorded_at") for f in entity.fields
        )
        has_value = any(f.name in ("value", "amount", "count", "metric") for f in entity.fields)
        if has_timestamp and has_value:
            signals.append(
                {
                    "type": "time_series_entity",
                    "entity": entity.name,
                }
            )

    # Check for dashboard surfaces
    for surface in appspec.surfaces:
        if surface.mode == "dashboard" or "dashboard" in surface.name.lower():
            signals.append(
                {
                    "type": "dashboard_surface",
                    "surface": surface.name,
                }
            )

    # Check for reporting workspaces
    for ws in appspec.workspaces:
        if "report" in ws.name.lower() or "analytics" in ws.name.lower():
            signals.append(
                {
                    "type": "analytics_workspace",
                    "workspace": ws.name,
                }
            )

    # Generate recommendations
    if signals:
        entities_for_analytics = list({s.get("entity") for s in signals if s.get("entity")})
        if entities_for_analytics:
            recommended_products.append(
                {
                    "name": "app_analytics",
                    "source_entities": entities_for_analytics,
                    "transforms": ["aggregate"],
                    "refresh": "hourly",
                }
            )

    return {
        "signals": signals,
        "has_analytics_intent": len(signals) > 0,
        "recommended_data_products": recommended_products,
    }


# ============================================================================
# Feedback Handling Model
# ============================================================================


class FeedbackSeverity(str, Enum):
    """Severity of feedback."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FeedbackScope(str, Enum):
    """Scope of feedback impact."""

    GLOBAL = "global"
    MODULE = "module"
    ENTITY = "entity"
    FIELD = "field"
    SURFACE = "surface"


@dataclass
class FeedbackEntry:
    """A feedback entry for tracking issues and improvements."""

    id: str
    pain_point: str
    expected: str
    observed: str
    severity: FeedbackSeverity
    scope: FeedbackScope
    hypothesis: str | None = None
    location: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    resolved: bool = False
    resolution: str | None = None


class FeedbackStore:
    """In-memory store for feedback entries."""

    def __init__(self) -> None:
        self._entries: dict[str, FeedbackEntry] = {}

    def add(self, entry: FeedbackEntry) -> None:
        """Add a feedback entry."""
        self._entries[entry.id] = entry

    def get(self, entry_id: str) -> FeedbackEntry | None:
        """Get a feedback entry by ID."""
        return self._entries.get(entry_id)

    def list_all(
        self,
        severity: FeedbackSeverity | None = None,
        scope: FeedbackScope | None = None,
        resolved: bool | None = None,
    ) -> list[FeedbackEntry]:
        """List feedback entries with optional filters."""
        entries = list(self._entries.values())

        if severity is not None:
            entries = [e for e in entries if e.severity == severity]
        if scope is not None:
            entries = [e for e in entries if e.scope == scope]
        if resolved is not None:
            entries = [e for e in entries if e.resolved == resolved]

        return sorted(entries, key=lambda e: e.created_at, reverse=True)

    def resolve(self, entry_id: str, resolution: str) -> bool:
        """Mark a feedback entry as resolved."""
        entry = self._entries.get(entry_id)
        if entry:
            entry.resolved = True
            entry.resolution = resolution
            return True
        return False

    def to_dict(self) -> list[dict[str, Any]]:
        """Export all entries as dicts."""
        return [
            {
                "id": e.id,
                "pain_point": e.pain_point,
                "expected": e.expected,
                "observed": e.observed,
                "severity": e.severity.value,
                "scope": e.scope.value,
                "hypothesis": e.hypothesis,
                "location": e.location,
                "created_at": e.created_at.isoformat(),
                "resolved": e.resolved,
                "resolution": e.resolution,
            }
            for e in self._entries.values()
        ]


# Global feedback store
_feedback_store = FeedbackStore()


def get_feedback_store() -> FeedbackStore:
    """Get the global feedback store."""
    return _feedback_store


# ============================================================================
# Tool Handler Functions (for MCP)
# ============================================================================


def handle_extract_semantics(args: dict[str, Any], project_path: Path) -> str:
    """Handle extract_semantics tool call."""
    try:
        manifest = load_manifest(project_path / "dazzle.toml")
        dsl_files = discover_dsl_files(project_path, manifest)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, manifest.project_root)

        extraction = extract_semantics(appspec)

        return json.dumps(
            {
                "entities": extraction.entities,
                "commands": extraction.commands,
                "events": extraction.events,
                "projections": extraction.projections,
                "tenancy_signals": extraction.tenancy_signals,
                "compliance_signals": extraction.compliance_signals,
                "summary": {
                    "entity_count": len(extraction.entities),
                    "command_count": len(extraction.commands),
                    "event_count": len(extraction.events),
                    "projection_count": len(extraction.projections),
                },
            },
            indent=2,
        )

    except Exception as e:
        return json.dumps({"error": str(e)})


def handle_validate_events(args: dict[str, Any], project_path: Path) -> str:
    """Handle validate_events tool call."""
    try:
        manifest = load_manifest(project_path / "dazzle.toml")
        dsl_files = discover_dsl_files(project_path, manifest)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, manifest.project_root)

        result = validate_event_first(appspec)

        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e)})


def handle_diff_appspec(args: dict[str, Any], project_path: Path) -> str:
    """Handle diff_appspec tool call."""
    # This would need two AppSpec versions to compare
    # For now, return a placeholder
    return json.dumps(
        {"error": "diff_appspec requires two AppSpec versions. Use with version control."}
    )


def handle_infer_tenancy(args: dict[str, Any], project_path: Path) -> str:
    """Handle infer_tenancy tool call."""
    try:
        manifest = load_manifest(project_path / "dazzle.toml")
        dsl_files = discover_dsl_files(project_path, manifest)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, manifest.project_root)

        result = infer_multi_tenancy(appspec)

        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e)})


def handle_infer_compliance(args: dict[str, Any], project_path: Path) -> str:
    """Handle infer_compliance tool call."""
    try:
        manifest = load_manifest(project_path / "dazzle.toml")
        dsl_files = discover_dsl_files(project_path, manifest)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, manifest.project_root)

        result = infer_compliance_requirements(appspec)

        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e)})


def handle_infer_analytics(args: dict[str, Any], project_path: Path) -> str:
    """Handle infer_analytics tool call."""
    try:
        manifest = load_manifest(project_path / "dazzle.toml")
        dsl_files = discover_dsl_files(project_path, manifest)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, manifest.project_root)

        result = infer_analytics_intent(appspec)

        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e)})


def handle_add_feedback(args: dict[str, Any], project_path: Path) -> str:
    """Handle add_feedback tool call."""
    import uuid

    try:
        entry = FeedbackEntry(
            id=str(uuid.uuid4())[:8],
            pain_point=args.get("pain_point", ""),
            expected=args.get("expected", ""),
            observed=args.get("observed", ""),
            severity=FeedbackSeverity(args.get("severity", "medium")),
            scope=FeedbackScope(args.get("scope", "entity")),
            hypothesis=args.get("hypothesis"),
            location=args.get("location"),
        )

        get_feedback_store().add(entry)

        # Attempt to create a GitHub issue
        from dazzle.mcp.server.github_issues import create_github_issue

        issue_body = (
            f"**Pain point:** {entry.pain_point}\n\n"
            f"**Expected:** {entry.expected}\n\n"
            f"**Observed:** {entry.observed}\n\n"
            f"**Severity:** {entry.severity.value}\n\n"
            f"**Scope:** {entry.scope.value}\n"
        )
        if entry.hypothesis:
            issue_body += f"\n**Hypothesis:** {entry.hypothesis}\n"
        if entry.location:
            issue_body += f"\n**Location:** {entry.location}\n"

        github_issue = create_github_issue(
            title=f"[Feedback] {entry.pain_point[:80]}",
            body=issue_body,
            labels=["feedback", entry.severity.value],
        )

        return json.dumps(
            {
                "id": entry.id,
                "message": "Feedback recorded",
                "github_issue": github_issue,
            }
        )

    except Exception as e:
        return json.dumps({"error": str(e)})


def handle_list_feedback(args: dict[str, Any], project_path: Path) -> str:
    """Handle list_feedback tool call."""
    try:
        severity = None
        if args.get("severity"):
            severity = FeedbackSeverity(args["severity"])

        scope = None
        if args.get("scope"):
            scope = FeedbackScope(args["scope"])

        resolved = args.get("resolved")

        entries = get_feedback_store().list_all(
            severity=severity,
            scope=scope,
            resolved=resolved,
        )

        return json.dumps(
            {
                "count": len(entries),
                "entries": [
                    {
                        "id": e.id,
                        "pain_point": e.pain_point,
                        "expected": e.expected,
                        "observed": e.observed,
                        "severity": e.severity.value,
                        "scope": e.scope.value,
                        "hypothesis": e.hypothesis,
                        "resolved": e.resolved,
                    }
                    for e in entries
                ],
            },
            indent=2,
        )

    except Exception as e:
        return json.dumps({"error": str(e)})


# ============================================================================
# Guard Extraction (Issue #81a)
# ============================================================================

# Patterns in story constraints that imply state machine guards
_GUARD_PATTERNS: list[tuple[str, str, list[str]]] = [
    # (pattern_key, guard_type, keywords)
    ("differ", "requires_different_field", ["differ", "different", "not the same"]),
    ("only_can", "requires_role", ["only", "assigned", "authorized"]),
    ("must_have", "requires_field", ["must have", "must be set"]),
    ("must_be", "requires_field_value", ["must be"]),
    ("requires_active", "requires_related", ["requires", "active", "valid"]),
    ("four_eye", "requires_different_field", ["four-eye", "4-eye", "dual"]),
    ("approval", "requires_role", ["approval", "approve"]),
    ("cannot_same", "requires_different_field", ["cannot", "same"]),
]


def extract_guards(appspec: ir.AppSpec) -> list[dict[str, Any]]:
    """Extract guard proposals from stories and entity state machines.

    Scans story constraints for guard-implying language and cross-references
    entity state machines to propose guards for transitions.
    """
    from dazzle.core.stories_persistence import load_stories

    stories = list(appspec.stories) if appspec.stories else []
    if not stories and appspec.metadata.get("project_root"):
        stories = load_stories(Path(appspec.metadata["project_root"]))

    if not stories:
        return []

    # Build entity state machine index
    entity_sm: dict[str, Any] = {}
    for entity in appspec.domain.entities:
        if entity.state_machine:
            entity_sm[entity.name] = entity

    proposals: list[dict[str, Any]] = []

    for story in stories:
        if not story.constraints:
            continue

        story_entities = story.scope if story.scope else []

        for constraint in story.constraints:
            constraint_lower = constraint.lower()

            for _key, guard_type, keywords in _GUARD_PATTERNS:
                if not any(kw in constraint_lower for kw in keywords):
                    continue

                for entity_name in story_entities:
                    matched_entity = entity_sm.get(entity_name)
                    if not matched_entity:
                        continue

                    sm = matched_entity.state_machine
                    target_transitions = _match_transitions_to_constraint(constraint_lower, sm)

                    if target_transitions:
                        for from_s, to_s in target_transitions:
                            proposals.append(
                                {
                                    "entity": entity_name,
                                    "transition": f"{from_s} → {to_s}",
                                    "guard_type": guard_type,
                                    "guard_expression": _build_guard_expression(
                                        guard_type, constraint, matched_entity
                                    ),
                                    "source_story": story.story_id,
                                    "source_constraint": constraint,
                                }
                            )
                    else:
                        proposals.append(
                            {
                                "entity": entity_name,
                                "transition": "*",
                                "guard_type": guard_type,
                                "guard_expression": _build_guard_expression(
                                    guard_type, constraint, matched_entity
                                ),
                                "source_story": story.story_id,
                                "source_constraint": constraint,
                            }
                        )
                    break  # One guard per constraint per entity

    # Deduplicate
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for p in proposals:
        key = f"{p['entity']}:{p['transition']}:{p['guard_expression']}"
        if key not in seen:
            seen.add(key)
            unique.append(p)

    return unique


def _match_transitions_to_constraint(constraint_lower: str, sm: Any) -> list[tuple[str, str]]:
    """Try to match a constraint to specific state machine transitions."""
    matches: list[tuple[str, str]] = []
    for transition in sm.transitions:
        from_s = transition.from_state.lower()
        to_s = transition.to_state.lower()
        if from_s in constraint_lower or to_s in constraint_lower:
            matches.append((transition.from_state, transition.to_state))
    return matches


def _build_guard_expression(guard_type: str, constraint: str, entity: Any) -> str:
    """Build a guard expression string from constraint text."""
    import re

    if guard_type == "requires_different_field":
        fields = [f.name for f in entity.fields]
        mentioned = [f for f in fields if f.lower() in constraint.lower()]
        if len(mentioned) >= 2:
            return f"requires_different_field({mentioned[0]}, {mentioned[1]})"
        return f"requires_different_actors: {constraint}"

    elif guard_type == "requires_role":
        role_match = re.search(r"(?:only|assigned)\s+(\w+)", constraint.lower())
        if role_match:
            return f"requires_role({role_match.group(1)})"
        return f"requires_role: {constraint}"

    elif guard_type == "requires_field":
        field_match = re.search(r"must have\s+(\w+)", constraint.lower())
        if field_match:
            return f"requires_field({field_match.group(1)})"
        return f"requires_field: {constraint}"

    elif guard_type == "requires_field_value":
        field_match = re.search(r"(\w+)\s+must be\s+(.+)", constraint.lower())
        if field_match:
            return f"requires({field_match.group(1)}={field_match.group(2).strip()})"
        return f"requires_value: {constraint}"

    elif guard_type == "requires_related":
        return f"requires_related: {constraint}"

    return f"guard: {constraint}"


def handle_extract_guards(args: dict[str, Any], project_path: Path) -> str:
    """Handle extract_guards semantics operation."""
    try:
        manifest = load_manifest(project_path / "dazzle.toml")
        dsl_files = discover_dsl_files(project_path, manifest)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, manifest.project_root)

        proposals = extract_guards(appspec)

        return json.dumps(
            {
                "guard_proposals": proposals,
                "count": len(proposals),
                "hint": (
                    "Review proposals and apply as guards on entity state machine "
                    "transitions in your DSL files."
                ),
            },
            indent=2,
        )

    except Exception as e:
        return json.dumps({"error": str(e)})
