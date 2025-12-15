"""
Unit tests for HLESS (High-Level Event Semantics Specification).

Tests cover:
1. RecordKind classification
2. StreamSpec validation
3. HLESSValidator Section 7 rule enforcement
4. Cross-stream reference validation
5. Idempotency defaults
"""

import pytest

from dazzle.core.ir import (
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
    get_default_idempotency,
    validate_stream,
    validate_streams_with_cross_references,
)
from dazzle.core.ir.fields import FieldSpec, FieldType, FieldTypeKind

# --- Fixtures ---


@pytest.fixture
def basic_time_semantics() -> TimeSemantics:
    """Basic time semantics for testing."""
    return TimeSemantics(t_event_field="created_at")


@pytest.fixture
def basic_idempotency() -> IdempotencyStrategy:
    """Basic idempotency strategy for testing."""
    return IdempotencyStrategy(
        strategy_type=IdempotencyType.DETERMINISTIC_ID,
        field="record_id",
    )


@pytest.fixture
def order_placed_schema() -> StreamSchema:
    """OrderPlaced schema for FACT stream testing."""
    return StreamSchema(
        name="OrderPlaced",
        version="v1",
        fields=[
            FieldSpec(
                name="order_id",
                type=FieldType(kind=FieldTypeKind.UUID),
            ),
            FieldSpec(
                name="total_amount",
                type=FieldType(kind=FieldTypeKind.DECIMAL),
            ),
        ],
    )


@pytest.fixture
def order_rejected_schema() -> StreamSchema:
    """OrderPlacementRejected schema for FACT stream testing."""
    return StreamSchema(
        name="OrderPlacementRejected",
        version="v1",
    )


@pytest.fixture
def order_requested_schema() -> StreamSchema:
    """OrderPlacementRequested schema for INTENT stream testing."""
    return StreamSchema(
        name="OrderPlacementRequested",
        version="v1",
    )


# --- RecordKind Tests ---


class TestRecordKind:
    """Tests for RecordKind enum."""

    def test_all_four_kinds_exist(self):
        """All four RecordKinds are defined."""
        assert RecordKind.INTENT.value == "intent"
        assert RecordKind.FACT.value == "fact"
        assert RecordKind.OBSERVATION.value == "observation"
        assert RecordKind.DERIVATION.value == "derivation"

    def test_record_kind_count(self):
        """Exactly four RecordKinds exist."""
        assert len(RecordKind) == 4


# --- StreamSpec Tests ---


class TestStreamSpec:
    """Tests for StreamSpec model."""

    def test_create_fact_stream(
        self,
        basic_time_semantics: TimeSemantics,
        basic_idempotency: IdempotencyStrategy,
        order_placed_schema: StreamSchema,
    ):
        """Can create a valid FACT stream."""
        stream = StreamSpec(
            name="orders.fact.v1",
            record_kind=RecordKind.FACT,
            schemas=[order_placed_schema],
            partition_key="order_id",
            ordering_scope="per_order",
            time_semantics=basic_time_semantics,
            idempotency=basic_idempotency,
            invariants=["OrderPlaced represents a completed and irreversible action"],
        )

        assert stream.name == "orders.fact.v1"
        assert stream.record_kind == RecordKind.FACT
        assert len(stream.schemas) == 1
        assert stream.get_schema("OrderPlaced") is not None

    def test_get_schema_by_name(
        self,
        basic_time_semantics: TimeSemantics,
        basic_idempotency: IdempotencyStrategy,
        order_placed_schema: StreamSchema,
        order_rejected_schema: StreamSchema,
    ):
        """Can retrieve schemas by name."""
        stream = StreamSpec(
            name="orders.fact.v1",
            record_kind=RecordKind.FACT,
            schemas=[order_placed_schema, order_rejected_schema],
            partition_key="order_id",
            ordering_scope="per_order",
            time_semantics=basic_time_semantics,
            idempotency=basic_idempotency,
        )

        assert stream.get_schema("OrderPlaced") is not None
        assert stream.get_schema("OrderPlacementRejected") is not None
        assert stream.get_schema("DoesNotExist") is None

    def test_schema_names(
        self,
        basic_time_semantics: TimeSemantics,
        basic_idempotency: IdempotencyStrategy,
        order_placed_schema: StreamSchema,
        order_rejected_schema: StreamSchema,
    ):
        """schema_names returns all schema names."""
        stream = StreamSpec(
            name="orders.fact.v1",
            record_kind=RecordKind.FACT,
            schemas=[order_placed_schema, order_rejected_schema],
            partition_key="order_id",
            ordering_scope="per_order",
            time_semantics=basic_time_semantics,
            idempotency=basic_idempotency,
        )

        names = stream.schema_names()
        assert "OrderPlaced" in names
        assert "OrderPlacementRejected" in names
        assert len(names) == 2


# --- Validation Tests: Rule 1 - FACT No Imperatives ---


class TestFACTNoImperatives:
    """Rule 1: FACT streams must not contain imperatives or requests."""

    def test_fact_with_imperative_name_fails(
        self,
        basic_time_semantics: TimeSemantics,
        basic_idempotency: IdempotencyStrategy,
    ):
        """FACT schema with imperative name is rejected."""
        stream = StreamSpec(
            name="orders.fact.v1",
            record_kind=RecordKind.FACT,
            schemas=[StreamSchema(name="CreateOrder")],  # Imperative!
            partition_key="order_id",
            ordering_scope="per_order",
            time_semantics=basic_time_semantics,
            idempotency=basic_idempotency,
        )

        result = validate_stream(stream)
        assert not result.valid
        assert any(v.rule == "FACT_NO_IMPERATIVES" for v in result.violations)

    def test_fact_with_past_tense_name_passes(
        self,
        basic_time_semantics: TimeSemantics,
        basic_idempotency: IdempotencyStrategy,
        order_placed_schema: StreamSchema,
    ):
        """FACT schema with past tense name is accepted."""
        stream = StreamSpec(
            name="orders.fact.v1",
            record_kind=RecordKind.FACT,
            schemas=[order_placed_schema],
            partition_key="order_id",
            ordering_scope="per_order",
            time_semantics=basic_time_semantics,
            idempotency=basic_idempotency,
        )

        result = validate_stream(stream)
        assert not any(v.rule == "FACT_NO_IMPERATIVES" for v in result.violations)

    @pytest.mark.parametrize(
        "name",
        [
            "PlaceOrder",
            "SubmitPayment",
            "SendEmail",
            "ProcessRefund",
            "DeleteUser",
            "UpdateInventory",
        ],
    )
    def test_various_imperatives_rejected(
        self,
        name: str,
        basic_time_semantics: TimeSemantics,
        basic_idempotency: IdempotencyStrategy,
    ):
        """Various imperative names are rejected in FACT streams."""
        stream = StreamSpec(
            name="test.fact.v1",
            record_kind=RecordKind.FACT,
            schemas=[StreamSchema(name=name)],
            partition_key="id",
            ordering_scope="per_id",
            time_semantics=basic_time_semantics,
            idempotency=basic_idempotency,
        )

        result = validate_stream(stream)
        assert any(v.rule == "FACT_NO_IMPERATIVES" for v in result.violations)


# --- Validation Tests: Rule 2 - INTENT No Success ---


class TestINTENTNoSuccess:
    """Rule 2: INTENT streams must not imply success."""

    def test_intent_with_completion_name_fails(
        self,
        basic_time_semantics: TimeSemantics,
        basic_idempotency: IdempotencyStrategy,
    ):
        """INTENT schema with completion name is rejected."""
        stream = StreamSpec(
            name="orders.intent.v1",
            record_kind=RecordKind.INTENT,
            schemas=[StreamSchema(name="OrderCreated")],  # Implies completion!
            partition_key="order_id",
            ordering_scope="per_order",
            time_semantics=basic_time_semantics,
            idempotency=basic_idempotency,
            expected_outcomes=[
                ExpectedOutcome(
                    condition=OutcomeCondition.SUCCESS,
                    emits=["OrderPlaced"],
                    target_stream="orders.fact.v1",
                )
            ],
        )

        result = validate_stream(stream)
        assert not result.valid
        assert any(v.rule == "INTENT_NO_SUCCESS" for v in result.violations)

    def test_intent_without_outcomes_fails(
        self,
        basic_time_semantics: TimeSemantics,
        basic_idempotency: IdempotencyStrategy,
        order_requested_schema: StreamSchema,
    ):
        """INTENT stream without expected_outcomes is rejected."""
        stream = StreamSpec(
            name="orders.intent.v1",
            record_kind=RecordKind.INTENT,
            schemas=[order_requested_schema],
            partition_key="order_id",
            ordering_scope="per_order",
            time_semantics=basic_time_semantics,
            idempotency=basic_idempotency,
            # Missing expected_outcomes!
        )

        result = validate_stream(stream)
        assert not result.valid
        assert any(v.rule == "INTENT_REQUIRES_OUTCOMES" for v in result.violations)

    def test_valid_intent_stream_passes(
        self,
        basic_time_semantics: TimeSemantics,
        basic_idempotency: IdempotencyStrategy,
        order_requested_schema: StreamSchema,
    ):
        """Valid INTENT stream with proper naming and outcomes passes."""
        stream = StreamSpec(
            name="orders.intent.v1",
            record_kind=RecordKind.INTENT,
            schemas=[order_requested_schema],
            partition_key="order_id",
            ordering_scope="per_order",
            time_semantics=basic_time_semantics,
            idempotency=basic_idempotency,
            expected_outcomes=[
                ExpectedOutcome(
                    condition=OutcomeCondition.SUCCESS,
                    emits=["OrderPlaced"],
                    target_stream="orders.fact.v1",
                ),
                ExpectedOutcome(
                    condition=OutcomeCondition.FAILURE,
                    emits=["OrderPlacementRejected"],
                    target_stream="orders.fact.v1",
                ),
            ],
        )

        result = validate_stream(stream)
        # Should not have INTENT-specific errors
        assert not any(v.rule == "INTENT_NO_SUCCESS" for v in result.violations)
        assert not any(v.rule == "INTENT_REQUIRES_OUTCOMES" for v in result.violations)


# --- Validation Tests: Rule 3 - DERIVATION Requires Lineage ---


class TestDERIVATIONRequiresLineage:
    """Rule 3: DERIVATION streams must reference source streams."""

    def test_derivation_without_lineage_fails(
        self,
        basic_time_semantics: TimeSemantics,
        basic_idempotency: IdempotencyStrategy,
    ):
        """DERIVATION stream without lineage is rejected."""
        stream = StreamSpec(
            name="metrics.derivation.v1",
            record_kind=RecordKind.DERIVATION,
            schemas=[StreamSchema(name="DailyRevenueCalculated")],
            partition_key="date",
            ordering_scope="per_day",
            time_semantics=basic_time_semantics,
            idempotency=basic_idempotency,
            # Missing lineage!
        )

        result = validate_stream(stream)
        assert not result.valid
        assert any(v.rule == "DERIVATION_REQUIRES_LINEAGE" for v in result.violations)

    def test_derivation_with_empty_sources_fails(
        self,
        basic_time_semantics: TimeSemantics,
        basic_idempotency: IdempotencyStrategy,
    ):
        """DERIVATION stream with empty source_streams is rejected."""
        stream = StreamSpec(
            name="metrics.derivation.v1",
            record_kind=RecordKind.DERIVATION,
            schemas=[StreamSchema(name="DailyRevenueCalculated")],
            partition_key="date",
            ordering_scope="per_day",
            time_semantics=basic_time_semantics,
            idempotency=basic_idempotency,
            lineage=DerivationLineage(
                source_streams=[],  # Empty!
                derivation_type=DerivationType.AGGREGATE,
            ),
        )

        result = validate_stream(stream)
        assert not result.valid
        assert any(v.rule == "DERIVATION_EMPTY_SOURCES" for v in result.violations)

    def test_valid_derivation_stream_passes(
        self,
        basic_idempotency: IdempotencyStrategy,
    ):
        """Valid DERIVATION stream with proper lineage passes."""
        stream = StreamSpec(
            name="metrics.derivation.v1",
            record_kind=RecordKind.DERIVATION,
            schemas=[StreamSchema(name="DailyRevenueCalculated")],
            partition_key="date",
            ordering_scope="per_day",
            time_semantics=TimeSemantics(
                t_event_field="date",
                t_process_field="calculated_at",
            ),
            idempotency=basic_idempotency,
            lineage=DerivationLineage(
                source_streams=["orders.fact.v1"],
                derivation_type=DerivationType.AGGREGATE,
                rebuild_strategy=RebuildStrategy.FULL_REPLAY,
            ),
            invariants=["Can be deleted and rebuilt from orders.fact.v1"],
        )

        result = validate_stream(stream)
        # Should not have DERIVATION-specific errors
        assert not any(v.rule == "DERIVATION_REQUIRES_LINEAGE" for v in result.violations)
        assert not any(v.rule == "DERIVATION_EMPTY_SOURCES" for v in result.violations)


# --- Validation Tests: Rule 4 - OBSERVATION No Truth Claims ---


class TestOBSERVATIONNoTruthClaims:
    """Rule 4: OBSERVATION streams must not assert correctness."""

    def test_observation_with_truth_claim_fails(
        self,
        basic_time_semantics: TimeSemantics,
        basic_idempotency: IdempotencyStrategy,
    ):
        """OBSERVATION invariant with truth assertion is rejected."""
        stream = StreamSpec(
            name="inventory.observation.v1",
            record_kind=RecordKind.OBSERVATION,
            schemas=[StreamSchema(name="InventoryLevelObserved")],
            partition_key="sku",
            ordering_scope="per_sku",
            time_semantics=basic_time_semantics,
            idempotency=basic_idempotency,
            invariants=[
                "The quantity is correct and authoritative",  # Truth claim!
            ],
        )

        result = validate_stream(stream)
        assert any(v.rule == "OBSERVATION_NO_TRUTH_CLAIMS" for v in result.violations)

    def test_observation_with_proper_invariants_passes(
        self,
        basic_time_semantics: TimeSemantics,
        basic_idempotency: IdempotencyStrategy,
    ):
        """OBSERVATION with observation-appropriate invariants passes."""
        stream = StreamSpec(
            name="inventory.observation.v1",
            record_kind=RecordKind.OBSERVATION,
            schemas=[StreamSchema(name="InventoryLevelObserved")],
            partition_key="sku",
            ordering_scope="per_sku",
            time_semantics=basic_time_semantics,
            idempotency=basic_idempotency,
            invariants=[
                "May contain duplicates",
                "Arrival may be out of order",
                "Records what was observed, not what is necessarily true",
            ],
        )

        result = validate_stream(stream)
        assert not any(v.rule == "OBSERVATION_NO_TRUTH_CLAIMS" for v in result.violations)

    @pytest.mark.parametrize(
        "bad_invariant",
        [
            "This value is accurate",
            "Ensures the data is correct",
            "Guarantees delivery",
            "The reading is true",
            "This must be the final value",
        ],
    )
    def test_various_truth_claims_rejected(
        self,
        bad_invariant: str,
        basic_time_semantics: TimeSemantics,
        basic_idempotency: IdempotencyStrategy,
    ):
        """Various truth claims are rejected in OBSERVATION streams."""
        stream = StreamSpec(
            name="test.observation.v1",
            record_kind=RecordKind.OBSERVATION,
            schemas=[StreamSchema(name="TestObservation")],
            partition_key="id",
            ordering_scope="per_id",
            time_semantics=basic_time_semantics,
            idempotency=basic_idempotency,
            invariants=[bad_invariant],
        )

        result = validate_stream(stream)
        assert any(v.rule == "OBSERVATION_NO_TRUTH_CLAIMS" for v in result.violations)


# --- Validation Tests: Rule 5 - Ordering Scope ---


class TestOrderingScope:
    """Rule 5: Order-dependent invariants must match partition key."""

    def test_order_invariant_without_scope_warns(
        self,
        basic_time_semantics: TimeSemantics,
        basic_idempotency: IdempotencyStrategy,
        order_placed_schema: StreamSchema,
    ):
        """Order-dependent invariant without scope reference warns."""
        stream = StreamSpec(
            name="orders.fact.v1",
            record_kind=RecordKind.FACT,
            schemas=[order_placed_schema],
            partition_key="order_id",
            ordering_scope="per_order",
            time_semantics=basic_time_semantics,
            idempotency=basic_idempotency,
            invariants=[
                "Events must arrive in sequence",  # Order-dependent
            ],
        )

        result = validate_stream(stream)
        assert any(v.rule == "ORDER_SCOPE_MISMATCH" for v in result.violations)

    def test_order_invariant_with_scope_passes(
        self,
        basic_time_semantics: TimeSemantics,
        basic_idempotency: IdempotencyStrategy,
        order_placed_schema: StreamSchema,
    ):
        """Order-dependent invariant with scope reference passes."""
        stream = StreamSpec(
            name="orders.fact.v1",
            record_kind=RecordKind.FACT,
            schemas=[order_placed_schema],
            partition_key="order_id",
            ordering_scope="per_order",
            time_semantics=basic_time_semantics,
            idempotency=basic_idempotency,
            invariants=[
                "Events are ordered within each order_id",  # Scoped!
            ],
        )

        result = validate_stream(stream)
        assert not any(v.rule == "ORDER_SCOPE_MISMATCH" for v in result.violations)


# --- Validation Tests: Rule 6 - Required Fields ---


class TestRequiredFields:
    """Rule 6: All streams must have required fields."""

    def test_stream_without_schemas_fails(
        self,
        basic_time_semantics: TimeSemantics,
        basic_idempotency: IdempotencyStrategy,
    ):
        """Stream without schemas is rejected."""
        stream = StreamSpec(
            name="test.fact.v1",
            record_kind=RecordKind.FACT,
            schemas=[],  # Empty!
            partition_key="id",
            ordering_scope="per_id",
            time_semantics=basic_time_semantics,
            idempotency=basic_idempotency,
        )

        result = validate_stream(stream)
        assert not result.valid
        assert any(v.rule == "STREAM_REQUIRES_SCHEMA" for v in result.violations)


# --- Cross-Stream Reference Validation ---


class TestCrossStreamValidation:
    """Tests for cross-stream reference validation."""

    def test_intent_outcome_to_nonexistent_stream_fails(self):
        """INTENT outcome referencing nonexistent stream fails."""
        intent_stream = StreamSpec(
            name="orders.intent.v1",
            record_kind=RecordKind.INTENT,
            schemas=[StreamSchema(name="OrderPlacementRequested")],
            partition_key="order_id",
            ordering_scope="per_order",
            time_semantics=TimeSemantics(t_event_field="requested_at"),
            idempotency=IdempotencyStrategy(
                strategy_type=IdempotencyType.DETERMINISTIC_ID,
                field="request_id",
            ),
            expected_outcomes=[
                ExpectedOutcome(
                    condition=OutcomeCondition.SUCCESS,
                    emits=["OrderPlaced"],
                    target_stream="nonexistent.fact.v1",  # Doesn't exist!
                )
            ],
        )

        result = validate_streams_with_cross_references([intent_stream])
        assert any(v.rule == "INTENT_OUTCOME_STREAM_NOT_FOUND" for v in result.violations)

    def test_intent_outcome_to_non_fact_stream_fails(self):
        """INTENT outcome targeting non-FACT stream fails."""
        intent_stream = StreamSpec(
            name="orders.intent.v1",
            record_kind=RecordKind.INTENT,
            schemas=[StreamSchema(name="OrderPlacementRequested")],
            partition_key="order_id",
            ordering_scope="per_order",
            time_semantics=TimeSemantics(t_event_field="requested_at"),
            idempotency=IdempotencyStrategy(
                strategy_type=IdempotencyType.DETERMINISTIC_ID,
                field="request_id",
            ),
            expected_outcomes=[
                ExpectedOutcome(
                    condition=OutcomeCondition.SUCCESS,
                    emits=["AnotherIntent"],
                    target_stream="another.intent.v1",  # Not a FACT stream!
                )
            ],
        )

        another_intent = StreamSpec(
            name="another.intent.v1",
            record_kind=RecordKind.INTENT,  # Not FACT!
            schemas=[StreamSchema(name="AnotherIntent")],
            partition_key="id",
            ordering_scope="per_id",
            time_semantics=TimeSemantics(t_event_field="created_at"),
            idempotency=IdempotencyStrategy(
                strategy_type=IdempotencyType.DETERMINISTIC_ID,
                field="request_id",
            ),
            expected_outcomes=[
                ExpectedOutcome(
                    condition=OutcomeCondition.SUCCESS,
                    emits=["Something"],
                )
            ],
        )

        result = validate_streams_with_cross_references([intent_stream, another_intent])
        assert any(v.rule == "INTENT_OUTCOME_NOT_FACT" for v in result.violations)

    def test_derivation_source_not_found_fails(self):
        """DERIVATION referencing nonexistent source stream fails."""
        derivation = StreamSpec(
            name="metrics.derivation.v1",
            record_kind=RecordKind.DERIVATION,
            schemas=[StreamSchema(name="MetricCalculated")],
            partition_key="date",
            ordering_scope="per_day",
            time_semantics=TimeSemantics(
                t_event_field="date",
                t_process_field="calculated_at",
            ),
            idempotency=IdempotencyStrategy(
                strategy_type=IdempotencyType.DETERMINISTIC_ID,
                field="derivation_id",
            ),
            lineage=DerivationLineage(
                source_streams=["nonexistent.fact.v1"],  # Doesn't exist!
                derivation_type=DerivationType.AGGREGATE,
            ),
        )

        result = validate_streams_with_cross_references([derivation])
        assert any(v.rule == "DERIVATION_SOURCE_NOT_FOUND" for v in result.violations)

    def test_partition_key_mismatch_without_cross_partition_fails(self):
        """Partition key mismatch without cross_partition flag fails."""
        intent_stream = StreamSpec(
            name="orders.intent.v1",
            record_kind=RecordKind.INTENT,
            schemas=[StreamSchema(name="OrderPlacementRequested")],
            partition_key="customer_id",  # Different from FACT stream!
            ordering_scope="per_customer",
            time_semantics=TimeSemantics(t_event_field="requested_at"),
            idempotency=IdempotencyStrategy(
                strategy_type=IdempotencyType.DETERMINISTIC_ID,
                field="request_id",
            ),
            expected_outcomes=[
                ExpectedOutcome(
                    condition=OutcomeCondition.SUCCESS,
                    emits=["OrderPlaced"],
                    target_stream="orders.fact.v1",
                )
            ],
        )

        fact_stream = StreamSpec(
            name="orders.fact.v1",
            record_kind=RecordKind.FACT,
            schemas=[StreamSchema(name="OrderPlaced")],
            partition_key="order_id",  # Different!
            ordering_scope="per_order",
            time_semantics=TimeSemantics(t_event_field="placed_at"),
            idempotency=IdempotencyStrategy(
                strategy_type=IdempotencyType.DETERMINISTIC_ID,
                field="record_id",
            ),
        )

        result = validate_streams_with_cross_references([intent_stream, fact_stream])
        assert any(v.rule == "INTENT_OUTCOME_PARTITION_MISMATCH" for v in result.violations)


# --- Idempotency Defaults ---


class TestIdempotencyDefaults:
    """Tests for default idempotency strategies."""

    def test_intent_default(self):
        """INTENT has correct default idempotency."""
        default = get_default_idempotency(RecordKind.INTENT)
        assert default.strategy_type == IdempotencyType.DETERMINISTIC_ID
        assert default.field == "request_id"

    def test_fact_default(self):
        """FACT has correct default idempotency."""
        default = get_default_idempotency(RecordKind.FACT)
        assert default.strategy_type == IdempotencyType.DETERMINISTIC_ID
        assert default.field == "record_id"

    def test_observation_default(self):
        """OBSERVATION has correct default idempotency (dedupe window)."""
        default = get_default_idempotency(RecordKind.OBSERVATION)
        assert default.strategy_type == IdempotencyType.DEDUPE_WINDOW
        assert default.window == "5 minutes"

    def test_derivation_default(self):
        """DERIVATION has correct default idempotency."""
        default = get_default_idempotency(RecordKind.DERIVATION)
        assert default.strategy_type == IdempotencyType.DETERMINISTIC_ID
        assert default.field == "derivation_id"

    def test_defaults_are_copies(self):
        """Default strategies are independent copies."""
        default1 = get_default_idempotency(RecordKind.FACT)
        default2 = get_default_idempotency(RecordKind.FACT)

        default1.field = "modified"
        assert default2.field == "record_id"  # Unchanged


# --- StreamSchema Tests ---


class TestStreamSchema:
    """Tests for StreamSchema model."""

    def test_qualified_name(self):
        """qualified_name returns name@version."""
        schema = StreamSchema(name="OrderPlaced", version="v2")
        assert schema.qualified_name == "OrderPlaced@v2"

    def test_default_version(self):
        """Default version is v1."""
        schema = StreamSchema(name="OrderPlaced")
        assert schema.version == "v1"
        assert schema.qualified_name == "OrderPlaced@v1"


# --- DSL Parsing Tests ---


class TestHLESSParsing:
    """Tests for HLESS DSL parsing."""

    def test_parse_simple_fact_stream(self):
        """Parse a simple FACT stream from DSL."""
        from pathlib import Path

        from dazzle.core.dsl_parser_impl import parse_dsl

        dsl = """
module test_hless
app test "Test App"

stream order_facts:
  kind: FACT
  description: "Immutable facts about orders"

  schema OrderPlaced:
    order_id: uuid required
    total_amount: int required
    placed_at: datetime required

  partition_key: order_id
  ordering_scope: per_order
  t_event: placed_at

  side_effects:
    allowed: false
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.streams) == 1
        stream = fragment.streams[0]
        assert stream.name == "order_facts"
        assert stream.record_kind == RecordKind.FACT
        assert stream.partition_key == "order_id"
        assert stream.ordering_scope == "per_order"
        assert stream.time_semantics.t_event_field == "placed_at"
        assert stream.side_effect_policy.external_effects_allowed is False

        # Check schema
        assert len(stream.schemas) == 1
        schema = stream.schemas[0]
        assert schema.name == "OrderPlaced"
        assert len(schema.fields) == 3

    def test_parse_intent_stream_with_outcomes(self):
        """Parse an INTENT stream with outcomes."""
        from pathlib import Path

        from dazzle.core.dsl_parser_impl import parse_dsl

        dsl = """
module test_hless
app test "Test App"

stream order_placement_requests:
  kind: INTENT
  description: "Requests to place orders"

  schema OrderPlacementRequested:
    order_id: uuid required
    customer_id: uuid required

  partition_key: order_id
  ordering_scope: per_order
  t_event: requested_at

  idempotency:
    type: deterministic_id
    field: request_id

  outcomes:
    success:
      emits OrderPlaced from order_facts
    failure:
      emits OrderPlacementRejected from order_facts
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.streams) == 1
        stream = fragment.streams[0]
        assert stream.name == "order_placement_requests"
        assert stream.record_kind == RecordKind.INTENT

        # Check idempotency
        assert stream.idempotency.strategy_type == IdempotencyType.DETERMINISTIC_ID
        assert stream.idempotency.field == "request_id"

        # Check outcomes
        assert len(stream.expected_outcomes) == 2
        success = next(o for o in stream.expected_outcomes if o.condition.value == "success")
        assert "OrderPlaced" in success.emits
        assert success.target_stream == "order_facts"

    def test_parse_derivation_stream_with_lineage(self):
        """Parse a DERIVATION stream with lineage."""
        from pathlib import Path

        from dazzle.core.dsl_parser_impl import parse_dsl

        dsl = """
module test_hless
app test "Test App"

stream daily_order_stats:
  kind: DERIVATION
  description: "Daily aggregated order statistics"

  schema DailyOrderTotal:
    date: date required
    total_orders: int required

  partition_key: date
  ordering_scope: per_day
  t_event: date
  t_process: calculated_at

  derives_from:
    streams: [order_facts]
    type: aggregate
    rebuild: full_replay
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.streams) == 1
        stream = fragment.streams[0]
        assert stream.name == "daily_order_stats"
        assert stream.record_kind == RecordKind.DERIVATION
        assert stream.time_semantics.t_process_field == "calculated_at"

        # Check lineage
        assert stream.lineage is not None
        assert "order_facts" in stream.lineage.source_streams
        assert stream.lineage.derivation_type == DerivationType.AGGREGATE
        assert stream.lineage.rebuild_strategy == RebuildStrategy.FULL_REPLAY

    def test_parse_observation_stream(self):
        """Parse an OBSERVATION stream."""
        from pathlib import Path

        from dazzle.core.dsl_parser_impl import parse_dsl

        dsl = """
module test_hless
app test "Test App"

stream sensor_readings:
  kind: OBSERVATION
  description: "Temperature sensor readings"

  schema TemperatureReading:
    sensor_id: uuid required
    temperature: int required
    observed_at: datetime required

  partition_key: sensor_id
  ordering_scope: per_sensor
  t_event: observed_at

  invariant: "May contain duplicates"
  note: "Readings can arrive out of order"
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.streams) == 1
        stream = fragment.streams[0]
        assert stream.name == "sensor_readings"
        assert stream.record_kind == RecordKind.OBSERVATION
        assert "May contain duplicates" in stream.invariants

    def test_parse_hless_pragma(self):
        """Parse @hless pragma."""
        from pathlib import Path

        from dazzle.core.dsl_parser_impl import parse_dsl
        from dazzle.core.ir import HLESSMode

        dsl = """
module test_hless
app test "Test App"

hless strict

stream order_facts:
  kind: FACT

  schema OrderPlaced:
    order_id: uuid required

  partition_key: order_id
  ordering_scope: per_order
  t_event: placed_at
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert fragment.hless_pragma is not None
        assert fragment.hless_pragma.mode == HLESSMode.STRICT

    def test_parse_multiple_streams(self):
        """Parse multiple streams in one file."""
        from pathlib import Path

        from dazzle.core.dsl_parser_impl import parse_dsl

        dsl = """
module test_hless
app test "Test App"

stream order_requests:
  kind: INTENT

  schema OrderRequested:
    order_id: uuid required

  partition_key: order_id
  ordering_scope: per_order
  t_event: requested_at

  outcomes:
    success:
      emits OrderPlaced from order_facts

stream order_facts:
  kind: FACT

  schema OrderPlaced:
    order_id: uuid required

  partition_key: order_id
  ordering_scope: per_order
  t_event: placed_at
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.streams) == 2
        stream_names = [s.name for s in fragment.streams]
        assert "order_requests" in stream_names
        assert "order_facts" in stream_names


# --- Forbidden Terminology Tests ---


class TestForbiddenTerminology:
    """Tests for forbidden terminology enforcement."""

    def test_event_in_stream_name_rejected_in_strict_mode(
        self,
        basic_time_semantics: TimeSemantics,
        basic_idempotency: IdempotencyStrategy,
    ):
        """'event' in stream name rejected in strict mode."""
        from dazzle.core.ir import HLESSMode, HLESSPragma

        stream = StreamSpec(
            name="order_events",  # Contains 'event'!
            record_kind=RecordKind.FACT,
            schemas=[StreamSchema(name="OrderPlaced")],
            partition_key="order_id",
            ordering_scope="per_order",
            time_semantics=basic_time_semantics,
            idempotency=basic_idempotency,
        )

        pragma = HLESSPragma(mode=HLESSMode.STRICT)
        result = validate_stream(stream, pragma)
        assert any(v.rule == "FORBIDDEN_TERMINOLOGY" for v in result.violations)

    def test_event_in_schema_name_rejected_in_strict_mode(
        self,
        basic_time_semantics: TimeSemantics,
        basic_idempotency: IdempotencyStrategy,
    ):
        """'Event' in schema name rejected in strict mode."""
        from dazzle.core.ir import HLESSMode, HLESSPragma

        stream = StreamSpec(
            name="orders.fact.v1",
            record_kind=RecordKind.FACT,
            schemas=[StreamSchema(name="OrderEvent")],  # Contains 'Event'!
            partition_key="order_id",
            ordering_scope="per_order",
            time_semantics=basic_time_semantics,
            idempotency=basic_idempotency,
        )

        pragma = HLESSPragma(mode=HLESSMode.STRICT)
        result = validate_stream(stream, pragma)
        assert any(v.rule == "FORBIDDEN_TERMINOLOGY" for v in result.violations)

    def test_event_allowed_in_warn_mode(
        self,
        basic_time_semantics: TimeSemantics,
        basic_idempotency: IdempotencyStrategy,
    ):
        """'event' allowed (no FORBIDDEN_TERMINOLOGY error) in warn mode."""
        from dazzle.core.ir import HLESSMode, HLESSPragma

        stream = StreamSpec(
            name="order_events",
            record_kind=RecordKind.FACT,
            schemas=[StreamSchema(name="OrderPlaced")],
            partition_key="order_id",
            ordering_scope="per_order",
            time_semantics=basic_time_semantics,
            idempotency=basic_idempotency,
        )

        pragma = HLESSPragma(mode=HLESSMode.WARN)
        result = validate_stream(stream, pragma)
        assert not any(v.rule == "FORBIDDEN_TERMINOLOGY" for v in result.violations)

    def test_event_allowed_without_pragma(
        self,
        basic_time_semantics: TimeSemantics,
        basic_idempotency: IdempotencyStrategy,
    ):
        """'event' allowed without any pragma."""
        stream = StreamSpec(
            name="order_events",
            record_kind=RecordKind.FACT,
            schemas=[StreamSchema(name="OrderPlaced")],
            partition_key="order_id",
            ordering_scope="per_order",
            time_semantics=basic_time_semantics,
            idempotency=basic_idempotency,
        )

        result = validate_stream(stream)
        assert not any(v.rule == "FORBIDDEN_TERMINOLOGY" for v in result.violations)

    @pytest.mark.parametrize(
        "bad_name",
        [
            "order_events",
            "user_events",
            "payment_event_log",
            "EventStream",
        ],
    )
    def test_various_event_names_rejected(
        self,
        bad_name: str,
        basic_time_semantics: TimeSemantics,
        basic_idempotency: IdempotencyStrategy,
    ):
        """Various 'event' variations rejected in strict mode."""
        from dazzle.core.ir import HLESSMode, HLESSPragma

        stream = StreamSpec(
            name=bad_name,
            record_kind=RecordKind.FACT,
            schemas=[StreamSchema(name="TestSchema")],
            partition_key="id",
            ordering_scope="per_id",
            time_semantics=basic_time_semantics,
            idempotency=basic_idempotency,
        )

        pragma = HLESSPragma(mode=HLESSMode.STRICT)
        result = validate_stream(stream, pragma)
        assert any(v.rule == "FORBIDDEN_TERMINOLOGY" for v in result.violations)
