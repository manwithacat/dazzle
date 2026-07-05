"""Hyperpart cohesion gate — the manifest and the code-site markers must
agree, so "these scattered files are all the same Hyperpart" stays TRUE
rather than rotting into a stale comment.

A Hyperpart's code is distributed by build necessity (markup + contract in
the registry, CSS concatenated in layer order, JS bundled). The binding is
declared two ways that must stay consistent:
  - top-down: the registry manifest (`controller`, `mock` pointers)
  - bottom-up: `HYPERPART: <id>` marker comments at each CSS block / controller

This gate enforces both directions. Interactive Hyperparts (those with a
controller — where the code is genuinely scattered across 4-5 files) must
be fully wired; pure-CSS Hyperparts adopt the marker convention as they're
touched.
"""

import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PKG))
sys.path.insert(0, str(PKG / "site"))
sys.path.insert(0, str(PKG / "tools"))

from hyperpart import marker_sites  # noqa: E402
from registry import HYPERPARTS  # noqa: E402

_IDS = {h.id for h in HYPERPARTS}
_CONTROLLERS_DIR = PKG / "controllers"
_MOCK_SRC = (PKG / "site" / "build_site.py").read_text(encoding="utf-8")


def test_declared_controllers_exist_and_are_marked() -> None:
    for h in HYPERPARTS:
        for ref in ((h.controller,) if h.controller else ()) + tuple(h.extensions):
            f = PKG / ref
            assert f.is_file(), f"{h.id}: declared controller {ref} does not exist"
            text = f.read_text(encoding="utf-8")
            assert f"HYPERPART: {h.id}" in text, (
                f"{h.id}: controller {ref} lacks its `HYPERPART: {h.id}` marker "
                "(bottom-up cohesion — an agent opening the file must see which "
                "Hyperpart it serves)"
            )


def test_no_unowned_controller() -> None:
    """Every controller file must be claimed by exactly one Hyperpart —
    an unowned controller is code with no home in the manifest."""
    declared = {h.controller for h in HYPERPARTS if h.controller}
    declared |= {ext for h in HYPERPARTS for ext in h.extensions}
    on_disk = {f"controllers/{f.name}" for f in _CONTROLLERS_DIR.glob("*.js")}
    unowned = sorted(on_disk - declared)
    assert not unowned, (
        f"controllers with no owning Hyperpart: {unowned} "
        "(add `controller=` or `extensions=` to one)"
    )


def test_declared_mock_endpoints_are_wired() -> None:
    for h in HYPERPARTS:
        if not h.mock:
            continue
        assert h.mock in _MOCK_SRC, (
            f"{h.id}: declared mock {h.mock} is not wired into the gallery mock "
            "(build_site.py RESPONSES) — the demo won't exercise the contract"
        )


def test_no_orphan_markers() -> None:
    """Every HYPERPART marker in the tree must name a real Hyperpart."""
    orphans = sorted(mid for mid in marker_sites() if mid not in _IDS)
    assert not orphans, f"HYPERPART markers naming unknown Hyperparts: {orphans}"


def test_interactive_hyperparts_have_a_style_marker() -> None:
    """A Hyperpart with a controller is genuinely scattered — its CSS must
    carry a marker so the styles half is discoverable, not lost."""
    sites = marker_sites()
    missing = [
        h.id
        for h in HYPERPARTS
        if h.controller and not any(".css" in s for s in sites.get(h.id, []))
    ]
    assert not missing, (
        f"interactive Hyperparts with no CSS `HYPERPART:` marker: {missing} "
        "(mark the component's CSS block so its styles are bound to the manifest)"
    )


def test_controller_marker_matches_owner() -> None:
    """A controller's marker id must equal the Hyperpart that declares it —
    no cross-wiring."""
    sites = marker_sites()
    for h in HYPERPARTS:
        if not h.controller:
            continue
        controller_sites = [s for s in sites.get(h.id, []) if s.startswith("controllers/")]
        assert any(h.controller in s for s in controller_sites), (
            f"{h.id}: its controller {h.controller} is not marked `HYPERPART: {h.id}` "
            f"(marker sites for {h.id}: {controller_sites})"
        )
