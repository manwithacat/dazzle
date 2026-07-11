"""Consumer map generator — reverse composition index drift gate."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "packages" / "hatchi-maxchi" / "tools" / "consumer_map.py"
COMMITTED = REPO / "packages" / "hatchi-maxchi" / "CONSUMER_MAP.md"
PKG = REPO / "packages" / "hatchi-maxchi"


def test_consumer_map_script_exits_zero() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "consumer map" in proc.stdout.lower()
    assert "combobox" in proc.stdout
    assert "refused" in proc.stdout.lower() or "Does not compose" in proc.stdout


def test_committed_consumer_map_matches_generator() -> None:
    from tests.unit._text_drift import assert_text_matches

    assert COMMITTED.is_file(), "missing CONSUMER_MAP.md — run consumer_map.py --write"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert_text_matches(
        proc.stdout.rstrip("\n"),
        COMMITTED.read_text(encoding="utf-8").rstrip("\n"),
        regenerate_hint="CONSUMER_MAP.md is stale — run: python packages/hatchi-maxchi/tools/consumer_map.py --write",
    )


def test_non_composition_targets_are_real_and_not_also_composed() -> None:
    sys.path.insert(0, str(PKG / "site"))
    from registry import HYPERPARTS  # noqa: E402

    ids = {h.id for h in HYPERPARTS}
    for h in HYPERPARTS:
        for nc in h.does_not_compose:
            assert nc.other in ids, f"{h.id}: does_not_compose.other {nc.other!r} unknown"
            assert nc.other != h.id, f"{h.id}: cannot refuse itself"
            assert nc.other not in h.composes, (
                f"{h.id}: {nc.other} is both composes and does_not_compose"
            )
            if nc.spike:
                spike_path = PKG / nc.spike
                assert spike_path.is_file(), (
                    f"{h.id}↛{nc.other}: spike {nc.spike} missing at {spike_path}"
                )


def test_non_composition_controller_locks() -> None:
    """Local-primitive locks: parent controller+extensions implement the
    refusal (require bare select markers; forbid combobox dogfood)."""
    sys.path.insert(0, str(PKG / "site"))
    from registry import HYPERPARTS  # noqa: E402

    for h in HYPERPARTS:
        if not h.does_not_compose:
            continue
        sources: list[Path] = []
        if h.controller:
            sources.append(PKG / h.controller)
        for ext in h.extensions:
            sources.append(PKG / ext)
        blob = "\n".join(p.read_text(encoding="utf-8") for p in sources if p.is_file())
        # partial must not embed the refused root either
        blob_partial = h.partial
        for nc in h.does_not_compose:
            for needle in nc.require_substrings:
                assert needle in blob, (
                    f"{h.id}↛{nc.other}: controller sources must contain {needle!r} "
                    f"(local primitive missing — did composition flip without registry?)"
                )
            for needle in nc.forbid_substrings:
                assert needle not in blob, (
                    f"{h.id}↛{nc.other}: controller sources must not contain {needle!r} "
                    f"(accidental dogfood of {nc.other})"
                )
                assert needle not in blob_partial, (
                    f"{h.id}↛{nc.other}: partial must not contain {needle!r}"
                )
