"""Tests for PA-LLM-07 — exceptions as control flow.

The four AST shape-detectors (silent-swallow, fallback-control-flow,
validation-via-exception, try-as-conditional) share the two tables below —
the `swallow-*` / `fallback-*` / `validation-*` / `conditional-*` id
prefixes keep the shape families visible.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path

import pytest

from dazzle.sentinel.agents.python_audit import (
    PythonAuditAgent,
    _detect_fallback_control_flow,
    _detect_silent_swallow,
    _detect_try_as_conditional,
    _detect_validation_via_exception,
)

_Detector = Callable[[ast.Module, Path], list]


def _parse(src: str) -> ast.Module:
    return ast.parse(src)


# ---------------------------------------------------------------------------
# Positive: each shape-detector fires exactly once on its canonical shape.
# expected_line is asserted only when not None.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("detector", "src", "expected_line"),
    [
        # Shape 1: silent swallow ---------------------------------------------
        pytest.param(
            _detect_silent_swallow,
            "try:\n    do()\nexcept:\n    pass\n",
            3,
            id="swallow-bare-except-pass",
        ),
        pytest.param(
            _detect_silent_swallow,
            "try:\n    do()\nexcept Exception:\n    pass\n",
            None,
            id="swallow-except-exception-pass",
        ),
        # Shape 2: fallback control flow --------------------------------------
        pytest.param(
            # `try: x = api.get(); except Exception: x = DEFAULT` shape.
            _detect_fallback_control_flow,
            "try:\n    user = api.fetch(uid)\nexcept Exception:\n    user = None\n",
            None,
            id="fallback-literal-default",
        ),
        # Shape 3: validation via exception -----------------------------------
        pytest.param(
            _detect_validation_via_exception,
            "try:\n    int(s)\n    valid = True\nexcept ValueError:\n    valid = False\n",
            None,
            id="validation-int-cast",
        ),
        pytest.param(
            # The assigned-call variant `n = int(s)` is also validation-via-exception.
            _detect_validation_via_exception,
            "try:\n    n = int(s)\n    valid = True\nexcept ValueError:\n    valid = False\n",
            None,
            id="validation-assigned-call",
        ),
        # Shape 4: try-as-conditional -----------------------------------------
        pytest.param(
            _detect_try_as_conditional,
            "try:\n    v = d[k]\nexcept KeyError:\n    v = None\n",
            None,
            id="conditional-dict-get",
        ),
        pytest.param(
            _detect_try_as_conditional,
            "try:\n    v = obj.attr\nexcept AttributeError:\n    v = None\n",
            None,
            id="conditional-attr-access",
        ),
        pytest.param(
            _detect_try_as_conditional,
            "try:\n    v = seq[i]\nexcept IndexError:\n    v = None\n",
            None,
            id="conditional-index-access",
        ),
    ],
)
def test_exception_shape_fires(detector: _Detector, src: str, expected_line: int | None) -> None:
    hits = detector(_parse(src), Path("app/x.py"))
    assert len(hits) == 1
    if expected_line is not None:
        assert hits[0].line == expected_line


# ---------------------------------------------------------------------------
# Negative: false-positive guards per shape-detector
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("detector", "src"),
    [
        pytest.param(
            # Re-raising or specific recovery is fine.
            _detect_silent_swallow,
            "try:\n    do()\nexcept ValueError as e:\n"
            "    log.error('bad input: %s', e)\n    raise\n",
            id="swallow-specific-recovery",
        ),
        pytest.param(
            # If the except body does something different (e.g. raise, log+raise) it's fine.
            _detect_fallback_control_flow,
            "try:\n"
            "    user = api.fetch(uid)\n"
            "except Exception:\n"
            "    log.exception('fetch failed')\n"
            "    raise\n",
            id="fallback-distinct-action",
        ),
        pytest.param(
            # A try/except around a parse that uses the result downstream isn't validation.
            _detect_validation_via_exception,
            "try:\n"
            "    n = int(s)\n"
            "    items[n] = compute(n)\n"
            "except ValueError as e:\n"
            "    raise InvalidInput(s) from e\n",
            id="validation-real-parse",
        ),
        pytest.param(
            # KeyError around something that's not a subscript (e.g. external API call) is OK.
            _detect_try_as_conditional,
            "try:\n"
            "    result = service.call(payload)\n"
            "except KeyError as e:\n"
            "    raise ProtocolError(payload) from e\n",
            id="conditional-other-exception",
        ),
    ],
)
def test_exception_shape_negative_no_fire(detector: _Detector, src: str) -> None:
    assert detector(_parse(src), Path("app/x.py")) == []


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
