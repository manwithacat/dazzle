"""Run-id helper tests (#1153 follow-on)."""

from __future__ import annotations

import re
from pathlib import Path

from dazzle.perf.run_id import latest_run_id, make_run_id


def test_make_run_id_shape() -> None:
    rid = make_run_id()
    # YYYYMMDD-HHMMSS-XXXXXXXX where the tail is 8 hex chars.
    assert re.fullmatch(r"\d{8}-\d{6}-[0-9a-f]{8}", rid)


def test_make_run_id_unique() -> None:
    ids = {make_run_id() for _ in range(50)}
    assert len(ids) == 50


def test_latest_run_id_returns_newest(tmp_path: Path) -> None:
    perf_dir = tmp_path / "perf"
    perf_dir.mkdir()
    (perf_dir / "20260101-000000-aaaaaaaa.db").touch()
    (perf_dir / "20260201-000000-bbbbbbbb.db").touch()
    (perf_dir / "20260115-000000-cccccccc.db").touch()
    assert latest_run_id(perf_dir) == "20260201-000000-bbbbbbbb"


def test_latest_run_id_none_when_empty(tmp_path: Path) -> None:
    perf_dir = tmp_path / "perf"
    perf_dir.mkdir()
    assert latest_run_id(perf_dir) is None


def test_latest_run_id_none_when_missing(tmp_path: Path) -> None:
    assert latest_run_id(tmp_path / "does-not-exist") is None


def test_latest_run_id_ignores_non_db_files(tmp_path: Path) -> None:
    perf_dir = tmp_path / "perf"
    perf_dir.mkdir()
    (perf_dir / "20260101-000000-aaaaaaaa.db").touch()
    (perf_dir / "README.txt").touch()
    assert latest_run_id(perf_dir) == "20260101-000000-aaaaaaaa"
