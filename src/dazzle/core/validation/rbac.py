"""Scope-predicate, role-reference, and RBAC-diagnostic validation.

Split verbatim from dazzle.core.validator per #1361.
"""

from typing import Any

from dazzle.core.ir.identity import spec_display_id
from dazzle.product_quality.persona_homes import STABLE_PERSONA_USER_IDS

from .. import ir
from .conditions import _condition_field_references, _walk_role_names

_VISIBILITY_BOOL_FIELD_NAMES = frozenset(
    {"is_internal", "is_private", "internal_only", "internal", "private"}
)


def validate_visibility_bool_field_scope_coverage(
    appspec: ir.AppSpec,
) -> tuple[list[str], list[str]]:
    """Warn when an entity has a likely-visibility bool field but no scope filter.

    An entity carrying a bool field named `is_internal`, `is_private`,
    `internal_only`, etc. is signalling intent that some rows should be
    invisible to certain personas. If the entity is exposed to multiple
    personas via an unfiltered `all` scope (condition=None) and no scope
    rule references that field's name, the field is decoration — rows
    leak across personas regardless of its value.

    Caught by /fuzz on examples/support_tickets where Comment.is_internal
    was leaking to the `customer` persona (#1062).
    """
    errors: list[str] = []
    warnings: list[str] = []

    for entity in appspec.domain.entities:
        if entity.access is None or not entity.access.scopes:
            continue

        bool_visibility_fields = [
            f.name
            for f in entity.fields
            if f.name in _VISIBILITY_BOOL_FIELD_NAMES and f.type.kind == ir.FieldTypeKind.BOOL
        ]
        if not bool_visibility_fields:
            continue

        # Collect every persona named by any scope rule on this entity.
        all_personas: set[str] = set()
        for rule in entity.access.scopes:
            all_personas.update(rule.personas)

        if len(all_personas) < 2:
            # Single-persona exposure: no leak surface.
            continue

        referenced_fields: set[str] = set()
        for rule in entity.access.scopes:
            referenced_fields.update(_condition_field_references(rule.condition))

        unreferenced = [name for name in bool_visibility_fields if name not in referenced_fields]
        if not unreferenced:
            continue

        for field_name in unreferenced:
            warnings.append(
                f"Entity '{entity.name}': bool field '{field_name}' looks "
                f"like a visibility gate but no scope rule references it — "
                f"all {len(all_personas)} personas ({', '.join(sorted(all_personas))}) "
                f"see rows regardless of '{field_name}' value. Add a "
                f"`scope: list: {field_name} = false as: <persona>` rule "
                f"or rename the field if visibility wasn't the intent."
            )

    return errors, warnings


def validate_scope_predicates(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """
    Validate scope predicates against the FK graph (belt-and-suspenders).

    The linker already compiles scope predicates and catches many errors during
    ``build_scope_predicate``.  This validator provides a second layer that
    walks the *compiled* predicate trees and verifies:

    - ColumnCheck.field exists on the entity
    - PathCheck.path resolves through the FK graph
    - ExistsCheck.target_entity exists
    - No role/grant checks leak into scope rules (already blocked by the
      predicate builder, but verified here for defense-in-depth)

    Returns:
        Tuple of (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []

    fk_graph = appspec.fk_graph
    if fk_graph is None:
        return errors, warnings

    for entity in appspec.domain.entities:
        if entity.access is None or not entity.access.scopes:
            continue

        entity_field_names = {f.name for f in entity.fields}

        for rule in entity.access.scopes:
            predicate = rule.predicate
            if predicate is None:
                continue

            ctx = f"Entity '{entity.name}' scope rule"
            _validate_predicate_node(
                predicate,
                entity.name,
                entity_field_names,
                fk_graph,
                appspec,
                ctx,
                errors,
                warnings,
            )

    return errors, warnings


def _validate_predicate_node(
    node: object,
    entity_name: str,
    entity_field_names: set[str],
    fk_graph: Any,
    appspec: ir.AppSpec,
    ctx: str,
    errors: list[str],
    warnings: list[str],
) -> None:
    """Recursively validate a single predicate node against the FK graph."""
    # Import here to avoid circular imports at module level
    from ..ir.predicates import (
        BoolComposite,
        ColumnCheck,
        Contradiction,
        ExistsCheck,
        PathCheck,
        PolyPathCheck,
        Tautology,
        UserAttrCheck,
    )

    if isinstance(node, (Tautology, Contradiction)):
        return

    if isinstance(node, ColumnCheck):
        if node.field not in entity_field_names:
            errors.append(
                f"{ctx}: ColumnCheck references non-existent field "
                f"'{node.field}' on entity '{entity_name}'"
            )
        return

    if isinstance(node, UserAttrCheck):
        if node.field not in entity_field_names:
            errors.append(
                f"{ctx}: UserAttrCheck references non-existent field "
                f"'{node.field}' on entity '{entity_name}'"
            )
        return

    if isinstance(node, PathCheck):
        if not node.path:
            errors.append(f"{ctx}: PathCheck has empty path")
            return
        # Validate FK hops for all segments except the last, then check
        # the terminal field exists on the final entity.
        path_str = ".".join(node.path)
        current = entity_name
        for i, segment in enumerate(node.path):
            is_last = i == len(node.path) - 1
            if is_last:
                # Terminal segment: must be a plain field on current entity
                if not fk_graph.field_exists(current, segment):
                    errors.append(
                        f"{ctx}: PathCheck path '{path_str}' — terminal field "
                        f"'{segment}' does not exist on entity '{current}'"
                    )
            else:
                # Intermediate segment: must be an FK hop
                try:
                    _, target = fk_graph.resolve_segment(current, segment)
                    current = target
                except (ValueError, AttributeError) as exc:
                    # #1448: a poly_ref field used without a [Type] selector is a
                    # common mistake — give a poly-aware hint instead of a raw
                    # "no FK for segment" error.
                    ent = appspec.get_entity(current)
                    pf = next((f for f in (ent.fields if ent else []) if f.name == segment), None)
                    if pf is not None and pf.type.kind.value == "poly_ref":
                        errors.append(
                            f"{ctx}: E_POLY_SELECTOR_REQUIRED — '{segment}' is a poly_ref; "
                            f"write '{segment}[<TargetType>].…' to select a branch"
                        )
                    else:
                        errors.append(f"{ctx}: PathCheck path '{path_str}' — {exc}")
                    break  # Cannot continue resolving after a broken hop
        return

    if isinstance(node, PolyPathCheck):
        ent = appspec.get_entity(entity_name)
        poly_field = next((f for f in (ent.fields if ent else []) if f.name == node.field), None)
        if poly_field is None or poly_field.type.kind.value != "poly_ref":
            errors.append(
                f"{ctx}: E_POLY_SELECTOR_REQUIRED — '{node.field}' is not a poly_ref field "
                f"on '{entity_name}'"
            )
            return
        targets = poly_field.type.poly_targets or []
        if node.type_value not in targets:
            errors.append(
                f"{ctx}: E_POLY_BRANCH_UNDECLARED — branch '{node.type_value}' is not a declared "
                f"target of {entity_name}.{node.field} (declared: {targets or 'none'})"
            )
            return
        tgt = appspec.get_entity(node.type_value)
        if tgt is None:
            errors.append(
                f"{ctx}: E_POLY_BRANCH_UNDECLARED — unknown target entity '{node.type_value}'"
            )
            return
        id_field = next((f for f in tgt.fields if f.name == "id"), None)
        if id_field is None or id_field.type.kind.value != "uuid":
            errors.append(
                f"{ctx}: E_POLY_TARGET_NOT_UUID_PK — poly_ref target '{node.type_value}' must have "
                f"a uuid primary key"
            )
            return
        # Validate the sub-predicate rooted on the target entity.
        tgt_field_names = {f.name for f in tgt.fields}
        _validate_predicate_node(
            node.sub,
            node.type_value,
            tgt_field_names,
            fk_graph,
            appspec,
            f"{ctx} (poly branch {node.type_value})",
            errors,
            warnings,
        )
        return

    if isinstance(node, ExistsCheck):
        if not appspec.get_entity(node.target_entity):
            errors.append(
                f"{ctx}: ExistsCheck references non-existent entity '{node.target_entity}'"
            )
            return
        # Dotted junction-field paths (#858): walk segments through the FK
        # graph starting from the junction. All but the last must resolve
        # as FK hops; the last is a column on the tail entity.
        for binding in node.bindings:
            if "." not in binding.junction_field:
                continue
            segments = binding.junction_field.split(".")
            current = node.target_entity
            for i, segment in enumerate(segments):
                is_last = i == len(segments) - 1
                if is_last:
                    if not fk_graph.field_exists(current, segment):
                        errors.append(
                            f"{ctx}: via binding '{binding.junction_field}' — "
                            f"terminal field '{segment}' does not exist on '{current}'"
                        )
                else:
                    try:
                        _, target = fk_graph.resolve_segment(current, segment)
                        current = target
                    except (ValueError, AttributeError) as exc:
                        errors.append(f"{ctx}: via binding '{binding.junction_field}' — {exc}")
                        break
        return

    if isinstance(node, BoolComposite):
        for child in node.children:
            _validate_predicate_node(
                child,
                entity_name,
                entity_field_names,
                fk_graph,
                appspec,
                ctx,
                errors,
                warnings,
            )
        return


def _find_user_role_enum(appspec: ir.AppSpec) -> tuple[str, set[str]] | None:
    """Locate the User entity's enum-typed `role` field and return its values.

    Returns (entity_name, enum_values) or None if no User entity / no role
    field with enum values is found. Prefers the explicit USER archetype
    but falls back to "any entity named User with an enum role field" so
    fixtures that don't tag the archetype still get checked.
    """
    candidates: list[ir.EntitySpec] = []
    for entity in appspec.domain.entities:
        if entity.archetype_kind == ir.ArchetypeKind.USER:
            candidates.insert(0, entity)
        elif entity.name in {"User", "Account"}:
            candidates.append(entity)
    for entity in candidates:
        for field in entity.fields:
            if field.name != "role":
                continue
            if field.type.kind == ir.FieldTypeKind.ENUM and field.type.enum_values:
                return entity.name, set(field.type.enum_values)
    return None


def validate_role_references_against_enum(
    appspec: ir.AppSpec,
) -> tuple[list[str], list[str]]:
    """Warn when a `role(<name>)` check references a value not in User.role.

    A common /fuzz finding (shapes_validation #530): a permit clause
    `role(guardian)` silently never matches because `guardian` is a
    persona name, not a value in the User.role enum.
    """
    errors: list[str] = []
    warnings: list[str] = []

    user_info = _find_user_role_enum(appspec)
    if user_info is None:
        return errors, warnings
    user_entity_name, enum_values = user_info

    for entity in appspec.domain.entities:
        if entity.access is None:
            continue
        seen: set[tuple[str, str]] = set()
        for rule in entity.access.permissions:
            for role_name in _walk_role_names(rule.condition):
                if role_name in enum_values:
                    continue
                key = (entity.name, role_name)
                if key in seen:
                    continue
                seen.add(key)
                warnings.append(
                    f"Entity '{entity.name}': permit references "
                    f"role({role_name!r}) which is not in {user_entity_name}.role "
                    f"enum ({sorted(enum_values)}). The check will never "
                    f"match — rule is dead."
                )

    return errors, warnings


_ALLOWED_SCOPE_WILDCARDS = frozenset(
    {
        "*",
        "all",
        "any",
        "authenticated",
        "anonymous",
        "super_admin",
        "platform_admin",
        "sysadmin",
        "system",
        "operator",
    }
)


def _declared_persona_ids(appspec: ir.AppSpec) -> set[str]:
    declared = {spec_display_id(p, default=None, prefer="id") for p in appspec.personas or []}
    declared.discard(None)
    return {str(x) for x in declared}


def _is_unknown_scope_persona(token: str, declared: set[str]) -> bool:
    return token not in declared and token not in _ALLOWED_SCOPE_WILDCARDS


def _warn_unknown_tokens(
    tokens: list[str] | None,
    *,
    declared: set[str],
    prefix: str,
) -> list[str]:
    out: list[str] = []
    sorted_decl = sorted(declared)
    for persona in tokens or []:
        tok = str(persona)
        if _is_unknown_scope_persona(tok, declared):
            out.append(f"{prefix} {tok!r} ({sorted_decl}) (#1630).")
    return out


def validate_scope_personas_declared(
    appspec: ir.AppSpec,
) -> tuple[list[str], list[str]]:
    """Warn when ``as:`` / scope personas are not declared personas (#1630).

    A rename that leaves ``as: approver, ops`` while the persona is
    ``ops_engineer`` validates green but empties the desk at runtime.
    Wildcards (``*``) and platform admin tokens are allowed.
    """
    errors: list[str] = []
    warnings: list[str] = []
    declared_s = _declared_persona_ids(appspec)

    for entity in appspec.domain.entities:
        if entity.access is None:
            continue
        for scope_rule in entity.access.scopes or []:
            warnings.extend(
                _warn_unknown_tokens(
                    list(scope_rule.personas or []),
                    declared=declared_s,
                    prefix=(f"Entity '{entity.name}': scope `as:` references persona"),
                )
            )
        for perm_rule in entity.access.permissions or []:
            warnings.extend(
                _warn_unknown_tokens(
                    list(getattr(perm_rule, "personas", None) or []),
                    declared=declared_s,
                    prefix=(f"Entity '{entity.name}': permission rule references persona"),
                )
            )

    for ws in appspec.workspaces or []:
        ws_name = spec_display_id(ws, default="?")
        warnings.extend(
            _warn_unknown_tokens(
                list(getattr(ws, "allow_personas", None) or []),
                declared=declared_s,
                prefix=f"Workspace '{ws_name}': allow_personas references",
            )
        )

    return errors, warnings


def validate_stable_persona_ids_for_demo(
    appspec: ir.AppSpec,
) -> tuple[list[str], list[str]]:
    """Warn when persona ids fall outside STABLE map but use current_user (#1630).

    Assignment-aware demo seeds + ``/__test__/authenticate role=`` only share
    UUIDs for :data:`STABLE_PERSONA_USER_IDS` keys. Domain ids like
    ``promoter`` / ``booker`` empty desks under demo ops.
    """
    errors: list[str] = []
    warnings: list[str] = []
    if not _appspec_uses_current_user(appspec):
        return errors, warnings

    stable = set(STABLE_PERSONA_USER_IDS)
    sample = sorted(stable)[:8]
    for persona in appspec.personas or []:
        pid = str(spec_display_id(persona, default="", prefer="id") or "")
        if not pid or pid in stable:
            continue
        if pid in ("admin", "platform_admin", "superuser", "operator", "sysadmin"):
            continue
        if not getattr(persona, "default_workspace", None):
            continue
        warnings.append(
            f"Persona '{pid}' is not in STABLE_PERSONA_USER_IDS "
            f"({sample}…). Demo ``role=`` auth and assignment "
            f"seeds will not share a principal UUID — rename the persona "
            f"*id* to a STABLE key and keep a human title, or declare "
            f"stable ids (#1630)."
        )

    return errors, warnings


def _appspec_uses_current_user(appspec: ir.AppSpec) -> bool:
    """True if any scope/region filter text mentions current_user."""
    for entity in appspec.domain.entities:
        if entity.access is None:
            continue
        for rule in entity.access.scopes or []:
            if _condition_mentions_current_user(rule.condition):
                return True
    for ws in appspec.workspaces or []:
        for region in getattr(ws, "regions", None) or []:
            if _condition_mentions_current_user(getattr(region, "filter", None)):
                return True
    return False


def _condition_mentions_current_user(cond: Any) -> bool:
    if cond is None:
        return False
    try:
        text = str(cond.model_dump() if hasattr(cond, "model_dump") else cond)
    except Exception:  # noqa: BLE001 — best-effort walk
        text = str(cond)
    return "current_user" in text


def validate_admin_personas_scope_conflict(
    appspec: ir.AppSpec,
) -> tuple[list[str], list[str]]:
    """Reject a persona that is both a tenancy admin and bound to a scope rule.

    A persona listed in `tenancy.admin_personas` bypasses the tenant filter at
    runtime (#957). If the same persona is also named in a `scope: ... as:`
    rule, that rule is dead for that persona — its grants ignore the row
    filter — so the apparent partitioning is a silent cross-tenant leak (#1184).
    """
    errors: list[str] = []
    warnings: list[str] = []

    tenancy = appspec.tenancy
    if tenancy is None or not tenancy.admin_personas:
        return errors, warnings
    admin = set(tenancy.admin_personas)

    for entity in appspec.domain.entities:
        if entity.access is None or not entity.access.scopes:
            continue
        conflicting: set[str] = set()
        for rule in entity.access.scopes:
            conflicting |= admin.intersection(rule.personas)
        for persona in sorted(conflicting):
            errors.append(
                f"Entity '{entity.name}': persona '{persona}' is in "
                f"`tenancy.admin_personas` (bypasses the tenant filter) and "
                f"also bound to a `scope:` rule via `as:`. The scope rule is "
                f"dead for that persona — remove '{persona}' from one side."
            )
    return errors, warnings


def validate_rbac_matrix_diagnostics(
    appspec: ir.AppSpec,
) -> tuple[list[str], list[str]]:
    """Surface PolicyWarnings from `generate_access_matrix`.

    The RBAC matrix already detects redundant_forbid and orphan_role
    patterns at link-time, but no validator was surfacing them — they
    were silently discarded. This wires them into `dazzle validate`.
    """
    errors: list[str] = []
    warnings: list[str] = []

    try:
        from dazzle.rbac.matrix import generate_access_matrix
    except ImportError:
        return errors, warnings

    try:
        matrix = generate_access_matrix(appspec)
    except Exception:
        # Matrix generation can fail on incomplete AppSpecs during early
        # development; don't block validation.
        return errors, warnings

    for warning in matrix.warnings:
        warnings.append(f"[RBAC {warning.kind}] {warning.message}")

    return errors, warnings
