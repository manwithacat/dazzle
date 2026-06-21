"""Character-walk helpers for DSL parser internals (#1155, ADR-0024).

The DSL parser's policy is "no regex for DSL grammar" (ADR-0024). The
remaining lexical-shape regex uses — duration-literal splits and the
``Entity.field`` path probe — are migrated to deterministic char-walk
helpers in this module. Keeping them in one place makes the
``test_no_regex_in_parser`` allowlist enforceable (it now stays at
zero) and gives a single audit point for parser-surface lexical
recognition.

Public surface:

- :func:`split_duration_token` — split a DURATION_LITERAL token value
  (``"30min"``, ``"5m"``, ``"24h"``, ``"7d"``, ``"2w"``, ``"6y"``)
  into ``(value, unit_suffix)``. The lexer guarantees the shape; this
  helper unpacks it without re.

- :func:`short_duration_seconds` — convert a process-DSL duration
  string (``"30s"`` / ``"5m"`` / ``"2h"`` / ``"7d"``) to seconds.
  Stricter shape than the DURATION_LITERAL token — only the four
  single-character suffixes accepted by ``parse_duration``.

- :func:`is_short_duration_token` — lookahead-friendly predicate that
  returns True for a string matching ``\\d+[smhd]`` exactly. Used by
  ``_parse_duration_or_signal`` to disambiguate a duration from a
  signal name without committing tokens.

- :func:`extract_entity_field_prefix` — pick out the leading
  ``Entity.field`` from a re-joined narrative string in story
  parsing. Returns the matched prefix or ``None``. The shape is:
  initial uppercase letter, identifier characters, ``.``, initial
  lowercase letter, identifier characters.

- :func:`is_rename_hint_name` — predicate for the identifier that
  follows a ``was:`` rename hint (#1431, Task 4.2). True when the
  value is a non-empty DSL identifier: leading ASCII letter or
  underscore, then ASCII letters/digits/underscores. Used by the
  field/entity parsers to reject a bare ``was:`` (no name) without
  re.
"""

from __future__ import annotations

# Recognised DURATION_LITERAL suffixes — ordered longest-first so the
# multi-char ``min`` matches before the single-char ``m`` (months).
_DURATION_TOKEN_SUFFIXES: tuple[str, ...] = ("min", "h", "d", "w", "m", "y")

# Recognised short-form duration suffixes used by ``parse_duration``.
_SHORT_DURATION_SUFFIXES: frozenset[str] = frozenset({"s", "m", "h", "d"})


def split_duration_token(value: str) -> tuple[int, str] | None:
    """Split a DURATION_LITERAL token value into (numeric, suffix).

    Accepts the shape the lexer emits: one or more decimal digits
    followed by one of the suffixes in :data:`_DURATION_TOKEN_SUFFIXES`.
    Returns ``None`` when the shape doesn't match — caller surfaces
    the parse error.
    """
    if not value:
        return None
    # Find the digit/letter boundary. ASCII digits only: ``str.isdigit()`` is True for
    # Unicode super/subscripts ("²") that ``int()`` then rejects — guarding here keeps the
    # documented "return None on shape mismatch" contract instead of leaking a ValueError.
    digit_end = 0
    while digit_end < len(value) and value[digit_end].isascii() and value[digit_end].isdigit():
        digit_end += 1
    if digit_end == 0 or digit_end == len(value):
        return None
    suffix = value[digit_end:]
    if suffix not in _DURATION_TOKEN_SUFFIXES:
        return None
    return int(value[:digit_end]), suffix


def short_duration_seconds(value: str) -> int | None:
    """Convert ``"30s"`` / ``"5m"`` / ``"2h"`` / ``"7d"`` to seconds.

    Returns ``None`` on shape mismatch. Stricter than
    :func:`split_duration_token`: only the single-character suffixes
    ``s``, ``m``, ``h``, ``d`` are accepted (these are the units the
    process DSL's ``parse_duration`` understands).
    """
    stripped = value.strip()
    if not stripped:
        return None
    # ASCII digits only — see split_duration_token (Unicode super/subscripts pass
    # str.isdigit() but crash int()).
    digit_end = 0
    while (
        digit_end < len(stripped)
        and stripped[digit_end].isascii()
        and stripped[digit_end].isdigit()
    ):
        digit_end += 1
    if digit_end == 0 or digit_end != len(stripped) - 1:
        return None
    suffix = stripped[digit_end:]
    if suffix not in _SHORT_DURATION_SUFFIXES:
        return None
    n = int(stripped[:digit_end])
    multiplier = {"s": 1, "m": 60, "h": 3600, "d": 86400}[suffix]
    return n * multiplier


def is_short_duration_token(value: str) -> bool:
    """True when ``value`` matches ``\\d+[smhd]`` exactly.

    Lookahead predicate used to disambiguate a duration literal from
    a signal name without consuming the token.
    """
    return short_duration_seconds(value) is not None


def extract_entity_field_prefix(text: str) -> str | None:
    """Return the leading ``Entity.field`` shape from ``text`` or ``None``.

    Shape:
      - first char: ASCII uppercase
      - subsequent chars: ASCII letter, digit, or underscore (greedy)
      - then literal ``.``
      - then ASCII lowercase
      - then ASCII letter, digit, or underscore (greedy)

    The probe matches at position 0 only — mirrors the original
    ``re.match`` (not ``re.search``) semantics used by the story parser.
    """
    if not text:
        return None
    if not _is_ascii_upper(text[0]):
        return None
    i = 1
    while i < len(text) and _is_ident_char(text[i]):
        i += 1
    if i >= len(text) or text[i] != ".":
        return None
    dot_idx = i
    if dot_idx + 1 >= len(text) or not _is_ascii_lower(text[dot_idx + 1]):
        return None
    j = dot_idx + 2
    while j < len(text) and _is_ident_char(text[j]):
        j += 1
    return text[:j]


def is_rename_hint_name(value: str) -> bool:
    """True when ``value`` is a valid ``was:`` rename-hint identifier (#1431).

    Shape (deterministic char-walk, no re per ADR-0024):
      - non-empty
      - first char: ASCII letter or underscore
      - subsequent chars: ASCII letter, digit, or underscore

    Used by the field/entity parsers to validate the token following a
    ``was:`` clause — a bare ``was:`` (next token is ``COLON``/``NEWLINE``/
    a non-identifier) returns False, so the caller raises a clear parse
    error instead of mis-binding an old name.
    """
    if not value:
        return False
    first = value[0]
    if not (_is_ascii_upper(first) or _is_ascii_lower(first) or first == "_"):
        return False
    return all(_is_ident_char(c) for c in value[1:])


def _is_ascii_upper(c: str) -> bool:
    return "A" <= c <= "Z"


def _is_ascii_lower(c: str) -> bool:
    return "a" <= c <= "z"


def _is_ident_char(c: str) -> bool:
    return c.isascii() and (c.isalnum() or c == "_")
