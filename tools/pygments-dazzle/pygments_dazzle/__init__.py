"""Pygments lexer for the Dazzle DSL.

Registered via the ``pygments.lexers`` entry point (see ``pyproject.toml``) so
``mkdocs`` / ``pymdownx`` syntax-highlight ```dsl fenced code blocks across the
Dazzle documentation. Standalone on purpose — it depends only on Pygments, so
the docs build does not need the full ``dazzle`` runtime installed.
"""

from pygments.lexer import RegexLexer, words
from pygments.token import (
    Comment,
    Keyword,
    Name,
    Number,
    Operator,
    Punctuation,
    String,
    Text,
    Whitespace,
)

__all__ = ["DazzleDslLexer"]

# Top-level constructs + structural words. Mirrors the construct list in
# CLAUDE.md; a construct missing here simply renders unhighlighted (as a plain
# identifier), so exact parity with the parser is not required.
_KEYWORDS = (
    "module",
    "use",
    "app",
    "entity",
    "surface",
    "workspace",
    "experience",
    "island",
    "service",
    "foreign_model",
    "integration",
    "ledger",
    "transaction",
    "process",
    "schedule",
    "story",
    "archetype",
    "persona",
    "scenario",
    "enum",
    "webhook",
    "approval",
    "sla",
    "rhythm",
    "feedback_widget",
    "subprocessor",
    "analytics",
    "guide",
    "test",
    "flow",
    "rule",
    "message",
    "channel",
    "asset",
    "document",
    "template",
    "demo",
    "event_model",
    "subscribe",
    "projection",
    "stream",
    "hless",
    "policies",
    "tenancy",
    "interfaces",
    "data_products",
    "llm_model",
    "llm_config",
    "llm_intent",
    "notification",
    "job",
    "audit",
    "search",
    "grant_schema",
    "param",
    "question",
    "step",
    "section",
    "field",
    "uses",
    "permit",
    "scope",
    "as",
    "via",
    "from",
    "to",
)

_TYPES = (
    "uuid",
    "str",
    "int",
    "bool",
    "text",
    "float",
    "decimal",
    "date",
    "datetime",
    "time",
    "json",
    "ref",
)

_MODIFIERS = ("pk", "required", "unique", "optional", "indexed", "default")

_CONSTANTS = ("true", "false", "null")

_WORD_OPERATORS = ("and", "or", "not", "AND", "OR", "NOT")


class DazzleDslLexer(RegexLexer):
    """Syntax highlighting for the Dazzle DSL (``.dsl`` files)."""

    name = "Dazzle DSL"
    aliases = ["dsl", "dazzle"]
    filenames = ["*.dsl"]
    url = "https://github.com/manwithacat/dazzle"

    tokens = {
        "root": [
            (r"\s+", Whitespace),
            (r"#.*$", Comment.Single),
            (r'"', String, "string"),
            (words(_KEYWORDS, prefix=r"\b", suffix=r"\b"), Keyword),
            (words(_TYPES, prefix=r"\b", suffix=r"\b"), Keyword.Type),
            (words(_MODIFIERS, prefix=r"\b", suffix=r"\b"), Keyword.Pseudo),
            (words(_CONSTANTS, prefix=r"\b", suffix=r"\b"), Keyword.Constant),
            (words(_WORD_OPERATORS, prefix=r"\b", suffix=r"\b"), Operator.Word),
            # `field_name:` labels — checked after keywords so construct names win.
            (r"[A-Za-z_]\w*(?=\s*:)", Name.Label),
            (r"-?\d+\.\d+", Number.Float),
            (r"-?\d+", Number.Integer),
            (r"[A-Za-z_]\w*", Name),
            (r"[=!<>]=?", Operator),
            (r"[-:=(){}\[\],.]", Punctuation),
            (r".", Text),
        ],
        "string": [
            (r'[^"\\]+', String),
            (r"\\.", String.Escape),
            (r'"', String, "#pop"),
        ],
    }
