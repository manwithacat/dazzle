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


# --- findings vs stamp age (#1758 F3) ----------------------------------------
# Both used to land in `reasons`, so `residual=N` counted a stale measurement
# the same as a product finding — and `land-l25-smoke`, the campaign that exists
# to find gross bugs, was selected by nine stale stamps.


def _write_smoke(app_dir: Path, *, age_days: float = 30.0, auto_seed: int = 0) -> Path:
    dev = app_dir / "dev_docs"
    dev.mkdir(parents=True, exist_ok=True)
    report = dev / "qa-smoke-manager-20260101-000000.json"
    report.write_text(
        json.dumps({"schema_version": 1, "auto_seed": [{"id": f"a{i}"} for i in range(auto_seed)]}),
        encoding="utf-8",
    )
    import os

    old = time.time() - age_days * 86400
    os.utime(report, (old, old))
    return report


def test_a_stale_stamp_is_not_a_finding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load()
    monkeypatch.setattr(mod, "EXAMPLES", tmp_path)
    monkeypatch.setattr(mod, "SHOWCASE", ["a"])
    app = tmp_path / "a"
    app.mkdir()
    (app / "trial.toml").write_text("x", encoding="utf-8")
    _write_smoke(app, age_days=30.0)

    row = mod.score_app("a")

    assert row.is_residual() is True, "still outstanding"
    assert row.is_finding() is False, "but nothing was found"
    assert row.is_stale() is True


def test_an_auto_seed_is_a_finding_not_merely_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = _load()
    monkeypatch.setattr(mod, "EXAMPLES", tmp_path)
    monkeypatch.setattr(mod, "SHOWCASE", ["a"])
    app = tmp_path / "a"
    app.mkdir()
    (app / "trial.toml").write_text("x", encoding="utf-8")
    _write_smoke(app, age_days=30.0, auto_seed=2)

    row = mod.score_app("a")

    assert row.is_finding() is True
    assert row.smoke_auto_seed == 2


def test_status_reports_the_two_numbers_separately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = _load()
    monkeypatch.setattr(mod, "EXAMPLES", tmp_path)
    monkeypatch.setattr(mod, "SHOWCASE", ["stale_only", "seeded", "fresh"])
    for name, age, seed in (("stale_only", 30.0, 0), ("seeded", 30.0, 1), ("fresh", 0.0, 0)):
        app = tmp_path / name
        app.mkdir()
        (app / "trial.toml").write_text("x", encoding="utf-8")
        _write_smoke(app, age_days=age, auto_seed=seed)

    out = mod.format_status(mod.scan())

    assert "residual=1" in out, out
    assert "stale=2" in out, out
    assert "next_finding=seeded" in out, out
    assert "next_stale=" in out and "- " not in out.split("next_stale=")[1][:2], out


def test_next_follows_findings_not_stamp_age(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--next` answers "what should I work on"; a stale stamp with no finding is
    re-measurement, so the first *finding* app is the answer, not the oldest
    stamp."""
    mod = _load()
    monkeypatch.setattr(mod, "EXAMPLES", tmp_path)
    monkeypatch.setattr(mod, "SHOWCASE", ["stale_first", "seeded_second"])
    for name, seed in (("stale_first", 0), ("seeded_second", 1)):
        app = tmp_path / name
        app.mkdir()
        (app / "trial.toml").write_text("x", encoding="utf-8")
        _write_smoke(app, age_days=30.0, auto_seed=seed)

    assert mod.main(["--next"]) == 0
