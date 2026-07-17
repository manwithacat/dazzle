"""#1617 representation substrate — decide / classify / prove."""

from __future__ import annotations

from pathlib import Path

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
    assert any("gin-sql" in s for s in d.get("next_steps") or [])


def test_format_cell_json_summary() -> None:
    from dazzle.render.fragment.format_cell import format_cell

    out = format_cell({"theme": "dark", "locale": "en-GB"}, "json")
    assert "theme" in out and "dark" in out
    assert "{" not in out  # not raw dump


def test_json_identity_smell() -> None:
    ent = ir.EntitySpec(
        name="Blob",
        title="Blob",
        fields=[
            ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
            ir.FieldSpec(name="payload", type=ir.FieldType(kind=ir.FieldTypeKind.JSON)),
        ],
    )
    appspec = ir.AppSpec(name="t", domain=ir.DomainSpec(entities=[ent]), surfaces=[])
    findings = classify_appspec(appspec)["findings"]
    assert any(f["kind"] == "json_identity_smell" for f in findings)


def test_gin_index_sql() -> None:
    from dazzle.representation import gin_index_sql

    sql = gin_index_sql("Client", "extensions")
    assert "USING gin" in sql
    assert "jsonb_path_ops" in sql


def test_scalar_at_least_one_is_not_exclusive_fk() -> None:
    """email|phone contact invariant must not be rel.exclusive_fks / CHECK."""
    # Build via parse so invariant_expr is real
    import tempfile

    from dazzle.core.parser import parse_modules
    from dazzle.db.exclusive_checks import exclusive_anchor_field_sets

    body = """
entity Contact "Contact":
  id: uuid pk
  email: email
  phone: str(20)
  invariant: email != null or phone != null
"""
    d = Path(tempfile.mkdtemp())
    f = d / "app.dsl"
    f.write_text(f'module t\n\napp t "T"\n\n{body}', encoding="utf-8")
    (module,) = parse_modules([f])
    contact = module.fragment.entities[0]
    assert exclusive_anchor_field_sets(contact) == []
    appspec = ir.AppSpec(
        name="t",
        domain=ir.DomainSpec(entities=list(module.fragment.entities)),
        surfaces=[],
    )
    kinds = {f["kind"] for f in classify_appspec(appspec)["findings"]}
    assert "exclusive_fk_set" not in kinds
    assert "exclusive_fk_missing_open" not in kinds


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


def test_playbook_domain_data_shape() -> None:
    from dazzle.agent_loop import build_playbook

    pb = build_playbook("domain_data_shape")
    assert pb["ok"]
    assert "rel.exclusive_fks" in pb["body"]
    assert "representation decide" in pb["body"]


def test_wall_attach_includes_representation() -> None:
    from dazzle.representation import attach_representation_to_wall

    appspec = ir.AppSpec(
        name="t",
        domain=ir.DomainSpec(
            entities=[
                ir.EntitySpec(
                    name="Task",
                    title="Task",
                    fields=[
                        ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                    ],
                )
            ]
        ),
        surfaces=[],
    )
    wall = attach_representation_to_wall(
        {"markdown": "Story wall", "note": "binding", "counts": {}},
        appspec,
    )
    assert wall["representation"] is not None
    assert wall["representation"]["ok"] is True
    assert "Representation:" in wall["markdown"]


def test_bootstrap_decision_helper_exclusive() -> None:
    from dazzle.mcp.server.handlers.bootstrap import _representation_decision_for_spec

    d = _representation_decision_for_spec(
        "Build an app for company or sole trader clients with journey deep dive"
    )
    assert d.get("ok")
    assert d.get("pattern_id") == PatternId.EXCLUSIVE_FKS


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
