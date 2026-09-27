"""HM visual captures must represent the same current gallery on both platforms."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / "packages" / "hatchi-maxchi"
BASE = PACKAGE / "tests" / "baselines"
sys.path.insert(0, str(PACKAGE / "tools"))
from visual_baseline_manifest import image_hashes, source_digest  # noqa: E402


def test_hm_visual_baseline_darwin_linux_pairs_not_split() -> None:
    current_source = source_digest()
    sets: dict[str, set[str]] = {}
    for platform in ("darwin", "linux"):
        capture = BASE / platform / "capture.json"
        assert capture.is_file(), f"{platform} capture manifest missing; recapture visual baselines"
        recorded = json.loads(capture.read_text())
        assert recorded["source_digest"] == current_source, (
            f"{platform} visual baseline source is stale; recapture against current gallery"
        )
        current_images = image_hashes(platform)
        assert recorded["images"] == current_images, (
            f"{platform} visual images changed after capture manifest was written"
        )
        sets[platform] = set(current_images)

    assert sets["darwin"] == sets["linux"], (
        "Darwin and Linux visual scene coverage differs: "
        f"darwin-only={sorted(sets['darwin'] - sets['linux'])}, "
        f"linux-only={sorted(sets['linux'] - sets['darwin'])}"
    )
