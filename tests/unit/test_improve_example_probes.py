"""Unit tests for scripts/improve_example_probes.py (/improve OBSERVE suite)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "improve_example_probes.py"


def _load():
    spec = importlib.util.spec_from_file_location("improve_example_probes", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def probes():
    return _load()


def test_status_prints_structural_and_felt(probes, capsys) -> None:
    rc = probes.main(["--status"])
    out = capsys.readouterr().out
    assert "product_maturity " in out
    assert "demo_fleet " in out
    assert "journey_maturity " in out
    assert "example_probes residual_total=" in out
    assert "next=" in out
    # Continuous anti-warehouse gradient (feature_creep when residual=0).
    assert "warehouse_index " in out
    assert "wi_fleet=" in out
    # Felt bar lines always present (persona_homes / stills / product_quality).
    assert "persona_homes " in out or "product_quality residual_total=" in out
    assert rc in (0, 1)  # 0 when clean; 1 only with --strict


def test_next_prefers_structural_then_felt(probes, capsys) -> None:
    rc = probes.main(["--next"])
    out = capsys.readouterr().out.strip()
    # Empty when clean; otherwise a showcase app name.
    if out:
        assert (REPO / "examples" / out).is_dir()
        assert rc == 1
    else:
        assert rc == 0


def test_json_shape(probes, capsys) -> None:
    rc = probes.main(["--json"])
    payload = json.loads(capsys.readouterr().out)
    names = {p["name"] for p in payload["probes"]}
    assert {"product_maturity", "demo_fleet", "journey_maturity", "product_quality"} <= names
    for p in payload["probes"]:
        assert "status" in p
        assert "residual" in p
    assert "product_quality_lines" in payload
    assert "warehouse_index" in payload
    assert "wi_fleet=" in str(payload["warehouse_index"])
    assert rc == 0


def test_strict_exits_nonzero_when_felt_residual(probes, capsys) -> None:
    """Strict fails when product_quality still has residual (empty stills etc.)."""
    rc = probes.main(["--strict"])
    out = capsys.readouterr().out
    assert "example_probes residual_total=" in out
    # May be 0 if no local stills (CI) or >0 when empty heroes present.
    total_line = [ln for ln in out.splitlines() if ln.startswith("example_probes residual_total=")][
        0
    ]
    total = int(total_line.split("residual_total=")[1].split()[0])
    if total > 0:
        assert rc == 1
    else:
        assert rc == 0
