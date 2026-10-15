"""PA-LLM-10 sub-shape (b) — enum-dispatch chains over string literals (#1274).

The detector fires on `if x == "a": ... elif x == "b": ... elif x ==
"c": ...` chains (≥3 branches) where every branch is an `==`
comparison against a string constant on the same Name. A StrEnum +
`match` would prove exhaustiveness and catch typos; the bare-string
chain doesn't.

Design lock-in (from #1272 round-5 discussion + #1274 design comment):
- Function-body chains only (skip module-level / class-level).
- ≥3 branches required (a 2-branch if/else is a yes/no toggle).
- Strict mixed-comparator: any non-string-eq branch aborts the chain.
- noqa anchor: the opening `if` line (row in test_python_audit_agent.py).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.helpers.python_audit import scan


def _enum_dispatch_findings(tmp_path: Path, source: str) -> list:
    findings = scan(tmp_path, "PA-LLM-10", {"app/dispatch.py": source})
    return [f for f in findings if "Enum-dispatch" in f.title]


def test_fires_on_three_branch_chain(tmp_path: Path) -> None:
    """The canonical wrong shape — 3-branch if/elif/elif on string literals."""
    findings = _enum_dispatch_findings(
        tmp_path,
        "def handle(action: str) -> str:\n"
        "    if action == 'create': return 'A'\n"
        "    elif action == 'update': return 'B'\n"
        "    elif action == 'delete': return 'C'\n"
        "    return 'X'\n",
    )
    assert len(findings) == 1
    assert findings[0].heuristic_id == "PA-LLM-10"
    assert findings[0].catalogue_entry == "magic-string-typing"
    assert "action" in findings[0].title


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(
            # Fires once at the chain root, not once per elif `If` node.
            "def handle(s: str) -> int:\n"
            "    if s == 'a': return 1\n"
            "    elif s == 'b': return 2\n"
            "    elif s == 'c': return 3\n"
            "    elif s == 'd': return 4\n"
            "    return 0\n",
            id="four-branch-chain-fires-once",
        ),
        pytest.param(
            # `"foo" == x` — Python allows it, the detector normalises.
            "def handle(action: str) -> str:\n"
            "    if 'create' == action: return 'A'\n"
            "    elif 'update' == action: return 'B'\n"
            "    elif 'delete' == action: return 'C'\n"
            "    return 'X'\n",
            id="literal-on-left-side",
        ),
    ],
)
def test_fires_once_per_chain(tmp_path: Path, source: str) -> None:
    assert len(_enum_dispatch_findings(tmp_path, source)) == 1


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(
            # A yes/no toggle — the three-branch threshold is the design lock.
            "def handle(action: str) -> str:\n"
            "    if action == 'create': return 'A'\n"
            "    elif action == 'update': return 'B'\n"
            "    return 'X'\n",
            id="two-branch-chain",
        ),
        pytest.param(
            # Any non-string-eq branch (here `is None`) aborts the chain.
            "def handle(action) -> str:\n"
            "    if action == 'create': return 'A'\n"
            "    elif action == 'update': return 'B'\n"
            "    elif action is None: return 'X'\n"
            "    return 'Y'\n",
            id="mixed-comparator-chain",
        ),
        pytest.param(
            # A status-code dispatch, not a string discriminator.
            "def status_label(code: int) -> str:\n"
            "    if code == 200: return 'OK'\n"
            "    elif code == 404: return 'NF'\n"
            "    elif code == 500: return 'ERR'\n"
            "    return '?'\n",
            id="int-literals",
        ),
        pytest.param(
            # Different Names on the LHS — not a single discriminator.
            "def handle(a: str, b: str) -> str:\n"
            "    if a == 'x': return 'A'\n"
            "    elif b == 'y': return 'B'\n"
            "    elif a == 'z': return 'C'\n"
            "    return 'X'\n",
            id="different-discriminators",
        ),
        pytest.param(
            # Function-body chains only; module-level dispatch is config registration.
            "x = 'foo'\n"
            "if x == 'a': result = 'A'\n"
            "elif x == 'b': result = 'B'\n"
            "elif x == 'c': result = 'C'\n",
            id="module-level-chain",
        ),
    ],
)
def test_does_not_fire(tmp_path: Path, source: str) -> None:
    assert _enum_dispatch_findings(tmp_path, source) == []


def test_both_subshapes_can_fire_independently(tmp_path: Path) -> None:
    """Sub-shape (a) (ID-shaped str param) and sub-shape (b) (enum dispatch)
    share the PA-LLM-10 heuristic_id but are independent detectors."""
    findings = scan(
        tmp_path,
        "PA-LLM-10",
        {
            "app/dispatch.py": "def handle(user_id: str, action: str) -> str:\n"
            "    if action == 'a': return 'A'\n"
            "    elif action == 'b': return 'B'\n"
            "    elif action == 'c': return 'C'\n"
            "    return 'X'\n"
        },
    )
    assert len([f for f in findings if "ID parameter" in f.title]) == 1
    assert len([f for f in findings if "Enum-dispatch" in f.title]) == 1
