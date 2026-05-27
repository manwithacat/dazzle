"""PA-LLM-10 sub-shape (b) — enum-dispatch chains over string literals.

The detector fires on `if x == "a": ... elif x == "b": ... elif x ==
"c": ...` chains (≥3 branches) where every branch is an `==`
comparison against a string constant on the same Name. A StrEnum +
`match` would prove exhaustiveness and catch typos; the bare-string
chain doesn't.

Design lock-in (from #1272 round-5 discussion + #1274 design comment):
- Function-body chains only (skip module-level / class-level).
- ≥3 branches required (a 2-branch if/else is a yes/no toggle).
- Strict mixed-comparator: any non-string-eq branch aborts the chain.
- noqa anchor: the opening `if` line.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.sentinel.agents.python_audit import PythonAuditAgent


def _scan(tmp_path: Path, body: str) -> list:
    app = tmp_path / "app"
    app.mkdir()
    (app / "dispatch.py").write_text(body)
    agent = PythonAuditAgent(project_path=tmp_path)
    return agent.check_magic_string_typing(appspec=None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Positive — should fire
# ---------------------------------------------------------------------------


def test_fires_on_three_branch_chain(tmp_path: Path) -> None:
    """The canonical wrong shape — 3-branch if/elif/elif on string lits."""
    findings = _scan(
        tmp_path,
        "def handle(action: str) -> str:\n"
        "    if action == 'create': return 'A'\n"
        "    elif action == 'update': return 'B'\n"
        "    elif action == 'delete': return 'C'\n"
        "    return 'X'\n",
    )
    enum_findings = [f for f in findings if "Enum-dispatch" in f.title]
    assert len(enum_findings) == 1
    f = enum_findings[0]
    assert f.heuristic_id == "PA-LLM-10"
    assert f.catalogue_entry == "magic-string-typing"
    assert "action" in f.title


def test_fires_on_four_branch_chain(tmp_path: Path) -> None:
    """Longer chains fire too — same shape, just more branches."""
    findings = _scan(
        tmp_path,
        "def handle(s: str) -> int:\n"
        "    if s == 'a': return 1\n"
        "    elif s == 'b': return 2\n"
        "    elif s == 'c': return 3\n"
        "    elif s == 'd': return 4\n"
        "    return 0\n",
    )
    enum_findings = [f for f in findings if "Enum-dispatch" in f.title]
    assert len(enum_findings) == 1


def test_fires_when_literal_on_left_side(tmp_path: Path) -> None:
    """`"foo" == x` shape — Python allows it, the detector normalises."""
    findings = _scan(
        tmp_path,
        "def handle(action: str) -> str:\n"
        "    if 'create' == action: return 'A'\n"
        "    elif 'update' == action: return 'B'\n"
        "    elif 'delete' == action: return 'C'\n"
        "    return 'X'\n",
    )
    enum_findings = [f for f in findings if "Enum-dispatch" in f.title]
    assert len(enum_findings) == 1


# ---------------------------------------------------------------------------
# Negative — should NOT fire
# ---------------------------------------------------------------------------


def test_does_not_fire_on_two_branch_chain(tmp_path: Path) -> None:
    """`if x == 'a': ... elif x == 'b':` is a yes/no toggle. Three-
    branch threshold is the design lock."""
    findings = _scan(
        tmp_path,
        "def handle(action: str) -> str:\n"
        "    if action == 'create': return 'A'\n"
        "    elif action == 'update': return 'B'\n"
        "    return 'X'\n",
    )
    enum_findings = [f for f in findings if "Enum-dispatch" in f.title]
    assert enum_findings == []


def test_does_not_fire_on_mixed_comparator_chain(tmp_path: Path) -> None:
    """Strict mixed-comparator (per design): any non-string-eq branch
    aborts the chain entirely. This catches the typical case where the
    chain ends with an `else:` style guard, e.g. `elif x is None:`."""
    findings = _scan(
        tmp_path,
        "def handle(action) -> str:\n"
        "    if action == 'create': return 'A'\n"
        "    elif action == 'update': return 'B'\n"
        "    elif action is None: return 'X'\n"  # non-string-eq → aborts
        "    return 'Y'\n",
    )
    enum_findings = [f for f in findings if "Enum-dispatch" in f.title]
    assert enum_findings == []


def test_does_not_fire_on_chain_with_int_literals(tmp_path: Path) -> None:
    """Non-string literal branches don't trip the heuristic — this is
    a status-code dispatch, not a string-discriminator dispatch."""
    findings = _scan(
        tmp_path,
        "def status_label(code: int) -> str:\n"
        "    if code == 200: return 'OK'\n"
        "    elif code == 404: return 'NF'\n"
        "    elif code == 500: return 'ERR'\n"
        "    return '?'\n",
    )
    enum_findings = [f for f in findings if "Enum-dispatch" in f.title]
    assert enum_findings == []


def test_does_not_fire_on_different_discriminators(tmp_path: Path) -> None:
    """`if a == 'x': ... elif b == 'y':` — different Names on the LHS,
    not a dispatch over a single discriminator."""
    findings = _scan(
        tmp_path,
        "def handle(a: str, b: str) -> str:\n"
        "    if a == 'x': return 'A'\n"
        "    elif b == 'y': return 'B'\n"
        "    elif a == 'z': return 'C'\n"
        "    return 'X'\n",
    )
    enum_findings = [f for f in findings if "Enum-dispatch" in f.title]
    assert enum_findings == []


def test_does_not_fire_on_module_level_chain(tmp_path: Path) -> None:
    """Function-body chains only (design lock). Module-level dispatch
    tables are a different shape — likely config registration."""
    findings = _scan(
        tmp_path,
        "x = 'foo'\n"
        "if x == 'a': result = 'A'\n"
        "elif x == 'b': result = 'B'\n"
        "elif x == 'c': result = 'C'\n",
    )
    enum_findings = [f for f in findings if "Enum-dispatch" in f.title]
    assert enum_findings == []


def test_fires_only_once_per_chain_not_per_elif(tmp_path: Path) -> None:
    """Important not-double-counting test: `if/elif/elif/elif` would
    `ast.walk` to four `If` nodes (the outer + each elif). The detector
    must only fire at the chain root, not at every node."""
    findings = _scan(
        tmp_path,
        "def handle(action: str) -> str:\n"
        "    if action == 'a': return 'A'\n"
        "    elif action == 'b': return 'B'\n"
        "    elif action == 'c': return 'C'\n"
        "    elif action == 'd': return 'D'\n"
        "    return 'X'\n",
    )
    enum_findings = [f for f in findings if "Enum-dispatch" in f.title]
    assert len(enum_findings) == 1, (
        f"Chain must fire exactly once at the root, not per elif. Got: {enum_findings}"
    )


# ---------------------------------------------------------------------------
# Suppression
# ---------------------------------------------------------------------------


def test_noqa_on_opening_if_line_suppresses(tmp_path: Path) -> None:
    """`# noqa: PA-LLM-10 — <reason>` on the opening `if` line silences."""
    findings = _scan(
        tmp_path,
        "def handle(action: str) -> str:\n"
        "    if action == 'create': return 'A'  # noqa: PA-LLM-10 — user input\n"
        "    elif action == 'update': return 'B'\n"
        "    elif action == 'delete': return 'C'\n"
        "    return 'X'\n",
    )
    enum_findings = [f for f in findings if "Enum-dispatch" in f.title]
    assert enum_findings == []


# ---------------------------------------------------------------------------
# Coexistence with sub-shape (a)
# ---------------------------------------------------------------------------


def test_both_subshapes_can_fire_independently(tmp_path: Path) -> None:
    """Sub-shape (a) (ID-shaped str param) and sub-shape (b) (enum
    dispatch) share the PA-LLM-10 heuristic_id but are independent
    detectors. Each can fire in the same file without interfering."""
    findings = _scan(
        tmp_path,
        "def handle(user_id: str, action: str) -> str:\n"  # (a) fires on user_id
        "    if action == 'a': return 'A'\n"  # (b) fires on action
        "    elif action == 'b': return 'B'\n"
        "    elif action == 'c': return 'C'\n"
        "    return 'X'\n",
    )
    id_findings = [f for f in findings if "ID parameter" in f.title]
    enum_findings = [f for f in findings if "Enum-dispatch" in f.title]
    assert len(id_findings) == 1
    assert len(enum_findings) == 1
