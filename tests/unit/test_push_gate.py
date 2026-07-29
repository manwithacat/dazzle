"""Gate: push_gate stamp / throttle / HM path helpers stay coherent."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "push_gate.py"


def _load():
    name = "dazzle_scripts_push_gate"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_hm_visual_paths_detect_gallery_css() -> None:
    mod = _load()
    hits = mod.hm_visual_paths(
        [
            "packages/hatchi-maxchi/components/kanban.css",
            "src/dazzle/http/runtime/x.py",
            "docs/readme.md",
        ]
    )
    assert hits == ["packages/hatchi-maxchi/components/kanban.css"]


def test_hm_visual_paths_ignore_contracts_only() -> None:
    mod = _load()
    hits = mod.hm_visual_paths(
        ["packages/hatchi-maxchi/contracts/kanban.py", "packages/hatchi-maxchi/CONTRACT_SURFACE.md"]
    )
    assert hits == []


def test_tree_fingerprint_stable_for_same_tree() -> None:
    mod = _load()
    a = mod.tree_fingerprint()
    b = mod.tree_fingerprint()
    assert a == b
    assert len(a) == 64


def test_write_and_read_stamp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load()
    stamp_path = tmp_path / "push_gate_stamp.json"
    monkeypatch.setattr(mod, "STAMP_PATH", stamp_path)
    payload = mod.write_stamp(tier="0")
    assert stamp_path.is_file()
    loaded = mod.read_stamp()
    assert loaded is not None
    assert loaded["tier"] == "0"
    assert loaded["fingerprint"] == payload["fingerprint"]
    assert loaded["fingerprint"] == mod.tree_fingerprint()


def test_check_blocks_without_stamp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load()
    monkeypatch.setattr(mod, "STAMP_PATH", tmp_path / "missing.json")
    rc = mod.cmd_check(skip_throttle=True, skip_ci_wait=True)
    assert rc == 1


def test_check_blocks_fingerprint_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load()
    stamp_path = tmp_path / "push_gate_stamp.json"
    monkeypatch.setattr(mod, "STAMP_PATH", stamp_path)
    stamp_path.parent.mkdir(parents=True, exist_ok=True)
    stamp_path.write_text(
        json.dumps(
            {
                "at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "tier": "0",
                "fingerprint": "0" * 64,
                "head": "deadbeef",
            }
        ),
        encoding="utf-8",
    )
    rc = mod.cmd_check(skip_throttle=True, skip_ci_wait=True)
    assert rc == 1


def test_check_allows_valid_stamp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load()
    stamp_path = tmp_path / "push_gate_stamp.json"
    monkeypatch.setattr(mod, "STAMP_PATH", stamp_path)
    monkeypatch.setattr(mod, "main_commits_in_window", lambda _w: [])
    monkeypatch.setattr(mod, "probe_main_ci", lambda: {"status": "green"})
    monkeypatch.setattr(mod, "changed_paths_vs_main", lambda: ["docs/x.md"])
    mod.write_stamp(tier="0")
    rc = mod.cmd_check(skip_throttle=False, skip_ci_wait=False, min_tier="0")
    assert rc == 0


def test_check_blocks_in_progress_ci(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load()
    stamp_path = tmp_path / "push_gate_stamp.json"
    monkeypatch.setattr(mod, "STAMP_PATH", stamp_path)
    monkeypatch.setattr(mod, "main_commits_in_window", lambda _w: [])
    monkeypatch.setattr(
        mod,
        "probe_main_ci",
        lambda: {"status": "in_progress", "id": 1, "sha": "abc", "title": "x", "url": "u"},
    )
    monkeypatch.setattr(mod, "changed_paths_vs_main", lambda: [])
    mod.write_stamp(tier="0")
    assert mod.cmd_check() == 1
    assert mod.cmd_check(repair=True) == 0


def test_check_blocks_throttle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load()
    stamp_path = tmp_path / "push_gate_stamp.json"
    monkeypatch.setattr(mod, "STAMP_PATH", stamp_path)
    now = datetime.now(UTC)
    floods = [(f"s{i}", now - timedelta(minutes=i)) for i in range(mod.MAX_MAIN_COMMITS_PER_HOUR)]
    monkeypatch.setattr(mod, "main_commits_in_window", lambda _w: floods)
    monkeypatch.setattr(mod, "probe_main_ci", lambda: {"status": "green"})
    monkeypatch.setattr(mod, "changed_paths_vs_main", lambda: [])
    mod.write_stamp(tier="0")
    assert mod.cmd_check() == 1
    assert mod.cmd_check(repair=True) == 0
