"""Drift gate: every example app's onboarding guide stays concordant.

Each example app under ``examples/`` that ships an ``onboarding.dsl``
must link clean against its own DSL — i.e. every step's target,
``complete_on`` event, ``cta_target``, and audience persona resolves.

This catches the failure mode where a refactor renames a surface
without updating the guide. The simple_task-specific gate
(``test_simple_task_guide_concordance.py``) covers intentional-drift
scenarios in detail; this one is the breadth gate across all
example apps.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.core.guide_concordance import check_guide_concordance

EXAMPLES_ROOT = Path(__file__).resolve().parents[2] / "examples"

# Every example app ships guides as of the 2026-06-13 example-guides Phase 2
# authoring pass (all 11 examples covered, one guide per interactive persona).
# Keep the canonical one first so a per-app failure header reads cleanly.
_APPS_WITH_GUIDES = [
    "simple_task",
    "contact_manager",
    "support_tickets",
    "ops_dashboard",
    "fieldtest_hub",
    "project_tracker",
    "design_studio",
    "llm_ticket_classifier",
    "acme_billing",
    "hr_records",
    "invoice_ops",
]


@pytest.mark.parametrize("app", _APPS_WITH_GUIDES)
def test_example_has_at_least_one_guide(app: str) -> None:
    """Each listed example actually declares the guide(s) this test
    expects — a missing onboarding.dsl is a regression, not a silent
    skip."""
    appspec = load_project_appspec(EXAMPLES_ROOT / app)
    guides = list(getattr(appspec, "guides", None) or [])
    assert guides, f"{app}: expected at least one declared guide"


@pytest.mark.parametrize("app", _APPS_WITH_GUIDES)
def test_example_guides_pass_concordance(app: str) -> None:
    """Every guide step's target / completion / cta / audience resolves
    against the project's DSL. Drift fails fast at validate time."""
    appspec = load_project_appspec(EXAMPLES_ROOT / app)
    guides = list(getattr(appspec, "guides", None) or [])
    errors, _warnings = check_guide_concordance(
        guides,
        surfaces=appspec.surfaces,
        entities=appspec.domain.entities,
        personas=appspec.personas,
        streams=appspec.streams,
    )
    assert errors == [], (
        f"{app}: guide concordance failed — guide and DSL have drifted. "
        f"Errors:\n  " + "\n  ".join(errors)
    )


def test_documented_examples_match_filesystem_truth() -> None:
    """The parametrise list above must match what's actually committed.

    If a new example app ships an ``onboarding.dsl``, it should be
    added to ``_APPS_WITH_GUIDES`` so the concordance gate covers
    it. Likewise, removing a guide from an example requires updating
    this list.
    """
    on_disk = sorted(p.parent.parent.name for p in EXAMPLES_ROOT.glob("*/dsl/onboarding.dsl"))
    documented = sorted(_APPS_WITH_GUIDES)
    assert on_disk == documented, (
        f"Example-guide inventory drifted from filesystem. "
        f"On disk: {on_disk}; in test list: {documented}. "
        f"Update _APPS_WITH_GUIDES if you added or removed an example guide."
    )
