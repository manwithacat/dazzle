"""Tests for PA-LLM-09 — optional-instead-of-result.

The multi-return-None and multi-exception-catch arms share the two tables
below — expected_shape is asserted only when not None.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from dazzle.sentinel.agents.python_audit import (
    PythonAuditAgent,
    _detect_optional_instead_of_result,
)


def _parse(src: str) -> ast.Module:
    return ast.parse(src)


# ---------------------------------------------------------------------------
# Positive: multiple return None + multi-exception catch shapes.
# expected_shape is asserted only when not None.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("src", "expected_shape"),
    [
        pytest.param(
            "def parse(text: str) -> int | None:\n"
            "    if not text:\n"
            "        return None\n"
            "    if text.isspace():\n"
            "        return None\n"
            "    return int(text)\n",
            "multi_return_none",
            id="two-return-none",
        ),
        pytest.param(
            # Multiple return None statements yield one finding, not three.
            "def f(x) -> str | None:\n"
            "    if not x: return None\n"
            "    if x < 0: return None\n"
            "    if x > 100: return None\n"
            "    return str(x)\n",
            None,
            id="three-return-none-fires-once",
        ),
        pytest.param(
            "from typing import Optional\n"
            "def f(x) -> Optional[int]:\n"
            "    if x is None: return None\n"
            "    if x < 0: return None\n"
            "    return x\n",
            None,
            id="optional-legacy-syntax",
        ),
        pytest.param(
            # `None | int` (None on the left) is the same union as `int | None`.
            "def f(x) -> None | int:\n"
            "    if x == 0: return None\n"
            "    if x < 0: return None\n"
            "    return x\n",
            None,
            id="pipe-none-left-position",
        ),
        pytest.param(
            # A bare `return` (no value) is equivalent to `return None`.
            "def f(x) -> int | None:\n"
            "    if x == 0: return\n"
            "    if x < 0: return None\n"
            "    return x\n",
            None,
            id="bare-return-counts-as-none",
        ),
        pytest.param(
            "async def fetch(uid) -> int | None:\n"
            "    if not uid: return None\n"
            "    if uid < 0: return None\n"
            "    return await load(uid)\n",
            None,
            id="async-function",
        ),
        pytest.param(
            # Single return None but except (X, Y) catching >=2 types fires.
            "def parse(text) -> int | None:\n"
            "    try:\n"
            "        return int(text)\n"
            "    except (ValueError, TypeError):\n"
            "        return None\n",
            "multi_exception_catch",
            id="multi-exception-catch",
        ),
    ],
)
def test_optional_shape_fires(src: str, expected_shape: str | None) -> None:
    hits = _detect_optional_instead_of_result(_parse(src), Path("app/x.py"))
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
            # Single failure mode is legitimate Optional usage — no fire.
            "def find_user(uid) -> User | None:\n"
            "    if uid not in users: return None\n"
            "    return users[uid]\n",
            id="single-return-none",
        ),
        pytest.param(
            # Function returns int (not int | None) — out of scope even with two return None.
            "def f(x) -> int:\n"
            "    if x == 0: return None\n"
            "    if x < 0: return None\n"
            "    return x\n",
            id="no-optional-return",
        ),
        pytest.param(
            # `return None` inside a nested def doesn't contribute to the outer count.
            "def outer(x) -> int | None:\n"
            "    def inner():\n"
            "        if x == 0: return None\n"
            "        if x < 0: return None\n"
            "        return x\n"
            "    return inner() if x else None\n",
            id="nested-function-returns-dont-count",
        ),
        pytest.param(
            # `except KeyError: return None` (one type only) doesn't fire.
            "def get(d, k) -> int | None:\n"
            "    try:\n"
            "        return d[k]\n"
            "    except KeyError:\n"
            "        return None\n",
            id="single-exception-catch",
        ),
        pytest.param(
            # Function without return annotation doesn't fire.
            "def f(x):\n    if x: return None\n    return None\n",
            id="no-return-annotation",
        ),
    ],
)
def test_optional_negative_no_fire(src: str) -> None:
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


def test_nested_helper_inside_except_does_not_trip_outer_1273(tmp_path: Path) -> None:
    """#1273: `_has_multi_exception_catch_returning_none` previously used a
    naive `ast.walk` for its inner search, which descended into nested
    function bodies inside an except clause. A helper whose own body
    contained `return None` would then count as the outer function's
    failure-merging behaviour, fully fabricating PA-LLM-09 against
    well-formed code.

    This fixture: outer `fetch_user` returns `User | None` with a single
    `return None` in the main body (so the `>=2 return None` arm doesn't
    fire). Inside the except block it defines a helper that itself
    contains a `return None`. Pre-fix: the nested helper's return is
    discovered by `ast.walk`, the except is a 2-type tuple catch, so
    the `try/except (X, Y, ...): return None` arm fires. Post-fix: the
    walk skips nested FunctionDef so only the outer's body counts.
    """
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "fetcher.py").write_text(
        "from typing import Optional\n"
        "\n"
        "class User: pass\n"
        "\n"
        "def fetch_user(uid: str) -> Optional[User]:\n"
        "    try:\n"
        "        return load(uid)\n"
        "    except (ValueError, KeyError):\n"
        "        def _format_log(err: object) -> object | None:\n"
        "            if not err:\n"
        "                return None\n"
        "            return repr(err)\n"
        "        _format_log(None)\n"
        "        return load_fallback(uid)\n"
        "\n"
        "def load(uid): return User()\n"
        "def load_fallback(uid): return User()\n"
    )
    agent = PythonAuditAgent(project_path=tmp_path)
    findings = agent.check_optional_instead_of_result(appspec=None)  # type: ignore[arg-type]
    fetcher_findings = [f for f in findings if "fetcher.py" in str(f.location.file_path)]
    assert fetcher_findings == [], (
        f"PA-LLM-09 false-positive on fetcher.fetch_user: nested helper's "
        f"`return None` was incorrectly attributed to the outer function. "
        f"Got: {fetcher_findings} (#1273)"
    )
