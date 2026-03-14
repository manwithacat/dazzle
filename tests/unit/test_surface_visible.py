"""Tests for surface section/field visible: role-based visibility (#487).

Validates that the parser reads `visible:` conditions on sections and fields,
stores them as ConditionExpr in the IR, and that the condition evaluator can
determine visibility at runtime.
"""

from __future__ import annotations

from pathlib import Path

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

    def test_role_match_visible(self):
        from dazzle_back.runtime.condition_evaluator import evaluate_condition

        cond = ir.ConditionExpr(role_check=ir.RoleCheck(role_name="admin"))
        ctx = {"user_roles": ["admin"]}
        assert evaluate_condition(cond.model_dump(), {}, ctx) is True

    def test_role_no_match_hidden(self):
        from dazzle_back.runtime.condition_evaluator import evaluate_condition

        cond = ir.ConditionExpr(role_check=ir.RoleCheck(role_name="admin"))
        ctx = {"user_roles": ["agent"]}
        assert evaluate_condition(cond.model_dump(), {}, ctx) is False

    def test_compound_or_partial_match(self):
        from dazzle_back.runtime.condition_evaluator import evaluate_condition

        cond = ir.ConditionExpr(
            left=ir.ConditionExpr(role_check=ir.RoleCheck(role_name="admin")),
            operator=ir.LogicalOperator.OR,
            right=ir.ConditionExpr(role_check=ir.RoleCheck(role_name="manager")),
        )
        ctx = {"user_roles": ["manager"]}
        assert evaluate_condition(cond.model_dump(), {}, ctx) is True

    def test_compound_or_no_match(self):
        from dazzle_back.runtime.condition_evaluator import evaluate_condition

        cond = ir.ConditionExpr(
            left=ir.ConditionExpr(role_check=ir.RoleCheck(role_name="admin")),
            operator=ir.LogicalOperator.OR,
            right=ir.ConditionExpr(role_check=ir.RoleCheck(role_name="manager")),
        )
        ctx = {"user_roles": ["agent"]}
        assert evaluate_condition(cond.model_dump(), {}, ctx) is False

    def test_no_visible_condition_defaults_visible(self):
        """When visible is None, the field should remain visible."""
        from dazzle_back.runtime.condition_evaluator import evaluate_condition

        # Empty condition evaluates to True
        assert evaluate_condition({}, {}, {"user_roles": []}) is True
