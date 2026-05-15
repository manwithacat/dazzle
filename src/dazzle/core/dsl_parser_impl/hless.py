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

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, NoReturn

from .. import ir
from ..lexer import TokenType
from .dispatch import KeywordParser, parse_block_with_dispatch


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

        def error(self, message: str) -> NoReturn: ...

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

        state = _StreamState()
        parse_block_with_dispatch(
            self,
            first_class_keywords=_STREAM_KEYWORDS,
            ident_keywords=_STREAM_IDENT_KEYWORDS,
            state=state,
            on_unknown=_on_unknown_stream,
        )
        self.expect(TokenType.DEDENT)
        return _build_stream(self, name, state)

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
                field = self._parse_field_spec()  # type: ignore[attr-defined]  # mixin method from TypeParserMixin
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


# ============================================================ #
# parse_stream — keyword-dispatch decomposition (#1098 template) #
# ============================================================ #
#
# The 215-line monolith was replaced (v0.70.15) with the dispatch
# pattern shipped in #1097. Each former branch is a small ``_kw_*``
# free function below; the post-loop required-field validation +
# TimeSemantics build + default-idempotency injection live in
# :func:`_build_stream`.


@dataclass
class _StreamState:
    """Accumulator for :meth:`HLESSParserMixin.parse_stream`.

    One field per legal keyword in a ``stream:`` block, mirroring the
    locals of the legacy monolith. Required-field assertions and IR
    assembly happen in :func:`_build_stream` post-loop.
    """

    # Required
    record_kind: ir.RecordKind | None = None
    partition_key: str | None = None
    ordering_scope: str | None = None
    t_event_field: str | None = None
    # Time fields (defaulted)
    t_log_field: str = "_t_log"
    t_process_field: str | None = None
    # Optional
    idempotency: ir.IdempotencyStrategy | None = None
    schemas: list[ir.StreamSchema] = field(default_factory=list)
    invariants: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    causality_fields: list[str] = field(
        default_factory=lambda: ["trace_id", "causation_id", "correlation_id"]
    )
    side_effect_policy: ir.SideEffectPolicy = field(default_factory=ir.SideEffectPolicy)
    expected_outcomes: list[ir.ExpectedOutcome] | None = None
    lineage: ir.DerivationLineage | None = None
    description: str | None = None
    cross_partition: bool = False


# ---------- Token-keyed keyword parsers ---------- #


def _kw_kind(parser: Any, state: _StreamState) -> None:
    """``kind: INTENT | FACT | OBSERVATION | DERIVATION``"""
    parser.advance()
    parser.expect(TokenType.COLON)
    state.record_kind = parser._parse_record_kind()


def _kw_description(parser: Any, state: _StreamState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.description = parser.expect(TokenType.STRING).value


def _kw_schema(parser: Any, state: _StreamState) -> None:
    """``schema SchemaName: ...`` — appended to ``state.schemas``."""
    state.schemas.append(parser._parse_stream_schema())


def _kw_partition_key(parser: Any, state: _StreamState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.partition_key = parser.expect(TokenType.IDENTIFIER).value


def _kw_ordering_scope(parser: Any, state: _StreamState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.ordering_scope = parser.expect(TokenType.IDENTIFIER).value


def _kw_t_event(parser: Any, state: _StreamState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.t_event_field = parser.expect(TokenType.IDENTIFIER).value


def _kw_t_log(parser: Any, state: _StreamState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.t_log_field = parser.expect(TokenType.IDENTIFIER).value


def _kw_t_process(parser: Any, state: _StreamState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.t_process_field = parser.expect(TokenType.IDENTIFIER).value


def _kw_idempotency(parser: Any, state: _StreamState) -> None:
    state.idempotency = parser._parse_idempotency()


def _kw_invariant(parser: Any, state: _StreamState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.invariants.append(parser.expect(TokenType.STRING).value)


def _kw_note(parser: Any, state: _StreamState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.notes.append(parser.expect(TokenType.STRING).value)


def _kw_outcomes(parser: Any, state: _StreamState) -> None:
    state.expected_outcomes = parser._parse_outcomes()


def _kw_derives_from(parser: Any, state: _StreamState) -> None:
    state.lineage = parser._parse_lineage()


def _kw_side_effects(parser: Any, state: _StreamState) -> None:
    state.side_effect_policy = parser._parse_side_effects()


# ---------- IDENT-text-matched parsers ---------- #
#
# These keywords are not lexer tokens — they're matched on the
# IDENTIFIER value, mirroring the original monolith.


def _kw_causality_fields(parser: Any, state: _StreamState) -> None:
    """``causality_fields: [trace_id, causation_id, correlation_id]``"""
    parser.advance()
    parser.expect(TokenType.COLON)
    state.causality_fields = parser._parse_hless_list()


def _kw_cross_partition(parser: Any, state: _StreamState) -> None:
    """``cross_partition: true|false`` — bool flag (#984)."""
    parser.advance()
    parser.expect(TokenType.COLON)
    if parser.match(TokenType.TRUE):
        parser.advance()
        state.cross_partition = True
    elif parser.match(TokenType.FALSE):
        parser.advance()
        state.cross_partition = False
    else:
        # Assume identifier "true" or "false" (tolerant of lexer mode where
        # `true`/`false` come through as plain IDENTIFIERs).
        val = parser.expect(TokenType.IDENTIFIER).value
        state.cross_partition = val.lower() == "true"


# ---------- Dispatch tables ---------- #


_STREAM_KEYWORDS: dict[TokenType, KeywordParser[_StreamState]] = {
    TokenType.KIND: _kw_kind,
    TokenType.DESCRIPTION: _kw_description,
    TokenType.SCHEMA: _kw_schema,
    TokenType.PARTITION_KEY: _kw_partition_key,
    TokenType.ORDERING_SCOPE: _kw_ordering_scope,
    TokenType.T_EVENT: _kw_t_event,
    TokenType.T_LOG: _kw_t_log,
    TokenType.T_PROCESS: _kw_t_process,
    TokenType.IDEMPOTENCY: _kw_idempotency,
    TokenType.INVARIANT: _kw_invariant,
    TokenType.NOTE: _kw_note,
    TokenType.OUTCOMES: _kw_outcomes,
    TokenType.DERIVES_FROM: _kw_derives_from,
    TokenType.SIDE_EFFECTS: _kw_side_effects,
}


_STREAM_IDENT_KEYWORDS: dict[str, KeywordParser[_StreamState]] = {
    "causality_fields": _kw_causality_fields,
    "cross_partition": _kw_cross_partition,
}


def _on_unknown_stream(parser: Any) -> None:
    """Silently skip unknown keywords inside a ``stream:`` block.

    Mirrors the legacy ``else: self.advance()`` branch — forward-compat
    tolerance for additions to the grammar that older parsers don't yet
    recognise. The loop's top-of-iteration ``skip_newlines()`` cleans
    up after this on the next pass.
    """
    parser.advance()


# ---------- Post-loop builder ---------- #


def _build_stream(parser: Any, name: str, state: _StreamState) -> ir.StreamSpec:
    """Build the :class:`ir.StreamSpec` from the accumulated state.

    Required-field validation + TimeSemantics assembly + default
    idempotency injection — all mirrored from the legacy post-loop tail.
    """
    if state.record_kind is None:
        parser.error("Stream must specify 'kind: INTENT|FACT|OBSERVATION|DERIVATION'")
    if state.partition_key is None:
        parser.error("Stream must specify 'partition_key'")
    if state.ordering_scope is None:
        parser.error("Stream must specify 'ordering_scope'")
    if state.t_event_field is None:
        parser.error("Stream must specify 't_event' (domain occurrence time field)")
    # parser.error is NoReturn but `parser` is typed Any here, so re-narrow
    # for mypy after the four checks above.
    assert state.record_kind is not None
    assert state.partition_key is not None
    assert state.ordering_scope is not None
    assert state.t_event_field is not None

    time_semantics = ir.TimeSemantics(
        t_event_field=state.t_event_field,
        t_log_field=state.t_log_field,
        t_process_field=state.t_process_field,
    )

    idempotency = state.idempotency
    if idempotency is None:
        idempotency = ir.get_default_idempotency(state.record_kind)

    return ir.StreamSpec(
        name=name,
        record_kind=state.record_kind,
        schemas=state.schemas,
        partition_key=state.partition_key,
        ordering_scope=state.ordering_scope,
        time_semantics=time_semantics,
        idempotency=idempotency,
        causality_fields=state.causality_fields,
        invariants=state.invariants,
        side_effect_policy=state.side_effect_policy,
        expected_outcomes=state.expected_outcomes,
        lineage=state.lineage,
        cross_partition=state.cross_partition,
        description=state.description,
        notes=state.notes,
    )
