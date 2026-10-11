"""Framework mass ratchet (ADR-0057): source, test, doc lines and construct count only fall.

Same posture as the complexity and clone ratchets: a one-way valve. Lower the
baseline with `uv run python scripts/mass_ratchet.py --write-baseline` after
retiring mass; a rise needs `--force --reason` and is recorded in the fixture.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
BASELINE = REPO / "tests" / "unit" / "fixtures" / "mass_baseline.json"


def _ratchet():
    spec = importlib.util.spec_from_file_location(
        "mass_ratchet", REPO / "scripts" / "mass_ratchet.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_baseline_is_valid() -> None:
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    for m in ("src_lines", "test_lines", "docs_lines", "construct_count"):
        assert isinstance(data[m], int) and data[m] > 0, m


def test_mass_does_not_rise_above_baseline() -> None:
    ratchet = _ratchet()
    regressions = ratchet.compare(ratchet.measure(), ratchet.load_baseline())
    assert not regressions, (
        "Framework mass rose (ADR-0057 — mass may only fall):\n  "
        + "\n  ".join(regressions)
        + "\nRetire at least as much mass in this change, or record an operator exception with "
        "`scripts/mass_ratchet.py --write-baseline --force --reason '…'`."
    )


def test_exceptions_carry_a_reason() -> None:
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    for exc in data.get("exceptions", []):
        assert exc.get("reason", "").strip(), f"mass exception without a reason: {exc}"
