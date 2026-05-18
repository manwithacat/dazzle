"""#1147: orphan_role lint must operate on resolved role names, not
persona ids.

Pre-fix a persona named ``commercial`` with ``role: brand_owner``
tripped the lint because the matrix compared persona ids against
referenced role names. After #1147, ``PersonaSpec.role`` is the
explicit override (with ``id`` as the fallback), and the lint
diffs by ``effective_role`` — so two personas can share one role
without false-positive orphan warnings.
"""

from __future__ import annotations

from dazzle.core.ir import (
    AppSpec,
    DomainSpec,
    EntitySpec,
    FieldModifier,
    FieldSpec,
    FieldType,
    FieldTypeKind,
    PersonaSpec,
)
from dazzle.core.ir.domain import (
    AccessSpec,
    PermissionKind,
    PermissionRule,
    PolicyEffect,
)
from dazzle.rbac.matrix import generate_access_matrix


def _entity(name: str, *, permits: list[PermissionRule]) -> EntitySpec:
    return EntitySpec(
        name=name,
        title=name,
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind=FieldTypeKind.UUID),
                modifiers=[FieldModifier.PK],
            ),
        ],
        access=AccessSpec(permissions=permits),
    )


def _appspec(personas: list[PersonaSpec], entities: list[EntitySpec]) -> AppSpec:
    return AppSpec(
        name="t",
        title="t",
        domain=DomainSpec(entities=entities),
        personas=personas,
    )


def _orphan_warnings(matrix) -> list:
    return [w for w in matrix.warnings if w.kind == "orphan_role"]


def test_persona_with_role_field_not_orphaned() -> None:
    """The canonical bug class: persona id 'commercial', role
    'brand_owner', and 'brand_owner' appears in a permit rule —
    no orphan_role warning."""
    appspec = _appspec(
        personas=[PersonaSpec(id="commercial", label="Commercial", role="brand_owner")],
        entities=[
            _entity(
                "Campaign",
                permits=[
                    PermissionRule(
                        operation=PermissionKind.CREATE,
                        effect=PolicyEffect.PERMIT,
                        personas=["brand_owner"],
                    )
                ],
            )
        ],
    )
    matrix = generate_access_matrix(appspec)
    assert _orphan_warnings(matrix) == [], (
        f"expected no orphan warnings, got {[w.message for w in _orphan_warnings(matrix)]}"
    )


def test_two_personas_sharing_one_role_collapse_to_single_column() -> None:
    """Two personas with the same role produce one matrix column,
    not two — the role is the unit of authorisation, not the
    persona's display identity."""
    appspec = _appspec(
        personas=[
            PersonaSpec(id="commercial", label="Commercial", role="brand_owner"),
            PersonaSpec(id="agency", label="Agency", role="brand_owner"),
        ],
        entities=[
            _entity(
                "Campaign",
                permits=[
                    PermissionRule(
                        operation=PermissionKind.CREATE,
                        effect=PolicyEffect.PERMIT,
                        personas=["brand_owner"],
                    )
                ],
            )
        ],
    )
    matrix = generate_access_matrix(appspec)
    assert matrix.roles == ["brand_owner"]


def test_persona_without_role_field_still_uses_id_as_role() -> None:
    """Regression guard for the pre-#1147 convention: when a
    persona has no explicit role, its id IS the role."""
    appspec = _appspec(
        personas=[PersonaSpec(id="admin", label="Admin")],
        entities=[
            _entity(
                "Thing",
                permits=[
                    PermissionRule(
                        operation=PermissionKind.READ,
                        effect=PolicyEffect.PERMIT,
                        personas=["admin"],
                    )
                ],
            )
        ],
    )
    matrix = generate_access_matrix(appspec)
    assert matrix.roles == ["admin"]
    assert _orphan_warnings(matrix) == []


def test_genuine_orphan_role_still_warns() -> None:
    """The lint should still catch real orphans — a persona/role
    that no rule references."""
    appspec = _appspec(
        personas=[
            PersonaSpec(id="commercial", label="Commercial", role="brand_owner"),
            PersonaSpec(id="ghost", label="Ghost"),  # id=ghost, role=ghost, unreferenced
        ],
        entities=[
            _entity(
                "Campaign",
                permits=[
                    PermissionRule(
                        operation=PermissionKind.CREATE,
                        effect=PolicyEffect.PERMIT,
                        personas=["brand_owner"],
                    )
                ],
            )
        ],
    )
    matrix = generate_access_matrix(appspec)
    orphans = _orphan_warnings(matrix)
    assert len(orphans) == 1
    assert orphans[0].role == "ghost"


def test_orphan_warning_names_both_role_and_personas_when_mismatched() -> None:
    """When a role's only personas have a different id, the warning
    message includes both the role name and the persona id(s) so
    the operator can find both."""
    appspec = _appspec(
        personas=[
            PersonaSpec(id="commercial", label="Commercial", role="orphan_role"),
            PersonaSpec(id="agency", label="Agency", role="orphan_role"),
        ],
        entities=[
            _entity(
                "Thing",
                permits=[
                    PermissionRule(
                        operation=PermissionKind.READ,
                        effect=PolicyEffect.PERMIT,
                        personas=["other_role"],
                    )
                ],
            )
        ],
    )
    matrix = generate_access_matrix(appspec)
    orphans = _orphan_warnings(matrix)
    # orphan_role + other_role both trip — focus on the role with the
    # persona mismatch.
    orphan = next(w for w in orphans if w.role == "orphan_role")
    assert "orphan_role" in orphan.message
    assert "commercial" in orphan.message
    assert "agency" in orphan.message
