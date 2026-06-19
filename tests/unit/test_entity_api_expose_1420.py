"""#1420 Slice 2 — `api:` per-op generated-REST allowlist on an entity.

`api: list, read` exposes only those generated routes; `api: none` exposes none;
absent = all ops (backward compatible). Invalid ops are parse errors.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError


def _entity(extra: str, name: str = "Job"):
    dsl = f"""module t
app t "Test"
entity {name} "{name}":
  id: uuid pk
  title: str(80)
{extra}
"""
    module = parse_dsl(dsl, Path("test.dsl"))[5]
    return next(e for e in module.entities if e.name == name)


class TestEntityApiExpose:
    def test_absent_is_none_all_ops(self) -> None:
        assert _entity("").api_expose is None

    def test_allowlist_ops(self) -> None:
        assert _entity("  expose: list, read").api_expose == ("list", "read")

    def test_none_is_empty_tuple(self) -> None:
        assert _entity("  expose: none").api_expose == ()

    def test_invalid_op_is_parse_error(self) -> None:
        with pytest.raises(ParseError):
            _entity("  expose: list, bogus")
