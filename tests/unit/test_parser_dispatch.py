"""Tests for the keyword-dispatch helper (#1088a).

Exercises ``parse_block_with_dispatch`` against synthetic mini-parsers
so the helper's contract is locked independent of any one production
parser. Uses real ``Lexer`` token streams so the integration with the
existing tokenizer is verified end-to-end.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl.base import BaseParser
from dazzle.core.dsl_parser_impl.dispatch import (
    KeywordParser,
    parse_block_with_dispatch,
)
from dazzle.core.errors import ParseError
from dazzle.core.lexer import Lexer, TokenType

# ---------------------------------------------------------------------------
# Synthetic parser — minimal harness exercising the helper.
# ---------------------------------------------------------------------------


@dataclass
class _ToyState:
    """Accumulator for a synthetic three-keyword block."""

    name: str | None = None
    tags: list[str] = field(default_factory=list)
    enabled: bool = True


def _kw_name(parser, state: _ToyState) -> None:
    parser.advance()  # consume DESCRIPTION (we reuse it as our "name:" keyword)
    parser.expect(TokenType.COLON)
    state.name = parser.expect(TokenType.STRING).value
    parser.skip_newlines()


def _kw_tags(parser, state: _ToyState) -> None:
    parser.advance()  # consume GOALS (reused as "tags:")
    parser.expect(TokenType.COLON)
    state.tags = [parser.expect(TokenType.STRING).value]
    while parser.match(TokenType.COMMA):
        parser.advance()
        state.tags.append(parser.expect(TokenType.STRING).value)
    parser.skip_newlines()


def _kw_enabled_via_ident(parser, state: _ToyState) -> None:
    """Identifier-text-matched keyword."""
    parser.advance()
    parser.expect(TokenType.COLON)
    if parser.match(TokenType.TRUE):
        parser.advance()
        state.enabled = True
    elif parser.match(TokenType.FALSE):
        parser.advance()
        state.enabled = False
    parser.skip_newlines()


_FIRST_CLASS: dict[TokenType, KeywordParser] = {
    TokenType.DESCRIPTION: _kw_name,
    TokenType.GOALS: _kw_tags,
}
_IDENT_KW: dict[str, KeywordParser] = {
    "enabled": _kw_enabled_via_ident,
}


def _parse_toy_block(text: str) -> _ToyState:
    """Parse a 'persona' header + dispatch-driven body, ignoring the header."""
    tokens = Lexer(text, file=Path("<test>")).tokenize()
    parser = BaseParser(tokens, file=Path("<test>"))
    # Skip the synthetic `persona x "X":` header to land at INDENT.
    parser.expect(TokenType.PERSONA)
    parser.advance()  # ident
    if parser.match(TokenType.STRING):
        parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)

    state = _ToyState()
    parse_block_with_dispatch(
        parser,
        first_class_keywords=_FIRST_CLASS,
        ident_keywords=_IDENT_KW,
        state=state,
    )
    parser.expect(TokenType.DEDENT)
    return state


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_dispatches_first_class_keyword() -> None:
    state = _parse_toy_block('persona x "X":\n  description: "Alice"\n')
    assert state.name == "Alice"


def test_dispatches_identifier_keyword() -> None:
    state = _parse_toy_block('persona x "X":\n  enabled: false\n')
    assert state.enabled is False


def test_dispatches_multiple_keywords_in_one_block() -> None:
    state = _parse_toy_block(
        'persona x "X":\n  description: "Alice"\n  goals: "a", "b", "c"\n  enabled: true\n'
    )
    assert state.name == "Alice"
    assert state.tags == ["a", "b", "c"]
    assert state.enabled is True


def test_state_defaults_apply_when_keyword_absent() -> None:
    state = _parse_toy_block('persona x "X":\n  description: "Alice"\n')
    # Defaults from _ToyState definition.
    assert state.tags == []
    assert state.enabled is True


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_unknown_keyword_raises_parse_error() -> None:
    """Unknown keyword in block raises with the offending name in the message."""
    with pytest.raises(ParseError) as exc:
        _parse_toy_block('persona x "X":\n  unknown_thing: "value"\n')
    assert "unknown_thing" in str(exc.value).lower() or "unknown keyword" in str(exc.value).lower()


def test_unknown_keyword_uses_on_unknown_callback_when_provided() -> None:
    """Caller can supply ``on_unknown`` to override default error behaviour."""
    sentinel_calls: list[str] = []

    def _capture(parser) -> None:
        sentinel_calls.append(parser.current_token().value)
        parser.advance()
        # Drain to the next newline so the loop can make progress.
        while not parser.match(TokenType.NEWLINE, TokenType.DEDENT):
            parser.advance()
        parser.skip_newlines()

    tokens = Lexer(
        'persona x "X":\n  unknown_thing: "value"\n  description: "Alice"\n',
        file=Path("<test>"),
    ).tokenize()
    parser = BaseParser(tokens, file=Path("<test>"))
    parser.expect(TokenType.PERSONA)
    parser.advance()  # ident
    if parser.match(TokenType.STRING):
        parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)

    state = _ToyState()
    parse_block_with_dispatch(
        parser,
        first_class_keywords=_FIRST_CLASS,
        ident_keywords=_IDENT_KW,
        state=state,
        on_unknown=_capture,
    )
    parser.expect(TokenType.DEDENT)

    assert sentinel_calls == ["unknown_thing"]
    # The recognised keyword after the skipped unknown still parsed:
    assert state.name == "Alice"


def test_keyword_parser_can_raise() -> None:
    """A keyword parser raising propagates out unchanged."""

    class _BoomError(Exception):
        pass

    def _kw_boom(parser, _state: _ToyState) -> None:
        raise _BoomError("dispatch should not swallow this")

    tokens = Lexer('persona x "X":\n  description: "Alice"\n', file=Path("<test>")).tokenize()
    parser = BaseParser(tokens, file=Path("<test>"))
    parser.expect(TokenType.PERSONA)
    parser.advance()
    if parser.match(TokenType.STRING):
        parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)

    state = _ToyState()
    with pytest.raises(_BoomError):
        parse_block_with_dispatch(
            parser,
            first_class_keywords={TokenType.DESCRIPTION: _kw_boom},
            state=state,
        )


# ---------------------------------------------------------------------------
# Nested blocks — caller's keyword parser drives the inner dispatch.
# ---------------------------------------------------------------------------


@dataclass
class _OuterState:
    inner_count: int = 0
    inner_names: list[str] = field(default_factory=list)


@dataclass
class _InnerState:
    name: str | None = None


def _kw_outer_sub_block(parser, state: _OuterState) -> None:
    """An outer-level keyword whose value is itself an INDENT-block."""
    parser.advance()  # consume "interactive:" keyword for our test
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)

    inner = _InnerState()
    parse_block_with_dispatch(
        parser,
        first_class_keywords={TokenType.DESCRIPTION: _kw_inner_name},
        state=inner,
    )
    parser.expect(TokenType.DEDENT)

    state.inner_count += 1
    if inner.name:
        state.inner_names.append(inner.name)


def _kw_inner_name(parser, state: _InnerState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.name = parser.expect(TokenType.STRING).value
    parser.skip_newlines()


def test_nested_dispatch_works() -> None:
    """A keyword-parser can call dispatch again for its sub-block."""
    text = 'persona x "X":\n  interactive:\n    description: "Inner Alice"\n'
    tokens = Lexer(text, file=Path("<test>")).tokenize()
    parser = BaseParser(tokens, file=Path("<test>"))
    parser.expect(TokenType.PERSONA)
    parser.advance()
    if parser.match(TokenType.STRING):
        parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)

    state = _OuterState()
    parse_block_with_dispatch(
        parser,
        first_class_keywords={},
        ident_keywords={"interactive": _kw_outer_sub_block},
        state=state,
    )
    parser.expect(TokenType.DEDENT)

    assert state.inner_count == 1
    assert state.inner_names == ["Inner Alice"]
