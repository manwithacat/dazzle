"""Unit tests for qa_smoke_bar residual scoring (incl. dead crawl)."""

from __future__ import annotations

# Load script module (not installed as package)
import importlib.util
import json
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _load():
    import sys

    path = REPO / "scripts" / "qa_smoke_bar.py"
    spec = importlib.util.spec_from_file_location("qa_smoke_bar", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # 3.14 dataclasses need the module registered before @dataclass runs.
    sys.modules["qa_smoke_bar"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_is_dead_crawl(tmp_path: Path) -> None:
    mod = _load()
    dead = tmp_path / "qa-smoke-x.json"
    dead.write_text(json.dumps({"counts": {"ok": 0, "fail": 5}}), encoding="utf-8")
    assert mod._is_dead_crawl(dead) is True
    live = tmp_path / "qa-smoke-y.json"
    live.write_text(json.dumps({"counts": {"ok": 3, "fail": 2}}), encoding="utf-8")
    assert mod._is_dead_crawl(live) is False
    clean = tmp_path / "qa-smoke-z.json"
    clean.write_text(json.dumps({"counts": {"ok": 10, "fail": 0}}), encoding="utf-8")
    assert mod._is_dead_crawl(clean) is False


def test_score_app_dead_crawl_is_residual(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load()
    app = "simple_task"
    # Point EXAMPLES at a temp tree with a dead report only
    examples = tmp_path / "examples"
    dev = examples / app / "dev_docs"
    dev.mkdir(parents=True)
    (examples / app / "trial.toml").write_text("[trial]\n", encoding="utf-8")
    report = dev / "qa-smoke-manager-dead.json"
    report.write_text(
        json.dumps({"counts": {"ok": 0, "fail": 18}, "auto_seed": []}),
        encoding="utf-8",
    )
    # Fresh mtime so not stale-by-age
    now = time.time()
    import os

    os.utime(report, (now, now))
    monkeypatch.setattr(mod, "EXAMPLES", examples)
    monkeypatch.setattr(mod, "SHOWCASE", (app,))
    row = mod.score_app(app, stale_days=7)
    assert row.is_residual()
    assert "smoke_dead_crawl" in row.reasons
