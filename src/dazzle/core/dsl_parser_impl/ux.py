"""
UX semantic layer parsing for DAZZLE DSL.

Handles UX block parsing including attention signals, persona variants,
and surface-level UX specifications.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .. import ir
from ..errors import make_parse_error
from ..lexer import TokenType
from .dispatch import KeywordParser, parse_block_with_dispatch


class UXParserMixin:
    """
    Mixin providing UX semantic layer parsing.

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
        parse_condition_expr: Any

    def parse_ux_block(self) -> ir.UXSpec:
        """
        Parse UX block within a surface.

        Syntax:
            ux:
              purpose: "..."
              show: field1, field2
              sort: field1 desc, field2 asc
              filter: field1, field2
              search: field1, field2
              empty: "..."
              attention critical:
                when: condition
                message: "..."
                action: surface_name
              for persona_name:
                scope: ...
                ...
        """
        self.expect(TokenType.UX)
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        purpose = None
        show: list[str] = []
        sort: list[ir.SortSpec] = []
        filter_fields: list[str] = []
        search_fields: list[str] = []
        empty_message: str | ir.EmptyMessages | None = None
        search_first = False
        attention_signals: list[ir.AttentionSignal] = []
        persona_variants: list[ir.PersonaVariant] = []
        bulk_actions: list[ir.BulkActionSpec] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # purpose: "..."
            if self.match(TokenType.PURPOSE):
                self.advance()
                self.expect(TokenType.COLON)
                purpose = self.expect(TokenType.STRING).value
                self.skip_newlines()

            # show: field1, field2
            elif self.match(TokenType.SHOW):
                self.advance()
                self.expect(TokenType.COLON)
                show = self.parse_field_list()
                self.skip_newlines()

            # sort: field1 desc, field2 asc
            elif self.match(TokenType.SORT):
                self.advance()
                self.expect(TokenType.COLON)
                sort = self.parse_sort_list()
                self.skip_newlines()

            # filter: field1, field2
            elif self.match(TokenType.FILTER):
                self.advance()
                self.expect(TokenType.COLON)
                filter_fields = self.parse_field_list()
                self.skip_newlines()

            # search: field1, field2
            elif self.match(TokenType.SEARCH):
                self.advance()
                self.expect(TokenType.COLON)
                search_fields = self.parse_field_list()
                self.skip_newlines()

            # empty: "..."     (legacy form — single string)
            # empty:            (block form, #807 — typed per-case)
            #   collection: "..."
            #   filtered: "..."
            #   forbidden: "..."
            elif self.match(TokenType.EMPTY):
                self.advance()
                self.expect(TokenType.COLON)
                # Peek: STRING → legacy; NEWLINE → block form.
                if self.match(TokenType.STRING):
                    empty_message = self.expect(TokenType.STRING).value
                    self.skip_newlines()
                else:
                    empty_message = self.parse_empty_messages_block()

            # search_first: true|false
            elif self.match(TokenType.SEARCH_FIRST):
                self.advance()
                self.expect(TokenType.COLON)
                if self.match(TokenType.TRUE):
                    self.advance()
                    search_first = True
                elif self.match(TokenType.FALSE):
                    self.advance()
                    search_first = False
                else:
                    token = self.current_token()
                    raise make_parse_error(
                        f"Expected true or false, got {token.type.value}",
                        self.file,
                        token.line,
                        token.column,
                    )
                self.skip_newlines()

            # attention critical/warning/notice/info:
            elif self.match(TokenType.ATTENTION):
                signal = self.parse_attention_signal()
                attention_signals.append(signal)

            # as <persona>: persona variant inside ux block. Renamed
            # from `for <persona>:`.
            elif self.match(TokenType.AS):
                variant = self.parse_persona_variant()
                persona_variants.append(variant)

            # bulk_actions: indented block mapping action_name → field -> value
            elif self.match(TokenType.IDENTIFIER) and self.current_token().value == "bulk_actions":
                bulk_actions = self.parse_bulk_actions_block()

            else:
                break

        self.expect(TokenType.DEDENT)

        return ir.UXSpec(
            purpose=purpose,
            show=show,
            sort=sort,
            filter=filter_fields,
            search=search_fields,
            empty_message=empty_message,
            search_first=search_first,
            attention_signals=attention_signals,
            persona_variants=persona_variants,
            bulk_actions=bulk_actions,
        )

    def parse_empty_messages_block(self) -> ir.EmptyMessages:
        """Parse the block form of the ``empty:`` directive (#807).

        Syntax::

            empty:
              collection: "No X yet."
              filtered: "No X match the current filters."
              forbidden: "You can't see any X with your current role."

        Any sub-key may be omitted; omitted cases fall back to the
        framework default in ``fragments/empty_state.html``. Unknown
        sub-keys raise a parse error so typos don't silently drop.
        """
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        collection: str | None = None
        filtered: str | None = None
        forbidden: str | None = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            key_tok = self.expect_identifier_or_keyword()
            key = key_tok.value
            self.expect(TokenType.COLON)
            value = self.expect(TokenType.STRING).value
            self.skip_newlines()

            if key == "collection":
                collection = value
            elif key == "filtered":
                filtered = value
            elif key == "forbidden":
                forbidden = value
            else:
                raise make_parse_error(
                    f"Unknown empty: sub-key {key!r}. Valid keys: collection, filtered, forbidden.",
                    self.file,
                    key_tok.line,
                    key_tok.column,
                )

        self.expect(TokenType.DEDENT)
        return ir.EmptyMessages(collection=collection, filtered=filtered, forbidden=forbidden)

    def parse_bulk_actions_block(self) -> list[ir.BulkActionSpec]:
        """Parse the ``bulk_actions:`` sub-block of a ux: block (#785).

        Syntax:
            bulk_actions:
              accept: status -> active
              reject: status -> rejected

        Each child line is ``<action_name>: <field> -> <value>`` where
        ``value`` may be an identifier, quoted string, ``true``/``false``,
        or numeric literal. Empty blocks raise a parse error to keep the
        config intentional.
        """
        self.advance()  # consume 'bulk_actions' identifier
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        actions: list[ir.BulkActionSpec] = []
        block_line = self.current_token().line
        block_column = self.current_token().column

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            name_tok = self.expect_identifier_or_keyword()
            action_name = name_tok.value
            self.expect(TokenType.COLON)

            field_tok = self.expect_identifier_or_keyword()
            field_name = field_tok.value

            # Accept either `->` or two tokens ARROW-like. The lexer emits
            # ARROW for `->` in other contexts — reuse it here.
            if self.match(TokenType.ARROW):
                self.advance()
            else:
                token = self.current_token()
                raise make_parse_error(
                    f"Expected '->' in bulk_actions entry, got {token.value!r}",
                    self.file,
                    token.line,
                    token.column,
                )

            # Target value: string literal, identifier, keyword, or bool
            if self.match(TokenType.STRING):
                target_value = self.current_token().value
                self.advance()
            elif self.match(TokenType.TRUE):
                target_value = "true"
                self.advance()
            elif self.match(TokenType.FALSE):
                target_value = "false"
                self.advance()
            else:
                target_value = self.expect_identifier_or_keyword().value

            actions.append(
                ir.BulkActionSpec(
                    name=action_name,
                    field=field_name,
                    target_value=str(target_value),
                )
            )
            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        if not actions:
            raise make_parse_error(
                "bulk_actions: block must declare at least one action",
                self.file,
                block_line,
                block_column,
            )

        return actions

    def parse_field_list(self) -> list[str]:
        """Parse comma-separated list of field names."""
        fields = [self.expect_identifier_or_keyword().value]

        while self.match(TokenType.COMMA):
            self.advance()
            fields.append(self.expect_identifier_or_keyword().value)

        return fields

    def parse_sort_list(self) -> list[ir.SortSpec]:
        """Parse comma-separated list of sort expressions (field [asc|desc])."""
        sorts = []

        field = self.expect_identifier_or_keyword().value
        direction = "asc"
        if self.match(TokenType.ASC):
            self.advance()
            direction = "asc"
        elif self.match(TokenType.DESC):
            self.advance()
            direction = "desc"
        sorts.append(ir.SortSpec(field=field, direction=direction))

        while self.match(TokenType.COMMA):
            self.advance()
            field = self.expect_identifier_or_keyword().value
            direction = "asc"
            if self.match(TokenType.ASC):
                self.advance()
                direction = "asc"
            elif self.match(TokenType.DESC):
                self.advance()
                direction = "desc"
            sorts.append(ir.SortSpec(field=field, direction=direction))

        return sorts

    def parse_attention_signal(self) -> ir.AttentionSignal:
        """
        Parse attention signal block.

        Syntax:
            attention critical:
              when: condition_expr
              message: "..."
              action: surface_name
        """
        self.expect(TokenType.ATTENTION)

        # Parse signal level
        if self.match(TokenType.CRITICAL):
            level = ir.SignalLevel.CRITICAL
            self.advance()
        elif self.match(TokenType.WARNING):
            level = ir.SignalLevel.WARNING
            self.advance()
        elif self.match(TokenType.NOTICE):
            level = ir.SignalLevel.NOTICE
            self.advance()
        elif self.match(TokenType.INFO):
            level = ir.SignalLevel.INFO
            self.advance()
        else:
            token = self.current_token()
            raise make_parse_error(
                f"Expected signal level (critical/warning/notice/info), got {token.type.value}",
                self.file,
                token.line,
                token.column,
            )

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        condition = None
        message = None
        action = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # when: condition_expr
            if self.match(TokenType.WHEN):
                self.advance()
                self.expect(TokenType.COLON)
                condition = self.parse_condition_expr()
                self.skip_newlines()

            # message: "..."
            elif self.match(TokenType.MESSAGE):
                self.advance()
                self.expect(TokenType.COLON)
                message = self.expect(TokenType.STRING).value
                self.skip_newlines()

            # action: surface_name
            elif self.match(TokenType.ACTION):
                self.advance()
                self.expect(TokenType.COLON)
                action = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            else:
                break

        self.expect(TokenType.DEDENT)

        if condition is None:
            token = self.current_token()
            raise make_parse_error(
                "Attention signal requires 'when:' condition",
                self.file,
                token.line,
                token.column,
            )

        if message is None:
            token = self.current_token()
            raise make_parse_error(
                "Attention signal requires 'message:'",
                self.file,
                token.line,
                token.column,
            )

        return ir.AttentionSignal(
            level=level,
            condition=condition,
            message=message,
            action=action,
        )

    def parse_persona_variant(self) -> ir.PersonaVariant:
        """Parse an ``as <persona>:`` persona variant block.

        Refactored to dispatch-table style (follow-on to #1098). Body is
        a header parse → ``parse_block_with_dispatch`` → ``_build_persona_variant``
        builder. The 10 keyword branches (scope/purpose/show/hide/
        show_aggregate/action_primary/read_only/defaults/focus/empty)
        live as ``_pv_kw_*`` module-level free functions.

        Syntax::

            as persona_name:
              scope: all | condition_expr
              purpose: "..."
              show: field1, field2
              hide: field1, field2
              show_aggregate: metric1, metric2
              action_primary: surface_name
              read_only: true|false
              empty: "..."
        """
        self.expect(TokenType.AS)
        persona = self.expect_identifier_or_keyword().value
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        state = _PersonaVariantState()
        parse_block_with_dispatch(
            self,
            first_class_keywords=_PERSONA_VARIANT_KEYWORDS,
            state=state,
        )
        self.expect(TokenType.DEDENT)
        return _build_persona_variant(persona, state)


# ================================================================ #
# parse_persona_variant — keyword-dispatch decomposition (#1098 template) #
# ================================================================ #
#
# The 161-line monolith was replaced (v0.70.18) with the dispatch
# pattern shipped in #1097. Each former branch is a small ``_pv_kw_*``
# free function below; the IR assembly lives in :func:`_build_persona_variant`.
# Unknown keywords fall through to the dispatch helper's default —
# strictly better diagnostics than the legacy ``else: break`` +
# ``expect(DEDENT)`` produced.


@dataclass
class _PersonaVariantState:
    """Accumulator for :meth:`UXParserMixin.parse_persona_variant`.

    One field per legal keyword in an ``as <persona>:`` block.
    """

    scope: ir.ConditionExpr | None = None
    scope_all: bool = False
    purpose: str | None = None
    show: list[str] = field(default_factory=list)
    hide: list[str] = field(default_factory=list)
    show_aggregate: list[str] = field(default_factory=list)
    action_primary: str | None = None
    read_only: bool = False
    defaults: dict[str, Any] = field(default_factory=dict)
    focus: list[str] = field(default_factory=list)
    empty_message: str | None = None


# ---------- Keyword parsers ---------- #


def _pv_kw_scope(parser: Any, state: _PersonaVariantState) -> None:
    """``scope: all`` OR ``scope: <condition_expr>``"""
    parser.advance()
    parser.expect(TokenType.COLON)
    if parser.match(TokenType.ALL):
        parser.advance()
        state.scope_all = True
    else:
        state.scope = parser.parse_condition_expr()
    parser.skip_newlines()


def _pv_kw_purpose(parser: Any, state: _PersonaVariantState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.purpose = parser.expect(TokenType.STRING).value
    parser.skip_newlines()


def _pv_kw_show(parser: Any, state: _PersonaVariantState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.show = parser.parse_field_list()
    parser.skip_newlines()


def _pv_kw_hide(parser: Any, state: _PersonaVariantState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.hide = parser.parse_field_list()
    parser.skip_newlines()


def _pv_kw_show_aggregate(parser: Any, state: _PersonaVariantState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.show_aggregate = parser.parse_field_list()
    parser.skip_newlines()


def _pv_kw_action_primary(parser: Any, state: _PersonaVariantState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.action_primary = parser.expect_identifier_or_keyword().value
    parser.skip_newlines()


def _pv_kw_read_only(parser: Any, state: _PersonaVariantState) -> None:
    """``read_only: true|false``"""
    parser.advance()
    parser.expect(TokenType.COLON)
    if parser.match(TokenType.TRUE):
        parser.advance()
        state.read_only = True
    elif parser.match(TokenType.FALSE):
        parser.advance()
        state.read_only = False
    else:
        token = parser.current_token()
        raise make_parse_error(
            f"Expected true or false, got {token.type.value}",
            parser.file,
            token.line,
            token.column,
        )
    parser.skip_newlines()


def _pv_kw_defaults(parser: Any, state: _PersonaVariantState) -> None:
    """``defaults:`` block — ``field_name: <STRING | IDENT>`` lines.

    Identifier values like ``current_user`` are common — that's why we
    accept either STRING or IDENT for each field's value.
    """
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)
    while not parser.match(TokenType.DEDENT):
        parser.skip_newlines()
        if parser.match(TokenType.DEDENT):
            break
        field_name = parser.expect_identifier_or_keyword().value
        parser.expect(TokenType.COLON)
        if parser.match(TokenType.STRING):
            state.defaults[field_name] = parser.advance().value
        else:
            state.defaults[field_name] = parser.expect_identifier_or_keyword().value
        parser.skip_newlines()
    parser.expect(TokenType.DEDENT)


def _pv_kw_focus(parser: Any, state: _PersonaVariantState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.focus = parser.parse_field_list()
    parser.skip_newlines()


def _pv_kw_empty(parser: Any, state: _PersonaVariantState) -> None:
    """``empty: "<msg>"`` — per-persona empty-state copy override (closes EX-046)."""
    parser.advance()
    parser.expect(TokenType.COLON)
    state.empty_message = parser.expect(TokenType.STRING).value
    parser.skip_newlines()


# ---------- Dispatch table + builder ---------- #


_PERSONA_VARIANT_KEYWORDS: dict[TokenType, KeywordParser[_PersonaVariantState]] = {
    TokenType.SCOPE: _pv_kw_scope,
    TokenType.PURPOSE: _pv_kw_purpose,
    TokenType.SHOW: _pv_kw_show,
    TokenType.HIDE: _pv_kw_hide,
    TokenType.SHOW_AGGREGATE: _pv_kw_show_aggregate,
    TokenType.ACTION_PRIMARY: _pv_kw_action_primary,
    TokenType.READ_ONLY: _pv_kw_read_only,
    TokenType.DEFAULTS: _pv_kw_defaults,
    TokenType.FOCUS: _pv_kw_focus,
    TokenType.EMPTY: _pv_kw_empty,
}


def _build_persona_variant(persona: str, state: _PersonaVariantState) -> ir.PersonaVariant:
    """Construct the frozen :class:`ir.PersonaVariant` from accumulated state."""
    return ir.PersonaVariant(
        persona=persona,
        scope=state.scope,
        scope_all=state.scope_all,
        purpose=state.purpose,
        show=state.show,
        hide=state.hide,
        show_aggregate=state.show_aggregate,
        action_primary=state.action_primary,
        read_only=state.read_only,
        defaults=state.defaults,
        focus=state.focus,
        empty_message=state.empty_message,
    )
