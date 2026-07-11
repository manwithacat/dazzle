"""Phase C — reservoir metric + port-suggestion heuristics."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.hm_tailwind_reservoir import port_suggestions, scan

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]


def test_scan_includes_port_suggestions_key() -> None:
    result = scan(REPO)
    assert "port_suggestions" in result
    assert isinstance(result["port_suggestions"], list)
    assert result["css_lines_grand_total"] == 0


def test_port_suggestions_name_match_and_unknown() -> None:
    rows = port_suggestions(
        REPO,
        [
            ("src/dazzle/page/runtime/static/css/dz-pdf.css", 40),
            ("src/dazzle/page/runtime/static/css/mystery-widget.css", 12),
        ],
    )
    by_css = {r["dazzle_css"]: r for r in rows}
    pdf = by_css["src/dazzle/page/runtime/static/css/dz-pdf.css"]
    assert "pdf" in pdf["hm_candidates"]
    assert pdf["hm_candidates"].count("pdf") == 1  # de-duped
    assert pdf["action"] == "port_or_delete_duplicate"

    mystery = by_css["src/dazzle/page/runtime/static/css/mystery-widget.css"]
    assert mystery["hm_candidates"] == []
    assert mystery["action"] == "author_new_hm_or_rewrite_to_tokens"
