"""#1626 demo_fleet_bar probe — showcase apps stay above seed/nav floors."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "demo_fleet_bar.py"


def _load():
    spec = importlib.util.spec_from_file_location("demo_fleet_bar", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_showcase_demo_fleet_bar_ok() -> None:
    mod = _load()
    residual = [r for r in (mod.score_app(a) for a in mod.SHOWCASE) if not r.ok]
    assert not residual, "demo_fleet residual: " + ", ".join(
        f"{r.app}:{','.join(r.issues)}" for r in residual
    )
