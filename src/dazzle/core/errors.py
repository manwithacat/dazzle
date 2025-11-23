"""
Error types for DAZZLE DSL parsing, linking, and validation.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class DazzleError(Exception):
    """Base exception for all DAZZLE errors."""

    def __init__(self, message: str, context: Optional["ErrorContext"] = None):
        self.message = message
        self.context = context
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        """Format error message with context if available."""
        if self.context:
            return f"{self.context.format()}\n{self.message}"
        return self.message


class ParseError(DazzleError):
    """
    Raised when DSL syntax cannot be parsed.

    Examples:
    - Invalid syntax
    - Malformed constructs
    - Unexpected tokens
    - Indentation errors
    """

    pass


class LinkError(DazzleError):
    """
    Raised when modules cannot be linked together.

    Examples:
    - Missing module dependencies
    - Circular dependencies
    - Duplicate definitions across modules
    - Unresolved references between modules
    """

    pass


class ValidationError(DazzleError):
    """
    Raised when AppSpec fails semantic validation.

    Examples:
    - Entity without primary key
    - Surface referencing non-existent entity
    - Experience with unreachable steps
    - Integration referencing missing service
    """

    pass


class BackendError(DazzleError):
    """
    Raised when a backend fails to generate output.

    Examples:
    - Unsupported feature in backend
    - Output directory issues
    - Template rendering errors
    """

    pass


@dataclass
class ErrorContext:
    """
    Context information for an error, including source location.

    Attributes:
        file: Path to the source file where error occurred
        line: Line number (1-indexed)
        column: Column number (1-indexed)
        snippet: Optional code snippet showing the error location
        module: Optional module name where error occurred
    """

    file: Path
    line: int
    column: int
    snippet: str | None = None
    module: str | None = None

    def format(self) -> str:
        """
        Format error context as a human-readable string.

        Returns:
            Formatted string like: "file.dsl:10:5 in module foo.bar"
        """
        location = f"{self.file}:{self.line}:{self.column}"
        if self.module:
            location += f" in module {self.module}"

        if self.snippet:
            return f"{location}\n{self._format_snippet()}"
        return location

    def _format_snippet(self) -> str:
        """Format code snippet with line numbers and error marker."""
        if not self.snippet:
            return ""

        lines = self.snippet.split("\n")
        formatted = []

        # Calculate starting line number for snippet
        # Assume snippet shows 2 lines before and after error
        start_line = max(1, self.line - 2)

        for i, line in enumerate(lines):
            line_num = start_line + i
            prefix = f"{line_num:4d} | "
            formatted.append(prefix + line)

            # Add error marker (^^^) under the error column
            if line_num == self.line:
                marker_pos = len(prefix) + self.column - 1
                formatted.append(" " * marker_pos + "^^^")

        return "\n".join(formatted)


def make_parse_error(
    message: str,
    file: Path,
    line: int,
    column: int,
    snippet: str | None = None,
) -> ParseError:
    """
    Helper to create a ParseError with context.

    Args:
        message: Error description
        file: Source file path
        line: Line number (1-indexed)
        column: Column number (1-indexed)
        snippet: Optional code snippet

    Returns:
        ParseError with context attached
    """
    context = ErrorContext(file=file, line=line, column=column, snippet=snippet)
    return ParseError(message, context)


def make_link_error(
    message: str,
    file: Path | None = None,
    line: int | None = None,
    column: int | None = None,
    module: str | None = None,
) -> LinkError:
    """
    Helper to create a LinkError with optional context.

    Args:
        message: Error description
        file: Optional source file path
        line: Optional line number
        column: Optional column number
        module: Optional module name

    Returns:
        LinkError with context if location provided
    """
    if file and line and column:
        context = ErrorContext(
            file=file,
            line=line,
            column=column,
            module=module,
        )
        return LinkError(message, context)
    return LinkError(message)


def make_validation_error(
    message: str,
    file: Path | None = None,
    line: int | None = None,
    column: int | None = None,
    module: str | None = None,
) -> ValidationError:
    """
    Helper to create a ValidationError with optional context.

    Args:
        message: Error description
        file: Optional source file path
        line: Optional line number
        column: Optional column number
        module: Optional module name

    Returns:
        ValidationError with context if location provided
    """
    if file and line and column:
        context = ErrorContext(
            file=file,
            line=line,
            column=column,
            module=module,
        )
        return ValidationError(message, context)
    return ValidationError(message)
