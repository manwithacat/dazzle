"""Subscription vision prompt + parse — no anthropic client."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dazzle.qa.subscription_vision import (
    LIGHT_DIMENSION_KEYS,
    build_hyperpart_coherence_prompt,
    build_subscription_score_prompt,
    parse_hyperpart_coherence,
    parse_subscription_scores,
    scores_from_smoke_manifest,
    write_coherence,
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


def test_hyperpart_coherence_prompt_and_parse(tmp_path: Path) -> None:
    prompt = build_hyperpart_coherence_prompt(
        [{"image_id": "button", "path": "/tmp/button.png", "label": "button"}],
        findings_path="/tmp/c.json",
        batch_label="batch 1/2",
    )
    assert "coherent" in prompt.lower()
    assert "subscription" in prompt.lower()
    assert "metered" in prompt.lower() or "taste-panel" in prompt
    assert "/tmp/button.png" in prompt
    assert "batch 1/2" in prompt

    results = parse_hyperpart_coherence(
        [
            {
                "image_id": "button",
                "path": "/tmp/button.png",
                "coherent": True,
                "score": 8,
                "issues": [],
                "notes": "ok",
            },
            {
                "image_id": "wizard",
                "path": "/tmp/wizard.png",
                "coherent": True,
                "score": 9,
                "issues": [
                    {
                        "severity": "high",
                        "category": "empty_demo",
                        "description": "demo blank",
                    }
                ],
            },
        ]
    )
    assert results[0].coherent is True
    assert results[1].coherent is False  # high issue forces incoherent
    assert results[1].score == 9
    out = write_coherence(results, tmp_path / "coherence.json")
    blob = json.loads(out.read_text(encoding="utf-8"))
    assert blob["kind"] == "hyperpart_coherence"
    assert blob["n_incoherent"] == 1
    assert blob["ship_gate"] is False


def test_discover_hyperpart_pages() -> None:
    import importlib.util

    path = Path(__file__).resolve().parents[2] / "scripts" / "hm_pages_vision.py"
    spec = importlib.util.spec_from_file_location("hm_pages_vision", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    pages = mod.discover_hyperpart_pages()
    assert len(pages) >= 50
    stems = {n for n, _ in pages}
    assert "button" in stems
    assert "money" in stems
    assert all(rel.startswith("/hyperparts/") for _, rel in pages)
