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
    assert "menubar.dismiss_outside" in ids
    assert "menubar.escape_dismiss" in ids
    assert "navigation_menu.exclusive_open" in ids
    assert "navigation_menu.dismiss_outside" in ids
    assert "popover.dismiss_outside" in ids
    assert "menu.dismiss_outside" in ids
    assert "dialog.escape_closes" in ids
    assert "drawer.escape_closes" in ids
    assert "command.escape_closes" in ids
    assert "menu.escape_dismiss" in ids
    assert "accordion.exclusive_open" in ids
    assert "tree.multi_open" in ids
    assert "tooltip.hover_shows_hint" in ids
    assert "tooltip.force_open_shows_hint" in ids
    assert "popover.escape_dismiss" in ids
    assert "hover_card.escape_closes" in ids
    assert "hover_card.dismiss_outside" in ids
    assert "tabs.exclusive_select" in ids
    assert "switch.toggles_checked" in ids
    assert "controls.checkbox_toggles" in ids
    assert "controls.switch_toggles" in ids
    assert "slider.updates_readout" in ids
    assert "toggle.pressed_flips" in ids
    assert "toggle_group.radio_exclusive" in ids
    assert "carousel.advance_next" in ids
    assert "combobox.enhance_and_select" in ids
    assert "wizard.forward_after_valid" in ids
    assert "toast.dismiss_and_client_fire" in ids
    assert "tags.seed_add_and_remove" in ids
    assert "search_select.open_typeahead_select_hold" in ids
    assert "money.sync_minor_and_blur_normalize" in ids
    assert "app_shell.sidebar_toggle" in ids
    assert "master_detail.select_item" in ids
    assert "pagination.page_two_loads_rows" in ids
    assert "date_range.change_fires_search" in ids
    for p in PROBES:
        assert p.stem and p.page and p.kind and p.claim
        assert p.severity in {"blocker", "high", "medium", "low"}
        assert p.intent in {"exclusive", "multi_open", "hover"}
        assert p.kind in {
            "exclusive_details_open",
            "multi_details_open",
            "details_dismiss_outside",
            "details_escape_dismiss",
            "native_dialog_escape",
            "css_tooltip_hover",
            "css_tooltip_force_open",
            "data_open_escape",
            "data_open_dismiss_outside",
            "tabs_exclusive_select",
            "checkbox_toggle",
            "range_value_readout",
            "aria_pressed_toggle",
            "radio_group_select",
            "carousel_advance",
            "combobox_select",
            "wizard_step_forward",
            "toast_dismiss_and_fire",
            "tags_seed_add_remove",
            "search_select_typeahead_select",
            "money_sync_minor_blur",
            "app_shell_sidebar_toggle",
            "confirm_intercept_accept",
            "master_detail_select",
            "pagination_page_load",
            "date_range_change",
        }
    slider = next(p for p in PROBES if p.id == "slider.updates_readout")
    assert slider.kind == "range_value_readout"
    assert slider.fix_surface == "controller"
    carousel = next(p for p in PROBES if p.id == "carousel.advance_next")
    assert carousel.kind == "carousel_advance"
    assert carousel.fix_surface == "controller"
    combobox = next(p for p in PROBES if p.id == "combobox.enhance_and_select")
    assert combobox.kind == "combobox_select"
    assert combobox.fix_surface == "controller"
    wizard = next(p for p in PROBES if p.id == "wizard.forward_after_valid")
    assert wizard.kind == "wizard_step_forward"
    assert wizard.fix_surface == "controller"
    toast = next(p for p in PROBES if p.id == "toast.dismiss_and_client_fire")
    assert toast.kind == "toast_dismiss_and_fire"
    assert toast.fix_surface == "controller"
    assert toast.page == "hyperparts/toast-live.html"
    tags = next(p for p in PROBES if p.id == "tags.seed_add_and_remove")
    assert tags.kind == "tags_seed_add_remove"
    assert tags.fix_surface == "controller"
    assert tags.page == "hyperparts/tags.html"
    search_select = next(p for p in PROBES if p.id == "search_select.open_typeahead_select_hold")
    assert search_select.kind == "search_select_typeahead_select"
    assert search_select.fix_surface == "controller"
    assert search_select.page == "hyperparts/search-select.html"
    money = next(p for p in PROBES if p.id == "money.sync_minor_and_blur_normalize")
    assert money.kind == "money_sync_minor_blur"
    assert money.fix_surface == "controller"
    assert money.page == "hyperparts/money.html"
    app_shell = next(p for p in PROBES if p.id == "app_shell.sidebar_toggle")
    assert app_shell.kind == "app_shell_sidebar_toggle"
    assert app_shell.fix_surface == "controller"
    assert app_shell.page == "hyperparts/app-shell-live.html"
    confirm = next(p for p in PROBES if p.id == "confirm.intercept_and_accept")
    assert confirm.kind == "confirm_intercept_accept"
    assert confirm.fix_surface == "controller"
    assert confirm.page == "hyperparts/confirm.html"
    master_detail = next(p for p in PROBES if p.id == "master_detail.select_item")
    assert master_detail.kind == "master_detail_select"
    assert master_detail.fix_surface == "controller"
    assert master_detail.page == "hyperparts/master-detail.html"
    assert master_detail.stem == "master-detail"
    pagination = next(p for p in PROBES if p.id == "pagination.page_two_loads_rows")
    assert pagination.kind == "pagination_page_load"
    assert pagination.fix_surface == "controller"
    assert pagination.page == "hyperparts/pagination.html"
    assert pagination.stem == "pagination"
    date_range = next(p for p in PROBES if p.id == "date_range.change_fires_search")
    assert date_range.kind == "date_range_change"
    assert date_range.fix_surface == "controller"
    assert date_range.page == "hyperparts/date-range.html"
    assert date_range.stem == "date-range"
    tree = next(p for p in PROBES if p.id == "tree.multi_open")
    assert tree.intent == "multi_open"
    assert tree.kind == "multi_details_open"
    dialog = next(p for p in PROBES if p.id == "dialog.escape_closes")
    assert dialog.kind == "native_dialog_escape"
    assert dialog.fix_surface == "controller"


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
