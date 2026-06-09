"""Keyword-dispatch helper for `dsl_parser_impl/` parsers (#1088a).

Closes the long elif-chain anti-pattern that produced #1088's headline
case (`parse_workspace_region`: 859 lines, depth 53, 52-branch chain).
Each `BaseParser`-derived parser that consumes an INDENT/DEDENT block
can now use ``parse_block_with_dispatch`` to route per-keyword tokens
through a small dict lookup instead of unrolling a long if/elif.

Pattern (used by callers):

    @dataclass
    class _PersonaState:
        description: str | None = None
        goals: list[str] = field(default_factory=list)
        # ... one field per legal keyword in the block

    def _kw_description(parser: PersonaParser, state: _PersonaState) -> None:
        parser.advance()
        parser.expect(TokenType.COLON)
        state.description = parser.expect(TokenType.STRING).value
        parser.skip_newlines()

    _PERSONA_KEYWORDS: dict[TokenType, KeywordParser] = {
        TokenType.DESCRIPTION: _kw_description,
        # ...
    }

    def parse_persona(self) -> PersonaSpec:
        # ... header parsing ...
        state = _PersonaState()
        parse_block_with_dispatch(
            self,
            first_class_keywords=_PERSONA_KEYWORDS,
            ident_keywords=_PERSONA_IDENT_KEYWORDS,
            state=state,
        )
        self.expect(TokenType.DEDENT)
        return _build_persona(persona_id, label, state)

Spike data (issue #1099): on a representative 8-keyword construct, the
dispatch-table form replaces a hand-rolled elif chain with no measurable
perf cost (≤2% delta) and trivially testable per-keyword units. The
spike kept the bespoke domain-specific error messages — that's the
whole point of choosing this style over the Lark-generator alternative.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol, TypeVar

from dazzle.core.errors import make_parse_error
from dazzle.core.lexer import Token, TokenType

StateT = TypeVar("StateT")


class _ParserLike(Protocol):
    """The slice of BaseParser the dispatch loop touches.

    Declared as Protocol so callers don't need to subclass anything new —
    every existing ``BaseParser`` satisfies this structurally.
    """

    file: Path

    def match(self, *token_types: TokenType) -> bool: ...
    def skip_newlines(self) -> None: ...
    def current_token(self) -> Token: ...


KeywordParser = Callable[[_ParserLike, StateT], None]


def parse_block_with_dispatch[StateT](
    parser: _ParserLike,
    *,
    first_class_keywords: dict[TokenType, KeywordParser[StateT]],
    state: StateT,
    ident_keywords: dict[str, KeywordParser[StateT]] | None = None,
    on_unknown: Callable[[_ParserLike], None] | None = None,
) -> None:
    """Loop over the keywords inside an INDENT/DEDENT block, dispatching
    each one through the keyword tables and mutating ``state`` in place.

    Caller is responsible for the surrounding ``INDENT`` / ``DEDENT``
    token consumption — this helper handles only the body. That keeps
    the header-parsing semantics (label, name, etc.) under each caller's
    direct control.

    Args:
        parser: The active parser (typically ``self`` from a parser
            mixin). Must satisfy the ``_ParserLike`` protocol — every
            ``BaseParser`` already does.
        first_class_keywords: ``{TokenType.X: parser_fn}``. Maps each
            first-class keyword token to its parser function. The
            parser function consumes its keyword token + value tokens
            and mutates ``state`` in place.
        state: Accumulator instance. Typically a ``@dataclass`` whose
            fields mirror the legal keywords. Passed by reference into
            each keyword parser.
        ident_keywords: ``{"keyword_text": parser_fn}``. For keywords
            that match as plain ``IDENTIFIER`` tokens (no dedicated
            ``TokenType``). Optional — pass ``None`` if none.
        on_unknown: Callback invoked when the current token doesn't
            match any known keyword. Defaults to raising a generic
            ``"Unknown keyword in block"`` parse error at the current
            position. Override to forward to bespoke recovery logic
            (e.g., the existing ``_skip_unknown_or_raise_for_renamed_keyword``).
    """
    ident_kw = ident_keywords or {}

    while not parser.match(TokenType.DEDENT):
        parser.skip_newlines()
        if parser.match(TokenType.DEDENT):
            break

        tok = parser.current_token()

        first_class_fn = first_class_keywords.get(tok.type)
        if first_class_fn is not None:
            first_class_fn(parser, state)
            continue

        if tok.type == TokenType.IDENTIFIER:
            ident_fn = ident_kw.get(tok.value)
            if ident_fn is not None:
                ident_fn(parser, state)
                continue

        if on_unknown is not None:
            on_unknown(parser)
        else:
            _default_unknown_keyword(parser)


def _default_unknown_keyword(parser: _ParserLike) -> None:
    """Default ``on_unknown`` — raise a generic parse error at this token."""
    tok = parser.current_token()
    raise make_parse_error(
        f"Unknown keyword in block: {tok.value!r}",
        parser.file,
        tok.line,
        tok.column,
    )
