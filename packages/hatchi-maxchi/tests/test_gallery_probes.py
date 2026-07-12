"""Unit tests for gallery interaction probe catalog (no browser)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from gallery_probes import (  # noqa: E402
    PROBES,
    _open_item_selector,
    discover_report,
    emit_findings,
    match_observation,
    write_catalog,
)


def test_open_item_selector_applies_to_each_branch() -> None:
    sel = _open_item_selector(".navigation-menu details, [data-navigation-menu] details")
    assert sel == (".navigation-menu details[open], [data-navigation-menu] details[open]")
    assert _open_item_selector("details.menubar__item") == "details.menubar__item[open]"


def test_catalog_has_core_exclusive_open_probes() -> None:
    ids = {p.id for p in PROBES}
    assert "menubar.exclusive_open" in ids
    assert "navigation_menu.exclusive_open" in ids
    assert "accordion.exclusive_open" in ids
    assert "tree.multi_open" in ids
    for p in PROBES:
        assert p.stem and p.page and p.kind and p.claim
        assert p.severity in {"blocker", "high", "medium", "low"}
        assert p.intent in {"exclusive", "multi_open"}
    tree = next(p for p in PROBES if p.id == "tree.multi_open")
    assert tree.intent == "multi_open"
    assert tree.kind == "multi_details_open"


def test_match_observation_menubar_file_edit() -> None:
    hits = match_observation({"stem": "menubar", "claim": "opening Edit leaves File open"})
    assert any(p.id == "menubar.exclusive_open" for p in hits)


def test_match_observation_navigation_menu() -> None:
    hits = match_observation(
        {
            "stem": "navigation-menu",
            "claim": "Product stays open when Resources opens",
        }
    )
    assert any(p.id == "navigation_menu.exclusive_open" for p in hits)


def test_match_observation_unknown_stem_returns_empty() -> None:
    hits = match_observation({"stem": "nonexistent-widget-xyz", "claim": "broken"})
    assert hits == []


def test_discover_covers_catalogued_stems() -> None:
    report = discover_report()
    assert report["schema"] == "hm.gallery_probes.v1"
    assert "summary" in report
    assert report["summary"]["uncovered"] == 0, report["uncovered_stems"]
    # menubar + navigation-menu + tree multi-details covered
    by_stem = {c["stem"]: c for c in report["candidates"] if "stem" in c}
    assert "menubar" in by_stem
    assert by_stem["menubar"]["in_probe_catalog"] is True
    assert "navigation-menu" in by_stem
    assert by_stem["navigation-menu"]["in_probe_catalog"] is True
    assert "tree" in by_stem
    assert by_stem["tree"]["in_probe_catalog"] is True
    assert "multi_open" in by_stem["tree"]["intents"]


def test_match_observation_tree_multi_open() -> None:
    hits = match_observation({"stem": "tree", "claim": "expanding one branch collapses siblings"})
    assert any(p.id == "tree.multi_open" for p in hits)


def test_emit_findings_empty_and_fail() -> None:
    empty = emit_findings({"results": []})
    assert "No FAIL" in empty
    md = emit_findings(
        {
            "results": [
                {
                    "id": "menubar.exclusive_open",
                    "stem": "menubar",
                    "severity": "high",
                    "fix_surface": "controller",
                    "claim": "exclusive",
                    "detail": "got 2 open",
                    "verdict": "FAIL",
                    "evidence_png": "/tmp/x.png",
                }
            ]
        }
    )
    assert "HMC-probe-menubar-exclusive_open" in md
    assert "PENDING" in md


def test_write_catalog_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # write_catalog always targets PKG/GALLERY_PROBES.md — just ensure it runs
    path = write_catalog()
    text = path.read_text(encoding="utf-8")
    assert "menubar.exclusive_open" in text
    assert "navigation_menu.exclusive_open" in text
