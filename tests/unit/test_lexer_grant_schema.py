"""Test grant_schema keyword tokenization."""

from pathlib import Path

from dazzle.core.lexer import TokenType, tokenize


def test_grant_schema_keyword_tokenized():
    tokens = tokenize("grant_schema", Path("test.dsl"))
    assert tokens[0].type == TokenType.GRANT_SCHEMA
    assert tokens[0].value == "grant_schema"
