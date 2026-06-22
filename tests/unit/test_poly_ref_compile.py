"""#1448: PolyPathCheck compilation — app-layer (param) + RLS policy + degradation."""

from __future__ import annotations

import pytest

from dazzle.core.ir.fk_graph import FKGraph
from dazzle.core.ir.predicates import (
    CompOp,
    ExistsBinding,
    ExistsCheck,
    PolyPathCheck,
    UserAttrCheck,
)
from dazzle.http.runtime.predicate_compiler import (
    compile_predicate,
    compile_predicate_policy,
)


def _graph() -> FKGraph:
    graph = FKGraph()
    graph._edges = {"AIJob": [], "Cohort": [], "Membership": []}
    graph._fields = {
        "AIJob": {"id", "target_type", "target_id", "cost"},
        "Cohort": {"id", "uploaded_by"},
        "Membership": {"id", "cohort_id", "some_column"},
    }
    return graph


_TYPES = {("Cohort", "uploaded_by"): "uuid"}


def _types(entity: str, field: str) -> str:
    try:
        return _TYPES[(entity, field)]
    except KeyError:
        raise ValueError(f"no pg type for {entity}.{field}")


def _node(sub) -> PolyPathCheck:
    return PolyPathCheck(
        field="target",
        type_field="target_type",
        type_value="Cohort",
        id_field="target_id",
        target_entity="Cohort",
        sub=sub,
    )


def test_app_compile_poly_path_check():
    node = _node(UserAttrCheck(field="uploaded_by", op=CompOp.EQ, user_attr="entity_id"))
    sql, params = compile_predicate(node, "AIJob", _graph())
    assert '"target_type" = %s' in sql
    assert '"target_id" IN (SELECT "id" FROM' in sql
    assert '"uploaded_by"' in sql
    assert params[0] == "Cohort"
    # The sub's runtime marker (current_user) flows through after the type literal.
    assert len(params) == 2
    assert not isinstance(params[1], str)


def test_policy_compile_poly_path_check():
    node = _node(UserAttrCheck(field="uploaded_by", op=CompOp.EQ, user_attr="entity_id"))
    body = compile_predicate_policy(node, "AIJob", _graph(), entity_types=_types)
    assert "\"target_type\" = 'Cohort'" in body
    assert "current_setting(" in body  # GUC read for current_user
    assert "%s" not in body  # param-free


def test_policy_degrades_when_sub_not_expressible():
    # An ExistsCheck with an entity-column binding is not policy-expressible
    # (the compiler raises ValueError) → the poly wrapper must propagate that
    # so build_rls_scope_policy_ddl degrades the verb to the app layer (#1447).
    node = _node(
        ExistsCheck(
            target_entity="Membership",
            bindings=[ExistsBinding(junction_field="cohort_id", target="some_column")],
        )
    )
    with pytest.raises(ValueError):
        compile_predicate_policy(node, "AIJob", _graph(), entity_types=_types)
