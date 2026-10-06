"""The linux HM visual baseline is the committed oracle.

Darwin captures are local and gitignored. Standalone CI runs on Linux, and
only that set can make the pixel compare fail. A checkout without
``baselines/linux`` would skip the visual test instead of failing it.
"""

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


def test_hm_visual_baseline_linux_set_matches_its_manifest() -> None:
    current_source = source_digest()
    capture = BASE / "linux" / "capture.json"
    assert capture.is_file(), "linux capture manifest missing; recapture visual baselines"
    recorded = json.loads(capture.read_text())
    assert recorded["source_digest"] == current_source, (
        "linux visual baseline source is stale; recapture against current gallery"
    )
    current_images = image_hashes("linux")
    assert recorded["images"] == current_images, (
        "linux visual images changed after the capture manifest was written"
    )
    assert current_images, "linux baseline set is empty"
