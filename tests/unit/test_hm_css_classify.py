"""Phase C — load-bearing CSS classifier + token-literal heuristics."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.hm_css_classify import analyse_css_text, classify_prop, scan

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]


def test_classify_prop_buckets() -> None:
    assert classify_prop("display") == "load_bearing"
    assert classify_prop("pointer-events") == "load_bearing"
    assert classify_prop("z-index") == "load_bearing"
    assert classify_prop("color") == "aesthetic"
    assert classify_prop("box-shadow") == "aesthetic"
    assert classify_prop("margin-top") == "load_bearing"
    assert classify_prop("--space-md") == "token_var"


def test_analyse_load_bearing_and_tokens() -> None:
    css = """
    .hidden { display: none; pointer-events: none; }
    .pretty { color: #ff00aa; border-radius: 8px; box-shadow: 0 2px 4px #000; }
    .ok { color: var(--colour-text); padding: var(--space-md); }
    """
    row = analyse_css_text(css, path="components/demo.css")
    assert row["load_bearing"] >= 2
    assert row["aesthetic"] >= 2
    assert row["token_finding_count"] >= 1
    kinds = {t["kind"] for t in row["token_findings"]}
    assert "color_literal" in kinds


def test_token_file_allowlisted() -> None:
    css = ".root { color: #112233; padding: 16px; }"
    row = analyse_css_text(css, path="packages/hatchi-maxchi/tokens/tokens.css")
    assert row["token_finding_count"] == 0


def test_scan_repo_runs() -> None:
    result = scan(REPO)
    assert result["files_scanned"] > 0
    assert result["declarations"] > 0
    assert "load_bearing" in result["by_kind"]
    assert "policy" in result
