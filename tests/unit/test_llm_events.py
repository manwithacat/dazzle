"""
Unit tests for LLM event stream definitions.

Tests the HLESS-compliant event streams for LLM Jobs
as part of Issue #33: LLM Jobs as First-Class Events.
"""

from dazzle.core.ir import (
    LLM_DERIVATION_STREAM,
    LLM_FACT_STREAM,
    LLM_INTENT_STREAM,
    LLM_OBSERVATION_STREAM,
    LLM_SCHEMAS,
    create_llm_derivation_stream,
    create_llm_fact_stream,
    create_llm_intent_stream,
    create_llm_observation_stream,
    get_all_llm_streams,
)
from dazzle.core.ir.hless import (
    DerivationType,
    IdempotencyType,
    OutcomeCondition,
    RebuildStrategy,
    RecordKind,
)


class TestLLMStreamConstants:
    """Tests for stream name constants."""

    def test_stream_names(self):
        """Test stream names are correct."""
        assert LLM_INTENT_STREAM == "llm.intent.v1"
        assert LLM_FACT_STREAM == "llm.fact.v1"
        assert LLM_OBSERVATION_STREAM == "llm.observation.v1"
        assert LLM_DERIVATION_STREAM == "llm.derivation.v1"

    def test_schema_mappings(self):
        """Test schema to stream mappings."""
        assert LLM_SCHEMAS["LLMJobRequested"] == LLM_INTENT_STREAM
        assert LLM_SCHEMAS["LLMJobClaimed"] == LLM_FACT_STREAM
        assert LLM_SCHEMAS["LLMRouteSelected"] == LLM_FACT_STREAM
        assert LLM_SCHEMAS["LLMJobCompleted"] == LLM_FACT_STREAM
        assert LLM_SCHEMAS["LLMJobFailed"] == LLM_FACT_STREAM
        assert LLM_SCHEMAS["LLMArtifactStored"] == LLM_FACT_STREAM
        assert LLM_SCHEMAS["LLMTokensConsumed"] == LLM_OBSERVATION_STREAM
        assert LLM_SCHEMAS["LLMCostEstimate"] == LLM_DERIVATION_STREAM


class TestLLMIntentStream:
    """Tests for the LLM intent stream (INTENT records)."""

    def test_creates_valid_stream(self):
        """Test intent stream creation."""
        stream = create_llm_intent_stream()
        assert stream.name == "llm.intent.v1"
        assert stream.record_kind == RecordKind.INTENT

    def test_has_correct_schema(self):
        """Test intent stream has LLMJobRequested schema."""
        stream = create_llm_intent_stream()
        assert len(stream.schemas) == 1
        schema = stream.schemas[0]
        assert schema.name == "LLMJobRequested"
        assert schema.version == "v1"

    def test_schema_fields(self):
        """Test LLMJobRequested schema has required fields."""
        stream = create_llm_intent_stream()
        schema = stream.schemas[0]
        field_names = {f.name for f in schema.fields}
        assert "job_id" in field_names
        assert "intent_name" in field_names
        assert "input_data" in field_names
        assert "t_requested" in field_names

    def test_partition_key(self):
        """Test intent stream partitions by job_id."""
        stream = create_llm_intent_stream()
        assert stream.partition_key == "job_id"

    def test_idempotency_strategy(self):
        """Test intent stream has deterministic ID idempotency."""
        stream = create_llm_intent_stream()
        assert stream.idempotency is not None
        assert stream.idempotency.strategy_type == IdempotencyType.DETERMINISTIC_ID
        assert stream.idempotency.field == "job_id"

    def test_expected_outcomes(self):
        """Test intent stream defines expected outcomes."""
        stream = create_llm_intent_stream()
        assert stream.expected_outcomes is not None
        assert len(stream.expected_outcomes) == 3

        conditions = {o.condition for o in stream.expected_outcomes}
        assert OutcomeCondition.SUCCESS in conditions
        assert OutcomeCondition.FAILURE in conditions
        assert OutcomeCondition.TIMEOUT in conditions


class TestLLMFactStream:
    """Tests for the LLM fact stream (FACT records)."""

    def test_creates_valid_stream(self):
        """Test fact stream creation."""
        stream = create_llm_fact_stream()
        assert stream.name == "llm.fact.v1"
        assert stream.record_kind == RecordKind.FACT

    def test_has_all_fact_schemas(self):
        """Test fact stream contains all fact schemas."""
        stream = create_llm_fact_stream()
        schema_names = {s.name for s in stream.schemas}
        assert "LLMJobClaimed" in schema_names
        assert "LLMRouteSelected" in schema_names
        assert "LLMJobCompleted" in schema_names
        assert "LLMJobFailed" in schema_names
        assert "LLMArtifactStored" in schema_names
        assert len(stream.schemas) == 5

    def test_job_completed_schema(self):
        """Test LLMJobCompleted schema fields."""
        stream = create_llm_fact_stream()
        completed_schema = next(s for s in stream.schemas if s.name == "LLMJobCompleted")
        field_names = {f.name for f in completed_schema.fields}
        assert "job_id" in field_names
        assert "completion_artifact_id" in field_names
        assert "input_tokens" in field_names
        assert "output_tokens" in field_names
        assert "latency_ms" in field_names
        assert "t_completed" in field_names

    def test_job_failed_schema(self):
        """Test LLMJobFailed schema fields."""
        stream = create_llm_fact_stream()
        failed_schema = next(s for s in stream.schemas if s.name == "LLMJobFailed")
        field_names = {f.name for f in failed_schema.fields}
        assert "job_id" in field_names
        assert "error_code" in field_names
        assert "error_message" in field_names
        assert "retry_count" in field_names
        assert "is_retriable" in field_names

    def test_partition_key(self):
        """Test fact stream partitions by job_id."""
        stream = create_llm_fact_stream()
        assert stream.partition_key == "job_id"

    def test_invariants(self):
        """Test fact stream defines invariants."""
        stream = create_llm_fact_stream()
        assert stream.invariants is not None
        assert len(stream.invariants) >= 2


class TestLLMObservationStream:
    """Tests for the LLM observation stream (OBSERVATION records)."""

    def test_creates_valid_stream(self):
        """Test observation stream creation."""
        stream = create_llm_observation_stream()
        assert stream.name == "llm.observation.v1"
        assert stream.record_kind == RecordKind.OBSERVATION

    def test_has_tokens_consumed_schema(self):
        """Test observation stream has LLMTokensConsumed schema."""
        stream = create_llm_observation_stream()
        assert len(stream.schemas) == 1
        schema = stream.schemas[0]
        assert schema.name == "LLMTokensConsumed"

    def test_schema_fields(self):
        """Test LLMTokensConsumed schema fields."""
        stream = create_llm_observation_stream()
        schema = stream.schemas[0]
        field_names = {f.name for f in schema.fields}
        assert "observation_id" in field_names
        assert "job_id" in field_names
        assert "model_name" in field_names
        assert "input_tokens" in field_names
        assert "output_tokens" in field_names
        assert "source_system" in field_names
        assert "t_observed" in field_names

    def test_idempotency_uses_dedupe_window(self):
        """Test observation stream uses dedupe window idempotency."""
        stream = create_llm_observation_stream()
        assert stream.idempotency is not None
        assert stream.idempotency.strategy_type == IdempotencyType.DEDUPE_WINDOW
        assert stream.idempotency.window == "5 minutes"


class TestLLMDerivationStream:
    """Tests for the LLM derivation stream (DERIVATION records)."""

    def test_creates_valid_stream(self):
        """Test derivation stream creation."""
        stream = create_llm_derivation_stream()
        assert stream.name == "llm.derivation.v1"
        assert stream.record_kind == RecordKind.DERIVATION

    def test_has_cost_estimate_schema(self):
        """Test derivation stream has LLMCostEstimate schema."""
        stream = create_llm_derivation_stream()
        assert len(stream.schemas) == 1
        schema = stream.schemas[0]
        assert schema.name == "LLMCostEstimate"

    def test_schema_fields(self):
        """Test LLMCostEstimate schema fields."""
        stream = create_llm_derivation_stream()
        schema = stream.schemas[0]
        field_names = {f.name for f in schema.fields}
        assert "estimate_id" in field_names
        assert "job_id" in field_names
        assert "cost_usd" in field_names
        assert "pricing_version" in field_names
        assert "source_observation_ids" in field_names
        assert "t_calculated" in field_names

    def test_has_lineage(self):
        """Test derivation stream has lineage information."""
        stream = create_llm_derivation_stream()
        assert stream.lineage is not None
        assert "llm.observation.v1" in stream.lineage.source_streams
        assert "llm.fact.v1" in stream.lineage.source_streams
        assert stream.lineage.derivation_type == DerivationType.TRANSFORM
        assert stream.lineage.rebuild_strategy == RebuildStrategy.FULL_REPLAY


class TestGetAllLLMStreams:
    """Tests for get_all_llm_streams helper."""

    def test_returns_all_four_streams(self):
        """Test all streams are returned."""
        streams = get_all_llm_streams()
        assert len(streams) == 4

    def test_returns_correct_stream_types(self):
        """Test stream types are correct."""
        streams = get_all_llm_streams()
        record_kinds = {s.record_kind for s in streams}
        assert RecordKind.INTENT in record_kinds
        assert RecordKind.FACT in record_kinds
        assert RecordKind.OBSERVATION in record_kinds
        assert RecordKind.DERIVATION in record_kinds

    def test_stream_names(self):
        """Test all expected stream names are present."""
        streams = get_all_llm_streams()
        names = {s.name for s in streams}
        assert "llm.intent.v1" in names
        assert "llm.fact.v1" in names
        assert "llm.observation.v1" in names
        assert "llm.derivation.v1" in names


class TestHLESSCompliance:
    """Tests for HLESS compliance of LLM event streams."""

    def test_intent_stream_follows_intent_rules(self):
        """Test INTENT stream doesn't imply success."""
        stream = create_llm_intent_stream()
        # INTENT streams should describe what is wanted, not what happened
        assert stream.record_kind == RecordKind.INTENT
        schema = stream.schemas[0]
        # Schema description should not contain success/completion language
        assert "completed" not in schema.description.lower()
        assert "succeeded" not in schema.description.lower()

    def test_fact_stream_follows_fact_rules(self):
        """Test FACT stream doesn't contain imperatives."""
        stream = create_llm_fact_stream()
        assert stream.record_kind == RecordKind.FACT
        # FACT streams record immutable truths
        for schema in stream.schemas:
            # Descriptions should be in past tense or state facts
            assert (
                "request" not in schema.description.lower()
                or "has been" in schema.description.lower()
            )

    def test_observation_stream_follows_observation_rules(self):
        """Test OBSERVATION stream doesn't assert correctness."""
        stream = create_llm_observation_stream()
        assert stream.record_kind == RecordKind.OBSERVATION
        # OBSERVATION streams may be delayed/duplicated
        schema = stream.schemas[0]
        assert (
            "observation" in schema.description.lower() or "observed" in schema.description.lower()
        )

    def test_derivation_stream_has_source_streams(self):
        """Test DERIVATION stream references source streams."""
        stream = create_llm_derivation_stream()
        assert stream.record_kind == RecordKind.DERIVATION
        # DERIVATION must reference source streams
        assert stream.lineage is not None
        assert len(stream.lineage.source_streams) > 0

    def test_all_streams_have_time_semantics(self):
        """Test all streams define time semantics."""
        for stream in get_all_llm_streams():
            assert stream.time_semantics is not None
            assert stream.time_semantics.t_event_field is not None

    def test_all_streams_have_idempotency(self):
        """Test all streams define idempotency strategy."""
        for stream in get_all_llm_streams():
            assert stream.idempotency is not None
            assert stream.idempotency.strategy_type is not None
