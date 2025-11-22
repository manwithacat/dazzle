"""
Lexer/Tokenizer for DAZZLE DSL.

Converts raw DSL text into a stream of tokens with source location tracking.
Handles indentation-based blocks (Python-style) with INDENT/DEDENT tokens.
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional

from .errors import make_parse_error


class TokenType(Enum):
    """Token types in the DAZZLE DSL."""
    # Literals
    IDENTIFIER = "IDENTIFIER"
    STRING = "STRING"
    NUMBER = "NUMBER"

    # Keywords
    MODULE = "module"
    USE = "use"
    AS = "as"
    APP = "app"
    ENTITY = "entity"
    SURFACE = "surface"
    EXPERIENCE = "experience"
    SERVICE = "service"
    FOREIGN_MODEL = "foreign_model"
    INTEGRATION = "integration"
    FROM = "from"
    USES = "uses"
    MODE = "mode"
    SECTION = "section"
    FIELD = "field"
    ACTION = "action"
    STEP = "step"
    KIND = "kind"
    START = "start"
    AT = "at"
    ON = "on"
    WHEN = "when"
    CALL = "call"
    WITH = "with"
    MAP = "map"
    RESPONSE = "response"
    INTO = "into"
    MATCH = "match"
    SYNC = "sync"
    SCHEDULE = "schedule"
    SPEC = "spec"
    AUTH_PROFILE = "auth_profile"
    OWNER = "owner"
    KEY = "key"
    CONSTRAINT = "constraint"
    UNIQUE = "unique"
    INDEX = "index"
    URL = "url"
    INLINE = "inline"
    SUBMITTED = "submitted"

    # Test DSL Keywords
    TEST = "test"
    SETUP = "setup"
    DATA = "data"
    EXPECT = "expect"
    STATUS = "status"
    CREATED = "created"
    FILTER = "filter"
    SEARCH = "search"
    ORDER_BY = "order_by"
    COUNT = "count"
    ERROR_MESSAGE = "error_message"
    FIRST = "first"
    LAST = "last"
    QUERY = "query"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    GET = "get"
    TRUE = "true"
    FALSE = "false"

    # Operators
    COLON = ":"
    ARROW = "->"
    LARROW = "<-"
    BIARROW = "<->"
    COMMA = ","
    LPAREN = "("
    RPAREN = ")"
    LBRACKET = "["
    RBRACKET = "]"
    EQUALS = "="
    DOT = "."
    QUESTION = "?"

    # Special
    NEWLINE = "NEWLINE"
    INDENT = "INDENT"
    DEDENT = "DEDENT"
    EOF = "EOF"


# Keywords mapping
KEYWORDS = {
    "module", "use", "as", "app", "entity", "surface", "experience",
    "service", "foreign_model", "integration", "from", "uses", "mode",
    "section", "field", "action", "step", "kind", "start", "at", "on",
    "when", "call", "with", "map", "response", "into", "match", "sync",
    "schedule", "spec", "auth_profile", "owner", "key", "constraint",
    "unique", "index", "url", "inline", "submitted",
    # Test DSL keywords
    "test", "setup", "data", "expect", "status", "created", "filter",
    "search", "order_by", "count", "error_message", "first", "last",
    "query", "create", "update", "delete", "get", "true", "false",
}


@dataclass
class Token:
    """
    A single token in the DSL.

    Attributes:
        type: Type of token
        value: String value of the token
        line: Line number (1-indexed)
        column: Column number (1-indexed)
    """
    type: TokenType
    value: str
    line: int
    column: int

    def __repr__(self) -> str:
        return f"Token({self.type.value}, {self.value!r}, {self.line}:{self.column})"


class Lexer:
    """
    Lexer for DAZZLE DSL.

    Converts source text into a stream of tokens with indentation tracking.
    """

    def __init__(self, text: str, file: Path):
        """
        Initialize lexer.

        Args:
            text: Source text to tokenize
            file: Source file path (for error reporting)
        """
        self.text = text
        self.file = file
        self.pos = 0
        self.line = 1
        self.column = 1
        self.tokens: List[Token] = []
        self.indent_stack = [0]  # Stack of indentation levels

    def current_char(self) -> Optional[str]:
        """Get current character or None if at end."""
        if self.pos >= len(self.text):
            return None
        return self.text[self.pos]

    def peek_char(self, offset: int = 1) -> Optional[str]:
        """Peek ahead at character."""
        pos = self.pos + offset
        if pos >= len(self.text):
            return None
        return self.text[pos]

    def advance(self) -> None:
        """Move to next character, updating line/column."""
        if self.pos < len(self.text):
            if self.text[self.pos] == '\n':
                self.line += 1
                self.column = 1
            else:
                self.column += 1
            self.pos += 1

    def skip_whitespace(self, skip_newlines: bool = False) -> None:
        """Skip whitespace characters."""
        while self.current_char() in (' ', '\t', '\r') or (skip_newlines and self.current_char() == '\n'):
            self.advance()

    def skip_comment(self) -> None:
        """Skip comment (from # to end of line)."""
        if self.current_char() == '#':
            while self.current_char() and self.current_char() != '\n':
                self.advance()

    def read_string(self) -> str:
        """Read a quoted string."""
        start_line = self.line
        start_col = self.column
        quote = self.current_char()  # " or '
        self.advance()  # skip opening quote

        chars = []
        while self.current_char() and self.current_char() != quote:
            if self.current_char() == '\\':
                self.advance()
                # Handle escape sequences
                escape_char = self.current_char()
                if escape_char == 'n':
                    chars.append('\n')
                elif escape_char == 't':
                    chars.append('\t')
                elif escape_char == '\\':
                    chars.append('\\')
                elif escape_char == quote:
                    chars.append(quote)
                else:
                    chars.append(escape_char or '')
                self.advance()
            else:
                chars.append(self.current_char())
                self.advance()

        if self.current_char() != quote:
            raise make_parse_error(
                f"Unterminated string literal",
                self.file,
                start_line,
                start_col,
            )

        self.advance()  # skip closing quote
        return ''.join(chars)

    def read_number(self) -> str:
        """Read a number (integer or decimal)."""
        chars = []
        while self.current_char() and (self.current_char().isdigit() or self.current_char() == '.'):
            chars.append(self.current_char())
            self.advance()
        return ''.join(chars)

    def read_identifier(self) -> str:
        """Read an identifier or keyword."""
        chars = []
        while self.current_char() and (self.current_char().isalnum() or self.current_char() == '_'):
            chars.append(self.current_char())
            self.advance()
        return ''.join(chars)

    def handle_indentation(self, indent_level: int) -> None:
        """Generate INDENT/DEDENT tokens based on indentation level."""
        current_indent = self.indent_stack[-1]

        if indent_level > current_indent:
            self.indent_stack.append(indent_level)
            self.tokens.append(Token(TokenType.INDENT, "", self.line, 1))

        elif indent_level < current_indent:
            while self.indent_stack and self.indent_stack[-1] > indent_level:
                self.indent_stack.pop()
                self.tokens.append(Token(TokenType.DEDENT, "", self.line, 1))

            if self.indent_stack[-1] != indent_level:
                raise make_parse_error(
                    f"Inconsistent indentation (expected {self.indent_stack[-1]} spaces, got {indent_level})",
                    self.file,
                    self.line,
                    1,
                )

    def tokenize(self) -> List[Token]:
        """
        Tokenize the entire source text.

        Returns:
            List of tokens including INDENT/DEDENT and EOF

        Raises:
            ParseError: If syntax error encountered
        """
        at_line_start = True

        while self.pos < len(self.text):
            # Handle line start (indentation)
            if at_line_start:
                indent_level = 0
                while self.current_char() in (' ', '\t'):
                    if self.current_char() == ' ':
                        indent_level += 1
                    elif self.current_char() == '\t':
                        indent_level += 4  # Treat tab as 4 spaces
                    self.advance()

                # Skip blank lines and comments
                if self.current_char() in ('\n', '#'):
                    if self.current_char() == '#':
                        self.skip_comment()
                    if self.current_char() == '\n':
                        self.tokens.append(Token(TokenType.NEWLINE, "\\n", self.line, self.column))
                        self.advance()
                    continue

                # Handle indentation changes
                if self.current_char() is not None:
                    self.handle_indentation(indent_level)

                at_line_start = False

            # Skip whitespace (but not newlines)
            self.skip_whitespace(skip_newlines=False)

            ch = self.current_char()
            if ch is None:
                break

            # Save position for token
            token_line = self.line
            token_col = self.column

            # Comments
            if ch == '#':
                self.skip_comment()
                continue

            # Newlines
            elif ch == '\n':
                self.tokens.append(Token(TokenType.NEWLINE, "\\n", token_line, token_col))
                self.advance()
                at_line_start = True

            # Strings
            elif ch in ('"', "'"):
                value = self.read_string()
                self.tokens.append(Token(TokenType.STRING, value, token_line, token_col))

            # Numbers
            elif ch.isdigit():
                value = self.read_number()
                self.tokens.append(Token(TokenType.NUMBER, value, token_line, token_col))

            # Identifiers and keywords
            elif ch.isalpha() or ch == '_':
                value = self.read_identifier()
                if value in KEYWORDS:
                    token_type = TokenType(value)
                else:
                    token_type = TokenType.IDENTIFIER
                self.tokens.append(Token(token_type, value, token_line, token_col))

            # Operators
            elif ch == ':':
                self.advance()
                self.tokens.append(Token(TokenType.COLON, ":", token_line, token_col))

            elif ch == ',':
                self.advance()
                self.tokens.append(Token(TokenType.COMMA, ",", token_line, token_col))

            elif ch == '(':
                self.advance()
                self.tokens.append(Token(TokenType.LPAREN, "(", token_line, token_col))

            elif ch == ')':
                self.advance()
                self.tokens.append(Token(TokenType.RPAREN, ")", token_line, token_col))

            elif ch == '[':
                self.advance()
                self.tokens.append(Token(TokenType.LBRACKET, "[", token_line, token_col))

            elif ch == ']':
                self.advance()
                self.tokens.append(Token(TokenType.RBRACKET, "]", token_line, token_col))

            elif ch == '=':
                self.advance()
                self.tokens.append(Token(TokenType.EQUALS, "=", token_line, token_col))

            elif ch == '.':
                self.advance()
                self.tokens.append(Token(TokenType.DOT, ".", token_line, token_col))

            elif ch == '?':
                self.advance()
                self.tokens.append(Token(TokenType.QUESTION, "?", token_line, token_col))

            elif ch == '-':
                if self.peek_char() == '>':
                    self.advance()
                    self.advance()
                    self.tokens.append(Token(TokenType.ARROW, "->", token_line, token_col))
                else:
                    raise make_parse_error(
                        f"Unexpected character: {ch!r}",
                        self.file,
                        token_line,
                        token_col,
                    )

            elif ch == '<':
                if self.peek_char() == '-':
                    if self.peek_char(2) == '>':
                        self.advance()
                        self.advance()
                        self.advance()
                        self.tokens.append(Token(TokenType.BIARROW, "<->", token_line, token_col))
                    else:
                        self.advance()
                        self.advance()
                        self.tokens.append(Token(TokenType.LARROW, "<-", token_line, token_col))
                else:
                    raise make_parse_error(
                        f"Unexpected character: {ch!r}",
                        self.file,
                        token_line,
                        token_col,
                    )

            else:
                raise make_parse_error(
                    f"Unexpected character: {ch!r}",
                    self.file,
                    token_line,
                    token_col,
                )

        # Emit remaining DEDENTs
        while len(self.indent_stack) > 1:
            self.indent_stack.pop()
            self.tokens.append(Token(TokenType.DEDENT, "", self.line, self.column))

        # Add EOF token
        self.tokens.append(Token(TokenType.EOF, "", self.line, self.column))

        return self.tokens


def tokenize(text: str, file: Path) -> List[Token]:
    """
    Convenience function to tokenize DSL text.

    Args:
        text: Source text
        file: Source file path

    Returns:
        List of tokens
    """
    lexer = Lexer(text, file)
    return lexer.tokenize()
