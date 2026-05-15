"""
Test parsing for DAZZLE DSL.

Handles test and assertion declarations for API contract tests.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .. import ir
from ..errors import make_parse_error
from ..lexer import TokenType
from .dispatch import KeywordParser, parse_block_with_dispatch


class TestParserMixin:
    """
    Mixin providing test parsing.

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
        parse_value: Any

    def parse_test(self) -> ir.TestSpec:
        """Parse a ``test:`` declaration.

        Refactored to dispatch-table style (follow-on to #1098). Body is
        a header parse → ``parse_block_with_dispatch`` → ``_build_test``
        builder. The 7 outer keyword branches (setup / action / data /
        filter / search / order_by / expect) and the nested expect-loop
        assertion dispatch all live as module-level free functions.
        """
        self.expect(TokenType.TEST)
        name = self.expect(TokenType.IDENTIFIER).value
        description: str | None = None
        if self.match(TokenType.STRING):
            description = self.advance().value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        state = _TestState()
        parse_block_with_dispatch(
            self,
            first_class_keywords=_TEST_KEYWORDS,
            state=state,
            on_unknown=_on_unknown_test,
        )
        self.expect(TokenType.DEDENT)
        return _build_test(self, name, description, state)

    def parse_comparison_operator(self, op_str: str) -> ir.TestComparisonOperator:
        """Parse comparison operator string to enum."""
        op_map = {
            "equals": ir.TestComparisonOperator.EQUALS,
            "not_equals": ir.TestComparisonOperator.NOT_EQUALS,
            "greater_than": ir.TestComparisonOperator.GREATER_THAN,
            "less_than": ir.TestComparisonOperator.LESS_THAN,
            "contains": ir.TestComparisonOperator.CONTAINS,
            "not_contains": ir.TestComparisonOperator.NOT_CONTAINS,
        }
        if op_str not in op_map:
            raise make_parse_error(
                f"Unknown comparison operator: {op_str}",
                self.file,
                self.current_token().line,
                self.current_token().column,
            )
        return op_map[op_str]


# ============================================================ #
# parse_test — keyword-dispatch decomposition (#1098 template)  #
# ============================================================ #
#
# The 344-line monolith was replaced (v0.70.16) with the dispatch
# pattern shipped in #1097. The 7 outer branches (setup / action /
# data / filter / search / order_by / expect) become ``_kw_*`` free
# functions; the nested expect-loop's 7 assertion types become
# ``_assertion_*`` functions dispatched from inside ``_kw_expect``.
# Post-loop action-data merge + required-action check live in
# :func:`_build_test`.


@dataclass
class _TestState:
    """Accumulator for :meth:`TestParserMixin.parse_test`.

    One field per legal outer keyword in a ``test:`` block. The
    post-loop ``_build_test`` merges ``data`` into ``action`` and
    raises if ``action`` is still ``None``.
    """

    setup_steps: list[ir.TestSetupStep] = field(default_factory=list)
    action: ir.TestAction | None = None
    data: dict[str, Any] = field(default_factory=dict)
    filter_data: dict[str, Any] = field(default_factory=dict)
    assertions: list[ir.TestAssertion] = field(default_factory=list)


# ---------- Outer-block keyword parsers ---------- #


def _kw_setup(parser: Any, state: _TestState) -> None:
    """``setup:`` block — ``var: create Entity with field=value, ...`` lines."""
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)

    while not parser.match(TokenType.DEDENT):
        parser.skip_newlines()
        if parser.match(TokenType.DEDENT):
            break

        var_name = parser.expect_identifier_or_keyword().value
        parser.expect(TokenType.COLON)
        parser.expect(TokenType.CREATE)
        entity_name = parser.expect_identifier_or_keyword().value
        parser.expect(TokenType.WITH)

        step_data: dict[str, Any] = {}
        field_name = parser.expect_identifier_or_keyword().value
        parser.expect(TokenType.EQUALS)
        step_data[field_name] = parser.parse_value()

        while parser.match(TokenType.COMMA):
            parser.advance()
            field_name = parser.expect_identifier_or_keyword().value
            parser.expect(TokenType.EQUALS)
            step_data[field_name] = parser.parse_value()

        state.setup_steps.append(
            ir.TestSetupStep(
                variable_name=var_name,
                action=ir.TestActionKind.CREATE,
                entity_name=entity_name,
                data=step_data,
            )
        )
        parser.skip_newlines()

    parser.expect(TokenType.DEDENT)


_ACTION_KIND_TOKENS: dict[TokenType, ir.TestActionKind] = {
    TokenType.CREATE: ir.TestActionKind.CREATE,
    TokenType.UPDATE: ir.TestActionKind.UPDATE,
    TokenType.DELETE: ir.TestActionKind.DELETE,
    TokenType.GET: ir.TestActionKind.GET,
}


def _kw_action(parser: Any, state: _TestState) -> None:
    """``action: create|update|delete|get <target>``"""
    parser.advance()
    parser.expect(TokenType.COLON)

    action_token = parser.current_token()
    kind = _ACTION_KIND_TOKENS.get(action_token.type)
    if kind is None:
        raise make_parse_error(
            f"Expected action kind (create, update, delete, get), got {action_token.type.value}",
            parser.file,
            action_token.line,
            action_token.column,
        )
    parser.advance()
    target = parser.expect_identifier_or_keyword().value
    # Final ``data`` merge happens in _build_test once the data block has run.
    state.action = ir.TestAction(kind=kind, target=target, data={})
    parser.skip_newlines()


def _kw_data(parser: Any, state: _TestState) -> None:
    """``data:`` block — ``field: value`` lines for the action payload."""
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
        state.data[field_name] = parser.parse_value()
        parser.skip_newlines()

    parser.expect(TokenType.DEDENT)


def _kw_filter(parser: Any, state: _TestState) -> None:
    """``filter:`` block — ``field: value`` lines used to identify the target row."""
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
        state.filter_data[field_name] = parser.parse_value()
        parser.skip_newlines()

    parser.expect(TokenType.DEDENT)


def _kw_search(parser: Any, state: _TestState) -> None:
    """``search:`` block — currently parses ``query: <value>`` then discards.

    Behaviour preserved from the legacy monolith: the parsed value is not
    yet wired into the IR. Future work could route it through ``state``.
    """
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)

    parser.expect(TokenType.QUERY)
    parser.expect(TokenType.COLON)
    parser.parse_value()  # discarded — see docstring

    parser.skip_newlines()
    parser.expect(TokenType.DEDENT)


def _kw_order_by(parser: Any, state: _TestState) -> None:
    """``order_by: <value>`` — parsed and discarded (legacy behaviour)."""
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.parse_value()  # discarded — see _kw_search
    parser.skip_newlines()


def _kw_expect(parser: Any, state: _TestState) -> None:
    """``expect:`` block — nested dispatch on assertion type."""
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)

    while not parser.match(TokenType.DEDENT):
        parser.skip_newlines()
        if parser.match(TokenType.DEDENT):
            break

        tok = parser.current_token()
        fn = _ASSERTION_DISPATCH.get(tok.type)
        if fn is not None:
            fn(parser, state)
        else:
            # Mirrors the legacy fall-through: no advance, no append — the
            # loop's top-of-iteration skip_newlines will move past the token
            # on the next pass if it's a newline, otherwise expect(DEDENT)
            # will catch a truly unknown token.
            pass
        parser.skip_newlines()

    parser.expect(TokenType.DEDENT)


# ---------- Assertion-type parsers (inner dispatch) ---------- #


def _assertion_status(parser: Any, state: _TestState) -> None:
    """``status: <identifier>`` (the legacy IDENTIFIER-only constraint)."""
    parser.advance()
    parser.expect(TokenType.COLON)
    status_value = parser.expect(TokenType.IDENTIFIER).value
    state.assertions.append(
        ir.TestAssertion(kind=ir.TestAssertionKind.STATUS, expected_value=status_value)
    )


def _assertion_created(parser: Any, state: _TestState) -> None:
    """``created: true|false``"""
    parser.advance()
    parser.expect(TokenType.COLON)
    if parser.match(TokenType.TRUE):
        parser.advance()
        created_value = True
    elif parser.match(TokenType.FALSE):
        parser.advance()
        created_value = False
    else:
        tok = parser.current_token()
        raise make_parse_error(
            f"Expected true or false, got {tok.type.value}",
            parser.file,
            tok.line,
            tok.column,
        )
    state.assertions.append(
        ir.TestAssertion(kind=ir.TestAssertionKind.CREATED, expected_value=created_value)
    )


def _assertion_field(parser: Any, state: _TestState) -> None:
    """``field <name> <op> <value>`` OR ``field <name> <op> field <other>``."""
    parser.advance()
    field_name = parser.expect_identifier_or_keyword().value
    operator_token = parser.expect(TokenType.IDENTIFIER)
    operator = parser.parse_comparison_operator(operator_token.value)

    if parser.match(TokenType.FIELD):
        parser.advance()
        other_field = parser.expect_identifier_or_keyword().value
        expected_value: Any = f"field.{other_field}"
    else:
        expected_value = parser.parse_value()

    state.assertions.append(
        ir.TestAssertion(
            kind=ir.TestAssertionKind.FIELD,
            field_name=field_name,
            operator=operator,
            expected_value=expected_value,
        )
    )


def _assertion_error_message(parser: Any, state: _TestState) -> None:
    """``error_message <op> <value>``"""
    parser.advance()
    operator_token = parser.expect(TokenType.IDENTIFIER)
    operator = parser.parse_comparison_operator(operator_token.value)
    expected_value = parser.parse_value()
    state.assertions.append(
        ir.TestAssertion(
            kind=ir.TestAssertionKind.ERROR,
            operator=operator,
            expected_value=expected_value,
        )
    )


def _assertion_count(parser: Any, state: _TestState) -> None:
    """``count <op> <value>``"""
    parser.advance()
    operator_token = parser.expect(TokenType.IDENTIFIER)
    operator = parser.parse_comparison_operator(operator_token.value)
    expected_value = parser.parse_value()
    state.assertions.append(
        ir.TestAssertion(
            kind=ir.TestAssertionKind.COUNT,
            operator=operator,
            expected_value=expected_value,
        )
    )


def _assertion_first(parser: Any, state: _TestState) -> None:
    """``first field <name> <op> <value>`` — namespaces field as ``first.<name>``."""
    parser.advance()
    parser.expect(TokenType.FIELD)
    field_name = parser.expect_identifier_or_keyword().value
    operator_token = parser.expect(TokenType.IDENTIFIER)
    operator = parser.parse_comparison_operator(operator_token.value)
    expected_value = parser.parse_value()
    state.assertions.append(
        ir.TestAssertion(
            kind=ir.TestAssertionKind.FIELD,
            field_name=f"first.{field_name}",
            operator=operator,
            expected_value=expected_value,
        )
    )


def _assertion_last(parser: Any, state: _TestState) -> None:
    """``last field <name> <op> <value>`` — namespaces field as ``last.<name>``."""
    parser.advance()
    parser.expect(TokenType.FIELD)
    field_name = parser.expect_identifier_or_keyword().value
    operator_token = parser.expect(TokenType.IDENTIFIER)
    operator = parser.parse_comparison_operator(operator_token.value)
    expected_value = parser.parse_value()
    state.assertions.append(
        ir.TestAssertion(
            kind=ir.TestAssertionKind.FIELD,
            field_name=f"last.{field_name}",
            operator=operator,
            expected_value=expected_value,
        )
    )


_ASSERTION_DISPATCH: dict[TokenType, KeywordParser[_TestState]] = {
    TokenType.STATUS: _assertion_status,
    TokenType.CREATED: _assertion_created,
    TokenType.FIELD: _assertion_field,
    TokenType.ERROR_MESSAGE: _assertion_error_message,
    TokenType.COUNT: _assertion_count,
    TokenType.FIRST: _assertion_first,
    TokenType.LAST: _assertion_last,
}


# ---------- Outer dispatch tables + unknown handler ---------- #


_TEST_KEYWORDS: dict[TokenType, KeywordParser[_TestState]] = {
    TokenType.SETUP: _kw_setup,
    TokenType.ACTION: _kw_action,
    TokenType.DATA: _kw_data,
    TokenType.FILTER: _kw_filter,
    TokenType.SEARCH: _kw_search,
    TokenType.ORDER_BY: _kw_order_by,
    TokenType.EXPECT: _kw_expect,
}


def _on_unknown_test(parser: Any) -> None:
    """Silently skip unknown outer keywords (mirrors legacy ``else: self.advance()``)."""
    parser.advance()


# ---------- Post-loop builder ---------- #


def _build_test(parser: Any, name: str, description: str | None, state: _TestState) -> ir.TestSpec:
    """Merge action data + assert required action, build :class:`ir.TestSpec`.

    The legacy monolith rebuilt ``action`` post-loop with the accumulated
    ``data`` dict. We do the same so the test's payload lives on
    ``action.data`` rather than as a sibling field.
    """
    action = state.action
    if action is not None:
        action = ir.TestAction(kind=action.kind, target=action.target, data=state.data)

    if action is None:
        tok = parser.current_token()
        raise make_parse_error(
            f"Test {name} must have an action",
            parser.file,
            tok.line,
            tok.column,
        )

    return ir.TestSpec(
        name=name,
        description=description,
        setup_steps=state.setup_steps,
        action=action,
        assertions=state.assertions,
    )
