"""Top-level construct keywords tokenise to their reserved TokenType."""

from pathlib import Path

import pytest

from dazzle.core.lexer import TokenType, tokenize


@pytest.mark.parametrize(
    ("source", "token_type"),
    [
        pytest.param("grant_schema", TokenType.GRANT_SCHEMA, id="grant_schema"),
        pytest.param("rhythm onboarding", TokenType.RHYTHM, id="rhythm"),
        pytest.param("phase discovery", TokenType.PHASE, id="phase"),
        pytest.param("scene browse", TokenType.SCENE, id="scene"),
    ],
)
def test_keyword_tokenised(source: str, token_type: TokenType) -> None:
    first = tokenize(source, Path("test.dsl"))[0]
    assert (first.type, first.value) == (token_type, source.split()[0])
