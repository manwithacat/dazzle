"""
Anti-Turing-Complete Enforcement for Dazzle DSL.

This module validates that DSL content remains declarative and non-algorithmic.
The DSL must never support:
- Control flow (if, for, while, etc.)
- Function definitions (def, lambda, etc.)
- Recursion
- General-purpose computation

All complex logic must be delegated to service stubs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


class ViolationType(Enum):
    """Types of Anti-Turing violations."""

    BANNED_KEYWORD = "banned_keyword"
    BANNED_PATTERN = "banned_pattern"
    INVALID_FUNCTION_CALL = "invalid_function_call"
    RECURSIVE_REFERENCE = "recursive_reference"


@dataclass
class Violation:
    """A single Anti-Turing violation."""

    type: ViolationType
    message: str
    line: int
    column: int
    context: str  # The problematic line/snippet


class AntiTuringValidator:
    """
    Validates DSL content for Anti-Turing compliance.

    Ensures the DSL remains declarative and non-algorithmic by:
    1. Scanning for banned keywords (if, for, while, def, etc.)
    2. Detecting banned patterns (=>, ?:, etc.)
    3. Restricting function calls to allowed aggregates
    4. Checking for recursive references
    """

    # Keywords that indicate control flow or function definition
    BANNED_KEYWORDS: frozenset[str] = frozenset(
        {
            # Conditionals
            "if",
            "else",
            "elif",
            "then",
            # Loops
            "for",
            "while",
            "loop",
            "repeat",
            "each",
            # Function definitions
            "def",
            "fn",
            "function",
            "lambda",
            # Pattern matching (control flow)
            "match",
            "case",
            "switch",
            # Control flow keywords
            "return",
            "yield",
            "await",
            "break",
            "continue",
        }
    )

    # Patterns that indicate programming constructs
    BANNED_PATTERNS: list[tuple[str, str]] = [
        (r"=>", "Arrow function syntax"),
        (r"\?[^?]*:", "Ternary operator"),  # ? followed by anything then :
        (r"\{\s*\|", "Block/lambda syntax"),
        (r"do\s*\{", "Do-block syntax"),
    ]

    # Allowed aggregate/utility functions in expressions
    ALLOWED_FUNCTIONS: frozenset[str] = frozenset(
        {
            # Aggregates
            "count",
            "sum",
            "avg",
            "max",
            "min",
            # Date utilities
            "days_until",
            "days_since",
            "now",
            "today",
            # String utilities (if needed)
            "length",
            "lower",
            "upper",
            # RBAC primitives — used in permit/scope/state-machine
            # transition guards. #998 — anti-turing was rejecting
            # role() across every example app's RBAC rules.
            "role",
            # Workspace access-control declarations: `access: persona(a, b)`
            # in app.dsl. #998.
            "persona",
            # Time-bucketing aggregator: `group_by: bucket(field, day|week|month)`.
            # #998 — used in chart/report regions in ops_dashboard.
            "bucket",
            # Config / environment / schedule lookups — declarative
            # key→value indirections used in webhook URLs (`config("KEY")`),
            # API auth blocks (`env("KEY")`), and scheduled jobs
            # (`cron("0 * * * *")`). #998.
            "config",
            "env",
            "cron",
            # Declarative pattern primitives — `regex("...")` for
            # string-shape matching, `in("a", "b", ...)` for set
            # membership. Both used in messaging routing rules.
            # #998.
            "regex",
            "in",
        }
    )

    def __init__(self, strict: bool = False) -> None:
        """
        Initialize the validator.

        Args:
            strict: If True, treat warnings as errors
        """
        self.strict = strict

    def validate(self, content: str, filename: str = "<unknown>") -> list[Violation]:
        """
        Validate DSL content for Anti-Turing compliance.

        Args:
            content: The DSL file content
            filename: Name of the file (for error messages)

        Returns:
            List of violations found
        """
        violations: list[Violation] = []

        lines = content.splitlines()
        for line_num, line in enumerate(lines, start=1):
            # Skip empty lines
            if not line.strip():
                continue

            # Skip comment lines
            if line.strip().startswith("#"):
                continue

            # Check for banned keywords
            violations.extend(self._check_keywords(line, line_num))

            # Check for banned patterns
            violations.extend(self._check_patterns(line, line_num))

            # Check for invalid function calls
            violations.extend(self._check_function_calls(line, line_num))

        return violations

    def validate_file(self, path: Path) -> list[Violation]:
        """
        Validate a DSL file.

        Args:
            path: Path to the DSL file

        Returns:
            List of violations found
        """
        content = path.read_text(encoding="utf-8")
        return self.validate(content, str(path))

    # DSL-specific patterns that look like banned keywords but are allowed
    # at the top level of a line (NOT mid-expression).
    #
    # #998 — the persona/scope `for` syntaxes were renamed to `as` so
    # the anti-Turing carve-outs no longer have to defend `for`. The
    # remaining exceptions are minimal: structured-grammar block headers
    # that share a name with a banned keyword.
    ALLOWED_PATTERNS: list[str] = [
        # Story outcome block — `then:` is the structured-grammar
        # header alongside `given:` / `when:`, not control flow.
        # Ban on `then` mid-expression preserved by anchoring to
        # start-of-line + colon-only termination.
        r"^\s*then\s*:",
        # Match block — declarative pattern-matching header used in
        # process/messaging routing (pra fixture). Not control flow:
        # the body lists patterns and outcomes structurally.
        r"^\s*match\s*:",
        # Step-trigger declaration: `on <trigger> -> step <name>`. The
        # trigger name is user-defined and may collide with banned
        # keywords (e.g. `on continue -> step profile` in pra). Consume
        # the trigger word so the rest of the line still gets scanned.
        # #998.
        r"^\s*on\s+\w+\s*(?:->|→)",
    ]

    def _check_keywords(self, line: str, line_num: int) -> list[Violation]:
        """Check for banned keywords in a line."""
        violations: list[Violation] = []

        # Extract the non-quoted, non-comment parts of the line.
        # #998 — comments must be stripped before keyword scanning,
        # otherwise prose like `# for auditability` trips the
        # banned-`for` check.
        non_quoted = self._strip_comments(self._remove_quoted_strings(line))

        # Whitelist DSL block headers by *consuming the matched prefix*
        # rather than skipping the entire line. #998 — the prior
        # behaviour (return [] on any prefix match) meant a line like
        # `then: while true:` would silently skip the `while` check.
        # Now we only consume the matched header and continue scanning
        # the rest for banned keywords.
        for allowed_pattern in self.ALLOWED_PATTERNS:
            m = re.match(allowed_pattern, non_quoted, re.IGNORECASE)
            if m:
                non_quoted = " " * m.end() + non_quoted[m.end() :]
                break

        # Check each word
        for match in re.finditer(r"\b(\w+)\b", non_quoted):
            word = match.group(1).lower()
            if word in self.BANNED_KEYWORDS:
                violations.append(
                    Violation(
                        type=ViolationType.BANNED_KEYWORD,
                        message=f"Banned keyword '{word}' - DSL must be declarative",
                        line=line_num,
                        column=match.start() + 1,
                        context=line.strip(),
                    )
                )

        return violations

    def _check_patterns(self, line: str, line_num: int) -> list[Violation]:
        """Check for banned patterns in a line."""
        violations: list[Violation] = []

        # Remove quoted strings + comments first
        non_quoted = self._strip_comments(self._remove_quoted_strings(line))

        for pattern, description in self.BANNED_PATTERNS:
            for match in re.finditer(pattern, non_quoted):
                violations.append(
                    Violation(
                        type=ViolationType.BANNED_PATTERN,
                        message=f"Banned pattern: {description}",
                        line=line_num,
                        column=match.start() + 1,
                        context=line.strip(),
                    )
                )

        return violations

    def _check_function_calls(self, line: str, line_num: int) -> list[Violation]:
        """
        Check for function calls and ensure only allowed functions are used.

        Type annotations like str(200) are allowed.
        """
        violations: list[Violation] = []

        # Remove quoted strings + comments
        non_quoted = self._strip_comments(self._remove_quoted_strings(line))

        # Pattern for function-like calls: word(something) — no
        # whitespace between identifier and `(`. Function calls in
        # the DSL are always tight (e.g. `role(admin)`); whitespace
        # before `(` is grammar like `- open (order: 0)` (list item
        # + parenthesised key-value pair) and should NOT be parsed
        # as a call. #998.
        #
        # `via <Entity>(...)` is the junction-EXISTS scope predicate
        # — the entity name is user-defined (RealmGuardian, BlockList,
        # etc.) so it can't be enumerated in ALLOWED_FUNCTIONS. Skip
        # function-call checks when the identifier is preceded by
        # `via ` (CLAUDE.md scope rules). #998.
        for match in re.finditer(r"\b(\w+)\(\s*[^)]*\s*\)", non_quoted):
            preceding = non_quoted[: match.start()]
            if re.search(r"\bvia\s+$", preceding):
                continue
            func_name = match.group(1).lower()

            # Skip if this looks like a type annotation
            # Type annotations: str(200), decimal(10,2), enum[...], ref(Entity)
            type_keywords = {
                "str",
                "text",
                "int",
                "decimal",
                "bool",
                "date",
                "datetime",
                "uuid",
                "email",
                "ref",
                "money",
                "json",
            }
            if func_name in type_keywords:
                continue

            # Skip if it's an allowed function
            if func_name in self.ALLOWED_FUNCTIONS:
                continue

            # This is an invalid function call
            violations.append(
                Violation(
                    type=ViolationType.INVALID_FUNCTION_CALL,
                    message=(
                        f"Invalid function call '{func_name}()'"
                        f" - only allowed: {', '.join(sorted(self.ALLOWED_FUNCTIONS))}"
                    ),
                    line=line_num,
                    column=match.start() + 1,
                    context=line.strip(),
                )
            )

        return violations

    def _remove_quoted_strings(self, line: str) -> str:
        """Remove quoted strings from a line to avoid false positives."""
        # Remove double-quoted strings
        result = re.sub(r'"[^"]*"', '""', line)
        # Remove single-quoted strings
        result = re.sub(r"'[^']*'", "''", result)
        return result

    def _strip_comments(self, line: str) -> str:
        """Truncate the line at the first `#` outside a string. Quoted
        strings are already collapsed to empty by `_remove_quoted_strings`,
        so any remaining `#` is a real comment marker. #998 — comments
        were being scanned for banned keywords, so prose like
        ``# for auditability`` produced false-positive violations."""
        idx = line.find("#")
        return line if idx < 0 else line[:idx]

    def format_violations(self, violations: list[Violation]) -> str:
        """Format violations as a human-readable string."""
        if not violations:
            return "No Anti-Turing violations found."

        lines = [f"Found {len(violations)} Anti-Turing violation(s):", ""]

        for v in violations:
            lines.append(f"  Line {v.line}, Column {v.column}: {v.message}")
            lines.append(f"    > {v.context}")
            lines.append("")

        return "\n".join(lines)


def validate_dsl_file(path: Path, strict: bool = False) -> tuple[bool, str]:
    """
    Convenience function to validate a DSL file.

    Args:
        path: Path to the DSL file
        strict: If True, treat warnings as errors

    Returns:
        Tuple of (is_valid, message)
    """
    validator = AntiTuringValidator(strict=strict)
    violations = validator.validate_file(path)

    if not violations:
        return True, "Anti-Turing validation passed."

    return False, validator.format_violations(violations)


def validate_dsl_content(content: str, strict: bool = False) -> tuple[bool, str]:
    """
    Convenience function to validate DSL content.

    Args:
        content: The DSL content to validate
        strict: If True, treat warnings as errors

    Returns:
        Tuple of (is_valid, message)
    """
    validator = AntiTuringValidator(strict=strict)
    violations = validator.validate(content)

    if not violations:
        return True, "Anti-Turing validation passed."

    return False, validator.format_violations(violations)
