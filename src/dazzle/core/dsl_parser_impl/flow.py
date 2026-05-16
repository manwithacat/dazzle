"""
E2E flow parsing for DAZZLE DSL.

Handles E2E flow test declarations including preconditions, steps, and assertions.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .. import ir
from ..errors import make_parse_error
from ..lexer import TokenType
from .dispatch import KeywordParser, parse_block_with_dispatch


class FlowParserMixin:
    """
    Mixin providing E2E flow parsing.

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

    def parse_flow(self) -> ir.FlowSpec:
        """Parse an E2E ``flow <name> ["Description"]:`` declaration.

        Refactored to dispatch-table style (follow-on to #1098). 4 outer
        keyword branches (priority/tags/preconditions/steps). The
        ``priority`` keyword has dual identity — it tokenises as
        :class:`TokenType.PRIORITY` in some contexts and as a plain
        IDENTIFIER (value ``priority``) in others. Both routes dispatch
        to the same :func:`_f_kw_priority` parser via overlapping entries
        in the token-keyed and IDENT-keyed tables.

        Syntax::

            flow flow_name "Flow Description":
              priority: high|medium|low
              tags: tag1, tag2
              preconditions:
                authenticated: true
                user_role: admin
                view: task_list
              steps:
                navigate view:task_list
                fill field:Task.title "Test Value"
                click action:Task.save
                wait 1000
        """
        self.expect(TokenType.FLOW)

        name = self.expect(TokenType.IDENTIFIER).value
        description: str | None = None
        if self.match(TokenType.STRING):
            description = self.advance().value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        state = _FlowState()
        parse_block_with_dispatch(
            self,
            first_class_keywords=_FLOW_KEYWORDS,
            ident_keywords=_FLOW_IDENT_KEYWORDS,
            state=state,
            on_unknown=_on_unknown_flow,
        )
        self.expect(TokenType.DEDENT)
        return _build_flow(name, description, state)

    def parse_flow_preconditions(self) -> ir.FlowPrecondition:
        """Parse flow preconditions block."""
        authenticated = False
        user_role: str | None = None
        view: str | None = None
        fixtures: list[str] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # authenticated: true|false
            if self.match(TokenType.AUTHENTICATED):
                self.advance()
                self.expect(TokenType.COLON)
                if self.match(TokenType.TRUE):
                    self.advance()
                    authenticated = True
                elif self.match(TokenType.FALSE):
                    self.advance()
                    authenticated = False
                self.skip_newlines()

            # user_role: role_name
            elif self.match(TokenType.USER_ROLE):
                self.advance()
                self.expect(TokenType.COLON)
                user_role = self.expect(TokenType.IDENTIFIER).value
                self.skip_newlines()

            # view: view_name
            elif self.match(TokenType.VIEW):
                self.advance()
                self.expect(TokenType.COLON)
                view = self.expect(TokenType.IDENTIFIER).value
                self.skip_newlines()

            # fixtures: fixture1, fixture2
            elif self.match(TokenType.FIXTURES):
                self.advance()
                self.expect(TokenType.COLON)
                fixture = self.expect(TokenType.IDENTIFIER).value
                fixtures.append(fixture)
                while self.match(TokenType.COMMA):
                    self.advance()
                    fixture = self.expect(TokenType.IDENTIFIER).value
                    fixtures.append(fixture)
                self.skip_newlines()

            else:
                self.advance()

        return ir.FlowPrecondition(
            authenticated=authenticated,
            user_role=user_role,
            view=view,
            fixtures=fixtures,
        )

    def parse_flow_step(self) -> ir.FlowStep:
        """Parse a single flow step."""
        # navigate view:target
        if self.match(TokenType.NAVIGATE):
            self.advance()
            target = self.parse_semantic_target()
            return ir.FlowStep(kind=ir.FlowStepKind.NAVIGATE, target=target)

        # fill field:target "value" | fill field:target fixture_ref
        elif self.match(TokenType.FILL):
            self.advance()
            target = self.parse_semantic_target()
            value: str | None = None
            fixture_ref: str | None = None
            if self.match(TokenType.STRING):
                value = self.advance().value
            elif self.match(TokenType.IDENTIFIER):
                # Could be a fixture reference like Task_valid.title
                fixture_ref = self.advance().value
                if self.match(TokenType.DOT):
                    self.advance()
                    field = self.expect(TokenType.IDENTIFIER).value
                    fixture_ref = f"{fixture_ref}.{field}"
            return ir.FlowStep(
                kind=ir.FlowStepKind.FILL,
                target=target,
                value=value,
                fixture_ref=fixture_ref,
            )

        # click action:target
        elif self.match(TokenType.CLICK):
            self.advance()
            target = self.parse_semantic_target()
            return ir.FlowStep(kind=ir.FlowStepKind.CLICK, target=target)

        # wait 1000 | wait view:target
        elif self.match(TokenType.WAIT):
            self.advance()
            if self.match(TokenType.NUMBER):
                value = self.advance().value
                return ir.FlowStep(kind=ir.FlowStepKind.WAIT, value=value)
            else:
                target = self.parse_semantic_target()
                return ir.FlowStep(kind=ir.FlowStepKind.WAIT, target=target)

        # snapshot
        elif self.match(TokenType.SNAPSHOT):
            self.advance()
            return ir.FlowStep(kind=ir.FlowStepKind.SNAPSHOT)

        # assert assertion_kind target [expected]
        elif self.match(TokenType.EXPECT):
            self.advance()
            assertion = self.parse_flow_assertion()
            return ir.FlowStep(kind=ir.FlowStepKind.ASSERT, assertion=assertion)

        else:
            token = self.current_token()
            raise make_parse_error(
                f"Expected flow step (navigate, fill, click, wait, snapshot, expect), "
                f"got {token.type.value}",
                self.file,
                token.line,
                token.column,
            )

    def parse_semantic_target(self) -> str:
        """Parse a semantic target like view:task_list or field:Task.title."""
        # Format: type:identifier or type:Entity.field
        # target_type can be keywords like 'view', 'field', 'action', 'entity', 'row'
        target_type = self.expect_identifier_or_keyword().value
        self.expect(TokenType.COLON)
        identifier = self.expect_identifier_or_keyword().value

        # Check for dotted notation (Entity.field)
        if self.match(TokenType.DOT):
            self.advance()
            field = self.expect_identifier_or_keyword().value
            identifier = f"{identifier}.{field}"

        return f"{target_type}:{identifier}"

    def parse_flow_assertion(self) -> ir.FlowAssertion:
        """Parse a flow assertion."""
        # entity_exists Entity [where field=value]
        if self.match(TokenType.ENTITY_EXISTS):
            self.advance()
            entity = self.expect(TokenType.IDENTIFIER).value
            expected: dict[str, Any] | None = None
            if self.match(TokenType.WHERE):
                self.advance()
                expected = {}
                field = self.expect(TokenType.IDENTIFIER).value
                self.expect(TokenType.EQUALS)
                value = self.parse_value()
                expected[field] = value
            return ir.FlowAssertion(
                kind=ir.FlowAssertionKind.ENTITY_EXISTS,
                target=f"entity:{entity}",
                expected=expected,
            )

        # entity_not_exists Entity
        elif self.match(TokenType.ENTITY_NOT_EXISTS):
            self.advance()
            entity = self.expect(TokenType.IDENTIFIER).value
            return ir.FlowAssertion(
                kind=ir.FlowAssertionKind.ENTITY_NOT_EXISTS,
                target=f"entity:{entity}",
            )

        # validation_error field:Target.field
        elif self.match(TokenType.VALIDATION_ERROR):
            self.advance()
            target = self.parse_semantic_target()
            return ir.FlowAssertion(
                kind=ir.FlowAssertionKind.VALIDATION_ERROR,
                target=target,
            )

        # visible view:target | visible field:target
        elif self.match(TokenType.VISIBLE):
            self.advance()
            target = self.parse_semantic_target()
            return ir.FlowAssertion(
                kind=ir.FlowAssertionKind.VISIBLE,
                target=target,
            )

        # not_visible target
        elif self.match(TokenType.NOT_VISIBLE):
            self.advance()
            target = self.parse_semantic_target()
            return ir.FlowAssertion(
                kind=ir.FlowAssertionKind.NOT_VISIBLE,
                target=target,
            )

        # text_contains "expected text"
        elif self.match(TokenType.TEXT_CONTAINS):
            self.advance()
            expected_text = self.expect(TokenType.STRING).value
            return ir.FlowAssertion(
                kind=ir.FlowAssertionKind.TEXT_CONTAINS,
                expected=expected_text,
            )

        # redirects_to view:target
        elif self.match(TokenType.REDIRECTS_TO):
            self.advance()
            target = self.parse_semantic_target()
            return ir.FlowAssertion(
                kind=ir.FlowAssertionKind.REDIRECTS_TO,
                target=target,
            )

        # field_value field:target "expected"
        elif self.match(TokenType.FIELD_VALUE):
            self.advance()
            target = self.parse_semantic_target()
            expected_value = self.parse_value()
            return ir.FlowAssertion(
                kind=ir.FlowAssertionKind.FIELD_VALUE,
                target=target,
                expected=expected_value,
            )

        # count entity:Entity 5
        elif self.match(TokenType.COUNT):
            self.advance()
            target = self.parse_semantic_target()
            expected_count = int(self.expect(TokenType.NUMBER).value)
            return ir.FlowAssertion(
                kind=ir.FlowAssertionKind.COUNT,
                target=target,
                expected=expected_count,
            )

        else:
            token = self.current_token()
            raise make_parse_error(
                f"Expected assertion kind, got {token.type.value}",
                self.file,
                token.line,
                token.column,
            )


# ============================================================ #
# parse_flow — keyword-dispatch decomposition (#1098 template)  #
# ============================================================ #
#
# The 118-line monolith was replaced (v0.70.29) with the dispatch
# pattern shipped in #1097. 4 outer branches (priority/tags/
# preconditions/steps) routed through _FLOW_KEYWORDS and the
# IDENT-text-matched override for ``priority`` (which can appear
# as a lexer keyword OR a plain identifier depending on context).


_FLOW_PRIORITY_MAP = {
    "high": ir.FlowPriority.HIGH,
    "medium": ir.FlowPriority.MEDIUM,
    "low": ir.FlowPriority.LOW,
}


@dataclass
class _FlowState:
    """Accumulator for :meth:`FlowParserMixin.parse_flow`."""

    priority: ir.FlowPriority = ir.FlowPriority.MEDIUM
    tags: list[str] = field(default_factory=list)
    preconditions: ir.FlowPrecondition | None = None
    steps: list[ir.FlowStep] = field(default_factory=list)


# ---------- Keyword parsers ---------- #


def _f_kw_priority(parser: Any, state: _FlowState) -> None:
    """``priority: high|medium|low`` — validated.

    Routed to from both ``TokenType.PRIORITY`` and IDENT-text ``priority``
    so the legacy dual-tokenisation path is preserved.
    """
    parser.advance()
    parser.expect(TokenType.COLON)
    priority_token = parser.expect_identifier_or_keyword()
    priority_value = priority_token.value.lower()
    mapped = _FLOW_PRIORITY_MAP.get(priority_value)
    if mapped is None:
        raise make_parse_error(
            f"Expected priority (high, medium, low), got {priority_value}",
            parser.file,
            priority_token.line,
            priority_token.column,
        )
    state.priority = mapped
    parser.skip_newlines()


def _f_kw_tags(parser: Any, state: _FlowState) -> None:
    """``tags: tag1, tag2, ...`` — comma-separated identifier list."""
    parser.advance()
    parser.expect(TokenType.COLON)
    state.tags.append(parser.expect(TokenType.IDENTIFIER).value)
    while parser.match(TokenType.COMMA):
        parser.advance()
        state.tags.append(parser.expect(TokenType.IDENTIFIER).value)
    parser.skip_newlines()


def _f_kw_preconditions(parser: Any, state: _FlowState) -> None:
    """``preconditions:`` — nested block delegating to the mixin helper."""
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)
    state.preconditions = parser.parse_flow_preconditions()
    parser.expect(TokenType.DEDENT)


def _f_kw_steps(parser: Any, state: _FlowState) -> None:
    """``steps:`` — indented list of flow steps (navigate/fill/click/wait/...)."""
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)
    while not parser.match(TokenType.DEDENT):
        parser.skip_newlines()
        if parser.match(TokenType.DEDENT):
            break
        state.steps.append(parser.parse_flow_step())
        parser.skip_newlines()
    parser.expect(TokenType.DEDENT)


# ---------- Dispatch tables + on_unknown + builder ---------- #


_FLOW_KEYWORDS: dict[TokenType, KeywordParser[_FlowState]] = {
    TokenType.PRIORITY: _f_kw_priority,
    TokenType.TAGS: _f_kw_tags,
    TokenType.PRECONDITIONS: _f_kw_preconditions,
    TokenType.STEPS: _f_kw_steps,
}


_FLOW_IDENT_KEYWORDS: dict[str, KeywordParser[_FlowState]] = {
    # 'priority' may also tokenise as a plain IDENTIFIER depending on
    # the lexer's mode — same dispatch fn handles both routes.
    "priority": _f_kw_priority,
}


def _on_unknown_flow(parser: Any) -> None:
    """Silently skip unknown tokens (mirrors legacy ``else: self.advance()``)."""
    parser.advance()


def _build_flow(name: str, description: str | None, state: _FlowState) -> ir.FlowSpec:
    return ir.FlowSpec(
        id=name,
        description=description,
        priority=state.priority,
        preconditions=state.preconditions,
        steps=state.steps,
        tags=state.tags,
    )
