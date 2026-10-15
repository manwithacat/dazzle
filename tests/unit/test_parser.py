"""Parser contract: DSL text → IR fragment, one table (or test) per construct.

Where to add a test for a new DSL construct (AGENTS.md › Adding DSL Constructs):
find the section for the construct below and add a row to its table; add a new
section only for a new top-level construct. Each row parses a small DSL snippet
and pins the IR attributes the construct must produce, addressed by a dotted
path (``type.kind.value``, ``steps[0].service``, ``len:fields``). Rejections go
in ``PARSE_ERROR_CASES`` with the message the author sees.

The parser-conformance corpus (``fixtures/pra/dsl/*.dsl``) pins only that the
kitchen-sink files parse (``tests/unit/test_dazzle_validate_drift.py``); it does
not assert IR values, so the rows here are not duplicates of it.
"""

import re
from pathlib import Path
from typing import Any

import pytest

from dazzle.core import ir, linker_impl
from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError
from dazzle.core.ir import BucketRef, BusinessPriority, OutcomeKind, SourceLocation
from dazzle.core.ir.fields import FieldModifier

# Leading newline keeps the first construct after the header on line 5,
# which the source-location rows rely on.
HEADER = '\nmodule test.core\napp MyApp "My App"\n\n'

PRESENT = object()  # expected value meaning "is not None"


def _parse(body: str, *, header: str = HEADER) -> tuple[Any, ...]:
    return parse_dsl(header + body, Path("test.dsl"))


def _fragment(body: str) -> Any:
    return _parse(body)[-1]


def _resolve(obj: Any, path: str) -> Any:
    """Walk a dotted path: ``a.b[0].c``; ``len:a.b`` returns ``len(a.b)``."""
    want_len = path.startswith("len:")
    for part in re.findall(r"\[\d+\]|[^.\[\]]+", path.removeprefix("len:")):
        if part.startswith("["):
            obj = obj[int(part[1:-1])]
        elif isinstance(obj, dict):
            obj = obj[part]
        else:
            obj = getattr(obj, part)
    return len(obj) if want_len else obj


def _assert_attrs(obj: Any, expected: dict[str, Any]) -> None:
    for path, want in expected.items():
        got = _resolve(obj, path)
        if want is PRESENT:
            assert got is not None, path
        else:
            assert got == want, f"{path}: {got!r} != {want!r}"


def _field(fragment: Any, entity: str, field: str) -> Any:
    ent = next(e for e in fragment.entities if e.name == entity)
    return next(f for f in ent.fields if f.name == field)


# ---------------------------------------------------------------------------
# module / app header
# ---------------------------------------------------------------------------

HEADER_CASES = [
    pytest.param(
        'module test.core\n\napp MyApp "My Application":\n  description: "A test application"\n'
        "  multi_tenant: true\n  audit_trail: true\n",
        {
            "app_name": "MyApp",
            "app_title": "My Application",
            "config.description": "A test application",
            "config.multi_tenant": True,
            "config.audit_trail": True,
        },
        id="app-config-all-options",
    ),
    pytest.param(
        'module test.core\n\napp MyApp "My Application":\n  description: "Just a description"\n',
        {
            "config.description": "Just a description",
            "config.multi_tenant": False,
            "config.audit_trail": False,
        },
        id="app-config-partial-defaults-flags-false",
    ),
    pytest.param(
        'module test.core\n\napp MyApp "My Application":\n  multi_tenant: true\n'
        '  custom_feature: "enabled"\n  another_flag: true\n',
        {
            "config.multi_tenant": True,
            "config.features.custom_feature": "enabled",
            "config.features.another_flag": True,
        },
        id="app-config-unknown-keys-become-features",
    ),
    pytest.param(
        'module test.core\n\napp MyApp "My Application"\n',
        {"app_name": "MyApp", "app_title": "My Application", "config": None},
        id="app-without-config-body",
    ),
    pytest.param(
        'module test.enum.types\napp MyApp "My App"\n',
        {"module": "test.enum.types"},
        id="enum-keyword-inside-module-name-v0.25",
    ),
]


@pytest.mark.parametrize(("header", "expected"), HEADER_CASES)
def test_module_and_app_header(header: str, expected: dict[str, Any]) -> None:
    module, app_name, app_title, config, _, fragment = parse_dsl(
        header + '\nentity User "User":\n  id: uuid pk\n', Path("test.dsl")
    )
    parsed = {
        "module": module,
        "app_name": app_name,
        "app_title": app_title,
        "config": config,
    }
    _assert_attrs(parsed, expected)
    assert [e.name for e in fragment.entities] == ["User"]


# ---------------------------------------------------------------------------
# entity fields: types and modifiers
# ---------------------------------------------------------------------------

_EMPLOYEE = (
    'entity Employee "Employee":\n  id: uuid pk\n  name: str(200) required\n'
    "  bank_account: str(8) sensitive\n  ni_number: str(9) required sensitive\n"
)
_STUDENT = (
    'entity School "School":\n  id: uuid pk\n\n'
    'entity Student "Student":\n  id: uuid pk\n  school: ref School indexed\n'
    "  email: str(200) indexed\n  name: str(200) required\n"
)
_MB = 1024 * 1024

FIELD_CASES = [
    # (entity body, (entity, field), expected attributes on the FieldSpec)
    pytest.param(
        'entity Invoice "Invoice":\n  id: uuid pk\n  total: money required\n',
        ("Invoice", "total"),
        {"type.kind.value": "money", "type.currency_code": "GBP"},
        id="money-defaults-to-GBP",
    ),
    pytest.param(
        'entity Invoice "Invoice":\n  id: uuid pk\n  total: money(USD) required\n',
        ("Invoice", "total"),
        {"type.kind.value": "money", "type.currency_code": "USD"},
        id="money-explicit-currency",
    ),
    pytest.param(
        'entity Link "Link":\n  id: uuid pk\n  target: url required\n',
        ("Link", "target"),
        {"type.kind.value": "url", "is_required": True},
        id="url",
    ),
    pytest.param(
        'entity Client "Client":\n  id: uuid pk\n  contacts: has_many Contact via ClientContact\n\n'
        'entity Contact "Contact":\n  id: uuid pk\n\n'
        'entity ClientContact "CC":\n  id: uuid pk\n  client: ref Client\n  contact: ref Contact\n',
        ("Client", "contacts"),
        {
            "type.kind.value": "has_many",
            "type.ref_entity": "Contact",
            "type.via_entity": "ClientContact",
        },
        id="has-many-via-junction",
    ),
    pytest.param(
        _EMPLOYEE,
        ("Employee", "bank_account"),
        {"is_sensitive": True, "is_required": False},
        id="sensitive-optional",
    ),
    pytest.param(
        _EMPLOYEE,
        ("Employee", "ni_number"),
        {"is_sensitive": True, "is_required": True},
        id="sensitive-combined-with-required",
    ),
    pytest.param(
        _EMPLOYEE, ("Employee", "name"), {"is_sensitive": False}, id="not-sensitive-by-default"
    ),
    pytest.param(
        _STUDENT, ("Student", "school"), {"is_indexed": True}, id="indexed-on-ref-field-#578"
    ),
    pytest.param(_STUDENT, ("Student", "email"), {"is_indexed": True}, id="indexed-on-scalar"),
    pytest.param(_STUDENT, ("Student", "name"), {"is_indexed": False}, id="not-indexed-by-default"),
    pytest.param(
        'entity Event "Event":\n  id: uuid pk\n  source: enum[manual, approval, sla, webhook] = manual\n',
        ("Event", "source"),
        {"type.enum_values": ["manual", "approval", "sla", "webhook"], "default": "manual"},
        id="v0.25-keywords-usable-as-enum-values",
    ),
    # file(SIZE) and file(ui: …): #436, #1213
    pytest.param(
        'entity Doc "Doc":\n  id: uuid pk\n  attachment: file\n',
        ("Doc", "attachment"),
        {"type.kind.value": "file", "type.max_size": None, "type.ui_mode": None},
        id="file-bare-no-size-no-ui-mode",
    ),
    pytest.param(
        'entity Doc "Doc":\n  id: uuid pk\n  raw: file(200MB)\n',
        ("Doc", "raw"),
        {"type.max_size": 200 * _MB},
        id="file-size-MB-#436",
    ),
    pytest.param(
        'entity Doc "Doc":\n  id: uuid pk\n  raw: file(1GB)\n',
        ("Doc", "raw"),
        {"type.max_size": 1024 * _MB},
        id="file-size-GB-#436",
    ),
    pytest.param(
        'entity Doc "Doc":\n  id: uuid pk\n  raw: file(500KB)\n',
        ("Doc", "raw"),
        {"type.max_size": 500 * 1024},
        id="file-size-KB-#436",
    ),
    pytest.param(
        'entity Doc "Doc":\n  id: uuid pk\n  raw: file(ui: drag_drop)\n',
        ("Doc", "raw"),
        {"type.ui_mode": "drag_drop", "type.max_size": None},
        id="file-ui-drag-drop-#1213",
    ),
    pytest.param(
        'entity Doc "Doc":\n  id: uuid pk\n  raw: file(200MB, ui: drag_drop)\n',
        ("Doc", "raw"),
        {"type.ui_mode": "drag_drop", "type.max_size": 200 * _MB},
        id="file-size-and-ui-mode-#1213",
    ),
    pytest.param(
        'entity Doc "Doc":\n  id: uuid pk\n  raw: file(ui: managed_upload)\n',
        ("Doc", "raw"),
        {"type.ui_mode": "managed_upload"},
        id="file-ui-managed-upload-#1213",
    ),
    # `was:` rename hints (#1431): additive to the modifiers, absent → None
    pytest.param(
        'entity Task "Task":\n  id: uuid pk\n  title: str(200) required was: name\n',
        ("Task", "title"),
        {"renamed_from": "name", "is_required": True},
        id="was-after-modifiers-#1431",
    ),
    pytest.param(
        'entity Task "Task":\n  id: uuid pk\n  body: text was: description\n',
        ("Task", "body"),
        {"renamed_from": "description"},
        id="was-directly-after-type-#1431",
    ),
    pytest.param(
        'entity Task "Task":\n  id: uuid pk\n  body: text was: description\n',
        ("Task", "id"),
        {"renamed_from": None},
        id="no-was-is-none-#1431",
    ),
]


@pytest.mark.parametrize(("body", "target", "expected"), FIELD_CASES)
def test_entity_field(body: str, target: tuple[str, str], expected: dict[str, Any]) -> None:
    _assert_attrs(_field(_fragment(body), *target), expected)


def test_was_hint_keeps_required_modifier() -> None:
    field = _field(
        _fragment('entity Task "Task":\n  id: uuid pk\n  title: str(200) required was: name\n'),
        "Task",
        "title",
    )
    assert FieldModifier.REQUIRED in field.modifiers


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        pytest.param(
            'entity Task "Task":\n  was: TodoItem\n  id: uuid pk\n',
            "TodoItem",
            id="entity-was-#1431",
        ),
        pytest.param('entity Task "Task":\n  id: uuid pk\n', None, id="entity-no-was-is-none"),
    ],
)
def test_entity_rename_hint(body: str, expected: str | None) -> None:
    task = _fragment(body).entities[0]
    assert (task.name, task.renamed_from) == ("Task", expected)


# ---------------------------------------------------------------------------
# state machines: transitions, guards, on_transition effects
# ---------------------------------------------------------------------------


def test_transition_requires_guard_without_colon() -> None:
    """Colon-free `requires` guard syntax on transitions (#543)."""
    fragment = _fragment(
        'entity Doc "Doc":\n  id: uuid pk\n  summary: text\n'
        "  status: enum[draft,published,canonical]=draft\n\n"
        "  transitions:\n    draft -> published\n    published -> canonical requires summary\n"
    )
    transitions = fragment.entities[0].state_machine.transitions
    shape = [(t.from_state, t.to_state, [g.requires_field for g in t.guards]) for t in transitions]
    assert shape == [("draft", "published", []), ("published", "canonical", ["summary"])]


ON_TRANSITION_CASES = [
    # (target entity + transition, on_transition block, expected effects as
    #  (action, entity, where, assignment values)) — #435
    pytest.param(
        "draft -> prepared",
        "    draft -> prepared:\n      create Task:\n"
        '        task_type: "vat_preparation"\n        title: "Prepare VAT return"\n',
        [("create", "Task", None, ['"vat_preparation"', '"Prepare VAT return"'])],
        id="create-effect-with-assignments",
    ),
    pytest.param(
        "draft -> prepared",
        "    draft -> prepared:\n      update Deadline:\n"
        '        where: linked_return_id = self.id\n        status: "missed"\n',
        [("update", "Deadline", "linked_return_id = self.id", ['"missed"'])],
        id="update-effect-with-where",
    ),
    pytest.param(
        "* -> prepared",
        '    * -> prepared:\n      create Alert:\n        message: "Cancelled"\n',
        [("create", "Alert", None, ['"Cancelled"'])],
        id="wildcard-source-state",
    ),
    pytest.param(
        "draft -> prepared",
        '    draft -> prepared:\n      create Task:\n        title: "Review"\n'
        '      create Log:\n        message: "Submitted"\n',
        [("create", "Task", None, ['"Review"']), ("create", "Log", None, ['"Submitted"'])],
        id="multiple-effects-keep-order",
    ),
]


@pytest.mark.parametrize(("transition", "block", "expected"), ON_TRANSITION_CASES)
def test_on_transition_effects(
    transition: str, block: str, expected: list[tuple[str, str, str | None, list[str]]]
) -> None:
    fragment = _fragment(
        'entity VATReturn "VAT Return":\n  id: uuid pk\n'
        "  status: enum[draft,prepared]=draft\n\n"
        f"  transitions:\n    {transition}\n\n  on_transition:\n{block}"
    )
    source, target = (s.strip() for s in transition.split("->"))
    t = fragment.entities[0].state_machine.get_transition(source, target)
    assert t is not None
    got = [
        (e.action.value, e.entity_name, e.where, [a.value for a in e.assignments])
        for e in t.effects
    ]
    assert got == expected


# ---------------------------------------------------------------------------
# parse errors: what the author sees
# ---------------------------------------------------------------------------

PARSE_ERROR_CASES = [
    pytest.param(
        'entity Thing "Thing":\n  id: uuid pk\n  name:\n  status: bool\n',
        r"Missing field type after ':'",
        id="missing-field-type-#544",
    ),
    pytest.param(
        'entity E "E":\n  id: uuid pk\n  name: \n',
        r"Missing field type after ':'",
        id="missing-field-type-trailing-space-#544",
    ),
    pytest.param(
        'entity Thing "Thing":\n  id: uuid pk\n  category: foobar\n',
        r"Unknown type: 'foobar'",
        id="unknown-type-shown-with-repr-#544",
    ),
    pytest.param(
        'entity Doc "Doc":\n  id: uuid pk\n  raw: file(ui: bogus_mode)\n',
        r"Unknown file ui mode: 'bogus_mode'",
        id="file-unknown-ui-mode-#1213",
    ),
    pytest.param(
        'entity Task "Task":\n  id: uuid pk\n  title: str(200) was:\n',
        r"`was:` rename hint expects an identifier",
        id="field-was-without-identifier-#1431",
    ),
    pytest.param(
        'entity Task "Task":\n  was:\n  id: uuid pk\n',
        r"`was:` rename hint expects an identifier",
        id="entity-was-without-identifier-#1431",
    ),
    pytest.param(
        'entity Progress "Progress":\n  id: uuid pk\n  user_id: ref User required\n\n'
        "  permit:\n    read: owner\n    update: owner\n",
        r"belongs in a scope: block",
        id="bare-owner-in-permit-guides-to-scope-#729",
    ),
    pytest.param(
        'entity Progress "Progress":\n  id: uuid pk\n  user_id: ref User required\n\n'
        "  permit:\n    read: owner or role(admin)\n",
        r"belongs in a scope: block",
        id="owner-or-role-in-permit-guides-to-scope-#729",
    ),
    pytest.param(
        'entity Order "Order":\n  id: uuid pk\n  status: enum[draft,submitted]=draft\n\n'
        "  transitions:\n    draft -> submitted\n\n"
        '  on_transition:\n    submitted -> draft:\n      create Task:\n        title: "t"\n',
        r"on_transition references undefined transition: submitted -> draft",
        id="on-transition-unknown-transition-#435",
    ),
    pytest.param(
        'entity Campaign "Campaign":\n  id: uuid pk\n  name: str(200) required\n\n'
        'surface campaign_create "Create":\n  uses entity Campaign\n  mode: create\n'
        '  section details "Details":\n    field name "Name": required\n'
        '    field description "Brief"\n',
        r"Unexpected",
        id="unsupported-token-in-section-errors-not-hangs-#731",
    ),
    pytest.param(
        'entity Alert "Alert":\n  id: uuid pk\n  created_at: datetime\n\n'
        'workspace dash "D":\n  chart:\n    source: Alert\n    display: line_chart\n'
        "    group_by: bucket(created_at, millennia)\n",
        r"Invalid bucket unit 'millennia'",
        id="group-by-bucket-unknown-unit",
    ),
    pytest.param(
        'entity Order "Order":\n  id: uuid pk\n\n'
        'process P "P":\n  trigger: entity Order created\n  steps:\n'
        "    - step WaitForPayment:\n        wait: PaymentReceived\n",
        r"wait: expects a duration",
        id="process-wait-takes-duration-only",
    ),
    pytest.param(
        'foreign_model Thing from stripe "Thing":\n  key: thing_id\n  constraint not_a_real_kind\n',
        r"Invalid foreign constraint kind",
        id="foreign-constraint-kind-is-parse-error-not-ValueError",
    ),
    pytest.param(
        'workspace ops "Ops":\n  engine_hint: "command_center"\n  purpose: "internal desk"\n',
        r"engine_hint.*use 'stage:'",
        # The token stays in the lexer so the old spelling gets "rename this",
        # not "unknown keyword" (ADR-0003).
        id="engine-hint-removed-names-stage-#1720",
    ),
]


@pytest.mark.parametrize(("body", "message"), PARSE_ERROR_CASES)
def test_parse_error(body: str, message: str) -> None:
    with pytest.raises(ParseError, match=message):
        _parse(body)


# ---------------------------------------------------------------------------
# source locations (v0.31.0)
# ---------------------------------------------------------------------------

_TASK = 'entity Task "Task":\n  id: uuid pk\n  title: str(200) required\n'


@pytest.mark.parametrize(
    ("body", "node", "line"),
    [
        pytest.param(_TASK, "entities[0]", 5, id="entity"),
        pytest.param(
            _TASK + '\nentity User "User":\n  id: uuid pk\n', "entities[1]", 9, id="second-entity"
        ),
        pytest.param(
            _TASK + '\nsurface task_list "Tasks":\n  uses entity Task\n  mode: list\n'
            "  section main:\n    field title\n",
            "surfaces[0]",
            9,
            id="surface",
        ),
        pytest.param(
            _TASK + '\nworkspace dashboard "Dashboard":\n  tasks:\n    source: Task\n',
            "workspaces[0]",
            9,
            id="workspace",
        ),
        pytest.param(
            _TASK + '\nprocess order_flow "Flow":\n  trigger: entity Task created\n'
            "  steps:\n    - step S:\n        service: Svc\n",
            "processes[0]",
            9,
            id="process",
        ),
    ],
)
def test_source_location(body: str, node: str, line: int) -> None:
    source = _resolve(_fragment(body), node).source
    assert (source.file, source.line, source.column) == ("test.dsl", line, 1)


def test_source_location_str() -> None:
    assert str(SourceLocation(file="dsl/app.dsl", line=42, column=5)) == "dsl/app.dsl:42:5"


# ---------------------------------------------------------------------------
# surfaces: field elements, layout, priority, actions, related groups, companions
# ---------------------------------------------------------------------------

_ADMIN = 'persona admin "Admin":\n  role: admin\npersona manager "Manager":\n  role: manager\n\n'


def _create_surface(field_line: str, *, extra: str = "") -> str:
    return (
        'entity Task "Task":\n  id: uuid pk\n  title: str(200) required\n  dob: date\n\n'
        'surface task_create "Create Task":\n  uses entity Task\n  mode: create\n'
        f"{extra}  section main:\n{field_line}"
    )


SURFACE_CASES = [
    # (DSL body, expected attributes on surfaces[0])
    pytest.param(
        _create_surface('    field title "Title"\n'),
        {
            "sections[0].elements[0].field_name": "title",
            "sections[0].elements[0].label": "Title",
            "sections[0].elements[0].options": {},
            "layout": "wizard",
            "related_groups": [],
            "companions": [],
            "actions": [],
        },
        id="plain-field-no-options-defaults",
    ),
    pytest.param(
        _create_surface(
            '    field title "Company" source=companies_house_lookup.search_companies\n'
        ),
        {
            "sections[0].elements[0].label": "Company",
            "sections[0].elements[0].options.source": "companies_house_lookup.search_companies",
        },
        id="field-source-option",
    ),
    pytest.param(
        _ADMIN + _create_surface('    field dob "DOB" visible: role(admin) widget=picker\n'),
        {
            "sections[0].elements[0].options.widget": "picker",
            "sections[0].elements[0].visible": PRESENT,
        },
        id="widget-after-visible-#754",
    ),
    pytest.param(
        _ADMIN + _create_surface('    field dob "DOB" widget=picker visible: role(admin)\n'),
        {
            "sections[0].elements[0].options.widget": "picker",
            "sections[0].elements[0].visible": PRESENT,
        },
        id="widget-before-visible",
    ),
    pytest.param(
        _ADMIN
        + _create_surface(
            '    field dob "DOB" visible: role(admin) or role(manager) widget=picker\n'
        ),
        {
            "sections[0].elements[0].options.widget": "picker",
            "sections[0].elements[0].visible": PRESENT,
        },
        id="widget-after-compound-visible-#754",
    ),
    pytest.param(
        _create_surface('    field title "Title"\n', extra="  layout: single_page\n"),
        {"layout": "single_page"},
        id="layout-single-page-#918",
    ),
    pytest.param(
        _create_surface('    note: "Fill in the basics"\n    field title "Title"\n'),
        {"sections[0].note": "Fill in the basics"},
        id="section-note-#918",
    ),
    pytest.param(
        _create_surface('    field title "Title" help: "A short summary"\n'),
        {"sections[0].elements[0].help": "A short summary"},
        id="field-help-#918",
    ),
    pytest.param(
        _TASK + '\nsurface task_detail "Detail":\n  uses entity Task\n  mode: view\n'
        '  section main:\n    field title "Title"\n  action portal "View in Portal":\n'
        '    on click -> "https://portal.example.com/records/{id}" external\n',
        {
            "actions[0].name": "portal",
            "actions[0].label": "View in Portal",
            "actions[0].outcome.kind": OutcomeKind.EXTERNAL,
            "actions[0].outcome.url": "https://portal.example.com/records/{id}",
            "actions[0].outcome.new_tab": True,  # default for external links
            "actions[0].outcome.target": "",  # no symbol to resolve
        },
        id="external-action-link-#542",
    ),
]


@pytest.mark.parametrize(("body", "expected"), SURFACE_CASES)
def test_surface(body: str, expected: dict[str, Any]) -> None:
    _assert_attrs(_fragment(body).surfaces[0], expected)


@pytest.mark.parametrize(
    ("priority_line", "expected"),
    [
        pytest.param(f"  priority: {level}\n", BusinessPriority(level), id=f"surface-{level}")
        for level in ("critical", "high", "medium", "low")
    ]
    + [pytest.param("", BusinessPriority.MEDIUM, id="surface-defaults-to-medium")],
)
def test_surface_priority(priority_line: str, expected: BusinessPriority) -> None:
    fragment = _fragment(
        _TASK + '\nsurface task_list "Tasks":\n  uses entity Task\n  mode: list\n'
        f'{priority_line}  section main:\n    field title "Title"\n'
    )
    assert fragment.surfaces[0].priority == expected


@pytest.mark.parametrize(
    ("header_lines", "priority", "require_auth"),
    [
        pytest.param("  priority: critical\n", "critical", None, id="experience-critical"),
        pytest.param("", "medium", None, id="experience-defaults-to-medium"),
        pytest.param(
            "  access: authenticated\n  priority: high\n", "high", True, id="experience-with-access"
        ),
    ],
)
def test_experience_priority(header_lines: str, priority: str, require_auth: bool | None) -> None:
    fragment = _fragment(
        _create_surface('    field title "Title"\n')
        + f'\nexperience task_wizard "Wizard":\n{header_lines}  start at step intake\n'
        "  step intake:\n    kind: surface\n    surface task_create\n"
    )
    exp = fragment.experiences[0]
    assert exp.priority.value == priority
    assert (exp.access.require_auth if exp.access else None) == require_auth


def _view_surface(related: str) -> str:
    return (
        'entity Contact "Contact":\n  id: uuid pk\n  name: str(100) required\n\n'
        'entity TaxReturn "Tax Return":\n  id: uuid pk\n  contact: ref Contact\n'
        "  status: str(50)\n  period: str(20)\n\n"
        'entity Document "Document":\n  id: uuid pk\n  contact: ref Contact\n\n'
        'surface contact_detail "Contact Detail":\n  uses entity Contact\n  mode: view\n'
        f'  section main:\n    field name "Name"\n{related}'
    )


@pytest.mark.parametrize(
    ("related", "expected"),
    [
        pytest.param("", [], id="none"),
        pytest.param(
            '  related compliance "Compliance":\n    display: status_cards\n    show: TaxReturn\n',
            [("compliance", "Compliance", "status_cards", ["TaxReturn"], [])],
            id="status-cards",
        ),
        pytest.param(
            '  related tasks "Tasks":\n    display: queue\n    show: TaxReturn\n'
            "    columns: status, period\n",
            [("tasks", "Tasks", "queue", ["TaxReturn"], ["status", "period"])],
            id="queue-display-cycle-1494",
        ),
        pytest.param(
            '  related discussion "Discussion":\n    display: conversation\n    show: Document\n'
            "    columns: content, author, created_at\n",
            [
                (
                    "discussion",
                    "Discussion",
                    "conversation",
                    ["Document"],
                    ["content", "author", "created_at"],
                )
            ],
            id="conversation-display-cycle-1893",
        ),
        pytest.param(
            '  related compliance "Compliance":\n    display: table\n    show: TaxReturn\n'
            "    columns: status, period\n",
            [("compliance", "Compliance", "table", ["TaxReturn"], ["status", "period"])],
            id="table-columns-projection-#1600",
        ),
        pytest.param(
            '  related compliance "Compliance":\n    display: status_cards\n'
            "    show: TaxReturn, Document\n"
            '  related documents "Documents":\n    display: file_list\n    show: Document\n',
            [
                ("compliance", "Compliance", "status_cards", ["TaxReturn", "Document"], []),
                ("documents", "Documents", "file_list", ["Document"], []),
            ],
            id="multiple-blocks-multi-entity-show",
        ),
    ],
)
def test_surface_related_groups(related: str, expected: list[tuple[Any, ...]]) -> None:
    groups = _fragment(_view_surface(related)).surfaces[0].related_groups
    got = [(g.name, g.title, g.display.value, g.show, g.columns or []) for g in groups]
    assert got == expected


def _companion_surface(companions: str) -> str:
    return (
        'entity Pupil "Pupil":\n  id: uuid pk\n\n'
        'entity Doc "Doc":\n  id: uuid pk\n  pages: int\n  auto_run: bool\n\n'
        'surface doc_create "Upload":\n  uses entity Doc\n  mode: create\n\n'
        f'{companions}\n  section automation "Automation":\n    field auto_run "Run"\n'
    )


COMPANION_CASES = [
    # Companion regions on create/edit surfaces (#923, Part D of #918)
    pytest.param(
        '  companion summary "Batch summary" position=top:\n    eyebrow: "Live"\n'
        "    display: summary_row\n    aggregate:\n      pages: max(pages)\n",
        {
            "companions[0].name": "summary",
            "companions[0].title": "Batch summary",
            "companions[0].eyebrow": "Live",
            "companions[0].position.value": "top",
            "companions[0].section_anchor": None,
            "companions[0].display": "summary_row",
            "companions[0].aggregate.pages": PRESENT,
        },
        id="position-top-with-aggregate",
    ),
    pytest.param(
        '  companion job_plan "Triggers" position=below_section[automation]:\n'
        "    display: status_list\n    entries:\n"
        '      - title: "Classify the batch"\n        caption: "Match paper"\n'
        '      - title: "Separate the PDF"\n',
        {
            "companions[0].position.value": "below_section",
            "companions[0].section_anchor": "automation",
            "len:companions[0].entries": 2,
            "companions[0].entries[0].title": "Classify the batch",
            "companions[0].entries[0].caption": "Match paper",
            "companions[0].entries[1].title": "Separate the PDF",
        },
        id="position-below-section-anchor-with-entries",
    ),
    pytest.param(
        '  companion plain "Footer note":\n    display: status_list\n',
        {"companions[0].position.value": "bottom", "companions[0].section_anchor": None},
        id="position-defaults-to-bottom",
    ),
    pytest.param(
        '  companion plan "Pipeline" position=bottom:\n    display: pipeline_steps\n'
        '    stages:\n      - label: "Classify"\n        caption: "Sort by paper"\n'
        '      - label: "Score"\n',
        {
            "companions[0].display": "pipeline_steps",
            "len:companions[0].stages": 2,
            "companions[0].stages[0].label": "Classify",
            "companions[0].stages[0].caption": "Sort by paper",
            "companions[0].stages[1].label": "Score",
            "companions[0].stages[1].caption": None,
        },
        id="pipeline-stages",
    ),
    pytest.param(
        '  companion roster "Cohort roster" position=top:\n    source: Pupil\n'
        "    display: list\n    limit: 5\n",
        {
            "companions[0].source": "Pupil",
            "companions[0].display": "list",
            "companions[0].limit": 5,
        },
        id="source-bound",
    ),
    pytest.param(
        '  companion a "Top A" position=top:\n    display: status_list\n\n'
        '  companion b "Bottom B" position=bottom:\n    display: status_list\n\n'
        '  companion c "Top C" position=top:\n    display: status_list\n',
        {
            "len:companions": 3,
            "companions[0].name": "a",
            "companions[1].name": "b",
            "companions[2].name": "c",
        },
        # The renderer relies on declaration order for stable layout.
        id="declaration-order-preserved",
    ),
]


@pytest.mark.parametrize(("companions", "expected"), COMPANION_CASES)
def test_surface_companion(companions: str, expected: dict[str, Any]) -> None:
    _assert_attrs(_fragment(_companion_surface(companions)).surfaces[0], expected)


# ---------------------------------------------------------------------------
# workspaces: regions, nav groups, nav definitions, primary actions, context selector
# ---------------------------------------------------------------------------

_ALERT = (
    'entity Alert "Alert":\n  id: uuid pk\n  created_at: datetime\n  severity: enum[high, low]\n\n'
)


def _region(region: str) -> str:
    return _ALERT + f'workspace dash "Dashboard":\n  chart:\n    source: Alert\n{region}'


# group_by: bucket(field, unit) — v0.60.0, cycle 28.
_COUNT = "    aggregate:\n      count: count(Alert)\n"

REGION_CASES = (
    [
        pytest.param(
            _region(f"    display: {mode}\n"), {"display.value": mode}, id=f"display-{mode}"
        )
        for mode in ("kanban", "bar_chart", "activity_feed")
    ]
    + [
        pytest.param(
            _region(
                f"    display: line_chart\n    group_by: bucket(created_at, {unit})\n" + _COUNT
            ),
            {"group_by": BucketRef(field="created_at", unit=unit)},
            id=f"group-by-bucket-{unit}",
        )
        for unit in ("day", "week", "month", "quarter", "year")
    ]
    + [
        pytest.param(
            _region(
                "    display: pivot_table\n    group_by: [bucket(created_at, week), severity]\n"
                + _COUNT
            ),
            {"group_by_dims": [BucketRef(field="created_at", unit="week"), "severity"]},
            id="group-by-multi-dim-bucket-plus-scalar",
        ),
        pytest.param(
            _region("    display: bar_chart\n    group_by: severity\n" + _COUNT),
            {"group_by": "severity"},
            id="group-by-bare-field",
        ),
    ]
)


@pytest.mark.parametrize(("body", "expected"), REGION_CASES)
def test_workspace_region(body: str, expected: dict[str, Any]) -> None:
    _assert_attrs(_fragment(body).workspaces[0].regions[0], expected)


_NAV_ENTITIES = "".join(
    f'entity {name} "{name}":\n  id: uuid pk\n\n'
    for name in ("Task", "User", "Question", "Topic", "Note")
)

NAV_GROUP_CASES = [
    # Workspace nav_group parsing (v0.38.0, #418).
    # (workspace nav_group lines, [(label, icon, collapsed, [(entity, icon)])])
    pytest.param("", [], id="none"),
    pytest.param(
        '  nav_group "Management" icon=settings:\n    Task\n    User\n',
        [("Management", "settings", False, [("Task", None), ("User", None)])],
        id="basic-with-icon",
    ),
    pytest.param(
        '  nav_group "Hidden" collapsed:\n    Task\n',
        [("Hidden", None, True, [("Task", None)])],
        id="collapsed-no-icon",
    ),
    pytest.param(
        '  nav_group "Work":\n    Task icon=check-circle\n',
        [("Work", None, False, [("Task", "check-circle")])],
        id="item-icon",
    ),
    pytest.param(
        '  nav_group "Tasks" icon=clipboard:\n    Task\n  nav_group "Admin" icon=shield:\n    User\n',
        [
            ("Tasks", "clipboard", False, [("Task", None)]),
            ("Admin", "shield", False, [("User", None)]),
        ],
        id="multiple-groups-in-order",
    ),
    pytest.param(
        '  nav_group "Questions" icon=help-circle:\n    Question icon=circle-help\n'
        '  nav_group "Reverse" icon=circle-help:\n    Topic icon=file-question\n'
        '  nav_group "Notes" icon=sticky-note:\n    Note icon=note-pencil\n',
        [
            ("Questions", "help-circle", False, [("Question", "circle-help")]),
            ("Reverse", "circle-help", False, [("Topic", "file-question")]),
            ("Notes", "sticky-note", False, [("Note", "note-pencil")]),
        ],
        id="hyphenated-icons-containing-keywords-#922",
    ),
]


@pytest.mark.parametrize(("groups", "expected"), NAV_GROUP_CASES)
def test_workspace_nav_groups(groups: str, expected: list[tuple[Any, ...]]) -> None:
    ws = _fragment(
        _NAV_ENTITIES + f'workspace dashboard "Dashboard":\n{groups}  tasks:\n    source: Task\n'
    ).workspaces[0]
    got = [
        (g.label, g.icon, g.collapsed, [(i.entity, i.icon) for i in g.items]) for g in ws.nav_groups
    ]
    assert got == expected
    # No `when:` declared → group and item visibility conditions stay None (#1324).
    assert all(g.when is None and all(i.when is None for i in g.items) for g in ws.nav_groups)


def test_nav_definition_top_level() -> None:
    """#926: top-level `nav <name>:` declares a reusable block; workspaces
    reference it with `uses nav <name>`. Inside the block `group` and
    `nav_group` are synonyms. The parser records the reference only — the
    linker materialises the groups, so the workspace's own list stays empty."""
    fragment = _fragment(
        _NAV_ENTITIES + "nav teacher_nav:\n"
        '  group "My Classes" icon=users:\n    Task\n'
        '  nav_group "Work":\n    User\n\n'
        'workspace dashboard "Dashboard":\n  uses nav teacher_nav\n  c:\n    source: Task\n'
    )
    nav = fragment.navs[0]
    assert nav.name == "teacher_nav"
    assert [(g.label, g.icon, [i.entity for i in g.items]) for g in nav.groups] == [
        ("My Classes", "users", ["Task"]),
        ("Work", None, ["User"]),
    ]
    ws = fragment.workspaces[0]
    assert (ws.nav_ref, ws.nav_groups) == ("teacher_nav", [])


def test_nav_group_when_on_header_and_item() -> None:
    """#1324 FR-4 slice A: optional ``when: <cond>`` on a group header and
    on an item parse to ConditionExprs (render-time visibility)."""
    nav = _fragment(
        _NAV_ENTITIES + "nav teacher_nav:\n"
        '  group "Integrations" icon=plug when: tenant_config.mis_connected:\n'
        "    Task\n    User when: tenant_config.beta_features\n"
    ).navs[0]
    group = nav.groups[0]
    assert (group.label, group.icon) == ("Integrations", "plug")
    assert group.when.comparison.field == "tenant_config.mis_connected"
    assert [(i.entity, i.when and i.when.comparison.field) for i in group.items] == [
        ("Task", None),
        ("User", "tenant_config.beta_features"),
    ]


@pytest.mark.parametrize(
    ("nav_ref", "expected_ref", "expected_labels"),
    [
        # Linker prepends the inherited groups, then the workspace's own.
        pytest.param("teacher_nav", "teacher_nav", ["Classes", "Local"], id="resolved-composes"),
        # Unresolved: own groups survive; validation reports the error later.
        pytest.param("nonexistent_nav", "nonexistent_nav", ["Local"], id="unresolved-no-crash"),
    ],
)
def test_nav_definition_linked_into_workspace(
    nav_ref: str, expected_ref: str, expected_labels: list[str]
) -> None:
    _, app_name, app_title, app_config, uses, fragment = _parse(
        _NAV_ENTITIES + 'nav teacher_nav:\n  group "Classes" icon=users:\n    Task\n\n'
        f'workspace proctor "Proctor":\n  uses nav {nav_ref}\n'
        '  group "Local" icon=calendar:\n    User\n  s:\n    source: User\n'
    )
    mod = ir.ModuleIR(
        name="test.core",
        file=Path("test.dsl"),
        app_name=app_name,
        app_title=app_title,
        app_config=app_config,
        uses=uses,
        fragment=fragment,
    )
    merged = linker_impl.merge_fragments([mod], linker_impl.build_symbol_table([mod]))
    ws = merged.workspaces[0]
    assert ws.nav_ref == expected_ref
    assert [g.label for g in ws.nav_groups] == expected_labels


@pytest.mark.parametrize(
    ("block", "expected"),
    [
        pytest.param(
            '  primary_actions:\n    action "New Invoice" -> surface create_invoice\n'
            '    action "Dashboard" -> workspace ops_dashboard\n',
            [
                ("New Invoice", "surface", "create_invoice"),
                ("Dashboard", "workspace", "ops_dashboard"),
            ],
            id="surface-and-workspace-targets-#1324",
        ),
        pytest.param("", [], id="absent-is-empty-list"),
    ],
)
def test_workspace_primary_actions(block: str, expected: list[tuple[str, str, str]]) -> None:
    ws = _fragment(
        'entity Invoice "Invoice":\n  id: uuid pk\n\n'
        'workspace reports "Reports":\n' + block + "  metrics:\n    source: Invoice\n"
    ).workspaces[0]
    assert [(a.label, a.target_kind, a.target) for a in ws.primary_actions] == expected


_SELECTOR_ENTITIES = (
    'entity Trust "Trust":\n  id: uuid pk\n\n'
    'entity School "School":\n  id: uuid pk\n  name: str(100) required\n  trust: ref Trust\n\n'
    'entity Student "Student":\n  id: uuid pk\n\n'
)


@pytest.mark.parametrize(
    ("selector", "expected"),
    [
        pytest.param("", {"context_selector": None}, id="absent-is-none"),
        pytest.param(
            "  context_selector:\n    entity: School\n    display_field: name\n",
            {
                "context_selector.entity": "School",
                "context_selector.display_field": "name",
                "context_selector.scope_field": None,
                "context_selector.filter": None,
            },
            id="basic-#432",
        ),
        pytest.param(
            "  context_selector:\n    entity: School\n",
            {"context_selector.display_field": "name"},
            id="display-field-defaults-to-name",
        ),
        pytest.param(
            "  context_selector:\n    entity: School\n    display_field: name\n"
            "    scope_field: trust\n",
            {"context_selector.scope_field": "trust"},
            id="scope-field",
        ),
        pytest.param(
            "  context_selector:\n    entity: School\n    filter: department != External\n",
            {
                "context_selector.filter.comparison.field": "department",
                "context_selector.filter.comparison.operator.value": "!=",
                "context_selector.filter.comparison.value.literal": "External",
            },
            id="filter-condition",
        ),
    ],
)
def test_workspace_context_selector(selector: str, expected: dict[str, Any]) -> None:
    ws = _fragment(
        _SELECTOR_ENTITIES + f'workspace school_dashboard "School Dashboard":\n{selector}\n'
        "  students:\n    source: Student\n"
    ).workspaces[0]
    _assert_attrs(ws, expected)


def test_workspace_stage() -> None:
    """`stage:` is the spelling the #1720 `engine_hint:` error points to."""
    fragment = _fragment('workspace ops "Ops":\n  stage: "command_center"\n  purpose: "desk"\n')
    assert [w.stage for w in fragment.workspaces] == ["command_center"]


# ---------------------------------------------------------------------------
# story (v0.22.0)
# ---------------------------------------------------------------------------


def test_story_with_all_clauses() -> None:
    story = _fragment(
        'entity Invoice "Invoice":\n  id: uuid pk\n\n'
        'story ST-001 "Staff sends invoice":\n  persona: StaffUser\n'
        "  trigger: status_changed\n  entities: [Invoice, FollowupTask]\n\n"
        '  given:\n    - "Invoice.status is draft"\n\n'
        '  when:\n    - "User submits form"\n\n'
        '  then:\n    - "Invoice.status changes to sent"\n\n'
        '  unless:\n    - "Client.email is missing":\n        then: "FollowupTask is created"\n'
    ).stories[0]
    assert (story.story_id, story.title, story.persona) == (
        "ST-001",
        "Staff sends invoice",
        "StaffUser",
    )
    assert story.trigger.value == "status_changed"
    assert story.entities == ["Invoice", "FollowupTask"]
    assert [c.expression for c in story.given] == ["Invoice.status is draft"]
    assert [c.expression for c in story.when] == ["User submits form"]
    assert [c.expression for c in story.then] == ["Invoice.status changes to sent"]
    assert [(u.condition, u.then_outcomes) for u in story.unless] == [
        ("Client.email is missing", ["FollowupTask is created"])
    ]


@pytest.mark.parametrize(
    "trigger",
    [
        "form_submitted",
        "status_changed",
        "timer_elapsed",
        "external_event",
        "user_click",
        "cron_daily",
        "cron_hourly",
    ],
)
def test_story_trigger(trigger: str) -> None:
    fragment = _fragment(f'story ST-TRIG "T":\n  persona: User\n  trigger: {trigger}\n')
    assert [s.trigger.value for s in fragment.stories] == [trigger]


# ---------------------------------------------------------------------------
# process (v0.23.0)
# ---------------------------------------------------------------------------


def _process(lines: str) -> str:
    return (
        'entity Order "Order":\n  id: uuid pk\n  status: enum[pending,confirmed]=pending\n\n'
        f'process P "P":\n{lines}'
    )


@pytest.mark.parametrize(
    ("trigger", "expected"),
    [
        pytest.param(
            "entity Order status -> confirmed",
            {
                "kind.value": "entity_status_transition",
                "entity_name": "Order",
                "from_status": None,
                "to_status": "confirmed",
            },
            id="entity-status-transition",
        ),
        pytest.param(
            "entity Order created",
            {"kind.value": "entity_event", "entity_name": "Order", "event_type": "created"},
            id="entity-event",
        ),
        pytest.param("manual", {"kind.value": "manual"}, id="manual"),
        pytest.param(
            "signal PaymentComplete",
            {"kind.value": "signal", "process_name": "PaymentComplete"},
            id="signal",
        ),
    ],
)
def test_process_trigger(trigger: str, expected: dict[str, Any]) -> None:
    process = _fragment(
        _process(f"  trigger: {trigger}\n  steps:\n    - step S:\n        service: Svc\n")
    ).processes[0]
    _assert_attrs(process.trigger, expected)


PROCESS_STEP_CASES = [
    pytest.param(
        "    - step CheckInventory:\n        service: InventoryService\n        timeout: 30s\n",
        {
            "name": "CheckInventory",
            "kind.value": "service",
            "service": "InventoryService",
            "timeout_seconds": 30,
        },
        id="service-with-timeout",
    ),
    pytest.param(
        "    - step Notify:\n        channel: email\n        message: new_order_notification\n",
        {"kind.value": "send", "channel": "email", "message": "new_order_notification"},
        id="send",
    ),
    pytest.param(
        "    - step WaitForPayment:\n        wait: 24h\n",
        {"kind.value": "wait", "wait_duration_seconds": 86400},
        id="wait-duration",
    ),
    pytest.param(
        "    - step Approve:\n        human_task:\n          assignee: manager\n"
        "          surface: ApprovalForm\n          timeout: 2d\n",
        {
            "kind.value": "human_task",
            "human_task.assignee_expression": "manager",
            "human_task.surface": "ApprovalForm",
            "human_task.timeout_seconds": 172800,
        },
        id="human-task",
    ),
    pytest.param(
        "    - step Run:\n        subprocess: PaymentProcess\n",
        {"kind.value": "subprocess", "subprocess": "PaymentProcess"},
        id="subprocess",
    ),
    pytest.param(
        '    - step CheckAmount:\n        condition: "Order.total > 1000"\n'
        "        on_true: HighValueApproval\n        on_false: AutoApprove\n",
        {
            "kind.value": "condition",
            "condition": "Order.total > 1000",
            "on_true": "HighValueApproval",
            "on_false": "AutoApprove",
        },
        id="condition",
    ),
    pytest.param(
        "    - parallel Fanout:\n"
        "        - step NotifyCustomer:\n            channel: email\n            message: m1\n"
        "        - step NotifyWarehouse:\n            channel: email\n            message: m2\n"
        "        - step UpdateAnalytics:\n            service: AnalyticsService\n",
        {
            "kind.value": "parallel",
            "len:parallel_steps": 3,
            "parallel_steps[0].name": "NotifyCustomer",
            "parallel_steps[1].name": "NotifyWarehouse",
            "parallel_steps[2].name": "UpdateAnalytics",
        },
        id="parallel-branches",
    ),
    pytest.param(
        "    - step Reserve:\n        service: InventoryService\n"
        "        compensate: ReleaseInventory\n",
        {"compensate_with": "ReleaseInventory"},
        id="saga-compensate",
    ),
]


@pytest.mark.parametrize(("step", "expected"), PROCESS_STEP_CASES)
def test_process_step(step: str, expected: dict[str, Any]) -> None:
    process = _fragment(_process(f"  trigger: entity Order created\n  steps:\n{step}")).processes[0]
    assert len(process.steps) == 1
    _assert_attrs(process.steps[0], expected)


def test_process_header_inputs_timeout_and_step_order() -> None:
    process = _fragment(
        _process(
            "  trigger: entity Order created\n  implements: [ST-001, ST-002]\n  timeout: 1h\n"
            "  input:\n    order_id: uuid\n    priority: str\n"
            "  steps:\n"
            "    - step Step1:\n        service: Service1\n        timeout: 30s\n"
            "    - step Step2:\n        service: Service2\n        timeout: 1m\n"
            "    - step Step3:\n        channel: email\n        message: done\n"
        )
    ).processes[0]
    assert (process.name, process.title) == ("P", "P")
    assert process.implements == ["ST-001", "ST-002"]
    assert process.timeout_seconds == 3600
    assert [(i.name, i.type) for i in process.inputs] == [("order_id", "uuid"), ("priority", "str")]
    assert [(s.name, s.timeout_seconds) for s in process.steps][:2] == [
        ("Step1", 30),
        ("Step2", 60),
    ]
    assert process.steps[2].name == "Step3"


# ---------------------------------------------------------------------------
# schedule (v0.23.0)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("lines", "expected"),
    [
        pytest.param(
            '  cron: "0 6 * * *"\n  implements: [ST-010]\n',
            {"cron": "0 6 * * *", "implements": ["ST-010"], "interval_seconds": None},
            id="cron-with-implements",
        ),
        pytest.param("  interval: 5m\n", {"interval_seconds": 300, "cron": None}, id="interval-5m"),
        pytest.param("  interval: 1h\n", {"interval_seconds": 3600}, id="interval-1h"),
        pytest.param(
            '  cron: "0 9 * * 1-5"\n  timezone: "Europe/London"\n',
            {"timezone": "Europe/London"},
            id="timezone",
        ),
        pytest.param('  cron: "0 0 * * *"\n  catch_up: true\n', {"catch_up": True}, id="catch-up"),
    ],
)
def test_schedule(lines: str, expected: dict[str, Any]) -> None:
    schedule = _fragment(
        f'schedule DailyReport "Daily Report":\n{lines}'
        "  steps:\n    - step Work:\n        service: WorkService\n"
    ).schedules[0]
    assert (schedule.name, schedule.title) == ("DailyReport", "Daily Report")
    _assert_attrs(schedule, expected)


# ---------------------------------------------------------------------------
# view (v0.25.0)
# ---------------------------------------------------------------------------

_ORDER = (
    'entity Order "Order":\n  id: uuid pk\n  customer: str(100)\n'
    "  created_at: datetime auto_add\n  amount: decimal(10,2) required\n\n"
)


@pytest.mark.parametrize(
    ("view", "expected"),
    [
        pytest.param(
            'view OrderSummary "Order Summary":\n  source: Order\n  group_by: [status]\n'
            "  fields:\n    total_amount: sum(amount)\n    order_count: count()\n",
            {
                "name": "OrderSummary",
                "title": "Order Summary",
                "source_entity": "Order",
                "group_by": ["status"],
                "len:fields": 2,
                "fields[0].name": "total_amount",
                "fields[0].expression": PRESENT,
                "fields[1].name": "order_count",
            },
            id="aggregate-fields-and-group-by",
        ),
        pytest.param(
            'view Monthly "Monthly":\n  source: Order\n  group_by: [customer, month(created_at)]\n'
            "  fields:\n    total: sum(amount)\n",
            {"group_by": ["customer", "month(created_at)"]},
            id="function-call-in-group-by",
        ),
        pytest.param(
            'view Report "Report":\n  source: Order\n  fields:\n    label: str(200)\n'
            "    total: sum(amount)\n",
            {
                "fields[0].field_type": PRESENT,
                "fields[0].expression": None,
                "fields[1].expression": PRESENT,
                "fields[1].field_type": None,
            },
            id="typed-field-vs-aggregate-field",
        ),
        pytest.param(
            "view QuickReport:\n  source: Order\n  fields:\n    total: sum(amount)\n",
            {"name": "QuickReport", "title": None},
            id="title-optional",
        ),
    ],
)
def test_view(view: str, expected: dict[str, Any]) -> None:
    _assert_attrs(_fragment(_ORDER + view).views[0], expected)


# ---------------------------------------------------------------------------
# sla (v0.25.0)
# ---------------------------------------------------------------------------


def test_sla_full() -> None:
    """All sub-blocks. `entity:` inside the block must not be captured by the
    top-level entity dispatcher (#222)."""
    sla = _fragment(
        'entity SupportTicket "Support Ticket":\n  id: uuid pk\n'
        "  status: enum[open,on_hold,resolved]=open\n  escalated: bool=false\n\n"
        'sla TicketResponse "Ticket Response SLA":\n  entity: SupportTicket\n'
        "  starts_when: status -> open\n  pauses_when: status = on_hold\n"
        "  completes_when: status -> resolved\n"
        "  tiers:\n    warning: 15 minutes\n    breach: 8 hours\n    critical: 2 days\n"
        '  business_hours:\n    schedule: "Mon-Fri 09:00-17:00"\n    timezone: "Europe/London"\n'
        "  on_breach:\n    notify: support_lead\n    set: escalated = true\n"
    ).slas[0]
    assert (sla.name, sla.title, sla.entity) == (
        "TicketResponse",
        "Ticket Response SLA",
        "SupportTicket",
    )
    conditions = [sla.starts_when, sla.pauses_when, sla.completes_when]
    assert [(c.field, c.operator, c.value) for c in conditions] == [
        ("status", "->", "open"),
        ("status", "=", "on_hold"),
        ("status", "->", "resolved"),
    ]
    assert [(t.name, t.duration_value, t.duration_unit) for t in sla.tiers] == [
        ("warning", 15, "minutes"),
        ("breach", 8, "hours"),
        ("critical", 2, "days"),
    ]
    assert (sla.business_hours.schedule, sla.business_hours.timezone) == (
        "Mon-Fri 09:00-17:00",
        "Europe/London",
    )
    assert sla.on_breach.notify_role == "support_lead"
    assert [(a.field_path, a.value) for a in sla.on_breach.field_assignments] == [
        ("escalated", "true")
    ]


def test_sla_minimal_optional_blocks_are_none() -> None:
    sla = _fragment(
        'entity Task "Task":\n  id: uuid pk\n  status: enum[open,done]=open\n\n'
        "sla TaskCompletion:\n  entity: Task\n  starts_when: status -> open\n"
        "  completes_when: status -> done\n  tiers:\n    warning: 2 hours\n    breach: 4 hours\n"
    ).slas[0]
    assert sla.name == "TaskCompletion"
    assert (sla.title, sla.pauses_when, sla.business_hours, sla.on_breach) == (
        None,
        None,
        None,
        None,
    )
    assert len(sla.tiers) == 2


# ---------------------------------------------------------------------------
# dispatcher preservation (#222 root cause: older dispatchers dropped newer fields)
# ---------------------------------------------------------------------------

_STATEFUL = (
    'entity Task "Task":\n  id: uuid pk\n  status: enum[open, done] = open\n'
    "  transitions:\n    open -> done\n\n"
)
_SLA = (
    'sla TaskSLA "SLA":\n  entity: Task\n  starts_when: status -> open\n'
    "  completes_when: status -> done\n  tiers:\n    warning: 4 hours\n\n"
)
_SCENARIO = (
    'persona admin "Admin":\n  description: "Admin user"\n\n'
    'scenario smoke "Demo":\n  description: "Demo"\n  as persona admin:\n    start_route: "/"\n'
)


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        pytest.param(
            _STATEFUL + _SLA + _SCENARIO,
            {"slas": 1, "scenarios": 1, "personas": 1},
            id="sla-before-scenario-#222",
        ),
        pytest.param(
            _STATEFUL
            + 'view TaskSummary "Summary":\n  source: Task\n  fields:\n    count: count()\n\n'
            + _SLA
            + 'surface task_list "Tasks":\n  uses entity Task\n  mode: list\n'
            '  section main:\n    field status "Status"\n\n' + _SCENARIO,
            {"views": 1, "slas": 1, "entities": 1, "surfaces": 1, "personas": 1, "scenarios": 1},
            id="all-v0.25-constructs-interleaved-#222",
        ),
        pytest.param(
            _STATEFUL + _SLA + 'process TaskFlow "Flow":\n  trigger: entity Task created\n'
            "  steps:\n    - step S:\n        service: Svc\n",
            {"slas": 1, "processes": 1},
            id="sla-before-process-#222",
        ),
    ],
)
def test_constructs_survive_mixed_dispatch(body: str, expected: dict[str, int]) -> None:
    fragment = _fragment(body)
    assert {name: len(getattr(fragment, name)) for name in expected} == expected


def test_process_schedule_and_stories_in_one_module() -> None:
    fragment = _fragment(
        _STATEFUL + 'story ST-001 "Create":\n  persona: Customer\n  trigger: form_submitted\n\n'
        'story ST-002 "Fulfil":\n  persona: System\n  trigger: status_changed\n\n'
        'process TaskProcess "Task Process":\n  trigger: entity Task created\n'
        "  implements: [ST-001, ST-002]\n  steps:\n    - step S:\n        service: Svc\n\n"
        'schedule TaskCleanup "Cleanup":\n  cron: "0 0 * * *"\n'
        "  steps:\n    - step C:\n        service: CleanupService\n"
    )
    assert [s.story_id for s in fragment.stories] == ["ST-001", "ST-002"]
    assert [(p.name, p.implements) for p in fragment.processes] == [
        ("TaskProcess", ["ST-001", "ST-002"])
    ]
    assert [s.name for s in fragment.schedules] == ["TaskCleanup"]
