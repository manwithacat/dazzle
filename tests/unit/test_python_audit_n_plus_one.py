"""Tests for PA-LLM-08 — N+1 queries in user app code."""

from __future__ import annotations

import ast
from pathlib import Path

from dazzle.sentinel.agents.python_audit import (
    PythonAuditAgent,
    _detect_n_plus_one,
)


def _parse(src: str) -> ast.Module:
    return ast.parse(src)


# ---------------------------------------------------------------------------
# Positive: queryset chain shapes
# ---------------------------------------------------------------------------


def test_queryset_chain_all() -> None:
    """`for order in orders: x = order.lines.all()` is the canonical shape."""
    src = "for order in orders:\n    x = order.lines.all()\n"
    hits = _detect_n_plus_one(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_queryset_chain_first() -> None:
    """`.first()` after attribute chain on loop var fires."""
    src = "for order in orders:\n    x = order.payments.first()\n"
    hits = _detect_n_plus_one(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_queryset_chain_filter_terminator() -> None:
    """Chained .filter().all() fires (terminator at end of chain)."""
    src = "for order in orders:\n    x = order.lines.filter(state='paid').all()\n"
    hits = _detect_n_plus_one(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


# ---------------------------------------------------------------------------
# Positive: repo-call shape
# ---------------------------------------------------------------------------


def test_repo_call_with_loopvar_arg() -> None:
    """`<x>_repo.fetch(<loopvar>)` fires."""
    src = "for oid in order_ids:\n    x = order_repo.fetch(oid)\n"
    hits = _detect_n_plus_one(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_repo_call_with_loopvar_attr_arg() -> None:
    """`<x>_repo.list(field=<loopvar>.attr)` fires."""
    src = "for order in orders:\n    x = line_repo.list(order_id=order.id)\n"
    hits = _detect_n_plus_one(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


# ---------------------------------------------------------------------------
# Positive: len-wrapping shape
# ---------------------------------------------------------------------------


def test_len_wrapped_queryset() -> None:
    """`len(<loopvar>.attr.all())` fires through the outer len()."""
    src = "for order in orders:\n    c = len(order.lines.all())\n"
    hits = _detect_n_plus_one(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


# ---------------------------------------------------------------------------
# Negative: false-positive guards
# ---------------------------------------------------------------------------


def test_negative_attribute_access_no_call() -> None:
    """Plain attribute access on loop var (no method call) doesn't fire."""
    src = "for order in orders:\n    x = order.id\n"
    assert _detect_n_plus_one(_parse(src), Path("app/x.py")) == []


def test_negative_method_outside_queryset_set() -> None:
    """`.upper()` is not a queryset terminator."""
    src = "for s in strings:\n    x = s.upper()\n"
    assert _detect_n_plus_one(_parse(src), Path("app/x.py")) == []


def test_negative_call_no_loopvar_reference() -> None:
    """Repo call inside a loop whose args don't reference the loop var doesn't fire."""
    src = "for i in range(10):\n    x = order_repo.fetch(static_id)\n"
    assert _detect_n_plus_one(_parse(src), Path("app/x.py")) == []


def test_negative_repo_call_outside_loop() -> None:
    """Repo call at module scope doesn't fire."""
    src = "result = repo.list(scope={'x': 1})\n"
    assert _detect_n_plus_one(_parse(src), Path("app/x.py")) == []


def test_negative_dict_get_not_treated_as_queryset() -> None:
    """`d.get(k)` must not fire — `get` is excluded from _QUERYSET_METHODS."""
    src = "for k in keys:\n    x = mapping.get(k)\n"
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


# ---------------------------------------------------------------------------
# Comprehension N+1 (#1267) — same shapes, different AST node types.
# ---------------------------------------------------------------------------


def test_listcomp_queryset_chain() -> None:
    """`[order.lines.all() for order in orders]` fires."""
    src = "x = [order.lines.all() for order in orders]\n"
    hits = _detect_n_plus_one(_parse(src), Path("app/x.py"))
    assert len(hits) == 1
    assert hits[0].shape == "queryset"


def test_listcomp_repo_call() -> None:
    """`[order_repo.fetch(oid) for oid in ids]` fires."""
    src = "x = [order_repo.fetch(oid) for oid in ids]\n"
    hits = _detect_n_plus_one(_parse(src), Path("app/x.py"))
    assert len(hits) == 1
    assert hits[0].shape == "repo"


def test_listcomp_len_wrap() -> None:
    """`[len(order.lines.all()) for order in orders]` fires once on the len-wrap."""
    src = "x = [len(order.lines.all()) for order in orders]\n"
    hits = _detect_n_plus_one(_parse(src), Path("app/x.py"))
    assert len(hits) == 1
    assert hits[0].shape == "len_wrap"


def test_genexp_queryset_chain() -> None:
    """`(order.lines.all() for order in orders)` (generator expression) fires."""
    src = "x = (order.lines.all() for order in orders)\n"
    hits = _detect_n_plus_one(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_dictcomp_value_side() -> None:
    """`{order.id: order.lines.all() for order in orders}` fires on the value expr."""
    src = "x = {order.id: order.lines.all() for order in orders}\n"
    hits = _detect_n_plus_one(_parse(src), Path("app/x.py"))
    assert len(hits) == 1
    assert hits[0].shape == "queryset"


def test_setcomp_queryset_chain() -> None:
    """`{order.lines.first() for order in orders}` (set comprehension) fires."""
    src = "x = {order.lines.first() for order in orders}\n"
    hits = _detect_n_plus_one(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_nested_comprehension_accumulates_targets() -> None:
    """`[x.lines.all() for o in orders for x in o.items]` — both o and x are loop vars."""
    src = "y = [x.lines.all() for o in orders for x in o.items]\n"
    hits = _detect_n_plus_one(_parse(src), Path("app/x.py"))
    assert len(hits) == 1
    assert hits[0].shape == "queryset"


def test_negative_listcomp_attribute_access_only() -> None:
    """`[order.id for order in orders]` is just attribute access — no fire."""
    src = "x = [order.id for order in orders]\n"
    assert _detect_n_plus_one(_parse(src), Path("app/x.py")) == []


def test_negative_listcomp_method_outside_set() -> None:
    """`[s.upper() for s in strings]` — `.upper()` is not a queryset terminator."""
    src = "x = [s.upper() for s in strings]\n"
    assert _detect_n_plus_one(_parse(src), Path("app/x.py")) == []


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
