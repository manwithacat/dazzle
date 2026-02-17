"""
Tokenizer for Dazzle expression language.

Converts an expression string into a sequence of typed tokens.
"""

from __future__ import annotations

import re
from enum import StrEnum, auto


class TokenKind(StrEnum):
    """Token types for the expression language."""

    # Literals
    INT = auto()
    FLOAT = auto()
    STRING = auto()

    # Identifiers and keywords
    IDENT = auto()
    TRUE = auto()
    FALSE = auto()
    NULL = auto()
    AND = auto()
    OR = auto()
    NOT = auto()
    IN = auto()
    IS = auto()
    IF = auto()
    ELIF = auto()
    ELSE = auto()

    # Operators
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    PERCENT = auto()
    EQ = auto()
    NE = auto()
    LT = auto()
    GT = auto()
    LE = auto()
    GE = auto()

    # Punctuation
    LPAREN = auto()
    RPAREN = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    COMMA = auto()
    DOT = auto()
    ARROW = auto()  # ->
    COLON = auto()

    # Duration suffix (attached to preceding INT)
    DURATION = auto()

    # End of input
    EOF = auto()


class Token:
    """A single token from the expression tokenizer."""

    __slots__ = ("kind", "value", "pos")

    def __init__(self, kind: TokenKind, value: str, pos: int) -> None:
        self.kind = kind
        self.value = value
        self.pos = pos

    def __repr__(self) -> str:
        return f"Token({self.kind}, {self.value!r}, pos={self.pos})"


_KEYWORDS: dict[str, TokenKind] = {
    "true": TokenKind.TRUE,
    "false": TokenKind.FALSE,
    "null": TokenKind.NULL,
    "and": TokenKind.AND,
    "or": TokenKind.OR,
    "not": TokenKind.NOT,
    "in": TokenKind.IN,
    "is": TokenKind.IS,
    "if": TokenKind.IF,
    "elif": TokenKind.ELIF,
    "else": TokenKind.ELSE,
}

_DURATION_UNITS = {"d", "h", "m", "y", "w", "min"}

# Number pattern: int or float
_NUMBER_RE = re.compile(r"\d+(\.\d+)?")
# Identifier: letter or underscore followed by alphanumerics/underscores
_IDENT_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")


class ExpressionTokenError(Exception):
    """Error during expression tokenization."""

    def __init__(self, message: str, pos: int) -> None:
        super().__init__(message)
        self.pos = pos


def tokenize(source: str) -> list[Token]:
    """Tokenize an expression string into a list of tokens."""
    tokens: list[Token] = []
    i = 0
    n = len(source)

    while i < n:
        c = source[i]

        # Skip whitespace
        if c in " \t\n\r":
            i += 1
            continue

        # String literals
        if c in ('"', "'"):
            i, tok = _read_string(source, i)
            tokens.append(tok)
            continue

        # Numbers (may be followed by duration suffix)
        if c.isdigit():
            m = _NUMBER_RE.match(source, i)
            assert m is not None
            num_str = m.group(0)
            end = m.end()

            # Check for duration suffix
            suffix_m = _IDENT_RE.match(source, end)
            if suffix_m and suffix_m.group(0) in _DURATION_UNITS:
                suffix = suffix_m.group(0)
                tokens.append(Token(TokenKind.DURATION, num_str + suffix, i))
                i = suffix_m.end()
            elif "." in num_str:
                tokens.append(Token(TokenKind.FLOAT, num_str, i))
                i = end
            else:
                tokens.append(Token(TokenKind.INT, num_str, i))
                i = end
            continue

        # Identifiers and keywords
        if c.isalpha() or c == "_":
            m = _IDENT_RE.match(source, i)
            assert m is not None
            word = m.group(0)
            kind = _KEYWORDS.get(word, TokenKind.IDENT)
            tokens.append(Token(kind, word, i))
            i = m.end()
            continue

        # Two-character operators
        if i + 1 < n:
            two = source[i : i + 2]
            if two == "==":
                tokens.append(Token(TokenKind.EQ, "==", i))
                i += 2
                continue
            if two == "!=":
                tokens.append(Token(TokenKind.NE, "!=", i))
                i += 2
                continue
            if two == "<=":
                tokens.append(Token(TokenKind.LE, "<=", i))
                i += 2
                continue
            if two == ">=":
                tokens.append(Token(TokenKind.GE, ">=", i))
                i += 2
                continue
            if two == "->":
                tokens.append(Token(TokenKind.ARROW, "->", i))
                i += 2
                continue

        # Single-character operators and punctuation
        single_map: dict[str, TokenKind] = {
            "+": TokenKind.PLUS,
            "-": TokenKind.MINUS,
            "*": TokenKind.STAR,
            "/": TokenKind.SLASH,
            "%": TokenKind.PERCENT,
            "<": TokenKind.LT,
            ">": TokenKind.GT,
            "(": TokenKind.LPAREN,
            ")": TokenKind.RPAREN,
            "[": TokenKind.LBRACKET,
            "]": TokenKind.RBRACKET,
            ",": TokenKind.COMMA,
            ".": TokenKind.DOT,
            ":": TokenKind.COLON,
        }
        if c in single_map:
            tokens.append(Token(single_map[c], c, i))
            i += 1
            continue

        raise ExpressionTokenError(f"Unexpected character: {c!r}", i)

    tokens.append(Token(TokenKind.EOF, "", n))
    return tokens


def _read_string(source: str, start: int) -> tuple[int, Token]:
    """Read a quoted string literal."""
    quote = source[start]
    i = start + 1
    n = len(source)
    chars: list[str] = []

    while i < n:
        c = source[i]
        if c == "\\":
            if i + 1 < n:
                chars.append(source[i + 1])
                i += 2
                continue
            raise ExpressionTokenError("Unterminated escape sequence", i)
        if c == quote:
            return i + 1, Token(TokenKind.STRING, "".join(chars), start)
        chars.append(c)
        i += 1

    raise ExpressionTokenError("Unterminated string literal", start)
