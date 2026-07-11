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


# Controller/extension files whose Hyperpart does not yet declare a contract
# module. SHRINK-ONLY: remove entries as contracts land; never add to it.
# SHRINK-ONLY — empty means every controller/extension has a contract module
# (or rides a Hyperpart that declares contracts= covering it).
PENDING_CONTRACTS = frozenset()


def test_declared_contracts_exist() -> None:
    for h in HYPERPARTS:
        for ref in h.contracts:
            assert (PKG / ref).is_file(), f"{h.id}: declared contract {ref} does not exist"


def test_controller_bearing_hyperparts_have_contracts_or_pending() -> None:
    """The rollout ratchet: every controller/extension file is either covered
    by its Hyperpart's contract modules or explicitly PENDING. New controllers
    without contracts fail here (spec: allowlist only shrinks)."""
    for h in HYPERPARTS:
        files = ((h.controller,) if h.controller else ()) + tuple(h.extensions)
        for ref in files:
            if ref in PENDING_CONTRACTS:
                continue
            assert h.contracts, (
                f"{h.id}: controller {ref} has no contract module and is not in "
                f"PENDING_CONTRACTS — write contracts/<part>.py (see contracts/AUTHORING.md)"
            )


def test_pending_contracts_entries_are_real() -> None:
    """Stale-allowlist guard: every PENDING entry must name a controller file
    that is actually declared by some Hyperpart."""
    known = {
        ref
        for h in HYPERPARTS
        for ref in ((h.controller,) if h.controller else ()) + tuple(h.extensions)
    }
    ghosts = sorted(PENDING_CONTRACTS - known)
    assert not ghosts, f"PENDING_CONTRACTS names unknown controllers: {ghosts}"


# Controller-bearing Hyperparts not yet migrated to structured Guidance.
# SHRINK-ONLY — empty means every controller-bearing part has Guidance.
PENDING_GUIDANCE = frozenset()


def test_controller_parts_have_guidance_or_pending() -> None:
    for h in HYPERPARTS:
        if not h.controller or h.id in PENDING_GUIDANCE:
            continue
        g = h.guidance
        assert g is not None and g.seams and g.pitfalls, (
            f"{h.id}: controller-bearing part needs Guidance with seams + pitfalls "
            f"(or a PENDING_GUIDANCE entry — which only shrinks)"
        )


def test_guidance_composes_with_ids_are_real() -> None:
    for h in HYPERPARTS:
        if h.guidance:
            ghosts = sorted(set(h.guidance.composes_with) - _IDS)
            assert not ghosts, f"{h.id}: guidance.composes_with names unknown parts {ghosts}"


def test_every_part_has_a_committed_page() -> None:
    for h in HYPERPARTS:
        assert (PKG / "site" / "hyperparts" / f"{h.id}.html").is_file(), (
            f"{h.id}: no committed part page — run site/build_site.py and commit"
        )


# Linear reference skeleton — every part page and agent pack shares the same
# section order so humans/agents never hit a "thin" page missing the model.
_LINEAR_SECTION_IDS = ("copy", "exchange", "how-to", "dom-contract", "files")
_LINEAR_MD_HEADINGS = (
    "## Copy this",
    "## Server exchange",
    "## How to use it",
    "## DOM contract",
    "## Source files",
)


def test_every_part_page_has_linear_skeleton() -> None:
    """hyperparts/<id>.html always exposes the dual-audience section spine."""
    for h in HYPERPARTS:
        html = (PKG / "site" / "hyperparts" / f"{h.id}.html").read_text(encoding="utf-8")
        for sid in _LINEAR_SECTION_IDS:
            assert f'id="{sid}"' in html, (
                f"{h.id}: part page missing section id={sid!r} — "
                "run site/build_site.py (always-on skeleton)"
            )
        # Dogfood: theme is HM toggle-group; nav is HM breadcrumb; snippets use code Hyperpart.
        assert "toggle-group" in html, f"{h.id}: theme toggle must dogfood toggle-group"
        assert "breadcrumb" in html, f"{h.id}: part chrome must dogfood breadcrumb"
        assert 'class="code"' in html or "class='code'" in html or "code__" in html, (
            f"{h.id}: snippets must dogfood the code Hyperpart"
        )
        # Meta (dialect / dogfood / provenance) is footer-only — not above the spine.
        # (CSS also mentions hm-page-meta — match the footer element, not the style block.)
        meta_marker = '<footer class="hm-page-meta"'
        assert meta_marker in html, f"{h.id}: missing page meta footer"
        assert "hm-dogfood" in html, f"{h.id}: missing dogfood meta item"
        assert "Markup dialect" in html, f"{h.id}: missing dialect meta item"
        assert "Source repository" in html, f"{h.id}: missing repo link in meta footer"
        assert "htmx" in html.lower() and "4.0.0" in html, (
            f"{h.id}: meta footer must surface the pinned htmx version"
        )
        assert f"agents/{h.id}.md" in html, f"{h.id}: missing agent-pack link"
        spine_pos = html.find('id="copy"')
        meta_pos = html.find(meta_marker)
        assert spine_pos != -1 and meta_pos != -1 and spine_pos < meta_pos, (
            f"{h.id}: page meta footer must come after the implementer spine"
        )


def test_every_agent_pack_has_linear_skeleton() -> None:
    """agents/<id>.md mirrors the HTML section order for scrape parity."""
    for h in HYPERPARTS:
        md = (PKG / "site" / "agents" / f"{h.id}.md").read_text(encoding="utf-8")
        for heading in _LINEAR_MD_HEADINGS:
            assert heading in md, f"{h.id}: agent pack missing {heading!r} — run site/build_site.py"


# Controller-bearing parts with no atomic behaviour scenario yet. SHRINK-ONLY.
# SHRINK-ONLY — empty means every controller-bearing part has an atomic scenario.
PENDING_BEHAVIOUR = frozenset()


def test_controller_parts_have_behaviour_coverage_or_pending() -> None:
    """Atomicity can't be quietly opted out of: every controller-bearing part
    needs at least one behaviour scenario targeting its own page — via
    goto_part(page, "<id>") or a direct hyperparts/<id>.html navigation (the
    pdf test serves its page over ephemeral http for file:// fetch limits)."""
    behaviour_src = (PKG / "tests" / "test_behaviour.py").read_text(encoding="utf-8")
    for h in HYPERPARTS:
        if not h.controller or h.id in PENDING_BEHAVIOUR:
            continue
        covered = (
            f'goto_part(page, "{h.id}")' in behaviour_src
            or f"hyperparts/{h.id}.html" in behaviour_src
        )
        assert covered, (
            f"{h.id}: controller-bearing part has no atomic behaviour scenario "
            f"(add one targeting hyperparts/{h.id}.html, or a PENDING_BEHAVIOUR "
            f"entry — which only shrinks)"
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
