"""#1360: parse errors suggest fixes instead of dead-ending.

Unknown field types resolve foreign-language aliases (string → str(N)) and
fuzzy typos (emial → email); unknown keywords in dispatch-parsed blocks name
the legal keywords and the closest match. The error channel is the
highest-frequency teaching moment for agents — corrections should resolve
from the message alone.
"""

from pathlib import Path

import pytest

from dazzle.core.parser import parse_modules

PREAMBLE = 'module sug\n\napp sug "Sug"\n\n'


def _error_for(tmp_path: Path, body: str) -> str:
    f = tmp_path / "app.dsl"
    f.write_text(PREAMBLE + body, encoding="utf-8")
    with pytest.raises(Exception) as exc_info:
        parse_modules([f])
    return str(exc_info.value)


@pytest.mark.parametrize(
    ("bad_type", "expected_suggestion"),
    [
        ("string", "str(N)"),
        ("varchar", "str(N)"),
        ("integer", "int"),
        ("boolean", "bool"),
        ("numeric", "decimal(p,s)"),
        ("timestamp", "datetime"),
        ("foreign_key", "ref Entity"),
        ("emial", "email"),  # fuzzy, not aliased
        ("datetme", "datetime"),  # fuzzy, not aliased
    ],
)
def test_unknown_type_suggests_fix(tmp_path: Path, bad_type: str, expected_suggestion: str) -> None:
    msg = _error_for(tmp_path, f'entity Doc "Doc":\n  id: uuid pk\n  f: {bad_type} required\n')
    assert f"Unknown type: {bad_type!r}" in msg
    assert f"Did you mean {expected_suggestion!r}?" in msg
    assert "Valid types:" in msg


def test_unknown_type_without_match_still_lists_valid_types(tmp_path: Path) -> None:
    msg = _error_for(tmp_path, 'entity Doc "Doc":\n  id: uuid pk\n  f: zzqx required\n')
    assert "Unknown type: 'zzqx'" in msg
    assert "Did you mean" not in msg
    assert "Valid types:" in msg
    assert "ref" in msg and "uuid" in msg


def test_unknown_block_keyword_suggests_closest() -> None:
    # Exercise the dispatch default handler directly (most production blocks
    # override on_unknown with tolerant recovery) — a typo'd keyword must
    # name the legal keywords and the closest match.
    from dazzle.core.dsl_parser_impl.base import BaseParser
    from dazzle.core.dsl_parser_impl.dispatch import parse_block_with_dispatch
    from dazzle.core.lexer import Lexer, TokenType

    text = 'persona x "X":\n  enbled: true\n'
    tokens = Lexer(text, file=Path("<test>")).tokenize()
    parser = BaseParser(tokens, file=Path("<test>"))
    parser.expect(TokenType.PERSONA)
    parser.advance()
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)

    with pytest.raises(Exception) as exc_info:
        parse_block_with_dispatch(
            parser,
            first_class_keywords={TokenType.DESCRIPTION: lambda p, s: None},
            ident_keywords={"enabled": lambda p, s: None},
            state=object(),
        )
    msg = str(exc_info.value)
    assert "Unknown keyword in block: 'enbled'" in msg
    assert "Did you mean 'enabled'?" in msg
    assert "Valid keywords here: description, enabled" in msg
