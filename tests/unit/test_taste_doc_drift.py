"""docs/reference/taste.md must list exactly the live rubric dimensions."""

import re
from pathlib import Path

import pytest

from dazzle.core.taste_rubric import TASTE_DIMENSIONS

pytestmark = pytest.mark.gate

DOC = Path(__file__).parents[2] / "docs" / "reference" / "taste.md"


def test_taste_doc_exists() -> None:
    assert DOC.exists(), "docs/reference/taste.md is the canonical taste artifact"


def test_taste_doc_lists_every_rubric_dimension_exactly() -> None:
    text = DOC.read_text(encoding="utf-8")
    # Rubric section rows: | `key` | ... |
    doc_keys = re.findall(r"^\| `([a-z_]+)` \|", text, flags=re.MULTILINE)
    assert doc_keys == [d.key for d in TASTE_DIMENSIONS]


def test_taste_doc_has_principles_rules_and_rubric() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "## Principles" in text and "## Rules" in text and "## Rubric" in text
    # Rules are numbered TASTE-n, contiguous from 1, and at least 8 exist
    rules = re.findall(r"\*\*TASTE-(\d+)\*\*", text)
    assert len(rules) >= 8
    assert rules == [str(i) for i in range(1, len(rules) + 1)]
