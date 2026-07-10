"""#1566 hard gate: the HM design-context must claim every rubric dimension
exactly once, and every concept must measure something real."""

import pytest

from dazzle.core.design_context import (
    CONCEPT_MAP,
    DESIGN_CONCEPTS,
    RUBRICS,
    all_dimension_ids,
    concepts,
    dimensions_for,
    matrix,
    method_of,
    surface_of,
)

pytestmark = pytest.mark.gate

EXPECTED_CONCEPT_KEYS = {
    "type",
    "rhythm",
    "hierarchy",
    "colour",
    "motion",
    "structure",
    "finish",
    "cta",
    "family_fidelity",
}


def test_concept_vocabulary_is_the_agreed_set() -> None:
    assert {c.key for c in DESIGN_CONCEPTS} == EXPECTED_CONCEPT_KEYS


def test_every_concept_maps_to_at_least_one_real_dimension() -> None:
    real = all_dimension_ids()
    for c in DESIGN_CONCEPTS:
        assert c.dimensions, f"concept {c.key} claims no dimensions"
        for d in c.dimensions:
            assert d in real, f"concept {c.key} claims non-existent dimension {d}"


def test_every_rubric_dimension_is_claimed_by_exactly_one_concept() -> None:
    claimed: list[str] = [d for c in DESIGN_CONCEPTS for d in c.dimensions]
    # no dimension claimed twice
    assert len(claimed) == len(set(claimed)), "a dimension is claimed by >1 concept"
    # every real dimension is claimed (no orphans)
    assert set(claimed) == set(all_dimension_ids())


def test_concept_map_matches_design_concepts() -> None:
    assert CONCEPT_MAP == {c.key: c.dimensions for c in DESIGN_CONCEPTS}
    for key in EXPECTED_CONCEPT_KEYS:
        assert dimensions_for(key) == CONCEPT_MAP[key]


def test_matrix_is_well_formed() -> None:
    m = matrix()
    assert set(m.keys()) == {
        ("marketing", "deterministic"),
        ("marketing", "judged"),
        ("app_internals", "deterministic"),
        ("app_internals", "judged"),
    }
    assert m[("marketing", "deterministic")].name == "hygiene"
    assert m[("marketing", "judged")].name == "vision"
    assert m[("app_internals", "judged")].name == "taste"
    # the app-internals deterministic cell is filled by the component rubric (#1567)
    assert m[("app_internals", "deterministic")].name == "component"


def test_method_and_surface_lookups() -> None:
    assert method_of("hygiene.type_system") == "deterministic"
    assert method_of("vision.hero_impact") == "judged"
    assert surface_of("taste.perceived_craft") == "app_internals"
    assert surface_of("vision.cta_prominence") == "marketing"


def test_accessor_shapes() -> None:
    assert concepts() == DESIGN_CONCEPTS
    assert len(RUBRICS) == 4
    # 24 dimensions total across the four rubrics (20 + 4 component)
    assert len(all_dimension_ids()) == 24


def test_component_rubric_fills_the_deterministic_app_cell() -> None:
    from dazzle.core.design_context import dimensions_for, method_of, surface_of

    for key in ("colour_tokens", "namespace", "motion_tokens", "sizing_tokens"):
        qid = f"component.{key}"
        assert method_of(qid) == "deterministic"
        assert surface_of(qid) == "app_internals"
    assert "component.colour_tokens" in dimensions_for("colour")
    assert "component.namespace" in dimensions_for("structure")
    assert "component.motion_tokens" in dimensions_for("motion")
    assert "component.sizing_tokens" in dimensions_for("rhythm")


def test_generated_doc_is_current() -> None:
    from dazzle.core.design_context import DOC_PATH, render_markdown

    assert DOC_PATH.exists(), "docs/reference/hm-design-context.md must be generated"
    committed = DOC_PATH.read_text(encoding="utf-8")
    assert committed == render_markdown().rstrip("\n") + "\n", (
        "hm-design-context.md is stale — run: python scripts/gen_design_context.py"
    )
