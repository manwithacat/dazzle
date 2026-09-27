"""Blind review packs do not leak variants or lose human calibration cases."""

import json
import struct
from pathlib import Path

import pytest
from scripts.agent_taste_pairs import PNG_SIGNATURE, adjudicate, prepare


def _png(path: Path, *, width: int = 1440, height: int = 900) -> None:
    path.write_bytes(PNG_SIGNATURE + b"\x00\x00\x00\rIHDR" + struct.pack(">II", width, height))


def _json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_prepare_blinds_variant_paths_and_requires_matching_viewports(tmp_path: Path) -> None:
    _png(tmp_path / "full.png")
    _png(tmp_path / "focus.png")
    source = tmp_path / "cases.json"
    _json(
        source,
        [
            {
                "id": "engineer-seeded",
                "persona": "engineer",
                "job": "Find the next field issue",
                "state": "seeded",
                "screens": {"full": "full.png", "focus": "focus.png"},
            }
        ],
    )
    review_dir = tmp_path / "blind"
    mapping = tmp_path / "private-mapping.json"

    manifest_path = prepare(source, review_dir, mapping, seed=5)

    public_text = manifest_path.read_text(encoding="utf-8")
    assert "full.png" not in public_text
    assert "focus.png" not in public_text
    assert "engineering" not in public_text
    assert sorted(path.name for path in review_dir.iterdir()) == [
        "case-001-A.png",
        "case-001-B.png",
        "manifest.json",
    ]
    assert json.loads(public_text)[0]["viewport"] == [1440, 900]
    assert set(json.loads(mapping.read_text(encoding="utf-8"))[0]["variants"].values()) == {
        "full",
        "focus",
    }

    _png(tmp_path / "focus.png", height=768)
    with pytest.raises(ValueError, match="different dimensions"):
        prepare(source, tmp_path / "another-pack", tmp_path / "another-map.json", seed=5)


def test_adjudication_routes_disagreement_and_samples_agreement(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    _json(
        manifest,
        [
            {"case_id": "case-001", "A": "case-001-A.png", "B": "case-001-B.png"},
            {"case_id": "case-002", "A": "case-002-A.png", "B": "case-002-B.png"},
        ],
    )
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    _json(
        first,
        [
            {"case_id": "case-001", "winner": "A", "reason": "Urgency is readable"},
            {"case_id": "case-002", "winner": "B", "reason": "Evidence is closer"},
        ],
    )
    _json(
        second,
        [
            {"case_id": "case-001", "winner": "B", "reason": "Action is clearer"},
            {"case_id": "case-002", "winner": "B", "reason": "Evidence is closer"},
        ],
    )

    output = tmp_path / "human-queue.json"
    adjudicate(manifest, [first, second], output, seed=5)

    queue = json.loads(output.read_text(encoding="utf-8"))
    assert [(item["case_id"], item["reason_for_human"]) for item in queue] == [
        ("case-001", "disagreement"),
        ("case-002", "calibration"),
    ]


def test_adjudication_rejects_incomplete_review(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    _json(manifest, [{"case_id": "case-001"}])
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    _json(first, [{"case_id": "case-001", "winner": "A", "reason": "clear"}])
    _json(second, [])

    with pytest.raises(ValueError, match="does not cover"):
        adjudicate(manifest, [first, second], tmp_path / "queue.json", seed=0)
