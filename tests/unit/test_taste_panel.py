"""Blind taste panel — pool assembly, blinding, aggregation, parity math."""

import json
from pathlib import Path

import pytest

from dazzle.qa.taste_panel import (
    JudgeScore,
    aggregate_scores,
    assemble_pool,
    blind_order,
    noise_sd,
    parity_verdict,
)


def _write_manifests(tmp_path: Path) -> tuple[Path, Path]:
    shots = tmp_path / "shots"
    shots.mkdir()
    for name in ("a.png", "b.png", "r.png"):
        (shots / name).write_bytes(b"\x89PNG fake")
    fleet = tmp_path / "fleet.json"
    fleet.write_text(
        json.dumps(
            {
                "apps": [
                    {
                        "app": "ops_dashboard",
                        "screens": [
                            {
                                "persona": "admin",
                                "workspace": "main",
                                "url": "u",
                                "screenshot": str(shots / "a.png"),
                                "viewport": "desktop",
                                "theme": "light",
                            },
                            {
                                "persona": "admin",
                                "workspace": "main",
                                "url": "u",
                                "screenshot": str(shots / "b.png"),
                                "viewport": "desktop",
                                "theme": "dark",
                            },
                        ],
                    }
                ],
            }
        )
    )
    refs = tmp_path / "refs.json"
    refs.write_text(
        json.dumps(
            {
                "captured_at": "2026-07-02T00:00:00+00:00",
                "references": [
                    {
                        "name": "shadcn_dashboard",
                        "url": "u",
                        "theme": "light",
                        "screenshot": str(shots / "r.png"),
                    },
                ],
            }
        )
    )
    return fleet, refs


def test_assemble_pool_merges_sources_and_tags_theme(tmp_path: Path) -> None:
    fleet, refs = _write_manifests(tmp_path)
    pool = assemble_pool(fleet, refs)
    assert len(pool) == 3
    sources = sorted(p.source for p in pool)
    assert sources == ["dazzle", "dazzle", "reference"]
    assert {p.theme for p in pool} == {"light", "dark"}
    # image_ids are opaque and unique — no filenames leak to judges
    assert len({p.image_id for p in pool}) == 3
    for p in pool:
        assert "png" not in p.image_id
        assert "shadcn" not in p.image_id and "ops_dashboard" not in p.image_id


def test_assemble_pool_skips_missing_files(tmp_path: Path) -> None:
    fleet, refs = _write_manifests(tmp_path)
    data = json.loads(fleet.read_text())
    data["apps"][0]["screens"].append(
        {
            "persona": "x",
            "workspace": "gone",
            "url": "u",
            "screenshot": str(tmp_path / "missing.png"),
            "viewport": "desktop",
            "theme": "light",
        }
    )
    fleet.write_text(json.dumps(data))
    pool = assemble_pool(fleet, refs)
    assert len(pool) == 3  # missing file skipped, not crashed


def test_normalize_pool_frames_crops_tall_images_only(tmp_path: Path) -> None:
    Image = pytest.importorskip("PIL.Image")  # Pillow is an optional (viewport) dep

    from dazzle.qa.taste_panel import PanelImage, normalize_pool_frames

    tall = tmp_path / "tall.png"
    Image.new("RGB", (1440, 3000), "white").save(tall)
    fits = tmp_path / "fits.png"
    Image.new("RGB", (1440, 900), "white").save(fits)
    pool = [
        PanelImage(image_id="img-00", source="dazzle", label="a", path=tall, theme="light"),
        PanelImage(image_id="img-01", source="reference", label="r", path=fits, theme="light"),
    ]
    normalized = normalize_pool_frames(pool, frame_width=1440, frame_height=900)
    with Image.open(normalized[0].path) as img:
        assert img.size == (1440, 900)
    assert normalized[0].path.stem.endswith("-frame")
    assert normalized[0].image_id == "img-00"  # identity preserved
    assert normalized[1].path == fits  # in-frame image untouched


def test_blind_order_is_deterministic_and_shuffled(tmp_path: Path) -> None:
    fleet, refs = _write_manifests(tmp_path)
    pool = assemble_pool(fleet, refs)
    assert blind_order(pool, seed=7) == blind_order(pool, seed=7)
    assert {p.image_id for p in blind_order(pool, seed=7)} == {p.image_id for p in pool}


def test_aggregate_scores_means_by_source() -> None:
    scores = [
        JudgeScore(image_id="d1", dimension="perceived_craft", score=4, judge=0),
        JudgeScore(image_id="d1", dimension="perceived_craft", score=6, judge=1),
        JudgeScore(image_id="r1", dimension="perceived_craft", score=8, judge=0),
    ]
    sources = {"d1": "dazzle", "r1": "reference"}
    means = aggregate_scores(scores, sources=sources)
    assert means["perceived_craft"]["dazzle"] == pytest.approx(5.0)
    assert means["perceived_craft"]["reference"] == pytest.approx(8.0)


def test_noise_sd_pooled_over_repeats() -> None:
    scores = [
        JudgeScore(image_id="d1", dimension="perceived_craft", score=5, judge=0, repeat=0),
        JudgeScore(image_id="d1", dimension="perceived_craft", score=7, judge=0, repeat=1),
        JudgeScore(image_id="r1", dimension="perceived_craft", score=8, judge=0, repeat=0),
        JudgeScore(image_id="r1", dimension="perceived_craft", score=8, judge=0, repeat=1),
    ]
    sd = noise_sd(scores)
    # d1 sample-SD^2 = 2, r1 = 0 → pooled = sqrt((2+0)/2) = 1.0
    assert sd["perceived_craft"] == pytest.approx(1.0)


def test_parity_verdict_margin_floor_and_gap() -> None:
    means = {"perceived_craft": {"dazzle": 6.4, "reference": 7.0}}
    verdict = parity_verdict(means, {"perceived_craft": 0.1}, floor=0.5)
    v = verdict["perceived_craft"]
    assert v["margin"] == pytest.approx(0.5)  # floor beats 2*0.1
    assert v["gap"] == pytest.approx(0.6)
    assert v["parity"] is False  # 6.4 < 7.0 - 0.5
    verdict2 = parity_verdict(means, {"perceived_craft": 0.4}, floor=0.5)
    assert verdict2["perceived_craft"]["margin"] == pytest.approx(0.8)
    assert verdict2["perceived_craft"]["parity"] is True  # 6.4 >= 7.0 - 0.8
