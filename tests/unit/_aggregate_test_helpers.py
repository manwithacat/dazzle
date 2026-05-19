"""Helper for constructing :class:`AggregateRef` in tests from the DSL
surface syntax.

Pre-ADR-0024 tests passed aggregates as strings (``"count(Task where
status = open)"``). Post-migration the runtime consumes typed
:class:`AggregateRef`. To minimise churn in the dozens of test files,
this helper parses the same surface syntax through the real DSL parser
— producing the same IR the runtime would receive from a parsed
``aggregate:`` block.

Usage::

    from tests.unit._aggregate_test_helpers import agg

    metrics = await _compute_aggregate_metrics(
        aggregates={"total": agg("count(Task where status = open)")},
        ...
    )
"""

from __future__ import annotations

from pathlib import Path

from dazzle.core.dsl_parser_impl import Parser
from dazzle.core.ir import AggregateRef
from dazzle.core.lexer import tokenize


def agg(expr: str) -> AggregateRef:
    """Parse a single aggregate call from DSL surface syntax to typed IR.

    Equivalent to what the workspace parser produces when it encounters
    the same expression inside an ``aggregate:`` block.
    """
    tokens = tokenize(expr + "\n", Path("test.dsl"))
    return Parser(tokens, Path("test.dsl")).parse_aggregate_ref()
