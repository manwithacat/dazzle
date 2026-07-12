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
    assemble,
    validate_all,
    validate_cell,
    validate_gallery_drawer_source,
)


def test_hosts_and_guests_catalogued() -> None:
    assert "drawer.form_shell" in HOSTS
    assert "drawer.exchange_shell" in HOSTS
    assert "dialog.form_shell" in HOSTS
    for g in (
        "field",
        "switch",
        "toggle-group",
        "card",
        "badge",
        "alert",
        "controls",
    ):
        assert g in GUESTS


def test_all_compatible_cells_pass() -> None:
    results = validate_all()
    fails = [c for c in results if c.status == "FAIL"]
    assert not fails, "\n".join(f"{c.host_id} × {c.guest_id}: {c.errors}" for c in fails)
    assert all(c.status in ("PASS", "SKIP") for c in results)


def test_form_shell_and_exchange_shell_differ_in_form_scope() -> None:
    form_html = assemble("drawer.form_shell", "field")
    exch_html = assemble("drawer.exchange_shell", "field")
    assert form_html.count('method="dialog"') == 1
    assert exch_html.count('method="dialog"') >= 2
    # same BEM chrome
    for part in ("drawer__header", "drawer__body", "drawer__footer"):
        assert part in form_html and part in exch_html


def test_switch_guest_rejects_controls_pill() -> None:
    # Sanity: the check fires on bad markup
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
