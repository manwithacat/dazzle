"""#1626 T2 — presentation residual detects ref_as_repr / person_as_text."""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.product_quality.presentation import (
    _find_ref_as_repr,
    score_presentation,
)

pytestmark = pytest.mark.gate


def test_find_ref_as_repr_uuid_dict_patterns() -> None:
    assert _find_ref_as_repr("Device: {'id': UUID('d1000000-0000-4000-8000-000000000001')}")
    assert _find_ref_as_repr('Device: {"id": "d1000000-0000-4000-8000-000000000001"}')
    assert _find_ref_as_repr("oops UUID( d1000000 )")
    assert _find_ref_as_repr("FT-PROBE-A12 · open") is None


def test_score_presentation_skips_absent_shots(tmp_path: Path) -> None:
    # No screenshots dir → empty
    assert score_presentation(tmp_path, "fieldtest_hub") == []


def test_score_presentation_ocr_skip_or_detect(tmp_path: Path) -> None:
    """When hero still exists, residual only if OCR finds leak (or ocr_skip)."""
    shots = tmp_path / ".dazzle" / "qa" / "screenshots"
    shots.mkdir(parents=True)
    # Minimal valid-ish PNG (1x1) — tesseract may fail → ocr_skip, not residual.
    png = shots / "issue_triage_manager_desktop_light.png"
    # Tiny PNG header + IHDR + IEND is enough for file existence; OCR may fail.
    png.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x01\x01\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    scores = score_presentation(tmp_path, "fieldtest_hub")
    assert scores
    # Must not residual on unreadable tiny PNG (ocr_skip or empty ok).
    assert all(not s.residual for s in scores if s.kind in ("ocr_skip", "ok"))
