"""Tests for PA-LLM-09 — optional-instead-of-result.

The multi-return-None and multi-exception-catch arms share the two tables
below — expected_shape is asserted only when not None.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from dazzle.sentinel.agents.python_audit import (
    _detect_optional_instead_of_result,
)
from tests.unit.helpers.python_audit import (
    scan,
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
# Through the agent (noqa, catalogue wiring and tests/scripts scope are
# shared-contract rows in test_python_audit_agent.py)
# ---------------------------------------------------------------------------


def test_nested_helper_inside_except_does_not_trip_outer_1273(tmp_path: Path) -> None:
    """#1273: the multi-exception-catch arm used a naive `ast.walk` that
    descended into nested function bodies inside an except clause, so a
    helper's own `return None` was attributed to the outer function and
    PA-LLM-09 fired against well-formed code. The walk now skips nested
    FunctionDef; only the outer body counts."""
    findings = scan(
        tmp_path,
        "PA-LLM-09",
        {
            "app/fetcher.py": "from typing import Optional\n"
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
        },
    )
    assert findings == [], (
        f"nested helper's `return None` attributed to fetch_user (#1273): {findings}"
    )
