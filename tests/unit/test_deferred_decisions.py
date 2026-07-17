"""Deferred Decisions log — greppable long-horizon plans (docs/decisions/).

Keeps PARKED plans from rotting into issue comments only. See
docs/decisions/INDEX.md.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
DECISIONS = REPO / "docs" / "decisions"
INDEX = DECISIONS / "INDEX.md"

_HEADER_RE = re.compile(
    r"```yaml\s*\n(.*?)```",
    re.DOTALL,
)
_STATUS_RE = re.compile(r"^status:\s*(\w+)\s*$", re.MULTILINE)
_ID_RE = re.compile(r"^id:\s*(DD-\d+)\s*$", re.MULTILINE)


def _dd_files() -> list[Path]:
    return sorted(p for p in DECISIONS.glob("DD-*.md") if p.is_file() and p.name != "TEMPLATE.md")


def test_decisions_dir_and_index_exist() -> None:
    assert DECISIONS.is_dir(), "docs/decisions/ missing — see INDEX.md convention"
    assert INDEX.is_file(), "docs/decisions/INDEX.md missing"


def test_each_dd_has_stable_header_and_index_row() -> None:
    index_text = INDEX.read_text(encoding="utf-8")
    files = _dd_files()
    assert files, "expected at least one DD-*.md (e.g. DD-001)"

    for path in files:
        text = path.read_text(encoding="utf-8")
        m = _HEADER_RE.search(text)
        assert m, f"{path.name}: missing ```yaml header block"
        header = m.group(1)
        id_m = _ID_RE.search(header)
        st_m = _STATUS_RE.search(header)
        assert id_m, f"{path.name}: header missing id: DD-N"
        assert st_m, f"{path.name}: header missing status:"
        dd_id = id_m.group(1)
        status = st_m.group(1)
        assert status in {"PARKED", "FORCED", "DONE", "SUPERSEDED"}, (
            f"{path.name}: invalid status {status!r}"
        )
        assert dd_id.lower() in path.name.lower() or dd_id in path.name, (
            f"{path.name}: filename should include {dd_id}"
        )
        assert dd_id in index_text, f"INDEX.md missing row for {dd_id}"
        assert "Reopen when" in text, f"{path.name}: missing Reopen when section"
        assert "Plan" in text or "plan" in text.lower(), f"{path.name}: missing Plan section"


def test_dd_001_links_1621_and_1622() -> None:
    """Regression: the #1617 residual parking must stay discoverable."""
    path = DECISIONS / "DD-001-1617-poly-ref-and-sti-eav.md"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "1621" in text and "1622" in text
    assert "status: PARKED" in text


def test_practice_note_and_epistemic_layout_point_at_decisions() -> None:
    """Agent didactics must keep DDs in the reconstruction hierarchy."""
    practice = REPO / "docs" / "architecture" / "epistemic-engineering-practice.md"
    layout = REPO / "stems" / "epistemic-layout.md"
    assert practice.is_file()
    assert "docs/decisions" in practice.read_text(
        encoding="utf-8"
    ) or "decisions/" in practice.read_text(encoding="utf-8")
    layout_text = layout.read_text(encoding="utf-8")
    assert "docs/decisions" in layout_text or "decisions/" in layout_text
    assert "PARKED" in layout_text or "Deferred" in layout_text
