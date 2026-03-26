"""
Admin entity builder for DAZZLE.

Builds the synthetic platform EntitySpec objects used by the admin workspace.
Entities are profile-gated: some only appear for STANDARD and STRICT profiles.

Part of Issue #686 — universal admin workspace for auth-enabled Dazzle apps.
"""

from __future__ import annotations

from dazzle.core import ir
from dazzle.core.ir.admin_entities import ADMIN_ENTITY_DEFS
from dazzle.core.ir.fields import FieldModifier, FieldSpec, FieldType, FieldTypeKind
from dazzle.core.ir.security import SecurityConfig, SecurityProfile

# ---------------------------------------------------------------------------
# Field type parser (duplicated from linker._parse_field_type to avoid
# circular imports — linker imports IR which transitively imports many things)
# ---------------------------------------------------------------------------


def _parse_field_type(type_str: str) -> FieldType:
    """Parse a compact field type string into a FieldType.

    Handles: uuid, int, text, bool, float, datetime, str(N), enum[a,b,c].

    Args:
        type_str: Compact type descriptor, e.g. ``"str(200)"`` or
            ``"enum[healthy,degraded,unhealthy]"``.

    Returns:
        A :class:`~dazzle.core.ir.fields.FieldType` instance.

    Raises:
        ValueError: If *type_str* is not recognised.
    """
    if type_str == "uuid":
        return FieldType(kind=FieldTypeKind.UUID)
    if type_str == "int":
        return FieldType(kind=FieldTypeKind.INT)
    if type_str == "text":
        return FieldType(kind=FieldTypeKind.TEXT)
    if type_str == "bool":
        return FieldType(kind=FieldTypeKind.BOOL)
    if type_str == "float":
        return FieldType(kind=FieldTypeKind.FLOAT)
    if type_str == "datetime":
        return FieldType(kind=FieldTypeKind.DATETIME)
    if type_str.startswith("str(") and type_str.endswith(")"):
        max_len = int(type_str[4:-1])
        return FieldType(kind=FieldTypeKind.STR, max_length=max_len)
    if type_str.startswith("decimal(") and type_str.endswith(")"):
        parts = type_str[8:-1].split(",")
        return FieldType(
            kind=FieldTypeKind.DECIMAL,
            precision=int(parts[0]),
            scale=int(parts[1]),
        )
    if type_str.startswith("enum[") and type_str.endswith("]"):
        values = [v.strip() for v in type_str[5:-1].split(",")]
        return FieldType(kind=FieldTypeKind.ENUM, enum_values=values)
    if type_str.startswith("money(") and type_str.endswith(")"):
        currency = type_str[6:-1].strip()
        return FieldType(kind=FieldTypeKind.MONEY, currency_code=currency)
    if type_str.startswith("ref "):
        ref_entity = type_str[4:].strip()
        return FieldType(kind=FieldTypeKind.REF, ref_entity=ref_entity)
    raise ValueError(f"Unknown field type: {type_str!r}")


# ---------------------------------------------------------------------------
# Modifier map
# ---------------------------------------------------------------------------

_MODIFIER_MAP: dict[str, FieldModifier] = {
    "pk": FieldModifier.PK,
    "required": FieldModifier.REQUIRED,
    "unique": FieldModifier.UNIQUE,
}

# ---------------------------------------------------------------------------
# Profile gate helper
# ---------------------------------------------------------------------------


def _is_profile_included(profile_gate: str | None, active_profile: SecurityProfile) -> bool:
    """Return True if the entity should be included for *active_profile*.

    Args:
        profile_gate: ``None`` means available on all profiles; ``"standard"``
            means STANDARD and STRICT only.
        active_profile: The app's active :class:`SecurityProfile`.

    Returns:
        ``True`` if the entity should be included.
    """
    if profile_gate is None:
        return True
    if profile_gate == "standard":
        return active_profile in (SecurityProfile.STANDARD, SecurityProfile.STRICT)
    # Unknown gate → conservative exclude
    return False


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

_ADMIN_PERSONAS: list[str] = ["admin", "super_admin"]
_READ_ONLY_OPS: tuple[ir.PermissionKind, ...] = (
    ir.PermissionKind.READ,
    ir.PermissionKind.LIST,
)


def _build_admin_entities(security: SecurityConfig) -> list[ir.EntitySpec]:
    """Build the list of synthetic platform EntitySpec objects for the admin workspace.

    Only entities whose ``profile_gate`` is satisfied by *security.profile* are
    included.  All generated entities are read-only (READ + LIST) and restricted
    to ``admin`` / ``super_admin`` personas.

    Args:
        security: Application security configuration (provides the active profile).

    Returns:
        A list of :class:`~dazzle.core.ir.domain.EntitySpec` objects ready to be
        merged into the app's domain.
    """
    entities: list[ir.EntitySpec] = []

    for name, title, intent, fields_tuple, patterns, profile_gate in ADMIN_ENTITY_DEFS:
        if not _is_profile_included(profile_gate, security.profile):
            continue

        # Build FieldSpec list from compact tuple definitions
        fields: list[FieldSpec] = []
        for field_name, type_str, modifiers, default in fields_tuple:
            field_type = _parse_field_type(type_str)
            mods = [_MODIFIER_MAP[m] for m in modifiers]
            fields.append(
                FieldSpec(name=field_name, type=field_type, modifiers=mods, default=default)
            )

        # Read-only access restricted to admin personas
        access = ir.AccessSpec(
            permissions=[
                ir.PermissionRule(
                    operation=op,
                    require_auth=True,
                    effect=ir.PolicyEffect.PERMIT,
                    personas=list(_ADMIN_PERSONAS),
                )
                for op in _READ_ONLY_OPS
            ]
        )

        entities.append(
            ir.EntitySpec(
                name=name,
                title=title,
                intent=intent,
                domain="platform",
                patterns=list(patterns),
                fields=fields,
                access=access,
            )
        )

    return entities
