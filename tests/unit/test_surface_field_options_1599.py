"""#1599 — unsupported surface field options (e.g. search_trigger=) must warn.

Parser stores any key=value; form emission only honours a known set. Without a
validate warning, authors claim a UX (Companies House typeahead) that never
renders. Use source=<pack>.<op> for search-select.
"""

from __future__ import annotations

import pytest

from dazzle.core import ir
from dazzle.core.validation.surfaces import validate_surfaces

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


def test_search_trigger_option_warns_with_source_guidance() -> None:
    appspec = _appspec(
        _create_surface({"search_trigger": "companies_house_lookup"}),
    )
    errors, warnings = validate_surfaces(appspec)
    assert errors == []
    hit = [w for w in warnings if "search_trigger" in w]
    assert len(hit) == 1
    assert "source=" in hit[0]
    assert "companies_house_lookup.search_companies" in hit[0]
    assert "not rendered" in hit[0]


def test_unknown_field_option_warns_with_supported_list() -> None:
    appspec = _appspec(_create_surface({"made_up_opt": "x"}))
    errors, warnings = validate_surfaces(appspec)
    assert errors == []
    hit = [w for w in warnings if "made_up_opt" in w]
    assert len(hit) == 1
    assert "unsupported option" in hit[0]
    assert "source" in hit[0]
    assert "widget" in hit[0]


def test_supported_source_option_does_not_warn_as_unsupported() -> None:
    """source= is rendered; pack/op resolution may error separately when api_kb is on."""
    appspec = _appspec(
        _create_surface({"source": "companies_house_lookup.search_companies"}),
    )
    _errors, warnings = validate_surfaces(appspec)
    assert not any("unsupported option" in w for w in warnings)
    assert not any("search_trigger" in w for w in warnings)


def test_supported_widget_option_silent() -> None:
    appspec = _appspec(_create_surface({"widget": "textarea"}))
    errors, warnings = validate_surfaces(appspec)
    assert errors == []
    assert not any("unsupported option" in w for w in warnings)
