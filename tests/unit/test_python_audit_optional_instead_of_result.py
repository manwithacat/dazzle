"""Tests for PA-LLM-09 — optional-instead-of-result."""

from __future__ import annotations

import ast
from pathlib import Path

from dazzle.sentinel.agents.python_audit import (
    PythonAuditAgent,
    _detect_optional_instead_of_result,
)


def _parse(src: str) -> ast.Module:
    return ast.parse(src)


# ---------------------------------------------------------------------------
# Positive: multiple return None
# ---------------------------------------------------------------------------


def test_two_return_none_fires() -> None:
    src = (
        "def parse(text: str) -> int | None:\n"
        "    if not text:\n"
        "        return None\n"
        "    if text.isspace():\n"
        "        return None\n"
        "    return int(text)\n"
    )
    hits = _detect_optional_instead_of_result(_parse(src), Path("app/x.py"))
    assert len(hits) == 1
    assert hits[0].shape == "multi_return_none"


def test_three_return_none_fires_once() -> None:
    """Multiple return None statements yield one finding, not three."""
    src = (
        "def f(x) -> str | None:\n"
        "    if not x: return None\n"
        "    if x < 0: return None\n"
        "    if x > 100: return None\n"
        "    return str(x)\n"
    )
    hits = _detect_optional_instead_of_result(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_optional_legacy_syntax() -> None:
    src = (
        "from typing import Optional\n"
        "def f(x) -> Optional[int]:\n"
        "    if x is None: return None\n"
        "    if x < 0: return None\n"
        "    return x\n"
    )
    hits = _detect_optional_instead_of_result(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_pipe_none_left_position() -> None:
    """`None | int` (None on the left) is the same union as `int | None`."""
    src = (
        "def f(x) -> None | int:\n"
        "    if x == 0: return None\n"
        "    if x < 0: return None\n"
        "    return x\n"
    )
    hits = _detect_optional_instead_of_result(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_bare_return_counts_as_none() -> None:
    """A bare `return` (no value) is equivalent to `return None`."""
    src = (
        "def f(x) -> int | None:\n    if x == 0: return\n    if x < 0: return None\n    return x\n"
    )
    hits = _detect_optional_instead_of_result(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_async_function_fires() -> None:
    src = (
        "async def fetch(uid) -> int | None:\n"
        "    if not uid: return None\n"
        "    if uid < 0: return None\n"
        "    return await load(uid)\n"
    )
    hits = _detect_optional_instead_of_result(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


# ---------------------------------------------------------------------------
# Positive: multi-exception catch
# ---------------------------------------------------------------------------


def test_multi_exception_catch_fires() -> None:
    """Single return None but except (X, Y) catching >=2 types fires."""
    src = (
        "def parse(text) -> int | None:\n"
        "    try:\n"
        "        return int(text)\n"
        "    except (ValueError, TypeError):\n"
        "        return None\n"
    )
    hits = _detect_optional_instead_of_result(_parse(src), Path("app/x.py"))
    assert len(hits) == 1
    assert hits[0].shape == "multi_exception_catch"


# ---------------------------------------------------------------------------
# Negative: false-positive guards
# ---------------------------------------------------------------------------


def test_negative_single_return_none() -> None:
    """Single failure mode is legitimate Optional usage — no fire."""
    src = (
        "def find_user(uid) -> User | None:\n"
        "    if uid not in users: return None\n"
        "    return users[uid]\n"
    )
    assert _detect_optional_instead_of_result(_parse(src), Path("app/x.py")) == []


def test_negative_no_optional_return() -> None:
    """Function returns int (not int | None) — out of scope even with two return None."""
    src = "def f(x) -> int:\n    if x == 0: return None\n    if x < 0: return None\n    return x\n"
    assert _detect_optional_instead_of_result(_parse(src), Path("app/x.py")) == []


def test_negative_nested_function_returns_dont_count() -> None:
    """`return None` inside a nested def doesn't contribute to the outer count."""
    src = (
        "def outer(x) -> int | None:\n"
        "    def inner():\n"
        "        if x == 0: return None\n"
        "        if x < 0: return None\n"
        "        return x\n"
        "    return inner() if x else None\n"
    )
    assert _detect_optional_instead_of_result(_parse(src), Path("app/x.py")) == []


def test_negative_single_exception_catch() -> None:
    """`except KeyError: return None` (one type only) doesn't fire."""
    src = (
        "def get(d, k) -> int | None:\n"
        "    try:\n"
        "        return d[k]\n"
        "    except KeyError:\n"
        "        return None\n"
    )
    assert _detect_optional_instead_of_result(_parse(src), Path("app/x.py")) == []


def test_negative_no_return_annotation() -> None:
    """Function without return annotation doesn't fire."""
    src = "def f(x):\n    if x: return None\n    return None\n"
    assert _detect_optional_instead_of_result(_parse(src), Path("app/x.py")) == []


# ---------------------------------------------------------------------------
# Suppression
# ---------------------------------------------------------------------------


def test_noqa_suppression_on_def(tmp_path: Path) -> None:
    """`# noqa: PA-LLM-09` on the def line suppresses the finding."""
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "x.py").write_text(
        "def lookup(k) -> int | None:  # noqa: PA-LLM-09 - both Nones mean 'miss'\n"
        "    if not k: return None\n"
        "    if k not in cache: return None\n"
        "    return cache[k]\n"
    )
    agent = PythonAuditAgent(project_path=tmp_path)
    assert agent.check_optional_instead_of_result(appspec=None) == []  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------


def test_heuristic_yields_finding_with_catalogue_entry(tmp_path: Path) -> None:
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "parse.py").write_text(
        "def parse(text: str) -> int | None:\n"
        "    if not text: return None\n"
        "    if text.isspace(): return None\n"
        "    return int(text)\n"
    )
    agent = PythonAuditAgent(project_path=tmp_path)
    findings = agent.check_optional_instead_of_result(appspec=None)  # type: ignore[arg-type]
    assert len(findings) == 1
    f = findings[0]
    assert f.heuristic_id == "PA-LLM-09"
    assert f.catalogue_entry == "optional-instead-of-result"
    assert f.remediation is not None
    assert any(
        "docs/counter-priors/optional-instead-of-result.md" in ref
        for ref in f.remediation.references
    )


def test_heuristic_skips_tests_and_scripts(tmp_path: Path) -> None:
    for sub in ("tests", "scripts"):
        d = tmp_path / sub
        d.mkdir()
        (d / "f.py").write_text(
            "def f(x) -> int | None:\n"
            "    if not x: return None\n"
            "    if x < 0: return None\n"
            "    return x\n"
        )
    agent = PythonAuditAgent(project_path=tmp_path)
    assert agent.check_optional_instead_of_result(appspec=None) == []  # type: ignore[arg-type]
