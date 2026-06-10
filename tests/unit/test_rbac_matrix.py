"""Tests for the static access matrix generator (Layer 1 RBAC)."""

from dazzle.core.ir.appspec import AppSpec
from dazzle.core.ir.conditions import (
    Comparison,
    ComparisonOperator,
    ConditionExpr,
    ConditionValue,
    GrantCheck,
    RoleCheck,
)
from dazzle.core.ir.domain import (
    AccessSpec,
    DomainSpec,
    EntitySpec,
    PermissionKind,
    PermissionRule,
    PolicyEffect,
    ScopeRule,
)
from dazzle.core.ir.fields import FieldSpec, FieldType, FieldTypeKind
from dazzle.core.ir.personas import PersonaSpec
from dazzle.rbac.matrix import (
    PolicyDecision,
    generate_access_matrix,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_field(name: str = "id") -> FieldSpec:
    return FieldSpec(name=name, type=FieldType(kind=FieldTypeKind.UUID))


def _make_entity(
    name: str,
    access: AccessSpec | None = None,
    fields: list[FieldSpec] | None = None,
) -> EntitySpec:
    return EntitySpec(
        name=name,
        fields=fields or [_make_field()],
        access=access,
    )


def _make_persona(pid: str, label: str = "") -> PersonaSpec:
    return PersonaSpec(id=pid, label=label or pid)


def _make_appspec(
    entities: list[EntitySpec],
    personas: list[PersonaSpec] | None = None,
) -> AppSpec:
    return AppSpec(
        name="test_app",
        domain=DomainSpec(entities=entities),
        personas=personas or [],
    )


def _permit_rule(
    operation: PermissionKind,
    personas: list[str] | None = None,
    condition: ConditionExpr | None = None,
) -> PermissionRule:
    return PermissionRule(
        operation=operation,
        effect=PolicyEffect.PERMIT,
        personas=personas or [],
        condition=condition,
    )


def _forbid_rule(
    operation: PermissionKind,
    personas: list[str] | None = None,
    condition: ConditionExpr | None = None,
) -> PermissionRule:
    return PermissionRule(
        operation=operation,
        effect=PolicyEffect.FORBID,
        personas=personas or [],
        condition=condition,
    )


def _role_cond(role_name: str) -> ConditionExpr:
    """Build a pure role-check condition."""
    return ConditionExpr(role_check=RoleCheck(role_name=role_name))


def _field_cond(field: str = "owner_id") -> ConditionExpr:
    """Build a simple field comparison condition."""
    return ConditionExpr(
        comparison=Comparison(
            field=field,
            operator=ComparisonOperator.EQUALS,
            value=ConditionValue(literal="current_user"),
        )
    )


def _grant_cond(relation: str = "viewer", scope_field: str = "department") -> ConditionExpr:
    """Build a grant-check condition (runtime row filter)."""
    return ConditionExpr(grant_check=GrantCheck(relation=relation, scope_field=scope_field))


# ---------------------------------------------------------------------------
# Test: no access rules → PERMIT_UNPROTECTED
# ---------------------------------------------------------------------------


def test_unprotected_entity_combined() -> None:
    """Combined PERMIT_UNPROTECTED contract:
    - access=None on every operation → PERMIT_UNPROTECTED.
    - emits an unprotected_entity warning.
    - access=AccessSpec(permissions=[]) is also treated as unprotected.
    """
    # access=None on every op.
    entity = _make_entity("Task", access=None)
    appspec = _make_appspec([entity], [_make_persona("admin")])
    matrix = generate_access_matrix(appspec)
    for op in ["list", "read", "create", "update", "delete"]:
        assert matrix.get("admin", "Task", op) == PolicyDecision.PERMIT_UNPROTECTED
    assert "unprotected_entity" in [w.kind for w in matrix.warnings]

    # Empty permissions list also unprotected.
    entity_empty = _make_entity("Task", access=AccessSpec(permissions=[]))
    appspec2 = _make_appspec([entity_empty], [_make_persona("admin")])
    assert (
        generate_access_matrix(appspec2).get("admin", "Task", "read")
        == PolicyDecision.PERMIT_UNPROTECTED
    )


# ---------------------------------------------------------------------------
# Test: pure role gate
# ---------------------------------------------------------------------------


def test_pure_role_gate_combined() -> None:
    """Combined pure role gate contract:
    - PERMIT for matching role; DENY for non-matching.
    - Empty personas list matches all roles.
    - No rule for operation → DENY.
    """
    # PERMIT/DENY by persona membership.
    access = AccessSpec(permissions=[_permit_rule(PermissionKind.READ, personas=["admin"])])
    entity = _make_entity("Task", access=access)
    appspec = _make_appspec([entity], [_make_persona("admin"), _make_persona("guest")])
    matrix = generate_access_matrix(appspec)
    assert matrix.get("admin", "Task", "read") == PolicyDecision.PERMIT
    assert matrix.get("guest", "Task", "read") == PolicyDecision.DENY
    # Operation with no rule → DENY.
    assert matrix.get("admin", "Task", "delete") == PolicyDecision.DENY

    # Empty personas list applies to all roles.
    access_open = AccessSpec(permissions=[_permit_rule(PermissionKind.LIST, personas=[])])
    appspec_open = _make_appspec(
        [_make_entity("Task", access=access_open)],
        [_make_persona("admin"), _make_persona("guest")],
    )
    matrix_open = generate_access_matrix(appspec_open)
    assert matrix_open.get("admin", "Task", "list") == PolicyDecision.PERMIT
    assert matrix_open.get("guest", "Task", "list") == PolicyDecision.PERMIT


# ---------------------------------------------------------------------------
# Test: role-check condition → still PERMIT (not filtered)
# ---------------------------------------------------------------------------


class TestRoleCheckCondition:
    def test_role_check_condition_gives_permit(self) -> None:
        """A permit rule whose condition is a pure role_check is PERMIT, not PERMIT_FILTERED."""
        cond = _role_cond("admin")
        access = AccessSpec(
            permissions=[
                _permit_rule(PermissionKind.READ, condition=cond),
            ]
        )
        entity = _make_entity("Task", access=access)
        appspec = _make_appspec([entity], [_make_persona("admin"), _make_persona("guest")])
        matrix = generate_access_matrix(appspec)

        assert matrix.get("admin", "Task", "read") == PolicyDecision.PERMIT
        assert matrix.get("guest", "Task", "read") == PolicyDecision.DENY


# ---------------------------------------------------------------------------
# Test: field condition → PERMIT_FILTERED
# ---------------------------------------------------------------------------


def test_field_condition_gives_permit_filtered_combined() -> None:
    """Both field comparisons and grant_check conditions resolve to PERMIT_FILTERED."""
    # Field comparison condition.
    field_access = AccessSpec(
        permissions=[
            _permit_rule(PermissionKind.READ, personas=["user"], condition=_field_cond("owner_id"))
        ]
    )
    appspec1 = _make_appspec([_make_entity("Task", access=field_access)], [_make_persona("user")])
    assert (
        generate_access_matrix(appspec1).get("user", "Task", "read")
        == PolicyDecision.PERMIT_FILTERED
    )

    # grant_check condition.
    grant_access = AccessSpec(
        permissions=[_permit_rule(PermissionKind.LIST, personas=["staff"], condition=_grant_cond())]
    )
    appspec2 = _make_appspec([_make_entity("Doc", access=grant_access)], [_make_persona("staff")])
    assert (
        generate_access_matrix(appspec2).get("staff", "Doc", "list")
        == PolicyDecision.PERMIT_FILTERED
    )


# ---------------------------------------------------------------------------
# Test: FORBID override
# ---------------------------------------------------------------------------


def test_forbid_override_combined() -> None:
    """Combined FORBID-override contract:
    - FORBID beats PERMIT for the same role.
    - FORBID with empty personas (wildcard) overrides PERMIT for any role.
    - FORBID for one role does not affect other permitted roles.
    """
    # 1) Same-role FORBID beats PERMIT.
    a1 = AccessSpec(
        permissions=[
            _permit_rule(PermissionKind.DELETE, personas=["admin"]),
            _forbid_rule(PermissionKind.DELETE, personas=["admin"]),
        ]
    )
    m1 = generate_access_matrix(
        _make_appspec([_make_entity("Task", access=a1)], [_make_persona("admin")])
    )
    assert m1.get("admin", "Task", "delete") == PolicyDecision.DENY

    # 2) Wildcard FORBID overrides all permits.
    a2 = AccessSpec(
        permissions=[
            _permit_rule(PermissionKind.DELETE, personas=["admin"]),
            _forbid_rule(PermissionKind.DELETE, personas=[]),
        ]
    )
    m2 = generate_access_matrix(
        _make_appspec(
            [_make_entity("Task", access=a2)], [_make_persona("admin"), _make_persona("guest")]
        )
    )
    assert m2.get("admin", "Task", "delete") == PolicyDecision.DENY
    assert m2.get("guest", "Task", "delete") == PolicyDecision.DENY

    # 3) Forbidding one role doesn't affect others.
    a3 = AccessSpec(
        permissions=[
            _permit_rule(PermissionKind.READ, personas=["admin"]),
            _permit_rule(PermissionKind.READ, personas=["editor"]),
            _forbid_rule(PermissionKind.READ, personas=["editor"]),
        ]
    )
    m3 = generate_access_matrix(
        _make_appspec(
            [_make_entity("Task", access=a3)], [_make_persona("admin"), _make_persona("editor")]
        )
    )
    assert m3.get("admin", "Task", "read") == PolicyDecision.PERMIT
    assert m3.get("editor", "Task", "read") == PolicyDecision.DENY


def test_deny_all_rule_denies_every_role() -> None:
    """`permit: <op>: false` (deny_all) must DENY for every role — no role may "match" a
    deny_all rule. Pins matrix._rule_matches_role's deny_all guard (a mutation-audit
    survivor where flipping the guard to True would invert the explicit denial into a
    permit, since the rule's effect is PERMIT)."""
    from dazzle.core.ir.domain import PermissionRule, PolicyEffect

    access = AccessSpec(
        permissions=[
            PermissionRule(
                operation=PermissionKind.UPDATE,
                effect=PolicyEffect.PERMIT,
                personas=[],
                condition=None,
                deny_all=True,
            ),
        ]
    )
    matrix = generate_access_matrix(
        _make_appspec(
            [_make_entity("Task", access=access)],
            [_make_persona("admin"), _make_persona("guest")],
        )
    )
    assert matrix.get("admin", "Task", "update") == PolicyDecision.DENY
    assert matrix.get("guest", "Task", "update") == PolicyDecision.DENY


def test_compound_role_gate_matches_either_branch() -> None:
    """A pure-role gate `role(admin) or role(editor)` (empty personas) must PERMIT BOTH
    admin and editor. Pins _condition_matches_role's recursive OR (a mutation-audit
    survivor where or→and would demand a single role be in BOTH branches — impossible for
    distinct roles, silently denying everyone the gate should admit)."""
    from dazzle.core.ir.conditions import LogicalOperator

    cond = ConditionExpr(
        left=_role_cond("admin"),
        operator=LogicalOperator.OR,
        right=_role_cond("editor"),
    )
    access = AccessSpec(
        permissions=[_permit_rule(PermissionKind.READ, personas=[], condition=cond)]
    )
    matrix = generate_access_matrix(
        _make_appspec(
            [_make_entity("Task", access=access)],
            [_make_persona("admin"), _make_persona("editor"), _make_persona("guest")],
        )
    )
    assert matrix.get("admin", "Task", "read") == PolicyDecision.PERMIT
    assert matrix.get("editor", "Task", "read") == PolicyDecision.PERMIT
    assert matrix.get("guest", "Task", "read") == PolicyDecision.DENY


# ---------------------------------------------------------------------------
# Test: mixed OR condition (role + field)
# ---------------------------------------------------------------------------


class TestMixedOrCondition:
    def test_or_role_and_field_is_permit_filtered(self) -> None:
        """OR of role_check and field comparison should be PERMIT_FILTERED."""
        from dazzle.core.ir.conditions import LogicalOperator

        cond = ConditionExpr(
            left=_role_cond("admin"),
            operator=LogicalOperator.OR,
            right=_field_cond("owner_id"),
        )
        access = AccessSpec(
            permissions=[
                _permit_rule(PermissionKind.UPDATE, personas=[], condition=cond),
            ]
        )
        entity = _make_entity("Task", access=access)
        appspec = _make_appspec([entity], [_make_persona("admin"), _make_persona("user")])
        matrix = generate_access_matrix(appspec)

        assert matrix.get("admin", "Task", "update") == PolicyDecision.PERMIT_FILTERED
        assert matrix.get("user", "Task", "update") == PolicyDecision.PERMIT_FILTERED


# ---------------------------------------------------------------------------
# Test: multiple entities / operations
# ---------------------------------------------------------------------------


class TestMultiEntityMatrix:
    def test_unrelated_entities_independent(self) -> None:
        task_access = AccessSpec(
            permissions=[_permit_rule(PermissionKind.READ, personas=["admin"])]
        )
        note_entity = _make_entity("Note", access=None)
        task_entity = _make_entity("Task", access=task_access)
        appspec = _make_appspec([task_entity, note_entity], [_make_persona("admin")])
        matrix = generate_access_matrix(appspec)

        assert matrix.get("admin", "Task", "read") == PolicyDecision.PERMIT
        assert matrix.get("admin", "Task", "delete") == PolicyDecision.DENY
        assert matrix.get("admin", "Note", "read") == PolicyDecision.PERMIT_UNPROTECTED


# ---------------------------------------------------------------------------
# Test: matrix.get() default
# ---------------------------------------------------------------------------


class TestMatrixGet:
    def test_get_unknown_triple_returns_deny(self) -> None:
        appspec = _make_appspec([], [])
        matrix = generate_access_matrix(appspec)

        assert matrix.get("ghost", "Missing", "list") == PolicyDecision.DENY


# ---------------------------------------------------------------------------
# Test: to_table()
# ---------------------------------------------------------------------------


def test_matrix_serialization_combined() -> None:
    """Combined to_table / to_json / to_csv contract on a single
    minimal Task+admin matrix (5 ops × 1 entity) plus the empty-matrix
    placeholder for to_table."""
    access = AccessSpec(permissions=[_permit_rule(PermissionKind.READ, personas=["admin"])])
    entity = _make_entity("Task", access=access)
    appspec = _make_appspec([entity], [_make_persona("admin")])
    matrix = generate_access_matrix(appspec)

    # to_table — contains roles, entities, decisions.
    table = matrix.to_table()
    for token in ("admin", "Task", "PERMIT", "DENY"):
        assert token in table

    # to_table empty placeholder.
    empty_table = generate_access_matrix(_make_appspec([], [])).to_table()
    assert "empty" in empty_table.lower()

    # to_json — structure + populated roles/entities + per-cell keys.
    data = matrix.to_json()
    for k in ("roles", "entities", "operations", "cells", "warnings"):
        assert k in data
    assert "admin" in data["roles"]
    assert "Task" in data["entities"]
    for cell in data["cells"]:
        for k in ("role", "entity", "operation", "decision"):
            assert k in cell

    # to_csv — header row + 5 ops × 1 entity = 6 lines.
    lines = matrix.to_csv().strip().splitlines()
    assert lines[0].startswith("entity,operation")
    assert "admin" in lines[0]
    assert len(lines) == 6


# ---------------------------------------------------------------------------
# Test: warnings
# ---------------------------------------------------------------------------


def test_warnings_combined() -> None:
    """Combined warnings contract:
    - Redundant FORBID (no matching PERMIT) emits redundant_forbid.
    - Persona never referenced emits orphan_role.
    - When all personas are used, no orphan_role warning.
    """
    # Redundant FORBID.
    a1 = AccessSpec(permissions=[_forbid_rule(PermissionKind.DELETE, personas=["guest"])])
    m1 = generate_access_matrix(
        _make_appspec(
            [_make_entity("Task", access=a1)], [_make_persona("admin"), _make_persona("guest")]
        )
    )
    assert "redundant_forbid" in [w.kind for w in m1.warnings]

    # Orphan role.
    a2 = AccessSpec(permissions=[_permit_rule(PermissionKind.READ, personas=["admin"])])
    m2 = generate_access_matrix(
        _make_appspec(
            [_make_entity("Task", access=a2)], [_make_persona("admin"), _make_persona("orphan")]
        )
    )
    assert any(w.role == "orphan" for w in m2.warnings if w.kind == "orphan_role")

    # No orphan when all roles used.
    a3 = AccessSpec(permissions=[_permit_rule(PermissionKind.READ, personas=["admin", "editor"])])
    m3 = generate_access_matrix(
        _make_appspec(
            [_make_entity("Task", access=a3)], [_make_persona("admin"), _make_persona("editor")]
        )
    )
    assert not [w for w in m3.warnings if w.kind == "orphan_role"]


# ---------------------------------------------------------------------------
# Test: scope rules → PERMIT, PERMIT_SCOPED, PERMIT_NO_SCOPE
# ---------------------------------------------------------------------------


def _scope_rule(
    operation: PermissionKind,
    personas: list[str],
    condition: ConditionExpr | None = None,
) -> ScopeRule:
    return ScopeRule(operation=operation, personas=personas, condition=condition)


def test_scope_rules_combined() -> None:
    """Combined scope-rule decision contract:
    - PERMIT + scope rule with condition=None ('scope: all') → PERMIT.
    - PERMIT + scope rule with field condition → PERMIT_SCOPED.
    - PERMIT + no matching scope rule → PERMIT_NO_SCOPE + no_scope_rule warning
      with correct entity/role/operation.
    - DENY for non-permitted roles is unchanged by scope rules.
    - personas=['*'] in scope matches any permitted role → PERMIT_SCOPED.
    - Legacy entity (no scopes block) with field condition still → PERMIT_FILTERED.
    """
    # 1) scope: all (condition=None) → PERMIT.
    a1 = AccessSpec(
        permissions=[_permit_rule(PermissionKind.READ, personas=["admin"])],
        scopes=[_scope_rule(PermissionKind.READ, personas=["admin"], condition=None)],
    )
    m1 = generate_access_matrix(
        _make_appspec([_make_entity("Task", access=a1)], [_make_persona("admin")])
    )
    assert m1.get("admin", "Task", "read") == PolicyDecision.PERMIT

    # 2) scope with field condition → PERMIT_SCOPED.
    a2 = AccessSpec(
        permissions=[_permit_rule(PermissionKind.READ, personas=["user"])],
        scopes=[
            _scope_rule(PermissionKind.READ, personas=["user"], condition=_field_cond("owner_id"))
        ],
    )
    m2 = generate_access_matrix(
        _make_appspec([_make_entity("Task", access=a2)], [_make_persona("user")])
    )
    assert m2.get("user", "Task", "read") == PolicyDecision.PERMIT_SCOPED

    # 3) PERMIT but no matching scope → PERMIT_NO_SCOPE + warning with correct fields.
    a3 = AccessSpec(
        permissions=[_permit_rule(PermissionKind.LIST, personas=["admin"])],
        scopes=[_scope_rule(PermissionKind.LIST, personas=["editor"], condition=None)],
    )
    m3 = generate_access_matrix(
        _make_appspec([_make_entity("Task", access=a3)], [_make_persona("admin")])
    )
    assert m3.get("admin", "Task", "list") == PolicyDecision.PERMIT_NO_SCOPE
    no_scope = [w for w in m3.warnings if w.kind == "no_scope_rule"]
    assert any(w.entity == "Task" and w.role == "admin" and w.operation == "list" for w in no_scope)

    # 4) Non-permitted role stays DENY despite scope rules.
    a4 = AccessSpec(
        permissions=[_permit_rule(PermissionKind.READ, personas=["admin"])],
        scopes=[_scope_rule(PermissionKind.READ, personas=["*"], condition=None)],
    )
    m4 = generate_access_matrix(
        _make_appspec(
            [_make_entity("Task", access=a4)], [_make_persona("admin"), _make_persona("guest")]
        )
    )
    assert m4.get("guest", "Task", "read") == PolicyDecision.DENY

    # 5) personas=['*'] in scope matches any permitted role.
    a5 = AccessSpec(
        permissions=[
            _permit_rule(PermissionKind.READ, personas=["admin"]),
            _permit_rule(PermissionKind.READ, personas=["editor"]),
        ],
        scopes=[
            _scope_rule(PermissionKind.READ, personas=["*"], condition=_field_cond("owner_id"))
        ],
    )
    m5 = generate_access_matrix(
        _make_appspec(
            [_make_entity("Task", access=a5)], [_make_persona("admin"), _make_persona("editor")]
        )
    )
    assert m5.get("admin", "Task", "read") == PolicyDecision.PERMIT_SCOPED
    assert m5.get("editor", "Task", "read") == PolicyDecision.PERMIT_SCOPED

    # 6) Legacy entity with no scopes block still resolves field condition → PERMIT_FILTERED.
    a6 = AccessSpec(
        permissions=[
            _permit_rule(PermissionKind.READ, personas=["user"], condition=_field_cond("owner_id"))
        ],
    )
    m6 = generate_access_matrix(
        _make_appspec([_make_entity("Task", access=a6)], [_make_persona("user")])
    )
    assert m6.get("user", "Task", "read") == PolicyDecision.PERMIT_FILTERED


def test_list_scope_falls_back_for_read_op() -> None:
    """#1071: `list:` scope rule implicitly covers `read:` when no explicit
    `read:` rule exists. The dominant DSL pattern across all Dazzle apps
    declares only `list:` and relies on this fallback. Without it, every
    app produces `PERMIT_NO_SCOPE` on `read` ops despite working `list:`.

    Cases:
    - permit on list+read, scope on list only → list passes (PERMIT),
      read falls back to list's scope (PERMIT).
    - permit on read only, scope with field cond on list → read inherits
      filtered scope (PERMIT_SCOPED).
    - Explicit `read:` scope wins over fallback.
    - Fallback does NOT apply to create/update/delete (still PERMIT_NO_SCOPE).
    """
    # Case A: list: all + read inherits list: all → both PERMIT.
    a = AccessSpec(
        permissions=[
            _permit_rule(PermissionKind.LIST, personas=["admin"]),
            _permit_rule(PermissionKind.READ, personas=["admin"]),
        ],
        scopes=[_scope_rule(PermissionKind.LIST, personas=["admin"], condition=None)],
    )
    m = generate_access_matrix(
        _make_appspec([_make_entity("Task", access=a)], [_make_persona("admin")])
    )
    assert m.get("admin", "Task", "list") == PolicyDecision.PERMIT
    assert m.get("admin", "Task", "read") == PolicyDecision.PERMIT

    # Case B: list:'all where owner=user' covers read too → PERMIT_SCOPED for both.
    b = AccessSpec(
        permissions=[
            _permit_rule(PermissionKind.LIST, personas=["user"]),
            _permit_rule(PermissionKind.READ, personas=["user"]),
        ],
        scopes=[
            _scope_rule(PermissionKind.LIST, personas=["user"], condition=_field_cond("owner_id"))
        ],
    )
    m = generate_access_matrix(
        _make_appspec([_make_entity("Task", access=b)], [_make_persona("user")])
    )
    assert m.get("user", "Task", "list") == PolicyDecision.PERMIT_SCOPED
    assert m.get("user", "Task", "read") == PolicyDecision.PERMIT_SCOPED

    # Case C: explicit read: rule wins over the list: fallback.
    c = AccessSpec(
        permissions=[
            _permit_rule(PermissionKind.LIST, personas=["admin"]),
            _permit_rule(PermissionKind.READ, personas=["admin"]),
        ],
        scopes=[
            _scope_rule(PermissionKind.LIST, personas=["admin"], condition=_field_cond("owner_id")),
            _scope_rule(PermissionKind.READ, personas=["admin"], condition=None),
        ],
    )
    m = generate_access_matrix(
        _make_appspec([_make_entity("Task", access=c)], [_make_persona("admin")])
    )
    # Explicit read: with condition=None should win → PERMIT (not PERMIT_SCOPED).
    assert m.get("admin", "Task", "read") == PolicyDecision.PERMIT

    # Case D: fallback does NOT apply to mutating ops (create/update/delete).
    # permit on update but only list: scope → still PERMIT_NO_SCOPE.
    d = AccessSpec(
        permissions=[
            _permit_rule(PermissionKind.UPDATE, personas=["admin"]),
            _permit_rule(PermissionKind.DELETE, personas=["admin"]),
            _permit_rule(PermissionKind.CREATE, personas=["admin"]),
        ],
        scopes=[_scope_rule(PermissionKind.LIST, personas=["admin"], condition=None)],
    )
    m = generate_access_matrix(
        _make_appspec([_make_entity("Task", access=d)], [_make_persona("admin")])
    )
    assert m.get("admin", "Task", "update") == PolicyDecision.PERMIT_NO_SCOPE
    assert m.get("admin", "Task", "delete") == PolicyDecision.PERMIT_NO_SCOPE
    assert m.get("admin", "Task", "create") == PolicyDecision.PERMIT_NO_SCOPE


# ---------------------------------------------------------------------------
# #1123 — `no_scope_rule` lint message differentiated per operation.
# Pre-v0.71.19 the same "will see 0 records" message fired for every
# op, which was misleading for create/update/delete (no row is "seen"
# on write ops; the request is rejected). The message now matches each
# op's actual runtime behaviour.
# ---------------------------------------------------------------------------


def test_no_scope_rule_message_list_says_will_see_zero_records() -> None:
    """List operations: scope rejection yields an empty result set,
    so the original "will see 0 records" message is accurate. Note:
    we exercise list (not read) — the matrix has a READ→LIST scope
    fallback (matrix.py:222) that masks the test condition for read."""
    access = AccessSpec(
        permissions=[_permit_rule(PermissionKind.LIST, personas=["admin"])],
        # Scope rule for `editor` only — admin has no matching scope.
        scopes=[_scope_rule(PermissionKind.LIST, personas=["editor"], condition=None)],
    )
    matrix = generate_access_matrix(
        _make_appspec([_make_entity("Task", access=access)], [_make_persona("admin")])
    )
    w = next(
        x
        for x in matrix.warnings
        if x.kind == "no_scope_rule" and x.entity == "Task" and x.operation == "list"
    )
    assert "will see 0 records" in w.message


def test_no_scope_rule_message_update_describes_404() -> None:
    """Update operations: scope rejection yields a 404 at request
    time. Message must mention the 404 outcome + the fix."""
    access = AccessSpec(
        permissions=[_permit_rule(PermissionKind.UPDATE, personas=["admin"])],
        scopes=[_scope_rule(PermissionKind.LIST, personas=["admin"], condition=None)],
    )
    matrix = generate_access_matrix(
        _make_appspec([_make_entity("Task", access=access)], [_make_persona("admin")])
    )
    w = next(
        x
        for x in matrix.warnings
        if x.kind == "no_scope_rule" and x.entity == "Task" and x.operation == "update"
    )
    assert "404" in w.message
    assert "scope: update:" in w.message


def test_no_scope_rule_message_delete_describes_404() -> None:
    access = AccessSpec(
        permissions=[_permit_rule(PermissionKind.DELETE, personas=["admin"])],
        scopes=[_scope_rule(PermissionKind.LIST, personas=["admin"], condition=None)],
    )
    matrix = generate_access_matrix(
        _make_appspec([_make_entity("Task", access=access)], [_make_persona("admin")])
    )
    w = next(
        x
        for x in matrix.warnings
        if x.kind == "no_scope_rule" and x.entity == "Task" and x.operation == "delete"
    )
    assert "404" in w.message
    assert "scope: delete:" in w.message


def test_no_scope_rule_message_create_says_will_403() -> None:
    """Create operations: scope rules now enforce at runtime as of
    v0.71.22 (#1124). The message must say so — pre-v0.71.22 message
    said "not yet enforced" which is no longer accurate."""
    access = AccessSpec(
        permissions=[_permit_rule(PermissionKind.CREATE, personas=["admin"])],
        scopes=[_scope_rule(PermissionKind.LIST, personas=["admin"], condition=None)],
    )
    matrix = generate_access_matrix(
        _make_appspec([_make_entity("Task", access=access)], [_make_persona("admin")])
    )
    w = next(
        x
        for x in matrix.warnings
        if x.kind == "no_scope_rule" and x.entity == "Task" and x.operation == "create"
    )
    assert "403" in w.message
    # No longer says "not yet enforced" — that was the pre-v0.71.22 message.
    assert "not yet enforced" not in w.message


# ---------------------------------------------------------------------------
# #1313 (ADR-0029): atomic-flow projection — visible in the matrix as a
# distinct grant path, NOT folded into the per-(role,entity,op) CRUD cells.
# ---------------------------------------------------------------------------


def _atomic_flow():
    from dazzle.core import ir

    return ir.AtomicFlowSpec(
        name="enrol",
        label="Enrol Student",
        permit_execute=["teacher", "admin"],
        inputs=[],
        steps=[
            ir.FlowCreate(entity="Enrolment", assignments={}),
            ir.FlowUpdate(
                entity="Enrolment",
                target=ir.FlowFieldValue(kind=ir.FlowFieldValueKind.INPUT_REF, input_name="x"),
                assignments={},
            ),
        ],
    )


def test_atomic_flow_projected_separately() -> None:
    appspec = AppSpec(
        name="t",
        domain=DomainSpec(entities=[_make_entity("Enrolment", access=None)]),
        personas=[_make_persona("teacher"), _make_persona("admin")],
        atomic_flows=[_atomic_flow()],
    )
    m = generate_access_matrix(appspec)
    assert len(m.atomic_flows) == 1
    proj = m.atomic_flows[0]
    assert proj.name == "enrol"
    assert proj.roles == ("teacher", "admin")
    # FlowCreate → create, FlowUpdate → update, in declaration order.
    assert proj.steps == (("Enrolment", "create"), ("Enrolment", "update"))
    # Surfaced in JSON + table…
    j = m.to_json()
    assert j["atomic_flows"][0]["name"] == "enrol"
    assert j["atomic_flows"][0]["steps"] == [
        {"entity": "Enrolment", "operation": "create"},
        {"entity": "Enrolment", "operation": "update"},
    ]
    assert "Atomic flows" in m.to_table()


def test_atomic_projection_does_not_pollute_crud_cells() -> None:
    """The flow's (entity, op) does NOT become a CRUD cell — the unprotected
    entity's cells are unchanged, so the conformance verifier is unaffected."""
    appspec = AppSpec(
        name="t",
        domain=DomainSpec(entities=[_make_entity("Enrolment", access=None)]),
        personas=[_make_persona("teacher")],
        atomic_flows=[_atomic_flow()],
    )
    m = generate_access_matrix(appspec)
    # The CRUD cell reflects the entity's own (absent) rules, not the flow.
    assert m.get("teacher", "Enrolment", "create") == PolicyDecision.PERMIT_UNPROTECTED


def test_no_atomic_flows_empty_projection() -> None:
    appspec = _make_appspec([_make_entity("Task", access=None)], [_make_persona("admin")])
    m = generate_access_matrix(appspec)
    assert m.atomic_flows == []
    assert m.to_json()["atomic_flows"] == []


def _atomic_flow_with_invariant():
    """A flow carrying a `sum(Posting.amount where ...) = 0` invariant (#1318)."""
    from dazzle.core import ir

    return ir.AtomicFlowSpec(
        name="balanced_post",
        label="Balanced Posting",
        permit_execute=["accountant"],
        inputs=[],
        steps=[ir.FlowCreate(entity="Posting", assignments={})],
        invariants=[
            ir.FlowInvariant(
                agg_fn=ir.FlowAggregateFn.SUM,
                entity="Posting",
                field="amount",
                anchor_entity="Transaction",
                anchor_input="txn",
                op=ir.CompOp.EQ,
                rhs=ir.InvariantRhs(literal=0),
            )
        ],
    )


def test_atomic_flow_invariant_surfaced() -> None:
    """A flow's invariants render to stable human strings in the matrix (#1318)."""
    appspec = AppSpec(
        name="t",
        domain=DomainSpec(entities=[_make_entity("Posting", access=None)]),
        personas=[_make_persona("accountant")],
        atomic_flows=[_atomic_flow_with_invariant()],
    )
    m = generate_access_matrix(appspec)
    assert m.atomic_flows[0].invariants == ("sum(Posting.amount) = 0",)
    j = m.to_json()
    assert j["atomic_flows"][0]["invariants"] == ["sum(Posting.amount) = 0"]
    # Rendered in the table's Atomic flows section too.
    assert "sum(Posting.amount) = 0" in m.to_table()


def test_atomic_flow_invariant_anchor_rhs() -> None:
    """An anchor-field rhs renders as ``input.<input>.<field>`` (#1318)."""
    from dazzle.core import ir

    flow = ir.AtomicFlowSpec(
        name="capped",
        label="Capped",
        permit_execute=["mgr"],
        inputs=[],
        steps=[ir.FlowCreate(entity="LineItem", assignments={})],
        invariants=[
            ir.FlowInvariant(
                agg_fn=ir.FlowAggregateFn.COUNT,
                entity="LineItem",
                field=None,
                anchor_entity="Budget",
                anchor_input="budget",
                op=ir.CompOp.LTE,
                rhs=ir.InvariantRhs(anchor_input="budget", anchor_field="max_items"),
            )
        ],
    )
    appspec = AppSpec(
        name="t",
        domain=DomainSpec(entities=[_make_entity("LineItem", access=None)]),
        personas=[_make_persona("mgr")],
        atomic_flows=[flow],
    )
    m = generate_access_matrix(appspec)
    assert m.atomic_flows[0].invariants == ("count(LineItem) <= input.budget.max_items",)


def test_atomic_flow_without_invariant_empty_tuple() -> None:
    """A flow with no invariants serialises ``invariants: []`` (additive shape)."""
    appspec = AppSpec(
        name="t",
        domain=DomainSpec(entities=[_make_entity("Enrolment", access=None)]),
        personas=[_make_persona("teacher"), _make_persona("admin")],
        atomic_flows=[_atomic_flow()],
    )
    m = generate_access_matrix(appspec)
    assert m.atomic_flows[0].invariants == ()
    assert m.to_json()["atomic_flows"][0]["invariants"] == []


# ---------------------------------------------------------------------------
# Test: dead scope rules (#1352)
# ---------------------------------------------------------------------------


def _scope_rule(
    operation: PermissionKind,
    personas: list[str],
    condition: ConditionExpr | None = None,
) -> ScopeRule:
    return ScopeRule(operation=operation, condition=condition, personas=personas)


def test_unknown_scope_persona_warns() -> None:
    """A scope rule binding `as:` to an undeclared persona/role is flagged (#1352)."""
    access = AccessSpec(
        permissions=[
            _permit_rule(PermissionKind.LIST, condition=_role_cond("admin")),
        ],
        scopes=[
            _scope_rule(PermissionKind.LIST, ["admin"]),
            _scope_rule(PermissionKind.DELETE, ["accountant"]),  # typo'd persona
        ],
    )
    appspec = _make_appspec([_make_entity("Invoice", access)], [_make_persona("admin")])
    m = generate_access_matrix(appspec)
    unknown = [w for w in m.warnings if w.kind == "unknown_scope_persona"]
    assert len(unknown) == 1
    assert unknown[0].role == "accountant"
    assert unknown[0].operation == "delete"
    # The fully-unknown rule must NOT additionally fire scope_without_permit.
    assert not [w for w in m.warnings if w.kind == "scope_without_permit"]


def test_scope_without_permit_warns() -> None:
    """A scope rule whose personas never pass permit is unreachable (#1352)."""
    access = AccessSpec(
        permissions=[
            _permit_rule(PermissionKind.LIST, condition=_role_cond("admin")),
            _permit_rule(PermissionKind.DELETE, condition=_role_cond("admin")),
        ],
        scopes=[
            _scope_rule(PermissionKind.LIST, ["admin"]),
            _scope_rule(PermissionKind.DELETE, ["admin"]),
            # member never passes permit for delete → dead rule.
            _scope_rule(PermissionKind.DELETE, ["member"]),
        ],
    )
    appspec = _make_appspec(
        [_make_entity("Invoice", access)],
        [_make_persona("admin"), _make_persona("member")],
    )
    m = generate_access_matrix(appspec)
    dead = [w for w in m.warnings if w.kind == "scope_without_permit"]
    assert len(dead) == 1
    assert dead[0].operation == "delete"
    assert "member" in dead[0].role


def test_paired_scope_and_permit_no_new_warnings() -> None:
    """Properly paired permit/scope rules emit neither #1352 warning."""
    access = AccessSpec(
        permissions=[
            _permit_rule(PermissionKind.LIST, condition=_role_cond("member")),
        ],
        scopes=[_scope_rule(PermissionKind.LIST, ["member"], condition=_field_cond())],
    )
    appspec = _make_appspec([_make_entity("Task", access)], [_make_persona("member")])
    m = generate_access_matrix(appspec)
    kinds = {w.kind for w in m.warnings}
    assert "unknown_scope_persona" not in kinds
    assert "scope_without_permit" not in kinds


def test_list_scope_serving_read_permit_is_reachable() -> None:
    """A LIST scope rule also serves READ (fallback), so a read-only permit keeps it alive."""
    access = AccessSpec(
        permissions=[
            _permit_rule(PermissionKind.READ, condition=_role_cond("member")),
        ],
        scopes=[_scope_rule(PermissionKind.LIST, ["member"], condition=_field_cond())],
    )
    appspec = _make_appspec([_make_entity("Task", access)], [_make_persona("member")])
    m = generate_access_matrix(appspec)
    assert not [w for w in m.warnings if w.kind == "scope_without_permit"]


def test_wildcard_scope_persona_not_unknown() -> None:
    """`as: *` is a legal wildcard binding, never flagged as unknown."""
    access = AccessSpec(
        permissions=[
            _permit_rule(PermissionKind.LIST, condition=_role_cond("admin")),
        ],
        scopes=[_scope_rule(PermissionKind.LIST, ["*"])],
    )
    appspec = _make_appspec([_make_entity("Doc", access)], [_make_persona("admin")])
    m = generate_access_matrix(appspec)
    kinds = {w.kind for w in m.warnings}
    assert "unknown_scope_persona" not in kinds
    assert "scope_without_permit" not in kinds
