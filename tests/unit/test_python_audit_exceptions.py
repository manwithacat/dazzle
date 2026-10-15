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
