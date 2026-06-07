"""Gate: no UNGUARDED ``ir.<Enum>(token.value)`` in the DSL parser surface.

Constructing an IR enum directly from a token value leaks the enum's ``ValueError``
out of the parser, which only ever promises ``ParseError`` — a fuzz-discoverable crash
class (see #1342 / `docs/history/2026-06-07-fuzz-catch-foreign-constraint-kind.md`). The
guarded path is ``self.enum_from_token(ir.SomeKind, token)`` (BaseParser), which converts
the ValueError into a clean ParseError listing the valid values.

A raw ``ir.<Enum>(x.value)`` is allowed ONLY inside a ``try`` (a few pre-existing sites
keep their hand-tuned error messages); everywhere else it must use ``enum_from_token``.
This gate fails on any unguarded site so a new one can't be added. There is no allowlist —
the migration in #1342 drained it to zero.
"""

from __future__ import annotations

import ast
import enum
from pathlib import Path

import dazzle.core.ir as ir

_PARSER_DIR = Path(__file__).resolve().parents[2] / "src" / "dazzle" / "core" / "dsl_parser_impl"
_ENUM_NAMES = {
    n for n in dir(ir) if isinstance(getattr(ir, n), type) and issubclass(getattr(ir, n), enum.Enum)
}


def _enclosed_in_try(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    cur: ast.AST | None = node
    while cur in parents:
        cur = parents[cur]
        if isinstance(cur, ast.Try):
            return True
    return False


def _unguarded_sites() -> list[str]:
    hits: list[str] = []
    for path in sorted(_PARSER_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        parents: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "ir"
                and node.func.attr in _ENUM_NAMES
                and node.args
                and isinstance(node.args[0], ast.Attribute)
                and node.args[0].attr == "value"
                and not _enclosed_in_try(node, parents)
            ):
                hits.append(f"{path.name}:{node.lineno}  ir.{node.func.attr}(…value)")
    return hits


def test_no_unguarded_enum_from_token() -> None:
    sites = _unguarded_sites()
    assert not sites, (
        "Unguarded ir.<Enum>(token.value) in the parser (leaks ValueError instead of "
        "ParseError). Use self.enum_from_token(ir.<Enum>, token) instead:\n  " + "\n  ".join(sites)
    )
