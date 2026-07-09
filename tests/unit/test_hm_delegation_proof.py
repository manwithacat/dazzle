"""HM delegation proof (Tier-2 sitespec directive, 2026-07-09).

Goal 1: *clear, machine-checkable proof that every design system + structure is
delegated from Dazzle into HaTchi-MaXchi.* This test enumerates every
Dazzle-native (non-HM-dist) CSS file the browser can receive and pins it to an
explicit allowlist with a delegation status:

- ``KEEP``      — a deliberate, documented Dazzle-side keep (not HM's job).
- ``MIGRATING`` — still Dazzle-native, scheduled to move into HM. Drains to zero
  as the Tier-2 phases land (site-sections → 1B, feedback/reset → 1C, themes → 2C).

Two guarantees:

1. ``test_served_css_matches_allowlist`` — the served Dazzle-native CSS set is
   EXACTLY the allowlist. Fails if a new undocumented Dazzle-native stylesheet
   appears (regression: someone added design CSS on the Dazzle side instead of
   HM) OR if a listed file was deleted without delisting (stale allowlist). This
   is the live ratchet that keeps the delegation honest cycle-over-cycle.

2. ``test_goal1_fully_delegated`` — asserts NO ``MIGRATING`` entries remain. It is
   ``xfail(strict=True)`` today (entries remain → expected fail → green). The
   moment Tier-2 drains the last ``MIGRATING`` entry it will XPASS, and strict
   xfail turns an unexpected pass into a FAILURE — forcing whoever finished the
   drain to delete the xfail marker and make this the standing green proof of
   Goal 1. That is the "clear proof" deliverable, wired to trip exactly when true.

The metric ``scripts/hm_tailwind_reservoir.py`` tracks the *size* of the drain;
this gate proves the *boundary*.
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

_REPO_ROOT = Path(__file__).resolve().parents[2]
_STATIC = _REPO_ROOT / "src" / "dazzle" / "page" / "runtime" / "static"

# Peripheral Dazzle-native design CSS served outside the css_loader main bundle
# (kept in sync with scripts/hm_tailwind_reservoir.py::_CSS_PERIPHERAL_GLOBS).
_PERIPHERAL_GLOBS = ("css/themes/*.css",)

# The single source of truth for Goal 1. Every Dazzle-native CSS file the browser
# receives must appear here. `custom.css` (project escape hatch) is not served by
# the framework bundle and is intentionally out of scope.
DELEGATION_ALLOWLIST: dict[str, str] = {
    # --- main bundle (css_loader.py) ---
    "css/reset.css": "KEEP",  # foundational reset layer; dedup vs HM vendor reset tracked in 1C
    "css/dz.css": "KEEP",  # all-pages `.htmx-indicator` HTMX chrome — documented floor
    # css/site-sections.css DELEGATED → HM components/sitespec.css (phase 1B, 2026-07-09).
    # css/feedback-widget.css DELEGATED → HM components/feedback-widget.css (phase 1C,
    # 2026-07-09) — was orphaned (unlinked) on the Dazzle side; now served via the HM dist.
    # --- peripheral (served outside the main bundle) ---
    "css/themes/stripe.css": "MIGRATING",  # → HM aesthetic-family token set (phase 2C)
    "css/themes/paper.css": "MIGRATING",  # → HM aesthetic-family token set (phase 2C)
    "css/themes/linear-dark.css": "MIGRATING",  # → HM aesthetic-family token set (phase 2C)
}


def _served_dazzle_native_rels() -> set[str]:
    """Every Dazzle-native (non-HM-dist, non-vendor) CSS file the browser gets:
    the css_loader main bundle plus the peripheral (feedback/themes) files."""
    from dazzle.page.runtime.css_loader import CSS_SOURCE_FILES, CSS_UNLAYERED_FILES

    rels: set[str] = set()
    for layer, rel in CSS_SOURCE_FILES:
        if layer is None:  # the HM dist artifact (`@hm-build:dz-`) — already HM-owned
            continue
        if rel.startswith("vendor/"):  # third-party CSS, not a design-delegation target
            continue
        rels.add(rel)
    rels.update(CSS_UNLAYERED_FILES)
    for pattern in _PERIPHERAL_GLOBS:
        if "*" in pattern:
            parent = _STATIC / Path(pattern).parent
            rels.update(str(p.relative_to(_STATIC)) for p in parent.glob(Path(pattern).name))
        elif (_STATIC / pattern).exists():
            rels.add(pattern)
    return rels


def test_served_css_matches_allowlist() -> None:
    """The served Dazzle-native CSS set is EXACTLY the delegation allowlist —
    no undocumented additions, no stale (deleted-but-listed) entries."""
    served = _served_dazzle_native_rels()
    allow = set(DELEGATION_ALLOWLIST)

    undocumented = served - allow
    assert not undocumented, (
        "New Dazzle-native design CSS is served but not in DELEGATION_ALLOWLIST: "
        f"{sorted(undocumented)}. Design CSS belongs in HaTchi-MaXchi — either move "
        "it into HM, or (if it is a deliberate Dazzle-side keep) add it as KEEP with "
        "a rationale."
    )
    stale = allow - served
    assert not stale, (
        f"DELEGATION_ALLOWLIST lists CSS files that are no longer served: "
        f"{sorted(stale)}. They were migrated/deleted — delist them so the allowlist "
        "stays an honest picture of the delegation boundary."
    )


@pytest.mark.xfail(
    strict=True,
    reason="Tier-2 sitespec convergence in progress — MIGRATING entries remain. "
    "When the last one drains this XPASSes; strict-xfail then fails CI to force "
    "removing this marker and standing up the green Goal-1 proof.",
)
def test_goal1_fully_delegated() -> None:
    """Goal 1 is proven when zero MIGRATING entries remain — every design rule the
    browser receives originates in HaTchi-MaXchi (or a documented KEEP)."""
    migrating = sorted(f for f, status in DELEGATION_ALLOWLIST.items() if status == "MIGRATING")
    assert not migrating, f"Still Dazzle-native (not yet delegated to HM): {migrating}"
