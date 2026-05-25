"""Tests for PA-LLM-07 — exceptions as control flow."""

from __future__ import annotations

import ast
from pathlib import Path

from dazzle.sentinel.agents.python_audit import (
    PythonAuditAgent,
    _detect_fallback_control_flow,
    _detect_silent_swallow,
    _detect_try_as_conditional,
    _detect_validation_via_exception,
)


def _parse(src: str) -> ast.Module:
    return ast.parse(src)


# ---------------------------------------------------------------------------
# Shape 1: silent swallow
# ---------------------------------------------------------------------------


def test_silent_swallow_bare_except_pass() -> None:
    tree = _parse("try:\n    do()\nexcept:\n    pass\n")
    hits = _detect_silent_swallow(tree, Path("app/x.py"))
    assert len(hits) == 1
    assert hits[0].line == 3


def test_silent_swallow_except_exception_pass() -> None:
    tree = _parse("try:\n    do()\nexcept Exception:\n    pass\n")
    hits = _detect_silent_swallow(tree, Path("app/x.py"))
    assert len(hits) == 1


def test_silent_swallow_negative_specific_recovery() -> None:
    """Re-raising or specific recovery is fine."""
    tree = _parse(
        "try:\n    do()\nexcept ValueError as e:\n    log.error('bad input: %s', e)\n    raise\n"
    )
    assert _detect_silent_swallow(tree, Path("app/x.py")) == []


# ---------------------------------------------------------------------------
# Shape 2: fallback control flow
# ---------------------------------------------------------------------------


def test_fallback_control_flow_literal_default() -> None:
    """`try: x = api.get(); except Exception: x = DEFAULT` shape."""
    src = "try:\n    user = api.fetch(uid)\nexcept Exception:\n    user = None\n"
    hits = _detect_fallback_control_flow(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_fallback_control_flow_negative_distinct_action() -> None:
    """If the except body does something different (e.g. raise, log+raise) it's fine."""
    src = (
        "try:\n"
        "    user = api.fetch(uid)\n"
        "except Exception:\n"
        "    log.exception('fetch failed')\n"
        "    raise\n"
    )
    assert _detect_fallback_control_flow(_parse(src), Path("app/x.py")) == []


# ---------------------------------------------------------------------------
# Shape 3: validation via exception
# ---------------------------------------------------------------------------


def test_validation_via_exception_int_cast() -> None:
    src = "try:\n    int(s)\n    valid = True\nexcept ValueError:\n    valid = False\n"
    hits = _detect_validation_via_exception(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_validation_via_exception_assigned_call() -> None:
    """The assigned-call variant `n = int(s)` is also validation-via-exception."""
    src = "try:\n    n = int(s)\n    valid = True\nexcept ValueError:\n    valid = False\n"
    hits = _detect_validation_via_exception(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_validation_via_exception_negative_real_parse() -> None:
    """A try/except around a parse that uses the result downstream isn't validation."""
    src = (
        "try:\n"
        "    n = int(s)\n"
        "    items[n] = compute(n)\n"
        "except ValueError as e:\n"
        "    raise InvalidInput(s) from e\n"
    )
    assert _detect_validation_via_exception(_parse(src), Path("app/x.py")) == []


# ---------------------------------------------------------------------------
# Shape 4: try-as-conditional
# ---------------------------------------------------------------------------


def test_try_as_conditional_dict_get() -> None:
    src = "try:\n    v = d[k]\nexcept KeyError:\n    v = None\n"
    hits = _detect_try_as_conditional(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_try_as_conditional_attr_access() -> None:
    src = "try:\n    v = obj.attr\nexcept AttributeError:\n    v = None\n"
    hits = _detect_try_as_conditional(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_try_as_conditional_index_access() -> None:
    src = "try:\n    v = seq[i]\nexcept IndexError:\n    v = None\n"
    hits = _detect_try_as_conditional(_parse(src), Path("app/x.py"))
    assert len(hits) == 1


def test_try_as_conditional_negative_other_exception() -> None:
    """KeyError around something that's not a subscript (e.g. external API call) is OK."""
    src = (
        "try:\n"
        "    result = service.call(payload)\n"
        "except KeyError as e:\n"
        "    raise ProtocolError(payload) from e\n"
    )
    assert _detect_try_as_conditional(_parse(src), Path("app/x.py")) == []


# ---------------------------------------------------------------------------
# Heuristic integration
# ---------------------------------------------------------------------------


def test_heuristic_yields_finding_with_catalogue_entry(tmp_path: Path) -> None:
    """End-to-end: the heuristic produces Findings carrying the catalogue entry id."""
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "sync.py").write_text(
        "def sync():\n    try:\n        v = d[k]\n    except KeyError:\n        v = None\n"
    )

    agent = PythonAuditAgent(project_path=tmp_path)
    findings = agent.check_exceptions_as_control_flow(appspec=None)  # type: ignore[arg-type]

    assert len(findings) == 1
    assert findings[0].heuristic_id == "PA-LLM-07"
    assert findings[0].catalogue_entry == "exceptions-as-control-flow"
    assert findings[0].remediation is not None
    assert any(
        "docs/counter-priors/exceptions-as-control-flow.md" in ref
        for ref in findings[0].remediation.references
    )


def test_heuristic_skips_tests_and_scripts(tmp_path: Path) -> None:
    """Test and script files are out of scope."""
    for sub in ("tests", "scripts"):
        d = tmp_path / sub
        d.mkdir()
        (d / "f.py").write_text("try:\n    do()\nexcept:\n    pass\n")

    agent = PythonAuditAgent(project_path=tmp_path)
    assert agent.check_exceptions_as_control_flow(appspec=None) == []  # type: ignore[arg-type]


def test_heuristic_noqa_suppression(tmp_path: Path) -> None:
    """A `# noqa: PA-LLM-07` comment on the try line suppresses the finding."""
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "x.py").write_text(
        "def f():\n    try:  # noqa: PA-LLM-07 - boundary suppression\n"
        "        v = d[k]\n    except KeyError:\n        v = None\n"
    )
    agent = PythonAuditAgent(project_path=tmp_path)
    assert agent.check_exceptions_as_control_flow(appspec=None) == []  # type: ignore[arg-type]
