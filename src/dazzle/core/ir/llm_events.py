"""
LLM Event Streams - HLESS-compliant event definitions for LLM Jobs.

This module defines the event streams for LLM job lifecycle management,
following HLESS (High-Level Event Semantics Specification) principles.

HLESS RecordKind Mappings:
- LLMJobRequested    → INTENT     (User/system wants LLM work done)
- LLMJobClaimed      → FACT       (System has accepted the job)
- LLMRouteSelected   → FACT       (Model routing decision made)
- LLMJobCompleted    → FACT       (LLM returned a response)
- LLMJobFailed       → FACT       (Job failed: timeout, error, etc.)
- LLMArtifactStored  → FACT       (Prompt/completion stored)
- LLMTokensConsumed  → OBSERVATION (Usage metrics observed)
- LLMCostEstimate    → DERIVATION  (Cost computed from tokens + pricing)

Part of Issue #33: LLM Jobs as First-Class Events.
"""

from __future__ import annotations

from .fields import FieldModifier, FieldSpec, FieldType, FieldTypeKind
from .hless import (
    DerivationLineage,
    DerivationType,
    ExpectedOutcome,
    IdempotencyStrategy,
    IdempotencyType,
    OutcomeCondition,
    RebuildStrategy,
    RecordKind,
    StreamSchema,
    StreamSpec,
    TimeSemantics,
)

# =============================================================================
# Helper for creating fields
# =============================================================================


def _field(
    name: str,
    kind: FieldTypeKind,
    required: bool = True,
    max_length: int | None = None,
) -> FieldSpec:
    """Helper to create FieldSpec with common patterns."""
    modifiers = [FieldModifier.REQUIRED] if required else []
    return FieldSpec(
        name=name,
        type=FieldType(kind=kind, max_length=max_length),
        modifiers=modifiers,
    )


# =============================================================================
# Schema Definitions
# =============================================================================


def _llm_job_requested_schema() -> StreamSchema:
    """Schema for LLMJobRequested - an INTENT to have LLM process something."""
    return StreamSchema(
        name="LLMJobRequested",
        version="v1",
        description="Request to execute an LLM intent",
        fields=[
            _field("job_id", FieldTypeKind.UUID),
            _field("intent_name", FieldTypeKind.STR, max_length=100),
            _field("input_data", FieldTypeKind.JSON),
            _field("requested_by", FieldTypeKind.STR, required=False, max_length=100),
            _field("priority", FieldTypeKind.INT, required=False),
            _field("t_requested", FieldTypeKind.DATETIME),
        ],
    )


def _llm_job_claimed_schema() -> StreamSchema:
    """Schema for LLMJobClaimed - FACT that job processing has started."""
    return StreamSchema(
        name="LLMJobClaimed",
        version="v1",
        description="Job has been claimed for processing",
        fields=[
            _field("job_id", FieldTypeKind.UUID),
            _field("worker_id", FieldTypeKind.STR, max_length=100),
            _field("t_claimed", FieldTypeKind.DATETIME),
        ],
    )


def _llm_route_selected_schema() -> StreamSchema:
    """Schema for LLMRouteSelected - FACT that a model was chosen."""
    return StreamSchema(
        name="LLMRouteSelected",
        version="v1",
        description="Model routing decision has been made",
        fields=[
            _field("job_id", FieldTypeKind.UUID),
            _field("model_name", FieldTypeKind.STR, max_length=100),
            _field("provider", FieldTypeKind.STR, max_length=50),
            _field("model_id", FieldTypeKind.STR, max_length=200),
            _field("routing_reason", FieldTypeKind.STR, required=False, max_length=500),
            _field("t_routed", FieldTypeKind.DATETIME),
        ],
    )


def _llm_job_completed_schema() -> StreamSchema:
    """Schema for LLMJobCompleted - FACT that LLM returned a response."""
    return StreamSchema(
        name="LLMJobCompleted",
        version="v1",
        description="LLM job completed successfully",
        fields=[
            _field("job_id", FieldTypeKind.UUID),
            _field("completion_artifact_id", FieldTypeKind.STR, max_length=200),
            _field("output_data", FieldTypeKind.JSON, required=False),
            _field("input_tokens", FieldTypeKind.INT),
            _field("output_tokens", FieldTypeKind.INT),
            _field("latency_ms", FieldTypeKind.INT),
            _field("t_completed", FieldTypeKind.DATETIME),
        ],
    )


def _llm_job_failed_schema() -> StreamSchema:
    """Schema for LLMJobFailed - FACT that job failed."""
    return StreamSchema(
        name="LLMJobFailed",
        version="v1",
        description="LLM job failed",
        fields=[
            _field("job_id", FieldTypeKind.UUID),
            _field("error_code", FieldTypeKind.STR, max_length=50),
            _field("error_message", FieldTypeKind.STR, max_length=2000),
            _field("retry_count", FieldTypeKind.INT),
            _field("is_retriable", FieldTypeKind.BOOL),
            _field("t_failed", FieldTypeKind.DATETIME),
        ],
    )


def _llm_artifact_stored_schema() -> StreamSchema:
    """Schema for LLMArtifactStored - FACT that an artifact was persisted."""
    return StreamSchema(
        name="LLMArtifactStored",
        version="v1",
        description="LLM artifact (prompt/completion) was stored",
        fields=[
            _field("artifact_id", FieldTypeKind.STR, max_length=200),
            _field("job_id", FieldTypeKind.UUID),
            _field("artifact_kind", FieldTypeKind.STR, max_length=50),
            _field("content_hash", FieldTypeKind.STR, max_length=100),
            _field("storage_uri", FieldTypeKind.STR, max_length=500),
            _field("byte_size", FieldTypeKind.INT),
            _field("t_stored", FieldTypeKind.DATETIME),
        ],
    )


def _llm_tokens_consumed_schema() -> StreamSchema:
    """Schema for LLMTokensConsumed - OBSERVATION of usage metrics."""
    return StreamSchema(
        name="LLMTokensConsumed",
        version="v1",
        description="Observation of token consumption (may be delayed/duplicated)",
        fields=[
            _field("observation_id", FieldTypeKind.UUID),
            _field("job_id", FieldTypeKind.UUID),
            _field("model_name", FieldTypeKind.STR, max_length=100),
            _field("input_tokens", FieldTypeKind.INT),
            _field("output_tokens", FieldTypeKind.INT),
            _field("source_system", FieldTypeKind.STR, max_length=100),
            _field("t_observed", FieldTypeKind.DATETIME),
        ],
    )


def _llm_cost_estimate_schema() -> StreamSchema:
    """Schema for LLMCostEstimate - DERIVATION of cost from tokens + pricing."""
    return StreamSchema(
        name="LLMCostEstimate",
        version="v1",
        description="Derived cost estimate from token consumption and pricing",
        fields=[
            _field("estimate_id", FieldTypeKind.UUID),
            _field("job_id", FieldTypeKind.UUID),
            _field("model_name", FieldTypeKind.STR, max_length=100),
            _field("input_tokens", FieldTypeKind.INT),
            _field("output_tokens", FieldTypeKind.INT),
            _field("cost_usd", FieldTypeKind.DECIMAL),
            _field("pricing_version", FieldTypeKind.STR, max_length=50),
            _field("source_observation_ids", FieldTypeKind.JSON),
            _field("t_calculated", FieldTypeKind.DATETIME),
        ],
    )


# =============================================================================
# Stream Definitions
# =============================================================================


def create_llm_intent_stream() -> StreamSpec:
    """
    Create the LLM intent stream (INTENT records).

    Contains: LLMJobRequested
    """
    return StreamSpec(
        name="llm.intent.v1",
        record_kind=RecordKind.INTENT,
        description="LLM job requests - intents to have LLM process something",
        schemas=[_llm_job_requested_schema()],
        partition_key="job_id",
        ordering_scope="per_job",
        time_semantics=TimeSemantics(t_event_field="t_requested"),
        idempotency=IdempotencyStrategy(
            strategy_type=IdempotencyType.DETERMINISTIC_ID,
            field="job_id",
            derivation="hash(intent_name, input_data_canonical, t_requested)",
        ),
        expected_outcomes=[
            ExpectedOutcome(
                condition=OutcomeCondition.SUCCESS,
                emits=["LLMJobCompleted"],
                target_stream="llm.fact.v1",
            ),
            ExpectedOutcome(
                condition=OutcomeCondition.FAILURE,
                emits=["LLMJobFailed"],
                target_stream="llm.fact.v1",
            ),
            ExpectedOutcome(
                condition=OutcomeCondition.TIMEOUT,
                emits=["LLMJobFailed"],
                target_stream="llm.fact.v1",
            ),
        ],
        invariants=[
            "job_id must be globally unique",
            "intent_name must reference a valid llm_intent",
            "input_data must satisfy intent's input requirements",
        ],
    )


def create_llm_fact_stream() -> StreamSpec:
    """
    Create the LLM fact stream (FACT records).

    Contains: LLMJobClaimed, LLMRouteSelected, LLMJobCompleted,
              LLMJobFailed, LLMArtifactStored
    """
    return StreamSpec(
        name="llm.fact.v1",
        record_kind=RecordKind.FACT,
        description="LLM job facts - permanent truths about job lifecycle",
        schemas=[
            _llm_job_claimed_schema(),
            _llm_route_selected_schema(),
            _llm_job_completed_schema(),
            _llm_job_failed_schema(),
            _llm_artifact_stored_schema(),
        ],
        partition_key="job_id",
        ordering_scope="per_job",
        time_semantics=TimeSemantics(
            t_event_field="t_claimed",  # Default; actual field varies by schema
        ),
        idempotency=IdempotencyStrategy(
            strategy_type=IdempotencyType.DETERMINISTIC_ID,
            field="record_id",
            derivation="hash(stream, schema_name, job_id, t_event)",
        ),
        invariants=[
            "LLMJobClaimed requires prior LLMJobRequested with same job_id",
            "LLMRouteSelected requires prior LLMJobClaimed",
            "LLMJobCompleted and LLMJobFailed are mutually exclusive per job",
            "Once completed or failed, no further facts for that job",
        ],
    )


def create_llm_observation_stream() -> StreamSpec:
    """
    Create the LLM observation stream (OBSERVATION records).

    Contains: LLMTokensConsumed
    """
    return StreamSpec(
        name="llm.observation.v1",
        record_kind=RecordKind.OBSERVATION,
        description="LLM usage observations - may be delayed, duplicated, or out of order",
        schemas=[_llm_tokens_consumed_schema()],
        partition_key="job_id",
        ordering_scope="per_job",
        time_semantics=TimeSemantics(t_event_field="t_observed"),
        idempotency=IdempotencyStrategy(
            strategy_type=IdempotencyType.DEDUPE_WINDOW,
            field="observation_fingerprint",
            derivation="hash(source_system, job_id, input_tokens, output_tokens)",
            window="5 minutes",
        ),
        invariants=[
            "Observations assert 'this was observed', not 'this is correct'",
            "Multiple observations for same job may exist from different sources",
            "Observations may arrive after job completion",
        ],
    )


def create_llm_derivation_stream() -> StreamSpec:
    """
    Create the LLM derivation stream (DERIVATION records).

    Contains: LLMCostEstimate
    """
    return StreamSpec(
        name="llm.derivation.v1",
        record_kind=RecordKind.DERIVATION,
        description="LLM derived values - computed from other records",
        schemas=[_llm_cost_estimate_schema()],
        partition_key="job_id",
        ordering_scope="per_job",
        time_semantics=TimeSemantics(
            t_event_field="t_calculated",
            t_process_field="t_calculated",
        ),
        idempotency=IdempotencyStrategy(
            strategy_type=IdempotencyType.DETERMINISTIC_ID,
            field="derivation_id",
            derivation="hash(job_id, pricing_version, source_observation_ids)",
        ),
        lineage=DerivationLineage(
            source_streams=["llm.observation.v1", "llm.fact.v1"],
            derivation_type=DerivationType.TRANSFORM,
            rebuild_strategy=RebuildStrategy.FULL_REPLAY,
            derivation_function="calculate_cost(observations, pricing_table)",
        ),
        invariants=[
            "Cost estimates must reference source observations",
            "Pricing version must be valid at calculation time",
            "Cost can be recomputed from sources",
        ],
    )


def get_all_llm_streams() -> list[StreamSpec]:
    """Get all LLM event stream specifications."""
    return [
        create_llm_intent_stream(),
        create_llm_fact_stream(),
        create_llm_observation_stream(),
        create_llm_derivation_stream(),
    ]


# =============================================================================
# Stream Names Constants
# =============================================================================


LLM_INTENT_STREAM = "llm.intent.v1"
LLM_FACT_STREAM = "llm.fact.v1"
LLM_OBSERVATION_STREAM = "llm.observation.v1"
LLM_DERIVATION_STREAM = "llm.derivation.v1"


# Schema names for reference
LLM_SCHEMAS = {
    "LLMJobRequested": LLM_INTENT_STREAM,
    "LLMJobClaimed": LLM_FACT_STREAM,
    "LLMRouteSelected": LLM_FACT_STREAM,
    "LLMJobCompleted": LLM_FACT_STREAM,
    "LLMJobFailed": LLM_FACT_STREAM,
    "LLMArtifactStored": LLM_FACT_STREAM,
    "LLMTokensConsumed": LLM_OBSERVATION_STREAM,
    "LLMCostEstimate": LLM_DERIVATION_STREAM,
}
