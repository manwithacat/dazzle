"""Darwin leftover-honesty refresh must land matching linux visual PNGs.

Oral #33 / cycle 2146: leftover-honesty that changes gallery markup refreshes
darwin in-cycle but linux stays on the previous month until cimonitor. HM
visual then re-reds Dazzle via hm_standalone_ci_status. Pair age is the
cheap local mirror — CI compares linux; we cannot rasterise ubuntu here.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
BASE = REPO / "packages" / "hatchi-maxchi" / "tests" / "baselines"


def _git_ok(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
    )


def _dirty_names(dir_rel: str) -> set[str]:
    proc = _git_ok(["status", "--porcelain", "--untracked-files=normal", "--", dir_rel])
    names: set[str] = set()
    for line in proc.stdout.splitlines():
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        names.add(Path(path).name)
    return names


def _commit_ts_by_name(dir_rel: str) -> dict[str, int]:
    proc = _git_ok(["log", "--format=%ct", "--name-only", "--", dir_rel])
    ts: dict[str, int] = {}
    current = 0
    for raw in proc.stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.isdigit():
            current = int(line)
            continue
        name = Path(line).name
        if name.endswith(".png") and name not in ts:
            ts[name] = current
    return ts


def test_hm_visual_baseline_darwin_linux_pairs_not_split() -> None:
    darwin = BASE / "darwin"
    linux = BASE / "linux"
    assert darwin.is_dir() and linux.is_dir()

    d_rel = "packages/hatchi-maxchi/tests/baselines/darwin"
    l_rel = "packages/hatchi-maxchi/tests/baselines/linux"
    d_dirty = _dirty_names(d_rel)
    l_dirty = _dirty_names(l_rel)
    d_ts = _commit_ts_by_name(d_rel)
    l_ts = _commit_ts_by_name(l_rel)

    missing: list[str] = []
    split: list[str] = []
    for png in sorted(darwin.glob("*.png")):
        peer = linux / png.name
        if not peer.is_file():
            missing.append(png.name)
            continue
        if png.name in d_dirty and png.name not in l_dirty:
            split.append(png.name)
            continue
        if (
            png.name not in d_dirty
            and png.name not in l_dirty
            and d_ts.get(png.name, 0) > l_ts.get(png.name, 0)
        ):
            split.append(png.name)

    assert not missing, (
        f"linux visual set missing darwin counterparts (dispatch update-baselines.yml): {missing}"
    )
    assert not split, (
        "darwin visual baseline newer than linux — leftover-honesty must "
        "refresh linux via update-baselines.yml in the same ship "
        f"(oral #33): {split}"
    )
