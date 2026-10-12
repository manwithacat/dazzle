"""Measure fields named ``*_ms`` must not dump unitless numbers (oral #154)."""

from __future__ import annotations

from dazzle.render.filters import clerk_measure_display, clerk_measure_suffix


def test_clerk_measure_suffix_from_field() -> None:
    assert clerk_measure_suffix("response_time_ms") == "ms"
    assert clerk_measure_suffix("latency_ms") == "ms"
    assert clerk_measure_suffix("duration_seconds") == "s"
    assert clerk_measure_suffix("win_pct") == "%"
    assert clerk_measure_suffix("count") == ""
    assert clerk_measure_suffix("zzz") == ""
    assert clerk_measure_suffix("1e2") == ""


def test_clerk_measure_display_adds_ms() -> None:
    assert clerk_measure_display(340, "response_time_ms") == "340ms"
    assert clerk_measure_display(340.0, "response_time_ms") == "340ms"
    assert clerk_measure_display(0, "response_time_ms") == "0ms"
    assert clerk_measure_display(12.5, "response_time_ms") == "12.5ms"
    assert clerk_measure_display(340, "count") == "340"


def test_clerk_measure_display_leftover_stays_put() -> None:
    assert clerk_measure_display("zzz", "response_time_ms") == "zzz"
    assert clerk_measure_display("1e2", "response_time_ms") == "1e2"
    assert clerk_measure_display("2abc", "response_time_ms") == "2abc"
    assert clerk_measure_display(340, "zzz") == "340"
