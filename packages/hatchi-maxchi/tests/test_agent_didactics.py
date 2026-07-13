"""Agent didactics — curriculum links resolve (epistemic engineering surface).

AGENTS.md is the always-on entry. Decisions and playbooks it names must exist
on disk so reconstruction cannot dead-end. This is a representation gate, not
a content review.
"""

from __future__ import annotations

import re
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
AGENTS = PKG / "AGENTS.md"

# Paths relative to package root that the curriculum must keep live.
_REQUIRED = (
    "stems/README.md",
    "stems/INDEX.md",
    "stems/hyperpart-not-component.md",
    "stems/three-layers.md",
    "stems/composition-declared.md",
    "stems/host-chrome-symmetry.md",
    "stems/pragmatic-gallery-aesthetics.md",
    "stems/invention-ladder.md",
    "stems/morph-safe-hypermedia.md",
    "docs/decisions/README.md",
    "docs/decisions/0001-hyperpart-not-component.md",
    "docs/decisions/0002-three-layers.md",
    "docs/decisions/0003-composition-declared.md",
    "docs/decisions/0004-invention-ladder.md",
    "docs/decisions/0005-morphing-policy.md",
    "docs/decisions/0006-dom-identity-and-state.md",
    "docs/decisions/0007-no-alpine-in-core.md",
    "docs/decisions/0008-template-lint-posture.md",
    "docs/decisions/0009-carousel-stage-and-motion.md",
    "docs/agent/pick-a-surface.md",
    "docs/agent/compose-or-refuse.md",
    "docs/agent/mutate-a-primitive.md",
    "docs/agent/invent-safely.md",
    "CONSUMER_MAP.md",
    "CONTRACT_SURFACE.md",
    "contracts/AUTHORING.md",
)

_BACKTICK_PATH = re.compile(
    r"`((?:docs|contracts|site)/[a-zA-Z0-9_./-]+\.(?:md|py)|"
    r"CONSUMER_MAP\.md|CONTRACT_SURFACE\.md|DUAL_LOCK_COVERAGE\.md)`"
)


def test_required_didactic_artefacts_exist() -> None:
    missing = [p for p in _REQUIRED if not (PKG / p).is_file()]
    assert not missing, f"missing didactic artefacts: {missing}"


def test_agents_md_curriculum_paths_resolve() -> None:
    """Every package-relative path cited in AGENTS.md backticks must exist."""
    text = AGENTS.read_text(encoding="utf-8")
    assert "How to read this package" in text or "curriculum" in text.lower()
    assert "Invention ladder" in text
    assert "Authority hierarchy" in text or "authority hierarchy" in text.lower()

    missing: list[str] = []
    for m in _BACKTICK_PATH.finditer(text):
        rel = m.group(1)
        # site/agents/<id>.md is a pattern, not a single file
        if "<" in rel or rel.startswith("site/agents/"):
            continue
        if not (PKG / rel).is_file():
            missing.append(rel)
    assert not missing, f"AGENTS.md links to missing paths: {missing}"


def test_llms_txt_points_at_curriculum() -> None:
    llms = (PKG / "site" / "llms.txt").read_text(encoding="utf-8")
    for needle in ("AGENTS.md", "docs/agent", "docs/decisions", "CONSUMER_MAP"):
        assert needle in llms, f"llms.txt should surface {needle}"


def test_playbooks_name_stop_conditions() -> None:
    """Didactic playbooks must teach when to stop (misconception exposure)."""
    for name in (
        "pick-a-surface.md",
        "compose-or-refuse.md",
        "mutate-a-primitive.md",
        "invent-safely.md",
    ):
        body = (PKG / "docs" / "agent" / name).read_text(encoding="utf-8")
        assert "Stop conditions" in body or "stop" in body.lower(), name


def test_agents_md_documents_mock_vs_product_icon_tokens() -> None:
    """Dual icon systems must stay in the always-on curriculum.

    Product partials use build-time {svg:}/{icon:} + sprite; MOCK_HTMX uses
    runtime {i:} + __HM_ICONS__. Agents that only knew the product path shipped
    drawer mock icons that expanded to empty spans.
    """
    text = AGENTS.read_text(encoding="utf-8")
    assert "Gallery icon tokens" in text or "two systems" in text.lower()
    assert "{i:" in text or "{i:name}" in text
    assert "__HM_ICONS__" in text
    assert "{svg:" in text or "{svg:name}" in text


def test_recipe_seeds_are_labelled_and_real_parts() -> None:
    import sys

    sys.path.insert(0, str(PKG / "site"))
    from registry import (  # noqa: E402
        _RECIPE_SEED,
        HYPERPARTS,
        RECIPE_LABELS,
        effective_layer,
    )

    ids = {h.id for h in HYPERPARTS}
    for pid, (recipe, layer) in _RECIPE_SEED.items():
        assert pid in ids, f"_RECIPE_SEED names unknown part {pid}"
        assert recipe in RECIPE_LABELS, f"recipe {recipe!r} missing RECIPE_LABELS"
        if layer is not None:
            assert layer in ("L1", "L2"), layer
    # Matrix criticals must stay seeded
    by_id = {h.id: h for h in HYPERPARTS}
    assert by_id["combobox"].recipe == "single-select-form"
    assert by_id["grid"].recipe == "list-region-host"
    assert effective_layer(by_id["grid"]) == "L2"
    assert effective_layer(by_id["combobox"]) == "L1"
    assert "combobox" in {nc.other for nc in by_id["grid"].does_not_compose}


def test_agent_packs_carry_epistemic_one_liner() -> None:
    """Generated packs must expose layer/recipe so agents reconstruct without AGENTS only."""
    for pid in ("combobox", "grid", "tags", "search-select"):
        md = (PKG / "site" / "agents" / f"{pid}.md").read_text(encoding="utf-8")
        assert "**Layer:**" in md, pid
        assert "**Recipe:**" in md, pid
        assert "CONSUMER_MAP.md" in md, pid


def test_agent_packs_document_morph_swap_for_morphing_hosts() -> None:
    """Grid (and other morph exchangers) must teach morph vs replace (decision 0005)."""
    grid = (PKG / "site" / "agents" / "grid.md").read_text(encoding="utf-8")
    assert "## Morph / swap" in grid, "grid agent pack missing Morph / swap section"
    assert "innerMorph" in grid
    assert "morph-safe-hypermedia" in grid
    assert "stable" in grid.lower()
    # Do/Don't covers morph identity
    assert "morph key" in grid.lower() or "data-dz-grid-row-id" in grid

    pagination = (PKG / "site" / "agents" / "pagination.md").read_text(encoding="utf-8")
    assert "## Morph / swap" in pagination
    assert "innerMorph" in pagination

    # L2 host without exchanges still gets identity rules
    shell = (PKG / "site" / "agents" / "app-shell.md").read_text(encoding="utf-8")
    assert "## Morph / swap" in shell
