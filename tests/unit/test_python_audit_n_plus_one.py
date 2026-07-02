"""Tests for PA-LLM-08 — N+1 queries in user app code.

For-loop and comprehension (#1267) rows share the two tables below —
the `loop-*` / `listcomp-*` / `genexp-*` / `dictcomp-*` / `setcomp-*`
id prefixes keep the shape symmetry visible.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from dazzle.sentinel.agents.python_audit import (
    PythonAuditAgent,
    _detect_n_plus_one,
)


def _parse(src: str) -> ast.Module:
    return ast.parse(src)


# ---------------------------------------------------------------------------
# Positive: queryset-chain / repo-call / len-wrap shapes, in for-loops and
# comprehensions (#1267 — same shapes, different AST node types).
# expected_shape is asserted only when not None.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("src", "expected_shape"),
    [
        # for-loop shapes -----------------------------------------------------
        pytest.param(
            # `for order in orders: x = order.lines.all()` is the canonical shape.
            "for order in orders:\n    x = order.lines.all()\n",
            None,
            id="loop-queryset-all",
        ),
        pytest.param(
            # `.first()` after attribute chain on loop var fires.
            "for order in orders:\n    x = order.payments.first()\n",
            None,
            id="loop-queryset-first",
        ),
        pytest.param(
            # Chained .filter().all() fires (terminator at end of chain).
            "for order in orders:\n    x = order.lines.filter(state='paid').all()\n",
            None,
            id="loop-queryset-filter-terminator",
        ),
        pytest.param(
            # `<x>_repo.fetch(<loopvar>)` fires.
            "for oid in order_ids:\n    x = order_repo.fetch(oid)\n",
            None,
            id="loop-repo-loopvar-arg",
        ),
        pytest.param(
            # `<x>_repo.list(field=<loopvar>.attr)` fires.
            "for order in orders:\n    x = line_repo.list(order_id=order.id)\n",
            None,
            id="loop-repo-loopvar-attr-arg",
        ),
        pytest.param(
            # `len(<loopvar>.attr.all())` fires through the outer len().
            "for order in orders:\n    c = len(order.lines.all())\n",
            None,
            id="loop-len-wrap",
        ),
        # comprehension shapes (#1267) ----------------------------------------
        pytest.param(
            "x = [order.lines.all() for order in orders]\n",
            "queryset",
            id="listcomp-queryset",
        ),
        pytest.param(
            "x = [order_repo.fetch(oid) for oid in ids]\n",
            "repo",
            id="listcomp-repo",
        ),
        pytest.param(
            # `[len(order.lines.all()) for ...]` fires once on the len-wrap.
            "x = [len(order.lines.all()) for order in orders]\n",
            "len_wrap",
            id="listcomp-len-wrap",
        ),
        pytest.param(
            "x = (order.lines.all() for order in orders)\n",
            None,
            id="genexp-queryset",
        ),
        pytest.param(
            # `{order.id: order.lines.all() for ...}` fires on the value expr.
            "x = {order.id: order.lines.all() for order in orders}\n",
            "queryset",
            id="dictcomp-value-side",
        ),
        pytest.param(
            "x = {order.lines.first() for order in orders}\n",
            None,
            id="setcomp-queryset-first",
        ),
        pytest.param(
            # Nested comprehension accumulates targets — both o and x are loop vars.
            "y = [x.lines.all() for o in orders for x in o.items]\n",
            "queryset",
            id="listcomp-nested-targets",
        ),
    ],
)
def test_n_plus_one_shape_fires(src: str, expected_shape: str | None) -> None:
    hits = _detect_n_plus_one(_parse(src), Path("app/x.py"))
    assert len(hits) == 1
    if expected_shape is not None:
        assert hits[0].shape == expected_shape


# ---------------------------------------------------------------------------
# Negative: false-positive guards
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "src",
    [
        pytest.param(
            # Plain attribute access on loop var (no method call) doesn't fire.
            "for order in orders:\n    x = order.id\n",
            id="loop-attribute-access-no-call",
        ),
        pytest.param(
            # `.upper()` is not a queryset terminator.
            "for s in strings:\n    x = s.upper()\n",
            id="loop-method-outside-queryset-set",
        ),
        pytest.param(
            # Repo call inside a loop whose args don't reference the loop var.
            "for i in range(10):\n    x = order_repo.fetch(static_id)\n",
            id="loop-call-no-loopvar-reference",
        ),
        pytest.param(
            # Repo call at module scope doesn't fire.
            "result = repo.list(scope={'x': 1})\n",
            id="repo-call-outside-loop",
        ),
        pytest.param(
            # `d.get(k)` must not fire — `get` is excluded from _QUERYSET_METHODS.
            "for k in keys:\n    x = mapping.get(k)\n",
            id="loop-dict-get-not-queryset",
        ),
        pytest.param(
            # `[order.id for order in orders]` is just attribute access — no fire.
            "x = [order.id for order in orders]\n",
            id="listcomp-attribute-access-only",
        ),
        pytest.param(
            # `[s.upper() for s in strings]` — `.upper()` is not a queryset terminator.
            "x = [s.upper() for s in strings]\n",
            id="listcomp-method-outside-set",
        ),
    ],
)
def test_n_plus_one_negative_no_fire(src: str) -> None:
    assert _detect_n_plus_one(_parse(src), Path("app/x.py")) == []


# ---------------------------------------------------------------------------
# Suppression
# ---------------------------------------------------------------------------


def test_noqa_suppression_on_for_line(tmp_path: Path) -> None:
    """`# noqa: PA-LLM-08` on the `for:` line suppresses every hit in the loop body."""
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "x.py").write_text(
        "def f():\n"
        "    for order in orders:  # noqa: PA-LLM-08 - prefetched\n"
        "        x = order.lines.all()\n"
    )
    agent = PythonAuditAgent(project_path=tmp_path)
    assert agent.check_n_plus_one_in_user_code(appspec=None) == []  # type: ignore[arg-type]


def test_noqa_suppression_on_call_line(tmp_path: Path) -> None:
    """`# noqa: PA-LLM-08` on the offending call line suppresses just that hit."""
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "x.py").write_text(
        "def f():\n    for order in orders:\n        x = order.lines.all()  # noqa: PA-LLM-08\n"
    )
    agent = PythonAuditAgent(project_path=tmp_path)
    assert agent.check_n_plus_one_in_user_code(appspec=None) == []  # type: ignore[arg-type]


def test_listcomp_noqa_suppression(tmp_path: Path) -> None:
    """`# noqa: PA-LLM-08` on the comprehension's line suppresses the finding."""
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "x.py").write_text(
        "def f(orders):\n"
        "    return [order.lines.all() for order in orders]  # noqa: PA-LLM-08 - prefetched\n"
    )
    agent = PythonAuditAgent(project_path=tmp_path)
    assert agent.check_n_plus_one_in_user_code(appspec=None) == []  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Integration: heuristic populates Finding correctly
# ---------------------------------------------------------------------------


def test_heuristic_yields_finding_with_catalogue_entry(tmp_path: Path) -> None:
    """End-to-end: a real PA-LLM-08 finding carries catalogue_entry + URL."""
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "render.py").write_text(
        "def render(orders):\n"
        "    out = []\n"
        "    for order in orders:\n"
        "        out.append(order.lines.all())\n"
        "    return out\n"
    )

    agent = PythonAuditAgent(project_path=tmp_path)
    findings = agent.check_n_plus_one_in_user_code(appspec=None)  # type: ignore[arg-type]

    assert len(findings) == 1
    f = findings[0]
    assert f.heuristic_id == "PA-LLM-08"
    assert f.catalogue_entry == "n-plus-one-in-user-code"
    assert f.remediation is not None
    assert any(
        "docs/counter-priors/n-plus-one-in-user-code.md" in ref for ref in f.remediation.references
    )


def test_heuristic_skips_tests_and_scripts(tmp_path: Path) -> None:
    """tests/ and scripts/ files are out of scope."""
    for sub in ("tests", "scripts"):
        d = tmp_path / sub
        d.mkdir()
        (d / "f.py").write_text("for x in xs:\n    y = x.lines.all()\n")

    agent = PythonAuditAgent(project_path=tmp_path)
    assert agent.check_n_plus_one_in_user_code(appspec=None) == []  # type: ignore[arg-type]
