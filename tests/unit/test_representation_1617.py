"""#1617 representation substrate — decide / classify / prove."""

from __future__ import annotations

from dazzle.core import ir
from dazzle.representation import (
    PatternId,
    classify_appspec,
    decide_representation,
    list_patterns,
    prove_representation,
)
from dazzle.representation.patterns import PATTERN_CATALOGUE

pytestmark = __import__("pytest").mark.gate


def test_catalogue_has_all_pattern_ids() -> None:
    ids = {p["id"] for p in list_patterns()}
    for pid in PatternId:
        assert pid in ids
        assert pid in PATTERN_CATALOGUE


def test_decide_exclusive_fks_from_text() -> None:
    d = decide_representation(text="company or sole trader client overview journey")
    assert d["pattern_id"] == PatternId.EXCLUSIVE_FKS
    assert "first_non_null" in d["dsl_sketch"]
    assert any(PatternId.POLY_REF in r for r in d["reject"])


def test_decide_poly_ref_from_attachable() -> None:
    d = decide_representation(text="commentable attachable polymorphic association")
    assert d["pattern_id"] == PatternId.POLY_REF
    assert "poly_ref" in d["dsl_sketch"]


def test_decide_json_extension_signal() -> None:
    d = decide_representation(signals={"tenant_variable_fields": True})
    assert d["pattern_id"] == PatternId.JSON_EXTENSION


def test_decide_default_explicit_ref() -> None:
    d = decide_representation(text="simple task list for one team")
    assert d["pattern_id"] == PatternId.EXPLICIT_REF


def _exclusive_entities() -> tuple[ir.EntitySpec, ir.EntitySpec, ir.EntitySpec]:
    case = ir.EntitySpec(
        name="Case",
        title="Case",
        fields=[ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID))],
    )
    matter = ir.EntitySpec(
        name="Matter",
        title="Matter",
        fields=[ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID))],
    )
    # Build Doc with optional refs + invariant via parse is easier for invariant expr;
    # use IR without invariant first and inject via SimpleNamespace for exclusive_set.
    return case, matter, case  # placeholder — see builders below


def _doc_entity_with_invariant():
    """Parse a tiny module so invariant_expr is real BinaryExpr tree."""
    import tempfile
    from pathlib import Path

    from dazzle.core.parser import parse_modules

    body = """
entity Case "Case":
  id: uuid pk

entity Matter "Matter":
  id: uuid pk

entity Doc "Doc":
  id: uuid pk
  case_ref: ref Case
  matter_ref: ref Matter
  invariant: case_ref != null or matter_ref != null
"""
    d = Path(tempfile.mkdtemp())
    f = d / "app.dsl"
    f.write_text(f'module t\n\napp t "T"\n\n{body}', encoding="utf-8")
    (module,) = parse_modules([f])
    entities = list(module.fragment.entities)
    return entities


def test_classify_and_prove_exclusive_happy_path() -> None:
    entities = _doc_entity_with_invariant()
    doc = next(e for e in entities if e.name == "Doc")
    case = next(e for e in entities if e.name == "Case")
    matter = next(e for e in entities if e.name == "Matter")
    doc_list = ir.SurfaceSpec(
        name="doc_list",
        title="Docs",
        entity_ref="Doc",
        mode=ir.SurfaceMode.LIST,
        open_via_targets=[
            ir.OpenViaTarget(via="case_ref", entity="Case"),
            ir.OpenViaTarget(via="matter_ref", entity="Matter"),
        ],
    )
    appspec = ir.AppSpec(
        name="t",
        domain=ir.DomainSpec(entities=[case, matter, doc]),
        surfaces=[doc_list],
    )
    classified = classify_appspec(appspec)
    assert classified["ok"]
    kinds = {f["kind"] for f in classified["findings"]}
    assert "exclusive_fk_set" in kinds
    assert classified["error_count"] == 0

    proved = prove_representation(appspec)
    assert proved["ok"]
    assert proved["result"] == "pass_representation"


def test_prove_fails_hand_rolled_poly() -> None:
    comment = ir.EntitySpec(
        name="Comment",
        title="Comment",
        fields=[
            ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
            ir.FieldSpec(
                name="subject_type",
                type=ir.FieldType(
                    kind=ir.FieldTypeKind.ENUM,
                    enum_values=["case", "matter"],
                ),
            ),
            ir.FieldSpec(name="subject_id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
            ir.FieldSpec(name="body", type=ir.FieldType(kind=ir.FieldTypeKind.TEXT)),
        ],
    )
    appspec = ir.AppSpec(
        name="t",
        domain=ir.DomainSpec(entities=[comment]),
        surfaces=[],
    )
    classified = classify_appspec(appspec)
    assert any(f["kind"] == "hand_rolled_poly" for f in classified["findings"])
    proved = prove_representation(appspec)
    assert not proved["ok"]
    assert proved["result"] == "fail_representation"


def test_prove_fails_exclusive_without_open() -> None:
    entities = _doc_entity_with_invariant()
    doc = next(e for e in entities if e.name == "Doc")
    case = next(e for e in entities if e.name == "Case")
    matter = next(e for e in entities if e.name == "Matter")
    doc_list = ir.SurfaceSpec(
        name="doc_list",
        title="Docs",
        entity_ref="Doc",
        mode=ir.SurfaceMode.LIST,
    )
    appspec = ir.AppSpec(
        name="t",
        domain=ir.DomainSpec(entities=[case, matter, doc]),
        surfaces=[doc_list],
    )
    proved = prove_representation(appspec)
    assert not proved["ok"]
    assert any("exclusive_fk_missing_open" in r for r in proved["reasons"])
