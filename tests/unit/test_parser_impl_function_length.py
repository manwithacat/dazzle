"""Drift gate: function-length budget for ``dsl_parser_impl/`` (#1088).

The dispatch-table sweep (v0.70.14 → v0.70.34) collapsed every
keyword-dispatch monolith over 100 lines. This gate prevents new
oversized parsers from accumulating — every function in the
parser-impl tree must be ≤120 lines (the issue's "Enforcement"
section sets this budget; current max is ~99 in the file we just
refactored, so the 21-line slack absorbs the next legitimate
addition).

What this gate enforces:
    Every ``def`` in ``src/dazzle/core/dsl_parser_impl/*.py`` has
    body length ≤ MAX_LINES. The AST measure (``end_lineno - lineno``)
    counts the function header through the last body line, matching
    the metric the original #1088 done-criterion used.

How to satisfy a violation:
    Refactor along one of the patterns proven in v0.70.14 →
    v0.70.34:
      * Keyword-dispatch shape → use
        ``dazzle.core.dsl_parser_impl.dispatch.parse_block_with_dispatch``
        + a state dataclass + per-keyword ``_kw_*`` free functions.
      * Sequential/phased shape (parse_experience_step) → extract
        each phase as a private mixin method that conditionally
        consumes its keyword and mutates the state accumulator.
      * Dash-list shape (_parse_pipeline_stages_block,
        _parse_action_cards_block, …) → extract a
        ``_parse_<entry>`` per-entry helper; the block becomes a
        thin loop.

The gate is intentionally generous — the working limit during the
sweep was ~100 lines but #1088's enforcement section specifies 120.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

MAX_LINES = 120
ROOT = Path(__file__).resolve().parents[2]
PARSER_IMPL = ROOT / "src" / "dazzle" / "core" / "dsl_parser_impl"


def _function_lengths(path: Path) -> list[tuple[int, str, int]]:
    """Return [(length, qualname, line)] for every FunctionDef in ``path``."""
    src = path.read_text()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []

    results: list[tuple[int, str, int]] = []

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                visit(child, f"{prefix}{child.name}.")
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                length = (child.end_lineno or child.lineno) - child.lineno
                results.append((length, f"{prefix}{child.name}", child.lineno))
                visit(child, f"{prefix}{child.name}.")

    visit(tree, "")
    return results


def test_no_oversized_parser_functions() -> None:
    """No function in ``dsl_parser_impl/`` may exceed ``MAX_LINES``.

    Fails the build with the offender list when violated so the
    fix target is obvious from the error.
    """
    violations: list[tuple[int, str, str]] = []
    for path in sorted(PARSER_IMPL.glob("*.py")):
        rel = path.relative_to(ROOT)
        for length, qualname, line in _function_lengths(path):
            if length > MAX_LINES:
                violations.append((length, qualname, f"{rel}:{line}"))

    if violations:
        violations.sort(reverse=True)
        msg = (
            f"Functions in dsl_parser_impl/ exceeding {MAX_LINES} lines "
            f"({len(violations)} offenders):\n"
        )
        for length, qualname, loc in violations:
            msg += f"  {length:>4}  {qualname}   ({loc})\n"
        msg += (
            "\nRefactor along one of the patterns proven in v0.70.14 → "
            "v0.70.34 — see the module docstring for guidance."
        )
        pytest.fail(msg)
