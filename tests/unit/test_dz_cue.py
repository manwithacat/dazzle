"""Structural ratchet for opt-in sound cues (stem chrome-cue-opt-in)."""

from __future__ import annotations

from pathlib import Path

CUE = (
    Path(__file__).resolve().parents[2] / "packages" / "hatchi-maxchi" / "controllers" / "dz-cue.js"
)


def test_cue_is_opt_in_and_silent_by_default() -> None:
    text = CUE.read_text(encoding="utf-8")
    assert "dz-sound" in text
    assert "data-dz-cue-sound" in text
    assert "prefers-reduced-motion" in text
    assert "window.dzCue" in text
    assert "play" in text
    # No external ding URL
    assert "http" not in text or "AudioContext" in text
    assert "cloudinary" not in text.lower()


def test_cue_listed_before_toast_in_hm_build() -> None:
    build = (
        Path(__file__).resolve().parents[2] / "packages" / "hatchi-maxchi" / "build.py"
    ).read_text(encoding="utf-8")
    i_cue = build.index("controllers/dz-cue.js")
    i_toast = build.index("controllers/dz-toast.js")
    assert i_cue < i_toast
