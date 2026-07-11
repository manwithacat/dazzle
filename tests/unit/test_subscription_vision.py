"""Subscription vision prompt + parse — no anthropic client."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dazzle.qa.subscription_vision import (
    LIGHT_DIMENSION_KEYS,
    build_subscription_score_prompt,
    parse_subscription_scores,
    scores_from_smoke_manifest,
    write_scores,
)

pytestmark = pytest.mark.gate


def test_prompt_forbids_metered_api_and_lists_images() -> None:
    prompt = build_subscription_score_prompt(
        [{"image_id": "a", "path": "/tmp/a.png", "label": "A"}],
        scores_path="/tmp/scores.json",
    )
    assert "subscription" in prompt.lower()
    assert "ANTHROPIC" in prompt or "Anthropic" in prompt or "metered" in prompt.lower()
    assert "taste-panel" in prompt
    assert "/tmp/a.png" in prompt
    assert "typographic_hierarchy" in prompt
    assert "dark_mode_integrity" not in prompt  # light theme only
    for key in LIGHT_DIMENSION_KEYS:
        assert key in prompt


def test_parse_scores_clamps_and_filters() -> None:
    raw = json.dumps(
        [
            {
                "image_id": "x",
                "path": "/p.png",
                "scores": {
                    "typographic_hierarchy": 7,
                    "spatial_rhythm": 99,
                    "not_a_dim": 5,
                    "color_discipline": "4",
                },
                "worst_detail": "uneven gaps",
            }
        ]
    )
    scores = parse_subscription_scores(raw)
    assert len(scores) == 1
    assert scores[0].scores["typographic_hierarchy"] == 7
    assert scores[0].scores["spatial_rhythm"] == 10  # clamped
    assert scores[0].scores["color_discipline"] == 4
    assert "not_a_dim" not in scores[0].scores
    assert scores[0].worst_detail == "uneven gaps"


def test_write_and_smoke_manifest(tmp_path: Path) -> None:
    png = tmp_path / "full_page.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n")
    man = tmp_path / "manifest.json"
    man.write_text(
        json.dumps(
            {
                "out": str(tmp_path),
                "full_page_png": str(png),
                "parts": ["money", "combobox"],
            }
        ),
        encoding="utf-8",
    )
    imgs = scores_from_smoke_manifest(man)
    assert len(imgs) == 1
    assert imgs[0]["path"] == str(png)
    assert "money" in imgs[0]["label"]

    scores = parse_subscription_scores(
        [
            {
                "image_id": imgs[0]["image_id"],
                "path": imgs[0]["path"],
                "scores": dict.fromkeys(LIGHT_DIMENSION_KEYS, 6),
                "worst_detail": "ok",
            }
        ]
    )
    out = write_scores(scores, tmp_path / "scores.json")
    blob = json.loads(out.read_text(encoding="utf-8"))
    assert blob["ship_gate"] is False
    assert blob["billing"] == "subscription-host-read"
    assert blob["scores"][0]["mean"] == 6.0
