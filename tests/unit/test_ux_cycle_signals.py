"""Tests for the flat-file signal bus (ux-cycle / improve / ux-converge)."""

from pathlib import Path

import pytest

from dazzle.cli.runtime_impl.ux_cycle_signals import (
    emit,
    mark_run,
    since_last_run,
)


@pytest.fixture
def signals_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the signal bus to a tmp dir so tests don't pollute real state."""
    signals_path = tmp_path / "signals"
    monkeypatch.setattr(
        "dazzle.cli.runtime_impl.ux_cycle_signals._SIGNALS_DIR",
        signals_path,
    )
    return signals_path


class TestSignalBus:
    def test_emit_creates_signal_file(self, signals_dir: Path):
        emit(source="ux-cycle", kind="ux-component-shipped", payload={"component": "data-table"})
        files = list(signals_dir.glob("*.json"))
        assert len(files) == 1

    def test_emit_payload_round_trips(self, signals_dir: Path):
        emit(source="ux-cycle", kind="ux-component-shipped", payload={"component": "data-table"})
        signals = since_last_run(source="improve")
        assert len(signals) == 1
        assert signals[0].source == "ux-cycle"
        assert signals[0].kind == "ux-component-shipped"
        assert signals[0].payload == {"component": "data-table"}

    def test_since_last_run_filters_by_timestamp(self, signals_dir: Path):
        emit(source="ux-cycle", kind="ux-component-shipped", payload={"component": "a"})
        mark_run(source="improve")
        # New signal after mark_run
        emit(source="ux-cycle", kind="ux-component-shipped", payload={"component": "b"})

        signals = since_last_run(source="improve")
        assert len(signals) == 1
        assert signals[0].payload["component"] == "b"

    def test_mark_run_persists_timestamp(self, signals_dir: Path):
        mark_run(source="improve")
        # Second mark_run should overwrite, not duplicate
        mark_run(source="improve")
        marker_files = list(signals_dir.glob(".mark-*.json"))
        assert len(marker_files) == 1

    def test_first_read_no_marker_returns_all_signals(self, signals_dir: Path):
        """A source that has never called mark_run sees all existing signals."""
        emit(source="ux-cycle", kind="x", payload={"a": 1})
        emit(source="improve", kind="y", payload={"b": 2})
        # ux-converge has never run — should see both
        signals = since_last_run(source="ux-converge")
        assert len(signals) == 2

    def test_does_not_return_own_signals(self, signals_dir: Path):
        """A source does not consume signals it emitted itself."""
        emit(source="ux-cycle", kind="x", payload={"a": 1})
        emit(source="improve", kind="y", payload={"b": 2})
        signals = since_last_run(source="ux-cycle")
        # Only the signal from improve should appear
        assert len(signals) == 1
        assert signals[0].source == "improve"

    def test_filter_by_kind(self, signals_dir: Path):
        emit(source="ux-cycle", kind="ux-component-shipped", payload={})
        emit(source="ux-cycle", kind="ux-regression", payload={})
        signals = since_last_run(source="improve", kind="ux-regression")
        assert len(signals) == 1
        assert signals[0].kind == "ux-regression"

    def test_empty_signals_dir(self, signals_dir: Path):
        signals = since_last_run(source="improve")
        assert signals == []
