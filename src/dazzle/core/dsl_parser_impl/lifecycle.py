"""Parser for the `lifecycle:` block inside an entity declaration (ADR-0020).

See docs/superpowers/plans/2026-04-13-lifecycle-evidence-predicates-plan.md
for the full design.

The `lifecycle:` block is orthogonal to the (auto-derived) state_machine on
EntitySpec. It captures progress ordering + per-transition evidence predicates
that the fitness methodology's progress_evaluator consumes to distinguish
motion from actual work.

Expected DSL shape:

    lifecycle:
      status_field: status
      states:
        - new         (order: 0)
        - in_progress (order: 1)
        - resolved    (order: 2)
      transitions:
        - from: new
          to: in_progress
          evidence: true
          role: support_agent
        - from: in_progress
          to: resolved
          evidence: resolution_notes != null
          roles: [support_agent, manager]
"""

from typing import TYPE_CHECKING, Any

from ..errors import make_parse_error
from ..ir.lifecycle import LifecycleSpec, LifecycleStateSpec, LifecycleTransitionSpec
from ..lexer import TokenType

if TYPE_CHECKING:
    from .base import BaseParser


def parse_lifecycle_block(parser: "BaseParser") -> LifecycleSpec:
    """Parse a `lifecycle:` block body.

    The caller must have already consumed the `lifecycle` token and its
    trailing `:` colon. This function handles the block body starting at
    the first NEWLINE/INDENT.
    """
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)

    status_field: str | None = None
    states: list[LifecycleStateSpec] = []
    transitions: list[LifecycleTransitionSpec] = []

    while not parser.match(TokenType.DEDENT):
        parser.skip_newlines()
        if parser.match(TokenType.DEDENT):
            break

        key = parser.expect_identifier_or_keyword().value
        parser.expect(TokenType.COLON)

        if key == "status_field":
            status_field = parser.expect_identifier_or_keyword().value
            parser.skip_newlines()

        elif key == "states":
            parser.skip_newlines()
            parser.expect(TokenType.INDENT)
            while not parser.match(TokenType.DEDENT):
                parser.skip_newlines()
                if parser.match(TokenType.DEDENT):
                    break
                states.append(_parse_state_entry(parser))
                parser.skip_newlines()
            parser.expect(TokenType.DEDENT)
            parser.skip_newlines()

        elif key == "transitions":
            parser.skip_newlines()
            parser.expect(TokenType.INDENT)
            while not parser.match(TokenType.DEDENT):
                parser.skip_newlines()
                if parser.match(TokenType.DEDENT):
                    break
                transitions.append(_parse_transition_entry(parser))
                parser.skip_newlines()
            parser.expect(TokenType.DEDENT)
            parser.skip_newlines()

        else:
            token = parser.current_token()
            raise make_parse_error(
                f"Unknown key `{key}` in lifecycle: block "
                "(expected one of: status_field, states, transitions)",
                parser.file,
                token.line,
                token.column,
            )

    parser.expect(TokenType.DEDENT)

    if status_field is None:
        token = parser.current_token()
        raise make_parse_error(
            "lifecycle: block missing required `status_field`",
            parser.file,
            token.line,
            token.column,
        )
    if not states:
        token = parser.current_token()
        raise make_parse_error(
            "lifecycle: block missing required `states`",
            parser.file,
            token.line,
            token.column,
        )

    return LifecycleSpec(
        status_field=status_field,
        states=states,
        transitions=transitions,
    )


def _parse_state_entry(parser: "BaseParser") -> LifecycleStateSpec:
    """Parse one `- <name> (order: N)` entry."""
    if not parser.match(TokenType.MINUS):
        token = parser.current_token()
        raise make_parse_error(
            "expected `-` at start of lifecycle state entry",
            parser.file,
            token.line,
            token.column,
        )
    parser.advance()

    name = parser.expect_identifier_or_keyword().value

    parser.expect(TokenType.LPAREN)
    meta_key = parser.expect_identifier_or_keyword().value
    if meta_key != "order":
        token = parser.current_token()
        raise make_parse_error(
            f"lifecycle state `{name}`: expected `order:` metadata, got `{meta_key}`",
            parser.file,
            token.line,
            token.column,
        )
    parser.expect(TokenType.COLON)
    order_tok = parser.expect(TokenType.NUMBER)
    try:
        order = int(order_tok.value)
    except (TypeError, ValueError) as exc:
        raise make_parse_error(
            f"lifecycle state `{name}`: order must be a non-negative integer, "
            f"got `{order_tok.value}`",
            parser.file,
            order_tok.line,
            order_tok.column,
        ) from exc
    parser.expect(TokenType.RPAREN)

    return LifecycleStateSpec(name=name, order=order)


def _parse_transition_entry(parser: "BaseParser") -> LifecycleTransitionSpec:
    """Parse one `- from: X / to: Y / evidence: ... / role(s): ...` entry.

    The first key lives on the same line as the leading `-`. The remaining
    keys are on indented continuation lines; the lexer emits INDENT/DEDENT
    around them.
    """
    if not parser.match(TokenType.MINUS):
        token = parser.current_token()
        raise make_parse_error(
            "expected `-` at start of lifecycle transition entry",
            parser.file,
            token.line,
            token.column,
        )
    parser.advance()

    state: dict[str, Any] = {
        "from": None,
        "to": None,
        "evidence": None,
        "roles": [],
    }

    # First key/value on the same line as the bullet.
    _parse_transition_kv(parser, state)
    parser.skip_newlines()

    # Subsequent keys come on indented continuation lines.
    if parser.match(TokenType.INDENT):
        parser.advance()
        while not parser.match(TokenType.DEDENT):
            parser.skip_newlines()
            if parser.match(TokenType.DEDENT):
                break
            _parse_transition_kv(parser, state)
            parser.skip_newlines()
        parser.expect(TokenType.DEDENT)

    if state["from"] is None or state["to"] is None:
        token = parser.current_token()
        raise make_parse_error(
            "lifecycle transition missing `from` or `to`",
            parser.file,
            token.line,
            token.column,
        )

    return LifecycleTransitionSpec(
        from_state=state["from"],
        to_state=state["to"],
        evidence=state["evidence"],
        roles=list(state["roles"]),
    )


def _parse_transition_kv(parser: "BaseParser", state: dict[str, Any]) -> None:
    """Parse one `<key>: <value>` line inside a transition entry."""
    # `from`, `to`, and `role` are reserved keywords, so we match them
    # by token type instead of using expect_identifier_or_keyword (which
    # would reject them).
    if parser.match(TokenType.FROM):
        parser.advance()
        parser.expect(TokenType.COLON)
        state["from"] = parser.expect_identifier_or_keyword().value
        return
    if parser.match(TokenType.TO):
        parser.advance()
        parser.expect(TokenType.COLON)
        state["to"] = parser.expect_identifier_or_keyword().value
        return
    if parser.match(TokenType.ROLE):
        parser.advance()
        parser.expect(TokenType.COLON)
        state["roles"].append(parser.expect_identifier_or_keyword().value)
        return

    key = parser.expect_identifier_or_keyword().value
    parser.expect(TokenType.COLON)

    if key == "evidence":
        # Evidence is a predicate expression; collect the remainder of the
        # line verbatim. A future pass will plug the scope-rule predicate
        # parser in for full semantic validation (plan task 4+).
        text = parser._collect_line_text()  # type: ignore[attr-defined]
        state["evidence"] = text if text else None
    elif key == "roles":
        # `roles: [a, b, c]`
        parser.expect(TokenType.LBRACKET)
        while not parser.match(TokenType.RBRACKET):
            state["roles"].append(parser.expect_identifier_or_keyword().value)
            if parser.match(TokenType.COMMA):
                parser.advance()
        parser.expect(TokenType.RBRACKET)
    else:
        token = parser.current_token()
        raise make_parse_error(
            f"unknown transition key `{key}` (expected: from, to, evidence, role, roles)",
            parser.file,
            token.line,
            token.column,
        )
