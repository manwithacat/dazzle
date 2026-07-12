"""Composition matrix harness — host chrome shells × guest Hyperparts."""

from __future__ import annotations

import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PKG / "tools"))

from composition_matrix import (  # noqa: E402
    COMPAT,
    GUESTS,
    HOSTS,
    INCOMPATIBLE,
    PLAYWRIGHT_CELLS,
    assemble,
    cell_policy,
    validate_all,
    validate_cell,
    validate_gallery_drawer_source,
    write_catalog,
)


def test_hosts_and_guests_catalogued() -> None:
    assert "drawer.form_shell" in HOSTS
    assert "drawer.exchange_shell" in HOSTS
    assert "dialog.form_shell" in HOSTS
    assert "dialog.exchange_shell" in HOSTS
    for g in (
        "field",
        "switch",
        "toggle-group",
        "card",
        "badge",
        "alert",
        "controls",
        "button",
        "menu",
        "tabs",
        "separator",
        "empty-state",
        "popover",
        "kbd",
        "skeleton",
        "nested-form",
        "nested-dialog",
        "command",
    ):
        assert g in GUESTS, g


def test_all_compatible_cells_pass() -> None:
    results = validate_all()
    fails = [c for c in results if c.status == "FAIL"]
    assert not fails, "\n".join(f"{c.host_id} × {c.guest_id}: {c.errors}" for c in fails)
    assert all(c.status in ("PASS", "SKIP") for c in results)
    # Expect some deliberate SKIPs (refusals)
    skips = [c for c in results if c.status == "SKIP"]
    assert len(skips) >= 8, f"expected incompatible cells, got {len(skips)}"


def test_incompatible_cells_have_reasons() -> None:
    assert INCOMPATIBLE
    for (h, g), reason in INCOMPATIBLE.items():
        assert h in HOSTS and g in GUESTS
        assert reason.strip()
        ok, r = cell_policy(h, g)
        assert not ok
        assert r


def test_nested_form_only_on_exchange_shell() -> None:
    r_form = validate_cell("drawer.form_shell", "nested-form")
    r_exch = validate_cell("drawer.exchange_shell", "nested-form")
    assert r_form.status == "SKIP"
    assert "exchange_shell" in r_form.notes or "form" in r_form.notes.lower()
    assert r_exch.status == "PASS"


def test_nested_dialog_and_command_always_skipped() -> None:
    for guest in ("nested-dialog", "command"):
        for host in HOSTS:
            r = validate_cell(host, guest)
            assert r.status == "SKIP", f"{host}×{guest} should refuse"
            assert r.notes


def test_form_shell_and_exchange_shell_differ_in_form_scope() -> None:
    form_html = assemble("drawer.form_shell", "field")
    exch_html = assemble("drawer.exchange_shell", "field")
    assert form_html.count('method="dialog"') == 1
    assert exch_html.count('method="dialog"') >= 2
    for part in ("drawer__header", "drawer__body", "drawer__footer"):
        assert part in form_html and part in exch_html


def test_switch_guest_rejects_controls_pill() -> None:
    from composition_matrix import _check_switch_track

    bad = '<label class="hm-inline"><input type="checkbox" class="dz-switch"></label>'
    assert _check_switch_track(bad)


def test_toggle_group_rejects_inner_legend() -> None:
    from composition_matrix import _check_toggle_no_legend

    bad = (
        '<fieldset class="dz-toggle-group" role="radiogroup">'
        "<legend>Density</legend>"
        "<label><input type=radio><span>A</span></label></fieldset>"
    )
    assert _check_toggle_no_legend(bad)


def test_gallery_drawer_pins() -> None:
    errs = validate_gallery_drawer_source()
    assert not errs, errs


def test_compat_covers_declared_pairs() -> None:
    for h in HOSTS:
        for g in GUESTS:
            assert (h, g) in COMPAT
            r = validate_cell(h, g)
            assert r.status in ("PASS", "SKIP", "FAIL")


def test_playwright_cells_are_compatible() -> None:
    for h, g in PLAYWRIGHT_CELLS:
        ok, reason = cell_policy(h, g)
        assert ok, f"{h}×{g}: {reason}"


def test_write_catalog(tmp_path: Path) -> None:
    out = tmp_path / "COMPOSITION_MATRIX.md"
    write_catalog(out)
    text = out.read_text(encoding="utf-8")
    assert "drawer.form_shell" in text
    assert "nested-dialog" in text
    assert "Compatibility grid" in text
    assert "Y" in text and "N" in text
