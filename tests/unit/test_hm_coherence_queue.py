"""hm_coherence_queue — drain ranking for /improve hyperpart_coherence."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "scripts" / "hm_coherence_queue.py"


def _load():
    import sys

    name = "hm_coherence_queue_under_test"
    spec = importlib.util.spec_from_file_location(name, _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # required for @dataclass under importlib
    spec.loader.exec_module(mod)
    return mod


def test_queue_ranks_incoherent_first(tmp_path: Path) -> None:
    mod = _load()
    path = tmp_path / "coherence.json"
    path.write_text(
        json.dumps(
            {
                "n": 3,
                "n_coherent": 1,
                "n_incoherent": 2,
                "mean_score": 5.0,
                "results": [
                    {
                        "image_id": "button",
                        "path": "/b.png",
                        "coherent": True,
                        "score": 9,
                        "issues": [],
                    },
                    {
                        "image_id": "pdf",
                        "path": "/p.png",
                        "coherent": False,
                        "score": 4,
                        "issues": [
                            {
                                "severity": "high",
                                "category": "empty_demo",
                                "description": "failed load",
                            }
                        ],
                    },
                    {
                        "image_id": "message",
                        "path": "/m.png",
                        "coherent": False,
                        "score": 6,
                        "issues": [
                            {
                                "severity": "medium",
                                "category": "spacing",
                                "description": "meta collision",
                            }
                        ],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    q = mod.build_queue(path)
    stems = [c.stem for c in q]
    assert stems[0] == "pdf"
    assert "message" in stems
    assert "button" not in stems
    assert q[0].backlog_scope == "coherence_drain pdf"
    rows = mod.seed_backlog_rows(q, start_id=56)
    assert rows[0].startswith("| HMC-056 | coherence_drain pdf |")


def test_status_missing(tmp_path: Path) -> None:
    mod = _load()
    line = mod.status_line(tmp_path / "nope.json")
    assert "missing" in line
