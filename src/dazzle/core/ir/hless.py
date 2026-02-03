"""
HLESS IR Types - High-Level Event Semantics Specification.

This module defines the intermediate representation for HLESS-compliant
append-only record streams. HLESS prevents semantic drift by:

1. Classifying every record into exactly one RecordKind
2. Enforcing time semantics (t_event, t_log, t_process)
3. Requiring explicit idempotency strategies
4. Tracking derivation lineage for computed values

CRITICAL: The unqualified word "event" is forbidden in HLESS mode.
Use RecordKind (INTENT, FACT, OBSERVATION, DERIVATION) instead.

See: dev_docs/architecture/event_first/high_level_event_semantics.md
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from .fields import FieldSpec


class RecordKind(StrEnum):
    """
    The four permitted record kinds.

    No other classification exists. Every record MUST be exactly one of these.

    INTENT: A fact that an actor *requested* or *attempted* an action.
            Does NOT imply success. May lead to acceptance or rejection.
            Example: OrderPlacementRequested, UserRequestedPasswordReset

    FACT: A fact about the domain that is now *permanently true*.
          Must remain true forever. Cannot be retracted.
          Example: OrderPlaced, InvoiceIssued, OrderPlacementRejected

    OBSERVATION: A fact that something was observed, measured, or reported.
                 May be duplicated, arrive late, or be out of order.
                 Truth is "this was observed", not "this is correct".
                 Example: TemperatureMeasured, ApiRequestReceived

    DERIVATION: A fact that a value was *computed* from other records.
                Always rebuildable. Carries lineage to source records.
                Must not introduce new domain truth.
                Example: AccountBalanceCalculated, DailyRevenueAggregated
    """

    INTENT = "intent"
    FACT = "fact"
    OBSERVATION = "observation"
    DERIVATION = "derivation"


class HLESSMode(StrEnum):
    """HLESS enforcement mode."""

    STRICT = "strict"  # Default - parser rejects non-compliant code
    WARN = "warn"  # Parser warns but allows (for migration)
    OFF = "off"  # Disabled (strongly discouraged, triggers LLM warnings)


class TimeSemantics(BaseModel):
    """
    Mandatory time axis distinction.

    HLESS requires distinguishing between:
    - t_event: When the thing occurred in the domain
    - t_log: When the record was appended to the log (auto-populated)
    - t_process: When it was processed (DERIVATION only)

    The word "time" must never be used without qualification.
    """

    t_event_field: str = Field(
        ...,
        description="Field containing the domain occurrence time",
    )
    t_log_field: str = Field(
        default="_t_log",
        description="Field for log append time (auto-populated)",
    )
    t_process_field: str | None = Field(
        default=None,
        description="Field for processing time (DERIVATION only)",
    )


class IdempotencyType(StrEnum):
    """Strategy types for duplicate detection."""

    DETERMINISTIC_ID = "deterministic_id"  # ID derived from content
    CONTENT_HASH = "content_hash"  # Hash of payload
    EXTERNAL_DEDUP = "external_dedup"  # External system handles dedup
    DEDUPE_WINDOW = "dedupe_window"  # Time-windowed deduplication


class IdempotencyStrategy(BaseModel):
    """
    How duplicate detection works for a stream.

    Every stream MUST have an explicit idempotency strategy.
    The normalizer fills defaults based on RecordKind if omitted.
    """

    strategy_type: IdempotencyType = Field(
        ...,
        description="Type of idempotency strategy",
    )
    field: str = Field(
        ...,
        description="Field carrying the idempotency key",
    )
    derivation: str | None = Field(
        default=None,
        description="How the key is derived (e.g., 'hash(stream, natural_key, t_event)')",
    )
    window: str | None = Field(
        default=None,
        description="Deduplication window for DEDUPE_WINDOW type (e.g., '5 minutes')",
    )


class SideEffectPolicy(BaseModel):
    """
    What external effects are permitted for records in this stream.

    By default, no external effects are allowed.
    """

    external_effects_allowed: bool = Field(
        default=False,
        description="Whether external side effects are permitted",
    )
    allowed_effects: list[str] = Field(
        default_factory=list,
        description="If allowed, what specific effects are permitted",
    )


class OutcomeCondition(StrEnum):
    """Conditions for INTENT stream outcomes."""

    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    PARTIAL = "partial"


class ExpectedOutcome(BaseModel):
    """
    For INTENT streams: what FACT records may result.

    INTENT streams MUST declare their expected outcomes to establish
    the contract between request and result.
    """

    condition: OutcomeCondition = Field(
        ...,
        description="Outcome condition (success, failure, timeout, partial)",
    )
    emits: list[str] = Field(
        ...,
        description="Schema names emitted to FACT streams",
    )
    target_stream: str | None = Field(
        default=None,
        description="Target stream for emissions (if different from default)",
    )


class DerivationType(StrEnum):
    """Types of derivation operations."""

    AGGREGATE = "aggregate"  # SUM, COUNT, AVG over records
    JOIN = "join"  # Combining records from multiple streams
    FILTER = "filter"  # Subset of source records
    TRANSFORM = "transform"  # 1:1 transformation
    SNAPSHOT = "snapshot"  # Point-in-time materialization
    WINDOW = "window"  # Time-windowed computation


class RebuildStrategy(StrEnum):
    """How a DERIVATION stream can be rebuilt."""

    FULL_REPLAY = "full_replay"  # Delete and rebuild from all sources
    INCREMENTAL = "incremental"  # Can be updated incrementally
    WINDOWED = "windowed"  # Only recent window matters


class WindowType(StrEnum):
    """Types of time windows for derivations."""

    TUMBLING = "tumbling"  # Non-overlapping fixed windows
    SLIDING = "sliding"  # Overlapping windows
    SESSION = "session"  # Activity-based windows


class WindowSpec(BaseModel):
    """Specification for windowed derivations."""

    type: WindowType = Field(..., description="Window type")
    size: str = Field(..., description="Window size (e.g., '1 hour', '1 day')")
    grace_period: str | None = Field(
        default=None,
        description="Late arrival tolerance",
    )


class DerivationLineage(BaseModel):
    """
    For DERIVATION streams: explicit source tracking.

    DERIVATION records MUST declare their lineage to ensure:
    1. Reproducibility - can always be rebuilt from sources
    2. Traceability - know what data contributed to a value
    3. Validation - verify sources exist and are accessible
    """

    source_streams: list[str] = Field(
        ...,
        description="Stream names this derives from",
    )
    derivation_type: DerivationType = Field(
        ...,
        description="Type of derivation operation",
    )
    rebuild_strategy: RebuildStrategy = Field(
        default=RebuildStrategy.FULL_REPLAY,
        description="How to rebuild this derivation",
    )
    window_spec: WindowSpec | None = Field(
        default=None,
        description="Window specification for windowed derivations",
    )
    derivation_function: str | None = Field(
        default=None,
        description="Reference to the derivation function (for reproducibility)",
    )


class SchemaCompatibility(StrEnum):
    """Compatibility level for schema evolution."""

    ADDITIVE = "additive"  # Backwards compatible (add fields, widen enums)
    BREAKING = "breaking"  # Requires new stream


class StreamSchema(BaseModel):
    """
    A versioned schema within a stream.

    Schemas define the structure of records in a stream.
    Multiple schemas can exist in a single stream (e.g., OrderPlaced, OrderRejected
    both in the order_facts stream).
    """

    name: str = Field(
        ...,
        description="Schema name (PascalCase, e.g., 'OrderPlaced')",
    )
    version: str = Field(
        default="v1",
        description="Schema version (e.g., 'v1', 'v2')",
    )
    fields: list[FieldSpec] = Field(
        default_factory=list,
        description="Schema fields",
    )
    extends: str | None = Field(
        default=None,
        description="Parent schema this extends (for additive evolution)",
    )
    compatibility: SchemaCompatibility = Field(
        default=SchemaCompatibility.ADDITIVE,
        description="Compatibility with previous version",
    )
    description: str | None = Field(
        default=None,
        description="Human-readable description",
    )

    @property
    def qualified_name(self) -> str:
        """Return the fully qualified schema name (e.g., 'OrderPlaced@v1')."""
        return f"{self.name}@{self.version}"


class StreamSpec(BaseModel):
    """
    HLESS-compliant stream specification.

    This is the ONLY way to define append-only record sequences in Dazzle.
    The word "event" is forbidden - use RecordKind instead.

    A StreamSpec is the minimum IDL required before any implementation.
    It defines:
    - What kind of records the stream contains
    - How records are partitioned and ordered
    - What schemas are valid
    - Time semantics
    - Idempotency strategy
    - Invariants that must hold
    """

    name: str = Field(
        ...,
        description="Stream name (e.g., 'orders.fact.v1')",
    )
    record_kind: RecordKind = Field(
        ...,
        description="The kind of records in this stream",
    )
    schemas: list[StreamSchema] = Field(
        default_factory=list,
        description="Schemas for records in this stream",
    )
    partition_key: str = Field(
        ...,
        description="Field used for partitioning (ordering guarantee)",
    )
    ordering_scope: str = Field(
        ...,
        description="Scope of ordering guarantee (e.g., 'per_order', 'per_customer', 'global')",
    )

    # Time semantics (mandatory)
    time_semantics: TimeSemantics = Field(
        ...,
        description="Time axis configuration",
    )

    # Idempotency (mandatory)
    idempotency: IdempotencyStrategy = Field(
        ...,
        description="Duplicate detection strategy",
    )

    # Causality tracking
    causality_fields: list[str] = Field(
        default_factory=lambda: ["trace_id", "causation_id", "correlation_id"],
        description="Fields for causality tracking",
    )

    # Invariants - human-readable, machine-validated
    invariants: list[str] = Field(
        default_factory=list,
        description="Invariants that must hold for records in this stream",
    )

    # Side effects
    side_effect_policy: SideEffectPolicy = Field(
        default_factory=SideEffectPolicy,
        description="Policy for external side effects",
    )

    # INTENT-specific: expected outcomes
    expected_outcomes: list[ExpectedOutcome] | None = Field(
        default=None,
        description="For INTENT streams: what FACT records may result",
    )

    # DERIVATION-specific: lineage
    lineage: DerivationLineage | None = Field(
        default=None,
        description="For DERIVATION streams: source tracking",
    )

    # Cross-partition declaration
    cross_partition: bool = Field(
        default=False,
        description="If true, allows cross-partition references in outcomes",
    )

    # Documentation
    description: str | None = Field(
        default=None,
        description="Human-readable description",
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Additional notes about this stream",
    )

    def get_schema(self, name: str, version: str | None = None) -> StreamSchema | None:
        """Get a schema by name, optionally filtering by version."""
        for schema in self.schemas:
            if schema.name == name:
                if version is None or schema.version == version:
                    return schema
        return None

    def schema_names(self) -> list[str]:
        """Get all schema names in this stream."""
        return [s.name for s in self.schemas]


class HLESSPragma(BaseModel):
    """
    HLESS pragma configuration.

    Controls HLESS enforcement at the module level.
    Default is STRICT mode.
    """

    mode: HLESSMode = Field(
        default=HLESSMode.STRICT,
        description="HLESS enforcement mode",
    )
    reason: str | None = Field(
        default=None,
        description="Reason for non-strict mode (required if not STRICT)",
    )


class HLESSViolation(BaseModel):
    """
    A violation of HLESS semantic rules.

    Used by the validator to report issues with clear
    explanations and suggestions.
    """

    rule: str = Field(
        ...,
        description="Rule identifier (e.g., 'FACT_NO_IMPERATIVES')",
    )
    message: str = Field(
        ...,
        description="Human-readable error message",
    )
    suggestion: str | None = Field(
        default=None,
        description="Suggested fix or clarification",
    )
    stream_name: str | None = Field(
        default=None,
        description="Stream where violation occurred",
    )
    schema_name: str | None = Field(
        default=None,
        description="Schema where violation occurred",
    )
    severity: Literal["error", "warning"] = Field(
        default="error",
        description="Violation severity",
    )


# Default idempotency strategies by RecordKind
IDEMPOTENCY_DEFAULTS: dict[RecordKind, IdempotencyStrategy] = {
    RecordKind.INTENT: IdempotencyStrategy(
        strategy_type=IdempotencyType.DETERMINISTIC_ID,
        field="request_id",
        derivation="hash(stream, natural_key, t_event)",
    ),
    RecordKind.FACT: IdempotencyStrategy(
        strategy_type=IdempotencyType.DETERMINISTIC_ID,
        field="record_id",
        derivation="hash(stream, rk, natural_key, t_event, payload_canonical)",
    ),
    RecordKind.OBSERVATION: IdempotencyStrategy(
        strategy_type=IdempotencyType.DEDUPE_WINDOW,
        field="observation_fingerprint",
        derivation="hash(source_system, observed_key, payload_hash)",
        window="5 minutes",
    ),
    RecordKind.DERIVATION: IdempotencyStrategy(
        strategy_type=IdempotencyType.DETERMINISTIC_ID,
        field="derivation_id",
        derivation="hash(source_record_ids, derivation_function, window)",
    ),
}


def get_default_idempotency(kind: RecordKind) -> IdempotencyStrategy:
    """Get the default idempotency strategy for a RecordKind."""
    return IDEMPOTENCY_DEFAULTS[kind].model_copy()
