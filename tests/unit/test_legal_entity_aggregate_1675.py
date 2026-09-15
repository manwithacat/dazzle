"""#1675: legal_entity grain — unpinned money sum/avg must not span Sites."""

from __future__ import annotations

from pathlib import Path

from dazzle.core import ir
from dazzle.core.ir.aggregates import AggregateRef
from dazzle.core.ir.conditions import Comparison, ComparisonOperator, ConditionExpr, ConditionValue
from dazzle.core.ir.fields import FieldModifier, FieldType, FieldTypeKind
from dazzle.core.ir.workspaces import ContextSelectorSpec, WorkspaceRegion, WorkspaceSpec
from dazzle.core.parser import parse_modules
from dazzle.core.validation.financial import validate_legal_entity_money_span


def _id() -> ir.FieldSpec:
    return ir.FieldSpec(
        name="id",
        type=FieldType(kind=FieldTypeKind.UUID),
        modifiers=[FieldModifier.PK],
    )


def _site(*, legal: bool) -> ir.EntitySpec:
    return ir.EntitySpec(
        name="Site",
        title="Site",
        legal_entity=legal,
        fields=[_id(), ir.FieldSpec(name="name", type=FieldType(kind=FieldTypeKind.TEXT))],
    )


def _invoice() -> ir.EntitySpec:
    return ir.EntitySpec(
        name="Invoice",
        title="Invoice",
        fields=[
            _id(),
            ir.FieldSpec(
                name="site",
                type=FieldType(kind=FieldTypeKind.REF, ref_entity="Site"),
            ),
            ir.FieldSpec(name="amount", type=FieldType(kind=FieldTypeKind.MONEY)),
        ],
    )


def _reading() -> ir.EntitySpec:
    return ir.EntitySpec(
        name="Reading",
        title="Reading",
        fields=[
            _id(),
            ir.FieldSpec(
                name="site",
                type=FieldType(kind=FieldTypeKind.REF, ref_entity="Site"),
            ),
            ir.FieldSpec(name="value_delta", type=FieldType(kind=FieldTypeKind.DECIMAL)),
        ],
    )


def _appspec(
    *,
    legal: bool,
    aggregates: dict[str, AggregateRef],
    group_by: str | None = None,
    context_selector: ContextSelectorSpec | None = None,
    source: str = "Invoice",
) -> ir.AppSpec:
    region = WorkspaceRegion(
        name="board",
        source=source,
        aggregates=aggregates,
        group_by=group_by,
    )
    return ir.AppSpec(
        name="t",
        domain=ir.DomainSpec(entities=[_site(legal=legal), _invoice(), _reading()]),
        surfaces=[],
        workspaces=[
            WorkspaceSpec(
                name="dash",
                purpose="x",
                stage="command_center",
                regions=[region],
                context_selector=context_selector,
            )
        ],
    )


def test_unpinned_money_sum_errors() -> None:
    appspec = _appspec(
        legal=True,
        aggregates={"total": AggregateRef(func="sum", entity="Invoice", column="amount")},
    )
    errors, warnings = validate_legal_entity_money_span(appspec)
    assert warnings == []
    assert len(errors) == 1
    assert "legal-entity grain Site" in errors[0]
    assert "group_by: site" in errors[0]


def test_plant_total_numeric_sum_allowed() -> None:
    appspec = _appspec(
        legal=True,
        source="Reading",
        aggregates={
            "kwh": AggregateRef(func="sum", entity="Reading", column="value_delta"),
        },
    )
    errors, _ = validate_legal_entity_money_span(appspec)
    assert errors == []


def test_group_by_site_pins_money() -> None:
    appspec = _appspec(
        legal=True,
        aggregates={"total": AggregateRef(func="sum", entity="Invoice", column="amount")},
        group_by="site",
    )
    errors, _ = validate_legal_entity_money_span(appspec)
    assert errors == []


def test_where_equality_pins_money() -> None:
    where = ConditionExpr(
        comparison=Comparison(
            field="site",
            operator=ComparisonOperator.EQUALS,
            value=ConditionValue(literal="current_context"),
        )
    )
    appspec = _appspec(
        legal=True,
        aggregates={
            "total": AggregateRef(func="sum", entity="Invoice", column="amount", where=where),
        },
    )
    errors, _ = validate_legal_entity_money_span(appspec)
    assert errors == []


def test_context_selector_pins_money() -> None:
    appspec = _appspec(
        legal=True,
        aggregates={"total": AggregateRef(func="sum", entity="Invoice", column="amount")},
        context_selector=ContextSelectorSpec(entity="Site"),
    )
    errors, _ = validate_legal_entity_money_span(appspec)
    assert errors == []


def test_no_legal_entity_tag_is_fail_open() -> None:
    appspec = _appspec(
        legal=False,
        aggregates={"total": AggregateRef(func="sum", entity="Invoice", column="amount")},
    )
    errors, _ = validate_legal_entity_money_span(appspec)
    assert errors == []


def test_wired_into_lint_appspec() -> None:
    from dazzle.core.lint import lint_appspec

    appspec = _appspec(
        legal=True,
        aggregates={"total": AggregateRef(func="sum", entity="Invoice", column="amount")},
    )
    errors, _warnings, _rel = lint_appspec(appspec, suggest=False)
    assert any("legal-entity grain Site" in e for e in errors)


def test_legal_entity_keyword_parses(tmp_path: Path) -> None:
    f = tmp_path / "app.dsl"
    f.write_text(
        """module t
app t "T"
entity Site "Site":
  legal_entity
  id: uuid pk
  name: text
""",
        encoding="utf-8",
    )
    (module,) = parse_modules([f])
    site = module.fragment.entities[0]
    assert site.legal_entity is True
