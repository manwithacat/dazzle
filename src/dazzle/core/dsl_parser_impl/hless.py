"""
HLESS parsing for DAZZLE DSL.

Handles stream declarations with HLESS (High-Level Event Semantics) compliance.
Part of v0.19.0 HLESS feature.

DSL syntax examples:

    stream order_placement_requests:
      kind: INTENT
      description: "Captures requests to place orders"

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

    stream order_facts:
      kind: FACT
      description: "Immutable facts about orders"

      schema OrderPlaced:
        order_id: uuid required
        total_amount: money required
        placed_at: datetime required

      partition_key: order_id
      ordering_scope: per_order
      t_event: placed_at

      invariant: "OrderPlaced represents a completed and irreversible action"

      side_effects:
        allowed: false
"""

from typing import TYPE_CHECKING, Any

from .. import ir
from ..lexer import TokenType


class HLESSParserMixin:
    """
    Mixin providing HLESS stream construct parsing.

    Parses:
    - stream: HLESS-compliant stream definitions
    - @hless pragma: HLESS mode configuration

    Note: This mixin expects to be combined with BaseParser via multiple inheritance.
    """

    if TYPE_CHECKING:
        expect: Any
        advance: Any
        match: Any
        current_token: Any
        expect_identifier_or_keyword: Any
        skip_newlines: Any
        file: Any
        parse_type_spec: Any
        parse_field_modifiers: Any
        error: Any
        _is_keyword_as_identifier: Any

    # =========================================================================
    # Stream Parsing
    # =========================================================================

    def parse_stream(self) -> ir.StreamSpec:
        """Parse stream declaration.

        DSL syntax:
            stream order_facts:
              kind: FACT
              description: "..."

              schema OrderPlaced:
                order_id: uuid required
                ...

              partition_key: order_id
              ordering_scope: per_order
              t_event: placed_at

              idempotency:
                type: deterministic_id
                field: record_id

              invariant: "..."
              note: "..."

              # For INTENT streams
              outcomes:
                success:
                  emits OrderPlaced from order_facts

              # For DERIVATION streams
              derives_from:
                streams: [source_stream]
                type: aggregate
                rebuild: full_replay
        """
        self.expect(TokenType.STREAM)
        name = self.expect(TokenType.IDENTIFIER).value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        # Required fields
        record_kind: ir.RecordKind | None = None
        partition_key: str | None = None
        ordering_scope: str | None = None
        time_semantics: ir.TimeSemantics | None = None
        idempotency: ir.IdempotencyStrategy | None = None

        # Optional fields
        schemas: list[ir.StreamSchema] = []
        invariants: list[str] = []
        notes: list[str] = []
        causality_fields: list[str] = ["trace_id", "causation_id", "correlation_id"]
        side_effect_policy = ir.SideEffectPolicy()
        expected_outcomes: list[ir.ExpectedOutcome] | None = None
        lineage: ir.DerivationLineage | None = None
        description: str | None = None
        cross_partition = False

        # Time fields (before building TimeSemantics)
        t_event_field: str | None = None
        t_log_field = "_t_log"
        t_process_field: str | None = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # kind: INTENT | FACT | OBSERVATION | DERIVATION
            if self.match(TokenType.KIND):
                self.advance()
                self.expect(TokenType.COLON)
                record_kind = self._parse_record_kind()

            # description: "..."
            elif self.match(TokenType.DESCRIPTION):
                self.advance()
                self.expect(TokenType.COLON)
                description = self.expect(TokenType.STRING).value

            # schema SchemaName:
            elif self.match(TokenType.SCHEMA):
                schema = self._parse_stream_schema()
                schemas.append(schema)

            # partition_key: field_name
            elif self.match(TokenType.PARTITION_KEY):
                self.advance()
                self.expect(TokenType.COLON)
                partition_key = self.expect(TokenType.IDENTIFIER).value

            # ordering_scope: per_order
            elif self.match(TokenType.ORDERING_SCOPE):
                self.advance()
                self.expect(TokenType.COLON)
                ordering_scope = self.expect(TokenType.IDENTIFIER).value

            # t_event: field_name
            elif self.match(TokenType.T_EVENT):
                self.advance()
                self.expect(TokenType.COLON)
                t_event_field = self.expect(TokenType.IDENTIFIER).value

            # t_log: field_name (optional, defaults to _t_log)
            elif self.match(TokenType.T_LOG):
                self.advance()
                self.expect(TokenType.COLON)
                t_log_field = self.expect(TokenType.IDENTIFIER).value

            # t_process: field_name (for DERIVATION)
            elif self.match(TokenType.T_PROCESS):
                self.advance()
                self.expect(TokenType.COLON)
                t_process_field = self.expect(TokenType.IDENTIFIER).value

            # idempotency:
            elif self.match(TokenType.IDEMPOTENCY):
                idempotency = self._parse_idempotency()

            # invariant: "..."
            elif self.match(TokenType.INVARIANT):
                self.advance()
                self.expect(TokenType.COLON)
                invariants.append(self.expect(TokenType.STRING).value)

            # note: "..."
            elif self.match(TokenType.NOTE):
                self.advance()
                self.expect(TokenType.COLON)
                notes.append(self.expect(TokenType.STRING).value)

            # outcomes: (for INTENT streams)
            elif self.match(TokenType.OUTCOMES):
                expected_outcomes = self._parse_outcomes()

            # derives_from: (for DERIVATION streams)
            elif self.match(TokenType.DERIVES_FROM):
                lineage = self._parse_lineage()

            # side_effects:
            elif self.match(TokenType.SIDE_EFFECTS):
                side_effect_policy = self._parse_side_effects()

            # causality_fields: [trace_id, causation_id, correlation_id]
            elif (
                self.match(TokenType.IDENTIFIER)
                and self.current_token().value == "causality_fields"
            ):
                self.advance()
                self.expect(TokenType.COLON)
                causality_fields = self._parse_hless_list()

            # cross_partition: true
            elif (
                self.match(TokenType.IDENTIFIER) and self.current_token().value == "cross_partition"
            ):
                self.advance()
                self.expect(TokenType.COLON)
                if self.match(TokenType.TRUE):
                    self.advance()
                    cross_partition = True
                elif self.match(TokenType.FALSE):
                    self.advance()
                    cross_partition = False
                else:
                    # Assume identifier "true" or "false"
                    val = self.expect(TokenType.IDENTIFIER).value
                    cross_partition = val.lower() == "true"

            else:
                # Skip unknown
                self.advance()

            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        # Validate required fields
        if record_kind is None:
            self.error("Stream must specify 'kind: INTENT|FACT|OBSERVATION|DERIVATION'")
        if partition_key is None:
            self.error("Stream must specify 'partition_key'")
        if ordering_scope is None:
            self.error("Stream must specify 'ordering_scope'")
        if t_event_field is None:
            self.error("Stream must specify 't_event' (domain occurrence time field)")

        # Build TimeSemantics
        time_semantics = ir.TimeSemantics(
            t_event_field=t_event_field,  # type: ignore
            t_log_field=t_log_field,
            t_process_field=t_process_field,
        )

        # Fill in default idempotency if not specified
        if idempotency is None:
            idempotency = ir.get_default_idempotency(record_kind)  # type: ignore

        return ir.StreamSpec(
            name=name,
            record_kind=record_kind,  # type: ignore
            schemas=schemas,
            partition_key=partition_key,  # type: ignore
            ordering_scope=ordering_scope,  # type: ignore
            time_semantics=time_semantics,
            idempotency=idempotency,
            causality_fields=causality_fields,
            invariants=invariants,
            side_effect_policy=side_effect_policy,
            expected_outcomes=expected_outcomes,
            lineage=lineage,
            cross_partition=cross_partition,
            description=description,
            notes=notes,
        )

    def _parse_record_kind(self) -> ir.RecordKind:
        """Parse RecordKind (INTENT, FACT, OBSERVATION, DERIVATION)."""
        token = self.current_token()

        if self.match(TokenType.INTENT):
            self.advance()
            return ir.RecordKind.INTENT
        elif self.match(TokenType.FACT):
            self.advance()
            return ir.RecordKind.FACT
        elif self.match(TokenType.OBSERVATION):
            self.advance()
            return ir.RecordKind.OBSERVATION
        elif self.match(TokenType.DERIVATION):
            self.advance()
            return ir.RecordKind.DERIVATION
        elif self.match(TokenType.IDENTIFIER):
            # Handle case-insensitive matching
            value = token.value.upper()
            self.advance()
            if value == "INTENT":
                return ir.RecordKind.INTENT
            elif value == "FACT":
                return ir.RecordKind.FACT
            elif value == "OBSERVATION":
                return ir.RecordKind.OBSERVATION
            elif value == "DERIVATION":
                return ir.RecordKind.DERIVATION
            else:
                self.error(
                    f"Invalid record kind '{token.value}'. "
                    f"Must be INTENT, FACT, OBSERVATION, or DERIVATION."
                )
        else:
            self.error("Expected record kind (INTENT, FACT, OBSERVATION, DERIVATION)")

        # Unreachable, but needed for type checker
        return ir.RecordKind.FACT

    def _parse_stream_schema(self) -> ir.StreamSchema:
        """Parse a schema definition within a stream.

        DSL syntax:
            schema OrderPlaced:
              order_id: uuid required
              total_amount: money required
        """
        self.expect(TokenType.SCHEMA)
        name = self.expect(TokenType.IDENTIFIER).value

        # Check for version suffix (e.g., OrderPlaced@v2)
        version = "v1"
        if self.match(TokenType.IDENTIFIER) and self.current_token().value.startswith("@"):
            version = self.advance().value[1:]  # Remove @ prefix

        fields: list[ir.FieldSpec] = []
        extends: str | None = None
        compatibility = ir.SchemaCompatibility.ADDITIVE
        description: str | None = None

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # extends: ParentSchema@v1
            if self.match(TokenType.EXTENDS):
                self.advance()
                self.expect(TokenType.COLON)
                extends = self.expect(TokenType.IDENTIFIER).value
                if self.match(TokenType.IDENTIFIER) and self.current_token().value.startswith("@"):
                    extends += self.advance().value

            # compatibility: additive | breaking
            elif self.match(TokenType.IDENTIFIER) and self.current_token().value == "compatibility":
                self.advance()
                self.expect(TokenType.COLON)
                compat_value = self.expect(TokenType.IDENTIFIER).value.lower()
                if compat_value == "breaking":
                    compatibility = ir.SchemaCompatibility.BREAKING
                else:
                    compatibility = ir.SchemaCompatibility.ADDITIVE

            # description: "..."
            elif self.match(TokenType.DESCRIPTION):
                self.advance()
                self.expect(TokenType.COLON)
                description = self.expect(TokenType.STRING).value

            # field_name: type modifiers
            # Note: field names may be keywords (e.g., 'currency' in v0.5 ledgers)
            elif self.match(TokenType.IDENTIFIER) or self._is_keyword_as_identifier():
                field = self._parse_schema_field()
                fields.append(field)

            else:
                self.advance()

            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.StreamSchema(
            name=name,
            version=version,
            fields=fields,
            extends=extends,
            compatibility=compatibility,
            description=description,
        )

    def _parse_schema_field(self) -> ir.FieldSpec:
        """Parse a field within a schema."""
        # Field names may be keywords (e.g., 'currency' in v0.5 ledgers)
        field_name = self.expect_identifier_or_keyword().value
        self.expect(TokenType.COLON)

        # Parse type
        type_spec = self.parse_type_spec()

        # Parse modifiers (required, optional, etc.) and default value
        modifiers, default_value = self.parse_field_modifiers()

        # Build FieldSpec
        return ir.FieldSpec(
            name=field_name,
            type=type_spec,
            modifiers=modifiers,
            default=default_value,
        )

    def _parse_idempotency(self) -> ir.IdempotencyStrategy:
        """Parse idempotency block.

        DSL syntax:
            idempotency:
              type: deterministic_id
              field: record_id
              derivation: "hash(stream, natural_key, t_event)"
        """
        self.expect(TokenType.IDEMPOTENCY)
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        strategy_type = ir.IdempotencyType.DETERMINISTIC_ID
        field = "record_id"
        derivation: str | None = None
        window: str | None = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # Handle 'type:' - IDENTIFIER since 'type' isn't a keyword
            if self.match(TokenType.IDENTIFIER) and self.current_token().value == "type":
                self.advance()
                self.expect(TokenType.COLON)
                type_value = self.expect_identifier_or_keyword().value.lower()
                if type_value == "deterministic_id":
                    strategy_type = ir.IdempotencyType.DETERMINISTIC_ID
                elif type_value == "content_hash":
                    strategy_type = ir.IdempotencyType.CONTENT_HASH
                elif type_value == "external_dedup":
                    strategy_type = ir.IdempotencyType.EXTERNAL_DEDUP
                elif type_value == "dedupe_window":
                    strategy_type = ir.IdempotencyType.DEDUPE_WINDOW

            # Handle 'field:' - FIELD is a keyword token
            elif self.match(TokenType.FIELD):
                self.advance()
                self.expect(TokenType.COLON)
                field = self.expect_identifier_or_keyword().value

            # Handle 'derivation:' - IDENTIFIER
            elif self.match(TokenType.IDENTIFIER) and self.current_token().value == "derivation":
                self.advance()
                self.expect(TokenType.COLON)
                derivation = self.expect(TokenType.STRING).value

            # Handle 'window:' - IDENTIFIER
            elif self.match(TokenType.IDENTIFIER) and self.current_token().value == "window":
                self.advance()
                self.expect(TokenType.COLON)
                if self.match(TokenType.STRING):
                    window = self.advance().value
                else:
                    window = self.expect_identifier_or_keyword().value

            else:
                self.advance()

            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.IdempotencyStrategy(
            strategy_type=strategy_type,
            field=field,
            derivation=derivation,
            window=window,
        )

    def _parse_outcomes(self) -> list[ir.ExpectedOutcome]:
        """Parse outcomes block for INTENT streams.

        DSL syntax:
            outcomes:
              success:
                emits OrderPlaced from order_facts
              failure:
                emits OrderPlacementRejected from order_facts
        """
        self.expect(TokenType.OUTCOMES)
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        outcomes: list[ir.ExpectedOutcome] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # success: / failure: / timeout: / partial:
            if (
                self.match(TokenType.IDENTIFIER)
                or self.match(TokenType.SUCCEEDED)
                or self.match(TokenType.FAILED)
            ):
                condition_str = self.advance().value.lower()

                # Map to OutcomeCondition
                if condition_str in ("success", "succeeded"):
                    condition = ir.OutcomeCondition.SUCCESS
                elif condition_str in ("failure", "failed"):
                    condition = ir.OutcomeCondition.FAILURE
                elif condition_str == "timeout":
                    condition = ir.OutcomeCondition.TIMEOUT
                elif condition_str == "partial":
                    condition = ir.OutcomeCondition.PARTIAL
                else:
                    # Skip unknown
                    continue

                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)

                emits: list[str] = []
                target_stream: str | None = None

                while not self.match(TokenType.DEDENT):
                    self.skip_newlines()
                    if self.match(TokenType.DEDENT):
                        break

                    # emits SchemaName from stream_name
                    if self.match(TokenType.EMITS):
                        self.advance()
                        schema_name = self.expect(TokenType.IDENTIFIER).value
                        emits.append(schema_name)

                        if self.match(TokenType.FROM):
                            self.advance()
                            target_stream = self.expect(TokenType.IDENTIFIER).value
                    else:
                        self.advance()

                    self.skip_newlines()

                self.expect(TokenType.DEDENT)

                outcomes.append(
                    ir.ExpectedOutcome(
                        condition=condition,
                        emits=emits,
                        target_stream=target_stream,
                    )
                )
            else:
                self.advance()

            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return outcomes

    def _parse_lineage(self) -> ir.DerivationLineage:
        """Parse derives_from block for DERIVATION streams.

        DSL syntax:
            derives_from:
              streams: [order_facts, payment_facts]
              type: aggregate
              rebuild: full_replay
              window: "1 day tumbling"
        """
        self.expect(TokenType.DERIVES_FROM)
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        source_streams: list[str] = []
        derivation_type = ir.DerivationType.AGGREGATE
        rebuild_strategy = ir.RebuildStrategy.FULL_REPLAY
        window_spec: ir.WindowSpec | None = None
        derivation_function: str | None = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # Check for 'streams:' key
            if self.match(TokenType.IDENTIFIER) and self.current_token().value == "streams":
                self.advance()
                self.expect(TokenType.COLON)
                source_streams = self._parse_hless_list()

            # Handle 'type:' key - note: type value may be a keyword (AGGREGATE)
            elif self.match(TokenType.IDENTIFIER) and self.current_token().value == "type":
                self.advance()
                self.expect(TokenType.COLON)
                # Type value could be AGGREGATE keyword or IDENTIFIER
                type_value = self.expect_identifier_or_keyword().value.lower()
                derivation_type = ir.DerivationType(type_value)

            # Handle 'rebuild:' key
            elif self.match(TokenType.IDENTIFIER) and self.current_token().value == "rebuild":
                self.advance()
                self.expect(TokenType.COLON)
                rebuild_value = self.expect_identifier_or_keyword().value.lower()
                rebuild_strategy = ir.RebuildStrategy(rebuild_value)

            # Handle 'window:' key
            elif self.match(TokenType.IDENTIFIER) and self.current_token().value == "window":
                self.advance()
                self.expect(TokenType.COLON)
                if self.match(TokenType.STRING):
                    window_str = self.advance().value
                    # Parse window string like "1 day tumbling"
                    window_spec = self._parse_window_spec_string(window_str)
                else:
                    # Might be a block
                    self.skip_newlines()
                    if self.match(TokenType.INDENT):
                        window_spec = self._parse_window_spec_block()

            # Handle 'function:' key
            elif self.match(TokenType.IDENTIFIER) and self.current_token().value == "function":
                self.advance()
                self.expect(TokenType.COLON)
                derivation_function = self.expect(TokenType.STRING).value

            else:
                self.advance()

            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.DerivationLineage(
            source_streams=source_streams,
            derivation_type=derivation_type,
            rebuild_strategy=rebuild_strategy,
            window_spec=window_spec,
            derivation_function=derivation_function,
        )

    def _parse_window_spec_string(self, window_str: str) -> ir.WindowSpec:
        """Parse a window spec from a string like '1 day tumbling'."""
        parts = window_str.lower().split()

        # Default values
        window_type = ir.WindowType.TUMBLING
        size = window_str

        # Try to extract window type from the string
        for part in parts:
            if part == "tumbling":
                window_type = ir.WindowType.TUMBLING
                size = window_str.replace("tumbling", "").strip()
            elif part == "sliding":
                window_type = ir.WindowType.SLIDING
                size = window_str.replace("sliding", "").strip()
            elif part == "session":
                window_type = ir.WindowType.SESSION
                size = window_str.replace("session", "").strip()

        return ir.WindowSpec(type=window_type, size=size)

    def _parse_window_spec_block(self) -> ir.WindowSpec:
        """Parse a window spec block."""
        self.expect(TokenType.INDENT)

        window_type = ir.WindowType.TUMBLING
        size = "1 day"
        grace_period: str | None = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.IDENTIFIER):
                key = self.current_token().value

                if key == "type":
                    self.advance()
                    self.expect(TokenType.COLON)
                    type_value = self.expect(TokenType.IDENTIFIER).value.lower()
                    window_type = ir.WindowType(type_value)

                elif key == "size":
                    self.advance()
                    self.expect(TokenType.COLON)
                    if self.match(TokenType.STRING):
                        size = self.advance().value
                    else:
                        size = self.expect(TokenType.IDENTIFIER).value

                elif key == "grace_period":
                    self.advance()
                    self.expect(TokenType.COLON)
                    if self.match(TokenType.STRING):
                        grace_period = self.advance().value
                    else:
                        grace_period = self.expect(TokenType.IDENTIFIER).value

                else:
                    self.advance()
            else:
                self.advance()

            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.WindowSpec(type=window_type, size=size, grace_period=grace_period)

    def _parse_side_effects(self) -> ir.SideEffectPolicy:
        """Parse side_effects block.

        DSL syntax:
            side_effects:
              allowed: false

            side_effects:
              allowed: true
              effects: [send_email, publish_notification]
        """
        self.expect(TokenType.SIDE_EFFECTS)
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        external_effects_allowed = False
        allowed_effects: list[str] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.ALLOWED) or (
                self.match(TokenType.IDENTIFIER) and self.current_token().value == "allowed"
            ):
                self.advance()
                self.expect(TokenType.COLON)
                if self.match(TokenType.TRUE):
                    self.advance()
                    external_effects_allowed = True
                elif self.match(TokenType.FALSE):
                    self.advance()
                    external_effects_allowed = False
                else:
                    val = self.expect(TokenType.IDENTIFIER).value
                    external_effects_allowed = val.lower() == "true"

            elif self.match(TokenType.IDENTIFIER) and self.current_token().value == "effects":
                self.advance()
                self.expect(TokenType.COLON)
                allowed_effects = self._parse_hless_list()

            else:
                self.advance()

            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.SideEffectPolicy(
            external_effects_allowed=external_effects_allowed,
            allowed_effects=allowed_effects,
        )

    def _parse_hless_list(self) -> list[str]:
        """Parse a list of identifiers or strings: [a, b, c] or inline.

        Note: Named _parse_hless_list to avoid collision with ScenarioParserMixin._parse_string_list
        """
        items: list[str] = []

        if self.match(TokenType.LBRACKET):
            self.advance()
            while not self.match(TokenType.RBRACKET):
                if self.match(TokenType.STRING):
                    items.append(self.advance().value)
                elif self.match(TokenType.IDENTIFIER):
                    items.append(self.advance().value)
                else:
                    # Handle keywords that might appear as values
                    items.append(self.expect_identifier_or_keyword().value)
                if self.match(TokenType.COMMA):
                    self.advance()
            self.expect(TokenType.RBRACKET)
        else:
            # Single item
            if self.match(TokenType.STRING):
                items.append(self.advance().value)
            elif self.match(TokenType.IDENTIFIER):
                items.append(self.advance().value)
            else:
                items.append(self.expect_identifier_or_keyword().value)

        return items

    # =========================================================================
    # HLESS Pragma Parsing
    # =========================================================================

    def parse_hless_pragma(self) -> ir.HLESSPragma:
        """Parse @hless pragma.

        DSL syntax:
            @hless strict
            @hless warn
            @hless off  # Strongly discouraged
        """
        # @ symbol would be handled by lexer, we just expect "hless"
        self.expect(TokenType.HLESS)

        mode = ir.HLESSMode.STRICT
        reason: str | None = None

        if self.match(TokenType.STRICT):
            self.advance()
            mode = ir.HLESSMode.STRICT
        elif self.match(TokenType.WARN):
            self.advance()
            mode = ir.HLESSMode.WARN
        elif self.match(TokenType.OFF):
            self.advance()
            mode = ir.HLESSMode.OFF
        elif self.match(TokenType.IDENTIFIER):
            mode_value = self.advance().value.lower()
            if mode_value == "strict":
                mode = ir.HLESSMode.STRICT
            elif mode_value == "warn":
                mode = ir.HLESSMode.WARN
            elif mode_value == "off":
                mode = ir.HLESSMode.OFF

        # Optional reason for non-strict mode
        if self.match(TokenType.STRING):
            reason = self.advance().value

        return ir.HLESSPragma(mode=mode, reason=reason)
