"""Shared ``refresh: every Ns`` interval parser (#1391 region, #1399 surface).

The live-refresh poll interval has identical surface syntax on workspace
regions (#1391) and standalone list/detail surfaces (#1399 slice 3):

    refresh: every 30s   |   refresh: every 30   |   refresh: 30s   |   refresh: 30

This module owns the token-consuming parse so both parser surfaces stay in
lockstep (one diagnostic, one 5s floor) instead of drifting. The caller
consumes ``refresh`` + ``:`` itself, then delegates the value here.
"""

from __future__ import annotations

from typing import Any

from ..errors import make_parse_error
from ..lexer import TokenType

# Load/cost floor — polling faster overloads the fetch endpoint. Shared by both
# the region (#1391) and surface (#1399) refresh surfaces. See
# docs/architecture/model-driven-failure-modes.md.
_MIN_REFRESH_SECONDS = 5


def parse_refresh_interval_seconds(parser: Any) -> int:
    """Parse the value side of ``refresh: every Ns`` and return whole seconds.

    The caller has already consumed the ``refresh`` keyword and the ``:``.
    Accepts an optional ``every``, then a NUMBER, then an optional ``s`` unit.
    Seconds only in v1 — a non-``s`` unit (``5m``/``2h``) or a DURATION_LITERAL
    is a directed parse error pointing at seconds. Enforces a 5s minimum.
    """
    if parser.match(TokenType.EVERY):
        parser.advance()  # optional `every`
    if parser.match(TokenType.DURATION_LITERAL):
        bad = parser.advance()
        raise make_parse_error(
            f"refresh interval {bad.value!r} must be expressed in seconds, "
            "e.g. `refresh: every 30s`.",
            parser.file,
            bad.line,
            bad.column,
        )
    num_tok = parser.expect(TokenType.NUMBER)
    try:
        seconds = int(num_tok.value)
    except (TypeError, ValueError):
        raise make_parse_error(
            "refresh interval must be a whole number of seconds.",
            parser.file,
            num_tok.line,
            num_tok.column,
        ) from None
    if parser.match(TokenType.IDENTIFIER):
        unit_tok = parser.advance()
        if str(unit_tok.value) != "s":
            raise make_parse_error(
                f"refresh unit {unit_tok.value!r} not supported — express the "
                "interval in seconds, e.g. `refresh: every 30s`.",
                parser.file,
                unit_tok.line,
                unit_tok.column,
            )
    if seconds < _MIN_REFRESH_SECONDS:
        raise make_parse_error(
            f"refresh interval must be at least {_MIN_REFRESH_SECONDS}s (got {seconds}s) — "
            "polling faster overloads the fetch endpoint.",
            parser.file,
            num_tok.line,
            num_tok.column,
        )
    return seconds
