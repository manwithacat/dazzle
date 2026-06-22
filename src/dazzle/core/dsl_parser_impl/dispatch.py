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

When to use this — and when NOT to (#1444, agent-cognition note):
    Use the table for *regular* keyword dispatch — a block loop where each
    keyword maps uniformly to a handler with **no lookahead**: `keyword token
    → _parse_<kw>(state)`. There the table wins on every axis (O(1), the legal
    keyword set is enumerable *data*, adding a keyword is one dict entry, and
    there are no hidden special cases). `parse_entity` and the process-step
    field block are exactly this; both were migrated.

    Keep a hand-written ladder when dispatch is *irregular* — it needs
    `peek_token` lookahead, ordering-dependent precedence, or a "default content"
    rule (e.g. *any bare identifier names a region*). `workspace.py`'s
    `_dispatch_workspace_keyword` is the canonical example: forcing it into a
    table would push the load-bearing peeks and the ordered identifier-specials
    into `on_unknown`/handler bodies, *scattering* the dispatch and *hiding* the
    subtle bits — the parts the next agent is most likely to get wrong. A linear
    ladder keeps precedence == source order, which reads in one pass. The win the
    table is for (bounding an unbounded keyword ladder) is enforced generically
    by the per-function complexity ratchet, not by forcing every dispatch into a
    table. Match the tool to the dispatch's *regularity*, not to a line count.
"""

from __future__ import annotations

import difflib
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
            known = sorted({tt.name.lower() for tt in first_class_keywords} | set(ident_kw))
            _default_unknown_keyword(parser, known)


def _default_unknown_keyword(parser: _ParserLike, known: list[str] | None = None) -> None:
    """Default ``on_unknown`` — raise a parse error at this token.

    #1360: when the caller's keyword tables are available, name the legal
    keywords and suggest the closest one — a typo'd keyword should resolve
    itself from the error message alone.
    """
    tok = parser.current_token()
    hint = ""
    if known:
        close = difflib.get_close_matches(str(tok.value), known, n=1, cutoff=0.6)
        suggest = f" Did you mean {close[0]!r}?" if close else ""
        hint = f"{suggest}\n  Valid keywords here: {', '.join(known)}"
    raise make_parse_error(
        f"Unknown keyword in block: {tok.value!r}.{hint}",
        parser.file,
        tok.line,
        tok.column,
    )
