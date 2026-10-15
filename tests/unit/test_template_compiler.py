"""Template compiler contract: Surface IR → PageContext.

Everything goes through the public entry points ``compile_surface_to_context``
and ``compile_appspec_to_templates``: form fields are read from
``ctx.form.fields``, list columns from ``ctx.table.columns``, entity columns
from the related-tab columns a detail page builds for a spoke entity.
"""

from typing import Any

import pytest

from dazzle.core import ir
from dazzle.core.ir import FieldTypeKind as K
from dazzle.core.ir import SurfaceMode
from dazzle.core.ir.fields import FieldModifier
from dazzle.core.ir.triples import derive_triples
from dazzle.core.linker_impl import SymbolTable, validate_references
from dazzle.page.converters.template_compiler import (
    compile_appspec_to_templates,
    compile_surface_to_context,
)

# =============================================================================
# Builders
# =============================================================================


def _f(name: str, kind: K, **type_kw: Any) -> ir.FieldSpec:
    return ir.FieldSpec(name=name, type=ir.FieldType(kind=kind, **type_kw))


def _str(name: str, n: int = 200) -> ir.FieldSpec:
    return _f(name, K.STR, max_length=n)


def _ref(name: str, entity: str, kind: K = K.REF) -> ir.FieldSpec:
    return _f(name, kind, ref_entity=entity)


def _entity(name: str, *fields: ir.FieldSpec) -> ir.EntitySpec:
    pk = ir.FieldSpec(name="id", type=ir.FieldType(kind=K.UUID), modifiers=[FieldModifier.PK])
    return ir.EntitySpec(name=name, title=name, fields=[pk, *fields])


def _sole_trader() -> ir.EntitySpec:
    return _entity(
        "SoleTrader",
        _str("trading_name"),
        _str("nino", 9),
        _str("utr", 10),
        _f("is_vat_registered", K.BOOL),
        _str("vat_number", 12),
    )


def _company() -> ir.EntitySpec:
    return _entity(
        "Company", _str("name"), _f("status", K.ENUM, enum_values=["active", "inactive"])
    )


def _contact(*extra: ir.FieldSpec) -> ir.EntitySpec:
    return _entity(
        "Contact", _str("full_name"), _f("email", K.EMAIL), _ref("company", "Company"), *extra
    )


def _task() -> ir.EntitySpec:
    return _entity("Task", _str("title"), _f("completed", K.BOOL), _ref("company", "Company"))


def _audit_log(type_kind: K = K.ENUM) -> ir.EntitySpec:
    type_kw = (
        {"enum_values": ["company", "sole_trader"]} if type_kind is K.ENUM else {"max_length": 100}
    )
    return _entity(
        "AuditLog",
        _f("entity_type", type_kind, **type_kw),
        _f("entity_id", K.UUID),
        _str("action", 100),
    )


def _el(name: str, label: str | None = None, **kw: Any) -> ir.SurfaceElement:
    return ir.SurfaceElement(field_name=name, label=label or name.replace("_", " ").title(), **kw)


def _surface(
    name: str, entity: str, mode: SurfaceMode, *elements: ir.SurfaceElement, **kw: Any
) -> ir.SurfaceSpec:
    sections = (
        [ir.SurfaceSection(name="main", title="Main", elements=list(elements))] if elements else []
    )
    return ir.SurfaceSpec(
        name=name, title=name, entity_ref=entity, mode=mode, sections=sections, **kw
    )


def _compile_app(entities: list[ir.EntitySpec], surfaces: list[ir.SurfaceSpec]) -> dict[str, Any]:
    return compile_appspec_to_templates(
        ir.AppSpec(name="test_app", title="Test App", version="0.1.0",
                   domain=ir.DomainSpec(entities=entities), surfaces=surfaces)
    )  # fmt: skip


def _attrs(obj: Any, names: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for path in names:
        value = obj
        for part in path.split("."):
            value = getattr(value, part)
        out[path] = value
    return out


# =============================================================================
# Form fields
# =============================================================================

_CLIENT = _entity("Client", _str("company_name"), _ref("assigned_to", "User"))
_SOURCE = {"source": "companies_house_lookup.search_companies"}

FORM_FIELD_CASES = [
    pytest.param(
        _el("company_name", options=_SOURCE),
        {
            "type": "search_select",
            # #1599: the endpoint names the pack so HTMX search routes to it
            "source.endpoint": "/_dazzle/fragments/search?source=companies_house_lookup",
            "source.display_key": "company_name",
            "source.value_key": "company_number",
        },
        id="source-option-becomes-search-select-#1599",
    ),
    pytest.param(
        _el("company_name"),
        {"type": "text", "source": None, "ref_entity": "", "ref_api": ""},
        id="plain-str-no-source-no-ref",
    ),
    pytest.param(
        _el("assigned_to"),
        {"type": "ref", "ref_entity": "User", "ref_api": "/users"},
        id="ref-field-auto-wires-entity-select-EX-044",
    ),
    pytest.param(
        _el("assigned_to", options=_SOURCE),
        {"type": "search_select", "ref_entity": "", "ref_api": ""},
        # The source-based search-select takes precedence over ref auto-wiring.
        id="explicit-source-suppresses-ref-auto-wiring",
    ),
]


@pytest.mark.parametrize(("element", "expected"), FORM_FIELD_CASES)
def test_form_field(element: ir.SurfaceElement, expected: dict[str, Any]) -> None:
    ctx = compile_surface_to_context(
        _surface("client_create", "Client", SurfaceMode.CREATE, element), _CLIENT
    )
    [field] = ctx.form.fields
    assert field.name == element.field_name
    assert _attrs(field, expected) == expected


@pytest.mark.parametrize(
    ("elements", "expected"),
    [
        pytest.param(
            [_el("owner"), _el("trading_name"), _el("utr", "UTR")],
            [("owner", "Owner"), ("trading_name", "Trading Name"), ("utr", "UTR")],
            # `owner` is not an entity field; sections are authoritative.
            id="sections-define-the-fields",
        ),
        pytest.param(
            [],
            [
                ("trading_name", "Trading Name"),
                ("nino", "Nino"),
                ("utr", "Utr"),
                ("is_vat_registered", "Is Vat Registered"),
                ("vat_number", "Vat Number"),
            ],
            id="no-sections-falls-back-to-non-pk-entity-fields",
        ),
    ],
)
def test_form_fields_sections_over_entity_fallback(
    elements: list[ir.SurfaceElement], expected: list[tuple[str, str]]
) -> None:
    ctx = compile_surface_to_context(
        _surface("st_create", "SoleTrader", SurfaceMode.CREATE, *elements), _sole_trader()
    )
    assert [(f.name, f.label) for f in ctx.form.fields] == expected


def test_explicit_field_format_reaches_detail_context() -> None:
    surface = _surface(
        "invoice_detail",
        "Invoice",
        SurfaceMode.VIEW,
        _el("amount", format=ir.FieldFormatSpec(kind="currency")),
    )
    ctx = compile_surface_to_context(surface, _entity("Invoice", _f("amount", K.DECIMAL)))
    assert [(f.name, f.extra) for f in ctx.detail.fields] == [
        ("amount", {"format_kind": "currency", "format_arg": None})
    ]


# =============================================================================
# Route collisions: two surfaces for one (entity, mode)
# =============================================================================

_SECTIONED = _surface(
    "sole_trader_create", "SoleTrader", SurfaceMode.CREATE, _el("trading_name"), _el("utr")
)
_SECTIONLESS = _surface("add_sole_trader", "SoleTrader", SurfaceMode.CREATE)


def _view(name: str, render: str | None) -> ir.SurfaceSpec:
    return _surface(name, "SoleTrader", SurfaceMode.VIEW, _el("trading_name"), render=render)


@pytest.mark.parametrize(
    ("surfaces", "route", "winner"),
    [
        pytest.param([_SECTIONED], "/soletrader/create", "sole_trader_create", id="single-surface"),
        pytest.param(
            [_SECTIONLESS, _SECTIONED],
            "/soletrader/create",
            "sole_trader_create",
            id="sectioned-wins-declared-second",
        ),
        pytest.param(
            [_SECTIONED, _SECTIONLESS],
            "/soletrader/create",
            "sole_trader_create",
            id="sectioned-wins-declared-first",
        ),
        pytest.param(
            [_view("plain_detail", None), _view("custom_detail", "class_summary_viewer")],
            "/soletrader/{id}",
            "custom_detail",
            # The pre-#1301 bug: the earlier plain surface won and the custom
            # renderer never dispatched.
            id="render-surface-wins-declared-second-#1301",
        ),
        pytest.param(
            [_view("custom_detail", "class_summary_viewer"), _view("plain_detail", None)],
            "/soletrader/{id}",
            "custom_detail",
            id="render-surface-wins-declared-first-#1301",
        ),
        pytest.param(
            [_view("first_detail", None), _view("second_detail", None)],
            "/soletrader/{id}",
            "first_detail",
            id="no-render-first-sectioned-wins",
        ),
    ],
)
def test_route_collision_winner(surfaces: list[ir.SurfaceSpec], route: str, winner: str) -> None:
    ctx = _compile_app([_sole_trader()], surfaces)[route]
    assert ctx.view_name == winner
    if ctx.form is not None:
        # The sectioned surface's fields, not the 5-field entity fallback.
        assert [f.name for f in ctx.form.fields] == ["trading_name", "utr"]


# =============================================================================
# Related tabs on detail pages (hub-and-spoke #301, polymorphic FK #321)
# =============================================================================


def _hub_surfaces(**detail_kw: Any) -> list[ir.SurfaceSpec]:
    return [
        _surface("company_list", "Company", SurfaceMode.LIST),
        _surface("company_detail", "Company", SurfaceMode.VIEW, **detail_kw),
        _surface("contact_list", "Contact", SurfaceMode.LIST),
        _surface("task_list", "Task", SurfaceMode.LIST),
    ]


def test_hub_detail_page_auto_tabs() -> None:
    contexts = _compile_app([_company(), _contact(), _task()], _hub_surfaces())
    assert contexts["/company"].detail is None  # list pages carry no tabs
    [group] = contexts["/company/{id}"].detail.related_groups
    assert (group.group_id, group.display, group.is_auto) == ("group-auto", "table", True)
    tabs = [
        (t.tab_id, t.label, t.filter_field, t.api_endpoint, t.create_url, t.detail_url_template,
         [c.key for c in t.columns])
        for t in group.tabs
    ]  # fmt: skip
    assert tabs == [
        # FK and PK columns are dropped from the spoke's tab
        ("tab-contact", "Contact", "company", "/contacts", "/contact/create", "/contact/{id}",
         ["full_name", "email"]),
        ("tab-task", "Task", "company", "/tasks", "/task/create", "/task/{id}",
         ["title", "completed"]),
    ]  # fmt: skip


def test_multiple_fk_paths_from_one_entity_get_distinct_tabs() -> None:
    """#1523: duplicate tab_ids break the HM tab strip's panel targeting and
    identical labels make tabs indistinguishable; both vary by FK field."""
    contexts = _compile_app(
        [_company(), _contact(_ref("billing_company", "Company"))],
        [_surface("company_detail", "Company", SurfaceMode.VIEW)],
    )
    tabs = contexts["/company/{id}"].detail.related_groups[0].tabs
    assert sorted((t.tab_id, t.label, t.filter_field) for t in tabs) == [
        ("tab-contact-billing-company", "Contact · Billing Company", "billing_company"),
        ("tab-contact-company", "Contact · Company", "company"),
    ]


@pytest.mark.parametrize(
    ("related_groups", "expected"),
    [
        pytest.param(
            [ir.RelatedGroup(name="people", title="People",
                             display=ir.RelatedDisplayMode.STATUS_CARDS, show=["Contact"])],
            [("People", "status_cards", False, [("Contact", ["full_name", "email"])]),
             ("Other", "table", True, [("Task", ["title", "completed"])])],
            id="declared-group-then-auto-group-for-the-rest",
        ),
        pytest.param(
            [ir.RelatedGroup(name="work", title="Work", display=ir.RelatedDisplayMode.TABLE,
                             show=["Task"], columns=["title"])],
            [("Work", "table", False, [("Task", ["title"])]),
             ("Other", "table", True, [("Contact", ["full_name", "email"])])],
            id="declared-columns-project-the-tab-#1600",
        ),
    ],
)  # fmt: skip
def test_declared_related_groups(
    related_groups: list[ir.RelatedGroup], expected: list[tuple[Any, ...]]
) -> None:
    contexts = _compile_app(
        [_company(), _contact(), _task()],
        [_surface("company_detail", "Company", SurfaceMode.VIEW, related_groups=related_groups)],
    )
    groups = contexts["/company/{id}"].detail.related_groups
    got = [
        (
            g.label,
            g.display,
            g.is_auto,
            [(t.entity_name, [c.key for c in t.columns]) for t in g.tabs],
        )
        for g in groups
    ]
    assert got == expected


@pytest.mark.parametrize(
    ("route", "type_value"),
    [
        pytest.param("/company/{id}", "company", id="company"),
        pytest.param("/soletrader/{id}", "sole_trader", id="sole-trader"),
    ],
)
def test_polymorphic_fk_tab(route: str, type_value: str) -> None:
    contexts = _compile_app(
        [_company(), _sole_trader(), _audit_log()],
        [
            _surface("company_detail", "Company", SurfaceMode.VIEW),
            _surface("sole_trader_detail", "SoleTrader", SurfaceMode.VIEW),
            _surface("audit_list", "AuditLog", SurfaceMode.LIST),
        ],
    )
    [tab] = [
        t for t in contexts[route].detail.related_groups[0].tabs if t.entity_name == "AuditLog"
    ]
    assert (tab.filter_type_field, tab.filter_type_value, tab.filter_field) == (
        "entity_type",
        type_value,
        "entity_id",
    )
    assert tab.api_endpoint == "/auditlogs"
    assert [c.key for c in tab.columns] == ["action"]  # discriminator + id hidden


@pytest.mark.parametrize(
    "entities",
    [
        pytest.param([_contact()], id="entity-without-reverse-refs"),
        # entity_type as str (not enum) is not a polymorphic discriminator (#321)
        pytest.param([_company(), _audit_log(K.STR)], id="str-type-field-is-not-polymorphic"),
    ],
)
def test_detail_page_without_related_tabs(entities: list[ir.EntitySpec]) -> None:
    hub = entities[0]
    route = f"/{hub.name.lower()}/{{id}}"
    contexts = _compile_app(entities, [_surface("detail", hub.name, SurfaceMode.VIEW)])
    assert contexts[route].detail.related_groups == []


# =============================================================================
# Column types: entity columns (via a spoke's related tab) and list filters
# =============================================================================


def _spoke_columns(*fields: ir.FieldSpec) -> dict[str, tuple[str, str]]:
    hub = _entity("Hub")
    spoke = _entity("Spoke", _ref("hub", "Hub"), *fields)
    ctx = compile_surface_to_context(
        _surface("hub_detail", "Hub", SurfaceMode.VIEW), hub, reverse_refs=[("Spoke", "hub", spoke)]
    )
    return {c.key: (c.type, c.label) for c in ctx.detail.related_groups[0].tabs[0].columns}


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        pytest.param(_str("name"), {"name": ("text", "Name")}, id="str-text"),
        pytest.param(
            _f("status", K.ENUM, enum_values=["a", "b"]),
            {"status": ("badge", "Status")},
            id="enum-badge",
        ),
        pytest.param(_f("completed", K.BOOL), {"completed": ("bool", "Completed")}, id="bool"),
        pytest.param(
            _ref("company", "Company"),
            {"company": ("ref", "Company")},
            id="ref-is-ref-not-text-#308",
        ),
        pytest.param(
            _ref("assigned_to_id", "User"),
            {"assigned_to": ("ref", "Assigned To")},
            id="ref-id-suffix-stripped-for-key-#553",
        ),
        pytest.param(
            _ref("order_id", "Order", K.BELONGS_TO),
            {"order": ("ref", "Order")},
            id="belongs-to-is-ref-id-suffix-stripped-#553",
        ),
    ],
)
def test_entity_column(field: ir.FieldSpec, expected: dict[str, tuple[str, str]]) -> None:
    # The PK and the FK back to the hub are never columns.
    assert _spoke_columns(field) == expected


@pytest.mark.parametrize(
    ("field", "column", "expected"),
    [
        pytest.param(
            _f("status", K.ENUM, enum_values=["in_progress", "on_hold", "done"]),
            "status",
            {
                "filter_type": "select",
                "filter_options": [
                    {"value": "in_progress", "label": "In Progress"},
                    {"value": "on_hold", "label": "On Hold"},
                    {"value": "done", "label": "Done"},
                ],
            },
            id="enum-filter-labels-title-cased-#584",
        ),
        pytest.param(
            _ref("assignee_id", "User"),
            "assignee",
            {
                "filterable": True,
                "filter_type": "select",
                "filter_options": [],
                "filter_ref_entity": "User",
                "filter_ref_api": "/users",
                # cycle 1365: list columns carry the avatar link meta
                "ref_entity": "User",
                "ref_route": "/app/user/{id}",
            },
            id="ref-filter-is-entity-select-#759",
        ),
        pytest.param(
            _ref("order_id", "Order", K.BELONGS_TO),
            "order",
            {"filter_type": "select", "filter_options": [], "filter_ref_entity": "Order"},
            id="belongs-to-filter-is-entity-select-#759",
        ),
    ],
)
def test_list_filter_column(field: ir.FieldSpec, column: str, expected: dict[str, Any]) -> None:
    surface = _surface("task_list", "Task", SurfaceMode.LIST, ux=ir.UXSpec(filter=[field.name]))
    ctx = compile_surface_to_context(surface, _entity("Task", field), app_prefix="/app")
    [col] = [c for c in ctx.table.columns if c.key == column]
    assert _attrs(col, expected) == expected


# =============================================================================
# Linker validation of related groups
# =============================================================================

_TAX_RETURN = _entity("TaxReturn", _ref("contact", "Contact"))
_STANDALONE = _entity("Standalone", _str("value"))


def _related(name: str, *show: str) -> ir.RelatedGroup:
    return ir.RelatedGroup(
        name=name, title=name, display=ir.RelatedDisplayMode.TABLE, show=list(show)
    )


@pytest.mark.parametrize(
    ("mode", "groups", "message"),
    [
        pytest.param(
            SurfaceMode.VIEW,
            [_related("c", "NonExistentEntity")],
            "related group 'c' references unknown entity 'NonExistentEntity'",
            id="unknown-entity",
        ),
        pytest.param(
            SurfaceMode.VIEW,
            [_related("misc", "Standalone")],
            "entity 'Standalone' has no FK to 'Contact'",
            id="no-fk-to-parent",
        ),
        pytest.param(
            SurfaceMode.VIEW,
            [_related("a", "TaxReturn"), _related("b", "TaxReturn")],
            "entity 'TaxReturn' appears in both related group 'b' and a previous group",
            id="same-entity-in-two-groups",
        ),
        pytest.param(
            SurfaceMode.LIST,
            [_related("a", "TaxReturn")],
            "has related blocks but is not mode: view",
            id="related-on-non-view-surface",
        ),
    ],
)
def test_related_group_validation(
    mode: SurfaceMode, groups: list[ir.RelatedGroup], message: str
) -> None:
    symbols = SymbolTable()
    for entity in (_company(), _contact(), _TAX_RETURN, _STANDALONE):
        symbols.add_entity(entity, "test")
    symbols.add_surface(_surface("contact_detail", "Contact", mode, related_groups=groups), "test")
    errors = validate_references(symbols)
    assert any(message in e for e in errors), errors


@pytest.mark.parametrize(
    ("groups", "expected"),
    [
        pytest.param([_related("compliance", "TaxReturn")], ["compliance"], id="with-groups"),
        pytest.param([], [], id="without-groups"),
    ],
)
def test_verifiable_triple_carries_related_groups(
    groups: list[ir.RelatedGroup], expected: list[str]
) -> None:
    surface = _surface(
        "contact_detail", "Contact", SurfaceMode.VIEW, _el("full_name"), related_groups=groups
    )
    triples = derive_triples(
        [_contact(), _TAX_RETURN], [surface], [ir.PersonaSpec(id="admin", label="Admin")]
    )
    assert next(t for t in triples if t.surface == "contact_detail").related_groups == expected
