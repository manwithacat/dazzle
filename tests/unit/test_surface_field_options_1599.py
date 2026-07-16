"""#1599 — search_trigger aliases to source= search-select; unknown options warn.

Parser stores any key=value. Form emission honours source= and aliases
search_trigger=<pack> → source=<pack>.search_*. Unknown keys still warn.
"""

from __future__ import annotations

import pytest

from dazzle.core import ir
from dazzle.core.validation.surfaces import validate_surfaces
from dazzle.page.converters.template_compiler import _build_form_fields
from dazzle.page.field_source_alias import resolve_search_trigger_to_source

pytestmark = pytest.mark.gate


def _entity() -> ir.EntitySpec:
    return ir.EntitySpec(
        name="Company",
        title="Company",
        fields=[
            ir.FieldSpec(
                name="id",
                type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                modifiers=[ir.FieldModifier.PK],
            ),
            ir.FieldSpec(
                name="company_number",
                type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=32),
            ),
        ],
    )


def _create_surface(options: dict[str, str]) -> ir.SurfaceSpec:
    return ir.SurfaceSpec(
        name="company_create",
        title="Create Company",
        entity_ref="Company",
        mode=ir.SurfaceMode.CREATE,
        sections=[
            ir.SurfaceSection(
                name="main",
                elements=[
                    ir.SurfaceElement(
                        field_name="company_number",
                        label="Company Number",
                        options=options,
                    ),
                ],
            )
        ],
    )


def _appspec(surface: ir.SurfaceSpec) -> ir.AppSpec:
    return ir.AppSpec(
        name="Test",
        domain=ir.DomainSpec(entities=[_entity()]),
        surfaces=[surface],
        experiences=[],
        apis=[],
        foreign_models=[],
        integrations=[],
    )


def test_search_trigger_aliases_to_search_companies() -> None:
    ref = resolve_search_trigger_to_source("companies_house_lookup")
    assert ref == "companies_house_lookup.search_companies"


def test_search_trigger_pack_dot_op_passthrough() -> None:
    ref = resolve_search_trigger_to_source("companies_house_lookup.search_officers")
    assert ref == "companies_house_lookup.search_officers"


def test_search_trigger_no_longer_warns_as_unrendered() -> None:
    """Alias is honoured at render — not an unsupported-option warning."""
    appspec = _appspec(
        _create_surface({"search_trigger": "companies_house_lookup"}),
    )
    errors, warnings = validate_surfaces(appspec)
    assert not any("not rendered" in w for w in warnings)
    assert not any("unsupported option" in w and "search_trigger" in w for w in warnings)
    # May error if pack registry empty in minimal env — when packs present, clean.
    assert not any("could not be resolved" in e for e in errors) or errors == []


def test_unknown_field_option_warns_with_supported_list() -> None:
    appspec = _appspec(_create_surface({"made_up_opt": "x"}))
    errors, warnings = validate_surfaces(appspec)
    assert errors == []
    hit = [w for w in warnings if "made_up_opt" in w]
    assert len(hit) == 1
    assert "unsupported option" in hit[0]
    assert "source" in hit[0]
    assert "search_trigger" in hit[0]


def test_supported_source_option_does_not_warn_as_unsupported() -> None:
    appspec = _appspec(
        _create_surface({"source": "companies_house_lookup.search_companies"}),
    )
    _errors, warnings = validate_surfaces(appspec)
    assert not any("unsupported option" in w for w in warnings)


def test_supported_widget_option_silent() -> None:
    appspec = _appspec(_create_surface({"widget": "textarea"}))
    errors, warnings = validate_surfaces(appspec)
    assert errors == []
    assert not any("unsupported option" in w for w in warnings)


def test_search_trigger_form_field_is_search_select() -> None:
    """Render path: search_trigger alone yields search_select form type."""
    surface = _create_surface({"search_trigger": "companies_house_lookup"})
    entity = _entity()
    fields = _build_form_fields(surface, entity)
    assert fields
    f0 = fields[0]
    assert f0.type == "search_select"
    assert f0.source is not None
