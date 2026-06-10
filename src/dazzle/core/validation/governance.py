"""Audit-config, governance-policy, and sensitive-field validation.

Split verbatim from dazzle.core.validator per #1361.
"""

from .. import ir


def validate_audit_config(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Validate entity audit configuration and warn about runtime status."""
    errors: list[str] = []
    warnings: list[str] = []

    valid_operations = {kind.value for kind in ir.PermissionKind}
    audited_entities: list[str] = []

    for entity in appspec.domain.entities:
        if entity.audit and entity.audit.enabled:
            audited_entities.append(entity.name)
            # Validate operation names
            for op in entity.audit.operations:
                if op.value not in valid_operations:
                    errors.append(
                        f"Entity '{entity.name}' audit config references "
                        f"unknown operation '{op.value}'."
                    )

    if audited_entities:
        count = len(audited_entities)
        noun = "entity has" if count == 1 else "entities have"
        warnings.append(
            f"[Info] {count} {noun} audit: enabled. "
            "CRUD operations and access decisions will be logged to the audit trail."
        )
        fcs = [e.name for e in appspec.domain.entities if e.audit and e.audit.include_field_changes]
        if fcs:
            warnings.append(
                f"[Info] {len(fcs)} audited entity/entities have "
                "include_field_changes enabled. Field-level diffs will be "
                "captured for update and delete operations."
            )

    return errors, warnings


def validate_governance_policies(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Validate governance policy definitions and warn about runtime status."""
    errors: list[str] = []
    warnings: list[str] = []

    if not appspec.policies:
        return errors, warnings

    entity_names = {e.name for e in appspec.domain.entities}
    entity_fields: dict[str, set[str]] = {
        e.name: {f.name for f in e.fields} for e in appspec.domain.entities
    }

    # Validate classifications
    if appspec.policies.classifications:
        for cls in appspec.policies.classifications:
            if cls.entity not in entity_names:
                errors.append(f"Classification references unknown entity '{cls.entity}'.")
            elif cls.field not in entity_fields.get(cls.entity, set()):
                errors.append(
                    f"Classification references unknown field '{cls.entity}.{cls.field}'."
                )

        count = len(appspec.policies.classifications)
        noun = "classification" if count == 1 else "classifications"
        warnings.append(
            f"[Preview] {count} data {noun} defined. "
            "Classification-based access filtering is not yet enforced at runtime."
        )

    # Validate erasures
    if appspec.policies.erasures:
        for erasure in appspec.policies.erasures:
            if erasure.entity not in entity_names:
                errors.append(f"Erasure policy references unknown entity '{erasure.entity}'.")
            elif erasure.field and erasure.field not in entity_fields.get(erasure.entity, set()):
                errors.append(
                    f"Erasure policy references unknown field '{erasure.entity}.{erasure.field}'."
                )

        count = len(appspec.policies.erasures)
        noun = "erasure policy" if count == 1 else "erasure policies"
        warnings.append(
            f"[Preview] {count} {noun} defined. "
            "Data erasure workflows are not yet enforced at runtime."
        )

    return errors, warnings


def validate_sensitive_fields(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Validate sensitive field markers and warn about runtime status."""
    errors: list[str] = []
    warnings: list[str] = []

    sensitive_fields: list[str] = []
    for entity in appspec.domain.entities:
        for field in entity.fields:
            if field.is_sensitive:
                sensitive_fields.append(f"{entity.name}.{field.name}")

    if sensitive_fields:
        count = len(sensitive_fields)
        noun = "field" if count == 1 else "fields"
        warnings.append(
            f"[Info] {count} {noun} marked 'sensitive'. "
            "Response masking is not yet enforced at runtime."
        )

    return errors, warnings
