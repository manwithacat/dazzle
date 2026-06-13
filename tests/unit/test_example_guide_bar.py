"""Fast gate: the per-persona guide quality bar across every example app.

Companion to ``test_example_guides_concordance.py`` (which runs concordance
on the apps that already ship guides). This module:

  * lints every declared guide against the terseness / in-fiction /
    closes-the-loop bar, and
  * asserts a coverage PARTITION — every interactive persona is either
    covered by a conforming guide, deliberately EXEMPT, or on the explicit
    PENDING Phase-2 worklist.

Concordance itself is enforced for free: ``load_project_appspec`` raises
``LinkError`` if any guide's target/event/field/CTA-permit fails to resolve.

Design: docs/superpowers/specs/2026-06-13-example-app-guides-design.md
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from dazzle.core.appspec_loader import load_project_appspec

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = REPO_ROOT / "examples"

# Quality-bar thresholds (calibrated against the 7 existing guides:
# body max 130, title max 40, max 4 steps — caps leave deliberate headroom).
MAX_BODY_CHARS = 200
MAX_TITLE_CHARS = 60
MAX_STEPS_PER_GUIDE = 6

# In-fiction lint: high-signal meta tokens that break kayfabe. Conservative
# by design (zero false positives on the current corpus); widen only if a
# real meta-leak slips through.
_META_TOKENS = re.compile(
    r"\b(dazzle|showcase|demonstrat\w*|this demo|example app|sample data)\b",
    re.IGNORECASE,
)

_PERSONA_REF = re.compile(r"\bpersona\s*=\s*([A-Za-z_][A-Za-z0-9_]*)")


def _examples() -> list[str]:
    """Every example app (a dir under examples/ with a dazzle.toml).

    Reads disk so it auto-tracks the Phase 0 reclassification (11 apps).
    """
    return sorted(p.name for p in EXAMPLES_DIR.iterdir() if (p / "dazzle.toml").is_file())


def _load(app: str):  # noqa: ANN202 — AppSpec type kept implicit to avoid a heavy import
    return load_project_appspec(EXAMPLES_DIR / app)


def _audience_personas(audience: str | None) -> set[str]:
    return set(_PERSONA_REF.findall(audience or ""))


def _interactive_personas(appspec) -> set[str]:  # noqa: ANN001
    return {p.id for p in appspec.personas if getattr(p, "interactive", True)}


def _personas_with_guide(appspec) -> set[str]:  # noqa: ANN001
    covered: set[str] = set()
    for g in appspec.guides:
        covered |= _audience_personas(g.audience)
    return covered


# --- Coverage registries -------------------------------------------------
#
# Every interactive persona of every example must be in exactly one bucket:
#   1. covered by a conforming guide (audience names the persona), OR
#   2. EXEMPT — deliberately no guide (admins / power users; overlays are
#      friction for them — the support_tickets onboarding.dsl comment), OR
#   3. PENDING — the Phase-2 authoring worklist; a guide is owed.
#
# Phase 2 shrinks PENDING to {} as it authors guides (the hygiene ratchet in
# test_guide_registry_hygiene fails if a PENDING persona gains a guide but
# isn't removed here). A persona may move PENDING -> EXEMPT only with a
# one-line rationale added below.

# Admins / power users that deliberately get NO onboarding overlay.
_GUIDE_EXEMPT: dict[str, set[str]] = {
    "support_tickets": {"admin"},
    "ops_dashboard": {"admin"},
    "fieldtest_hub": {"admin"},
    "project_tracker": {"admin"},
    "design_studio": {"admin"},
    "llm_ticket_classifier": {"admin"},
    "acme_billing": {"admin"},
    "hr_records": {"hr_admin"},
    "invoice_ops": {"tenant_admin", "finance_admin"},
}

# Interactive personas still owed a guide (Phase 2 worklist). DRAINED:
# Phase 2 completed 2026-06-13 — every example app now carries a guide for
# each interactive persona (admins exempt above). A new app/persona without a
# guide must be added here (or to _GUIDE_EXEMPT) or test_guide_coverage_partition
# fails. llm_ticket_classifier's two guides are intentionally orientation-only
# pending an optional DSL uplift (the app is view-centric; see PLAN.md).
_PENDING_GUIDE_AUTHORING: dict[str, set[str]] = {}


@pytest.mark.parametrize("app", _examples())
def test_example_appspec_loads(app: str) -> None:
    """Every example loads (which also enforces guide concordance)."""
    appspec = _load(app)
    assert appspec is not None
    # personas list is the substrate the coverage gate depends on
    assert isinstance(appspec.personas, list)


@pytest.mark.parametrize("app", _examples())
def test_guide_copy_is_terse(app: str) -> None:
    """Overlay copy stays terse — body/title under cap, <= 6 steps/guide.

    Onboarding overlays nobody reads a paragraph in; the cap is the
    structural enforcement of the design's "terse, in-fiction" rule and
    the parking of the externalised-content layer (Option B).
    """
    appspec = _load(app)
    problems: list[str] = []
    for g in appspec.guides:
        if len(g.steps) > MAX_STEPS_PER_GUIDE:
            problems.append(f"guide {g.name!r}: {len(g.steps)} steps > {MAX_STEPS_PER_GUIDE} cap")
        for s in g.steps:
            if len(s.body) > MAX_BODY_CHARS:
                problems.append(
                    f"guide {g.name!r} step {s.name!r}: body {len(s.body)} chars "
                    f"> {MAX_BODY_CHARS} cap — tighten it or move long-form content "
                    f"to a help surface (overlays must stay terse)"
                )
            if len(s.title) > MAX_TITLE_CHARS:
                problems.append(
                    f"guide {g.name!r} step {s.name!r}: title {len(s.title)} chars "
                    f"> {MAX_TITLE_CHARS} cap"
                )
    assert not problems, f"{app}: terseness violations:\n  " + "\n  ".join(problems)


@pytest.mark.parametrize("app", _examples())
def test_guide_copy_is_in_fiction(app: str) -> None:
    """Guide copy speaks as the product, never as a meta demo.

    Kayfabe: a guide says "File a ticket", never "this example shows
    bar_chart". Conservative high-signal token list (zero false positives
    on the current corpus).
    """
    appspec = _load(app)
    problems: list[str] = []
    for g in appspec.guides:
        for s in g.steps:
            for field_name, text in (("title", s.title), ("body", s.body)):
                hit = _META_TOKENS.search(text)
                if hit:
                    problems.append(
                        f"guide {g.name!r} step {s.name!r} {field_name}: meta phrase "
                        f"{hit.group(0)!r} breaks kayfabe — write as the product"
                    )
    assert not problems, f"{app}: in-fiction violations:\n  " + "\n  ".join(problems)


@pytest.mark.parametrize("app", _examples())
def test_guide_closes_the_loop(app: str) -> None:
    """Every guide ends by sending the user somewhere useful.

    A guide that finishes without an ``on_complete.redirect`` leaves the
    user stranded on the last step's surface. All 7 existing guides set it.
    """
    appspec = _load(app)
    problems: list[str] = []
    for g in appspec.guides:
        redirect = getattr(g.on_complete, "redirect", None) if g.on_complete else None
        if not redirect:
            problems.append(
                f"guide {g.name!r}: missing on_complete.redirect — a finished "
                f"guide must route the user to their home surface"
            )
    assert not problems, f"{app}: closes-the-loop violations:\n  " + "\n  ".join(problems)


@pytest.mark.parametrize("app", _examples())
def test_guide_coverage_partition(app: str) -> None:
    """Every interactive persona is covered, exempt, or explicitly pending.

    This is the gate that drives Phase 2: an interactive persona that is
    neither covered nor classified FAILS, forcing either a guide or an
    explicit EXEMPT/PENDING decision.
    """
    appspec = _load(app)
    interactive = _interactive_personas(appspec)
    covered = _personas_with_guide(appspec) & interactive
    exempt = _GUIDE_EXEMPT.get(app, set())
    pending = _PENDING_GUIDE_AUTHORING.get(app, set())

    unclassified = interactive - covered - exempt - pending
    assert not unclassified, (
        f"{app}: interactive persona(s) {sorted(unclassified)} have no guide and "
        f"aren't EXEMPT or PENDING. Author a guide whose audience names them, or "
        f"add them to _GUIDE_EXEMPT (with rationale) / _PENDING_GUIDE_AUTHORING in "
        f"tests/unit/test_example_guide_bar.py."
    )


def test_guide_registry_hygiene() -> None:
    """The coverage registries stay honest as Phase 2 progresses.

    - EXEMPT and PENDING name only real interactive personas of real apps.
    - No persona is in both EXEMPT and PENDING.
    - No PENDING persona already has a guide (the ratchet: Phase 2 must
      remove a persona from PENDING when it authors that persona's guide).
    """
    examples = set(_examples())
    problems: list[str] = []

    for registry_name, registry in (
        ("_GUIDE_EXEMPT", _GUIDE_EXEMPT),
        ("_PENDING_GUIDE_AUTHORING", _PENDING_GUIDE_AUTHORING),
    ):
        for app, personas in registry.items():
            if app not in examples:
                problems.append(f"{registry_name}: {app!r} is not an example app")
                continue
            interactive = _interactive_personas(_load(app))
            ghosts = personas - interactive
            if ghosts:
                problems.append(
                    f"{registry_name}[{app!r}]: {sorted(ghosts)} are not interactive "
                    f"personas of {app}"
                )

    for app in examples:
        exempt = _GUIDE_EXEMPT.get(app, set())
        pending = _PENDING_GUIDE_AUTHORING.get(app, set())
        both = exempt & pending
        if both:
            problems.append(f"{app}: {sorted(both)} in BOTH EXEMPT and PENDING")
        covered = _personas_with_guide(_load(app))
        stale = pending & covered
        if stale:
            problems.append(
                f"{app}: {sorted(stale)} are PENDING but already have a guide — "
                f"remove them from _PENDING_GUIDE_AUTHORING (Phase 2 ratchet)"
            )

    assert not problems, "guide registry hygiene:\n  " + "\n  ".join(problems)
