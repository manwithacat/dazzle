"""Tests for surface section/field visible: role-based visibility (#487).

Validates that the parser reads `visible:` conditions on sections and fields,
stores them as ConditionExpr in the IR, and that the condition evaluator can
determine visibility at runtime.
"""

from pathlib import Path

import pytest

from dazzle.core import ir
from dazzle.core.dsl_parser_impl import parse_dsl


def _parse_surfaces(dsl_text: str) -> list[ir.SurfaceSpec]:
    """Parse DSL text and return surfaces from the fragment."""
    _, _, _, _, _, fragment = parse_dsl(dsl_text, Path("test.dsl"))
    return fragment.surfaces


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


class TestSectionVisibleParsing:
    """Section-level visible: conditions are parsed into IR."""

    def test_section_visible_role(self):
        surfaces = _parse_surfaces("""\
module test
app test_app "Test"

entity Employee "Employee":
    id: uuid pk
    name: str(200) required
    bank_sort_code: str(6)

surface employee_detail "Employee Detail":
    uses entity Employee
    mode: view
    section personal "Personal":
        field name "Name"
    section bank "Bank Details":
        visible: role(admin)
        field bank_sort_code "Sort Code"
""")
        surface = surfaces[0]
        assert surface.name == "employee_detail"

        personal = surface.sections[0]
        assert personal.name == "personal"
        assert personal.visible is None

        bank = surface.sections[1]
        assert bank.name == "bank"
        assert bank.visible is not None
        assert bank.visible.role_check is not None
        assert bank.visible.role_check.role_name == "admin"

    def test_section_visible_compound(self):
        surfaces = _parse_surfaces("""\
module test
app test_app "Test"

entity Employee "Employee":
    id: uuid pk
    name: str(200) required
    bank_sort_code: str(6)

surface employee_detail "Employee Detail":
    uses entity Employee
    mode: view
    section bank "Bank Details":
        visible: role(admin) or role(manager)
        field bank_sort_code "Sort Code"
""")
        bank = surfaces[0].sections[0]
        assert bank.visible is not None
        assert bank.visible.is_compound
        assert bank.visible.operator == ir.LogicalOperator.OR
        assert bank.visible.left.role_check.role_name == "admin"
        assert bank.visible.right.role_check.role_name == "manager"


class TestFieldVisibleParsing:
    """Field-level visible: conditions are parsed into IR."""

    def test_field_visible_role(self):
        surfaces = _parse_surfaces("""\
module test
app test_app "Test"

entity Employee "Employee":
    id: uuid pk
    name: str(200) required
    ni_number: str(9)

surface employee_detail "Employee Detail":
    uses entity Employee
    mode: view
    section main "Details":
        field name "Name"
        field ni_number "NI Number" visible: role(admin) or role(manager)
""")
        section = surfaces[0].sections[0]

        name_elem = section.elements[0]
        assert name_elem.field_name == "name"
        assert name_elem.visible is None

        ni_elem = section.elements[1]
        assert ni_elem.field_name == "ni_number"
        assert ni_elem.visible is not None
        assert ni_elem.visible.is_compound
        assert ni_elem.visible.left.role_check.role_name == "admin"

    def test_field_visible_with_when(self):
        """visible: and when: can coexist on the same field."""
        surfaces = _parse_surfaces("""\
module test
app test_app "Test"

entity Employee "Employee":
    id: uuid pk
    name: str(200) required
    ni_number: str(9)
    has_ni: bool = false

surface employee_detail "Employee Detail":
    uses entity Employee
    mode: view
    section main "Details":
        field ni_number "NI Number" visible: role(admin) when: has_ni == true
""")
        elem = surfaces[0].sections[0].elements[0]
        assert elem.field_name == "ni_number"
        assert elem.visible is not None
        assert elem.visible.role_check.role_name == "admin"
        assert elem.when_expr is not None


# ---------------------------------------------------------------------------
# Runtime evaluation tests
# ---------------------------------------------------------------------------


class TestVisibleConditionEvaluation:
    """ConditionExpr role checks are evaluated correctly for visibility."""

    @pytest.mark.parametrize(
        "cond_dict,ctx,expected",
        [
            (
                ir.ConditionExpr(role_check=ir.RoleCheck(role_name="admin")).model_dump(),
                {"user_roles": ["admin"]},
                True,
            ),
            (
                ir.ConditionExpr(role_check=ir.RoleCheck(role_name="admin")).model_dump(),
                {"user_roles": ["agent"]},
                False,
            ),
            (
                ir.ConditionExpr(
                    left=ir.ConditionExpr(role_check=ir.RoleCheck(role_name="admin")),
                    operator=ir.LogicalOperator.OR,
                    right=ir.ConditionExpr(role_check=ir.RoleCheck(role_name="manager")),
                ).model_dump(),
                {"user_roles": ["manager"]},
                True,
            ),
            (
                ir.ConditionExpr(
                    left=ir.ConditionExpr(role_check=ir.RoleCheck(role_name="admin")),
                    operator=ir.LogicalOperator.OR,
                    right=ir.ConditionExpr(role_check=ir.RoleCheck(role_name="manager")),
                ).model_dump(),
                {"user_roles": ["agent"]},
                False,
            ),
            ({}, {"user_roles": []}, True),
        ],
        ids=[
            "test_role_match_visible",
            "test_role_no_match_hidden",
            "test_compound_or_partial_match",
            "test_compound_or_no_match",
            "test_no_visible_condition_defaults_visible",
        ],
    )
    def test_evaluate_visible_condition(self, cond_dict: dict, ctx: dict, expected: bool) -> None:
        from dazzle.http.runtime.condition_evaluator import evaluate_condition

        assert evaluate_condition(cond_dict, {}, ctx) is expected


# ---------------------------------------------------------------------------
# Related tab visibility (#501)
# ---------------------------------------------------------------------------


class TestRelatedTabVisibility:
    """Section visible: conditions propagate to related tabs."""

    def test_tab_visible_condition_propagated(self):
        """Related tab picks up visible_condition from matching section."""
        from dazzle.render.context import RelatedTabContext

        tab = RelatedTabContext(
            tab_id="tab-sen-record",
            label="SEN Records",
            entity_name="SENRecord",
            api_endpoint="/sen-records",
            filter_field="student_profile",
            columns=[],
            visible_condition={"role_check": {"role_name": "admin"}},
        )
        assert tab.visible_condition is not None
        assert tab.visible is True  # default

    def test_tab_hidden_when_role_mismatch(self):
        """Tab with visible_condition is hidden for unauthorized roles."""
        from dazzle.http.runtime.condition_evaluator import evaluate_condition
        from dazzle.render.context import RelatedTabContext

        cond = {"role_check": {"role_name": "admin"}}
        tab = RelatedTabContext(
            tab_id="tab-sen-record",
            label="SEN Records",
            entity_name="SENRecord",
            api_endpoint="/sen-records",
            filter_field="student_profile",
            columns=[],
            visible_condition=cond,
        )

        # Simulate runtime evaluation (as page_routes.py does)
        role_ctx = {"user_roles": ["student"]}
        if tab.visible_condition:
            if not evaluate_condition(tab.visible_condition, {}, role_ctx):
                tab.visible = False

        assert tab.visible is False

    def test_tab_visible_when_role_matches(self):
        """Tab with visible_condition stays visible for authorized roles."""
        from dazzle.http.runtime.condition_evaluator import evaluate_condition
        from dazzle.render.context import RelatedTabContext

        cond = {"role_check": {"role_name": "admin"}}
        tab = RelatedTabContext(
            tab_id="tab-sen-record",
            label="SEN Records",
            entity_name="SENRecord",
            api_endpoint="/sen-records",
            filter_field="student_profile",
            columns=[],
            visible_condition=cond,
        )

        role_ctx = {"user_roles": ["admin"]}
        if tab.visible_condition:
            if not evaluate_condition(tab.visible_condition, {}, role_ctx):
                tab.visible = False

        assert tab.visible is True


# ---------------------------------------------------------------------------
# Action visible: (#1787) — parsed predicate evaluated against record + principal
# ---------------------------------------------------------------------------


def _action_predicate(text: str) -> ir.ConditionExpr:
    surfaces = _parse_surfaces(
        'module test\napp t "T"\n\n'
        'entity Req "Req":\n    id: uuid pk\n    status: str(20)\n\n'
        'surface req_detail "Req":\n    uses entity Req\n    mode: view\n'
        '    section main:\n        field status "Status"\n'
        '    action act "Act":\n'
        f"        visible: {text}\n"
        '        on click -> "/r/{id}" external\n'
    )
    predicate = surfaces[0].actions[0].visible
    assert predicate is not None
    return predicate


class TestActionVisibleEvaluation:
    """The same ConditionExpr grammar as field visible:, evaluated per record."""

    @pytest.mark.parametrize(
        ("text", "record", "ctx", "expected"),
        [
            pytest.param(
                "status = draft and (role(agent) or role(manager))",
                {"status": "draft"},
                {"user_roles": ["manager"]},
                True,
                id="state-and-role-hold",
            ),
            pytest.param(
                "status = draft and (role(agent) or role(manager))",
                {"status": "sent"},
                {"user_roles": ["agent"]},
                False,
                id="state-fails",
            ),
            pytest.param(
                "status in [sent, partially_received] and role(agent)",
                {"status": "partially_received"},
                {"user_roles": ["client"]},
                False,
                id="role-fails",
            ),
            pytest.param(
                "not (status = closed)",
                {"status": "open"},
                {"user_roles": []},
                True,
                id="not-group-#1180",
            ),
            pytest.param(
                "assigned_agent = current_user.contact",
                {"assigned_agent": {"id": "c-1", "name": "Ann"}},
                {"current_user_entity": {"contact": "c-1"}},
                True,
                id="expanded-ref-compares-on-id",
            ),
            pytest.param(
                "client.status = active",
                {"client": {"id": "k-1", "status": "active"}},
                {},
                True,
                id="fk-path-through-expanded-ref",
            ),
            pytest.param(
                "nino_verified_at is null",
                {"nino_verified_at": None},
                {},
                True,
                id="is-null",
            ),
        ],
    )
    def test_action_predicate(self, text: str, record: dict, ctx: dict, expected: bool) -> None:
        from dazzle.core.condition_eval import evaluate_condition

        predicate = _action_predicate(text)
        assert evaluate_condition(predicate.model_dump(), record, ctx) is expected

    @pytest.mark.parametrize(
        "text",
        [
            "status = draft and (role(agent) or role(manager))",
            "status in [sent, partially_received] and role(agent)",
            "not (status = closed) or role(admin)",
            'has_grant("acting_hod", department)',
        ],
    )
    def test_predicate_text_round_trips(self, text: str) -> None:
        """Refusals and validator errors quote the predicate as written."""
        from dazzle.core.condition_eval import condition_to_dsl

        assert condition_to_dsl(_action_predicate(text)) == text
