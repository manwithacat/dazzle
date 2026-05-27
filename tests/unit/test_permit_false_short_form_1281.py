"""#1281 — `permit: <op>: false` short-form for append-only entities.

The pre-fix DSL required `permit: update: role(nobody)` to express
"this operation is forbidden for everyone." That relied on `nobody`
being an undeclared role that the runtime would never resolve — a
soft-deny that worked by accident and tripped the
`validate_role_references_against_enum` linter warning. #1281 adds a
first-class `permit: update: false` short-form that lowers to a
`PermissionRule(deny_all=True)`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir.domain import PermissionKind, PermissionRule, PolicyEffect


def _parse_audit_log(extra_block: str) -> object:
    """Parse a minimal DSL fragment carrying an `AuditLog` entity with
    the permit/forbid block in `extra_block`. Returns the parsed
    entity from the fragment."""
    source = (
        """\
module test_1281
app test "Test 1281"

entity AuditLog "Audit log":
  id: uuid pk
  actor_id: uuid required
  action: str(64) required
"""
        + extra_block
    )
    fragment = parse_dsl(source, Path("test_1281.dsl"))[-1]
    return next(e for e in fragment.entities if e.name == "AuditLog")


def test_permit_update_false_parses_to_deny_all() -> None:
    """`permit: update: false` is accepted and lowers to a
    PermissionRule with `deny_all=True`, `effect=PERMIT`, `condition=None`."""
    entity = _parse_audit_log(
        """\
  permit:
    create: authenticated
    read: authenticated
    update: false
    delete: false
"""
    )
    update_rule = next(r for r in entity.access.permissions if r.operation == PermissionKind.UPDATE)
    delete_rule = next(r for r in entity.access.permissions if r.operation == PermissionKind.DELETE)
    assert update_rule.deny_all is True
    assert update_rule.effect == PolicyEffect.PERMIT
    assert update_rule.condition is None
    assert delete_rule.deny_all is True
    # Sibling rules unaffected
    create_rule = next(r for r in entity.access.permissions if r.operation == PermissionKind.CREATE)
    assert create_rule.deny_all is False


def test_default_deny_all_is_false_for_normal_rules() -> None:
    """Existing non-`false` rules keep `deny_all=False` so the new
    field doesn't bleed into the legacy shape."""
    entity = _parse_audit_log(
        """\
  permit:
    create: authenticated
    read: role(admin)
"""
    )
    for rule in entity.access.permissions:
        assert rule.deny_all is False, (
            f"Non-`false` rule {rule.operation} should have deny_all=False"
        )


def test_permit_false_rejected_in_forbid_block() -> None:
    """`forbid: <op>: false` is ambiguous (does it mean permit everyone?)
    so we refuse the short-form there. Authors must write an explicit
    role/condition in `forbid:` blocks."""
    with pytest.raises(Exception, match="only valid in `permit:` blocks"):
        _parse_audit_log(
            """\
  forbid:
    update: false
"""
        )


def test_permit_false_coexists_with_other_rules_on_same_entity() -> None:
    """A `false` denial of one op doesn't disturb the other ops'
    `condition` / `personas` / `require_auth` shapes."""
    entity = _parse_audit_log(
        """\
  permit:
    create: role(admin)
    read: authenticated
    update: false
    delete: false
"""
    )
    rules_by_op = {r.operation: r for r in entity.access.permissions}
    assert rules_by_op[PermissionKind.CREATE].deny_all is False
    assert rules_by_op[PermissionKind.READ].deny_all is False
    assert rules_by_op[PermissionKind.READ].require_auth is True
    assert rules_by_op[PermissionKind.UPDATE].deny_all is True
    assert rules_by_op[PermissionKind.DELETE].deny_all is True


def test_permission_rule_default_field_is_false() -> None:
    """Sanity test: the new `deny_all` field defaults to False so
    existing IR consumers that don't know about it aren't surprised."""
    rule = PermissionRule(operation=PermissionKind.READ)
    assert rule.deny_all is False
