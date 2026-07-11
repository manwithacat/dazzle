"""Framework + package stems catalogues stay coherent (epistemic layout gate)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
STEMS = REPO / "stems"
HM_STEMS = REPO / "packages" / "hatchi-maxchi" / "stems"

_INDEX_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+\.md)\)")


def _index_targets(index: Path) -> list[Path]:
    text = index.read_text(encoding="utf-8")
    out: list[Path] = []
    for _label, rel in _INDEX_LINK.findall(text):
        if rel.startswith("http") or rel.startswith("../"):
            continue
        out.append((index.parent / rel).resolve())
    return out


def test_framework_stems_index_resolves() -> None:
    index = STEMS / "INDEX.md"
    assert index.is_file()
    assert (STEMS / "README.md").is_file()
    missing = [p for p in _index_targets(index) if not p.is_file()]
    assert not missing, f"stems/INDEX.md broken links: {missing}"


def test_framework_stem_files_have_claim_section() -> None:
    for path in sorted(STEMS.glob("*.md")):
        if path.name in ("README.md", "INDEX.md"):
            continue
        body = path.read_text(encoding="utf-8")
        assert "## Claim" in body, path.name
        assert "## Reconstruct" in body, path.name
        assert "## Expressions" in body, path.name


def test_hm_stems_index_resolves() -> None:
    index = HM_STEMS / "INDEX.md"
    assert index.is_file()
    missing = [p for p in _index_targets(index) if not p.is_file()]
    assert not missing, f"HM stems/INDEX.md broken links: {missing}"


def test_agents_md_points_at_stems() -> None:
    root = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    assert "stems/" in root
    assert "Epistemic layout" in root
    hm = (REPO / "packages" / "hatchi-maxchi" / "AGENTS.md").read_text(encoding="utf-8")
    assert "stems/INDEX.md" in hm


def test_docs_llms_txt_surfaces_stems() -> None:
    llms = (REPO / "docs" / "llms.txt").read_text(encoding="utf-8")
    assert "stems/" in llms
    assert "Epistemic entry" in llms or "Framework stems" in llms


def test_all_examples_have_stems() -> None:
    """Every example app mirrors framework stems with a local stems/ tree."""
    examples = REPO / "examples"
    missing: list[str] = []
    for path in sorted(examples.iterdir()):
        if not path.is_dir() or path.name.startswith(".") or path.name.startswith("_"):
            continue
        # only full example apps (dsl tree)
        if not (path / "dsl").is_dir():
            continue
        stems = path / "stems"
        if not (stems / "INDEX.md").is_file() or not (stems / "README.md").is_file():
            missing.append(path.name)
            continue
        # INDEX must link at least one local stem file that exists
        idx = (stems / "INDEX.md").read_text(encoding="utf-8")
        links = _INDEX_LINK.findall(idx)
        local = [
            (stems / rel).resolve()
            for _label, rel in links
            if not rel.startswith("http") and not rel.startswith("../")
        ]
        if not local or any(not p.is_file() for p in local):
            missing.append(f"{path.name}:broken-index")
    assert not missing, f"examples missing coherent stems/: {missing}"


def test_blank_template_includes_stems() -> None:
    blank = REPO / "src" / "dazzle" / "templates" / "blank" / "stems"
    assert (blank / "README.md").is_file()
    assert (blank / "INDEX.md").is_file()
