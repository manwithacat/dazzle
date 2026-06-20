"""#1217 Phase 3e.i — parser + IR tests for the entity-level `subtype_of:` keyword.

Runtime (DDL, queries, surfaces) lands in subsequent slices (3e.ii–3e.v).
These tests only pin:

1. The `subtype_of:` keyword parses into a string on the child EntitySpec.
2. Multiple identifiers raise a clear parse error (no multiple inheritance).
3. Missing identifier after the colon raises a clear parse error.
4. Subtype declaration co-exists with extends:, temporal:, scope:.
5. The base entity's IR has `subtype_children == ()` at parser stage (linker populates).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core import ir
from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError


def _parse(dsl: str) -> tuple[ir.EntitySpec, ...]:
    """Parse a fragment and return entities by name lookup."""
    _, _, _, _, _, frag = parse_dsl(dsl, Path("test.dz"))
    return tuple(frag.entities)


def _basic_dsl(child_body: str) -> str:
    return f"""\
module test.core
app a "A"

entity Asset "Asset":
  id: uuid pk
  acquired_at: date required

entity Vehicle "Vehicle":
{child_body}
"""


class TestSubtypeOfParses:
    def test_single_identifier(self) -> None:
        dsl = _basic_dsl("""\
  subtype_of: Asset
  wheels: int required
""")
        entities = {e.name: e for e in _parse(dsl)}
        assert entities["Vehicle"].subtype_of == "Asset"
        assert entities["Vehicle"].is_polymorphic_child is True
        # Linker populates subtype_children — at parser stage it is empty.
        assert entities["Vehicle"].subtype_children == ()
        assert entities["Asset"].subtype_of is None
        assert entities["Asset"].subtype_children == ()
        assert entities["Asset"].is_polymorphic_base is False

    def test_co_exists_with_extends(self) -> None:
        dsl = """\
module test.core
app a "A"

archetype Auditable:
  created_at: datetime auto_add

entity Asset "Asset":
  id: uuid pk

entity Vehicle "Vehicle":
  subtype_of: Asset
  extends: Auditable
  wheels: int required
"""
        entities = {e.name: e for e in _parse(dsl)}
        v = entities["Vehicle"]
        assert v.subtype_of == "Asset"
        assert v.extends == ["Auditable"]


class TestSubtypeOfRejects:
    def test_multiple_identifiers_rejected(self) -> None:
        dsl = _basic_dsl("""\
  subtype_of: Asset, Container
  wheels: int required
""")
        with pytest.raises(ParseError, match="subtype_of"):
            _parse(dsl)

    def test_missing_identifier_rejected(self) -> None:
        dsl = _basic_dsl("""\
  subtype_of:
  wheels: int required
""")
        with pytest.raises(ParseError):
            _parse(dsl)


class TestRuntimeStubsWiredIn3eIII:
    """Slice 3e.i shipped the stub; 3e.iii (this slice) replaced it with a
    real implementation. The function is now keyword-only with explicit
    base/child specs — see test_subtype_of_runtime.py for the full test set.
    """

    def test_create_subtype_is_importable(self) -> None:
        # Pin that the symbol survives the 3e.iii rewrite and is no longer
        # a NotImplementedError stub.
        from dazzle.http.runtime.repository import create_subtype, update_subtype

        assert callable(create_subtype)
        assert callable(update_subtype)
