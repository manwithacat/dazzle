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


def test_status_prints_all_three_probes(probes, capsys) -> None:
    rc = probes.main(["--status"])
    out = capsys.readouterr().out
    assert "product_maturity " in out
    assert "demo_fleet " in out
    assert "journey_maturity " in out
    assert "example_probes residual_total=" in out
    assert "next=" in out
    # Fleet currently mature — residual_total=0; keep as gate for improve loop.
    assert "residual_total=0" in out
    assert rc == 0


def test_next_empty_when_fleet_mature(probes, capsys) -> None:
    rc = probes.main(["--next"])
    out = capsys.readouterr().out.strip()
    assert out == ""
    assert rc == 0


def test_json_shape(probes, capsys) -> None:
    rc = probes.main(["--json"])
    payload = json.loads(capsys.readouterr().out)
    names = {p["name"] for p in payload["probes"]}
    assert names == {"product_maturity", "demo_fleet", "journey_maturity"}
    for p in payload["probes"]:
        assert "status" in p
        assert "residual" in p
        assert p["residual"] == 0
    assert payload["next"] is None
    assert payload["next_strategy"] is None
    assert payload["force"] is None
    assert rc == 0


def test_strict_exits_0_when_clean(probes, capsys) -> None:
    rc = probes.main(["--strict"])
    assert rc == 0
    # still prints status lines
    assert "example_probes residual_total=0" in capsys.readouterr().out
