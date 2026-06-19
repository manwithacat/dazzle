"""Graph-declaration, lifecycle, fitness, and storage-ref validation.

Split verbatim from dazzle.core.validator per #1361.
"""

from collections.abc import Mapping

from .. import ir
from ..ir.state_machine import state_name

# =============================================================================
# Graph semantics validation (v0.46.0 — #619)
# =============================================================================

# Numeric field types for graph weight validation
_NUMERIC_FIELD_TYPES = frozenset(
    {
        ir.FieldTypeKind.INT,
        ir.FieldTypeKind.DECIMAL,
        ir.FieldTypeKind.FLOAT,
    }
)


def validate_graph_declarations(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Validate graph_edge: and graph_node: declarations.

    Checks field references, types, and cross-entity consistency.

    Returns:
        Tuple of (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []
    entity_map = {e.name: e for e in appspec.domain.entities}

    for entity in appspec.domain.entities:
        if entity.graph_edge is not None:
            _validate_graph_edge(entity, entity_map, errors, warnings)
        if entity.graph_node is not None:
            _validate_graph_node(entity, entity_map, errors, warnings)

    return errors, warnings


def _validate_graph_edge(
    entity: ir.EntitySpec,
    entity_map: dict[str, ir.EntitySpec],
    errors: list[str],
    warnings: list[str],
) -> None:
    """Validate a single entity's graph_edge: block."""
    ge = entity.graph_edge
    assert ge is not None
    field_map = {f.name: f for f in entity.fields}

    # source field
    if ge.source not in field_map:
        errors.append(f"graph_edge source '{ge.source}' is not a field on {entity.name}")
    else:
        src_field = field_map[ge.source]
        if src_field.type.kind != ir.FieldTypeKind.REF:
            errors.append(
                f"graph_edge source must be a ref field, got '{src_field.type.kind.value}'"
            )

    # target field
    if ge.target not in field_map:
        errors.append(f"graph_edge target '{ge.target}' is not a field on {entity.name}")
    else:
        tgt_field = field_map[ge.target]
        if tgt_field.type.kind != ir.FieldTypeKind.REF:
            errors.append(
                f"graph_edge target must be a ref field, got '{tgt_field.type.kind.value}'"
            )

    # type_field (optional)
    if ge.type_field is not None:
        if ge.type_field not in field_map:
            errors.append(f"graph_edge type '{ge.type_field}' is not a field on {entity.name}")

    # weight_field (optional)
    if ge.weight_field is not None:
        if ge.weight_field not in field_map:
            errors.append(f"graph_edge weight '{ge.weight_field}' is not a field on {entity.name}")
        else:
            wf = field_map[ge.weight_field]
            if wf.type.kind not in _NUMERIC_FIELD_TYPES:
                errors.append("graph_edge weight must be int, decimal, or float")

    # Warnings: heterogeneous graph
    if ge.source in field_map and ge.target in field_map:
        src_ref = field_map[ge.source].type.ref_entity
        tgt_ref = field_map[ge.target].type.ref_entity
        if src_ref and tgt_ref and src_ref != tgt_ref:
            warnings.append(f"Heterogeneous graph: source refs {src_ref}, target refs {tgt_ref}")

    # Warning: no access control on edge entity
    if entity.access is None or not entity.access.permissions:
        warnings.append(f"Edge entity '{entity.name}' has no access control")

    # Warning: acyclic only detectable in seed data
    if ge.acyclic:
        warnings.append("acyclic declared but cycles only detected in seed data")


def _validate_graph_node(
    entity: ir.EntitySpec,
    entity_map: dict[str, ir.EntitySpec],
    errors: list[str],
    warnings: list[str],
) -> None:
    """Validate a single entity's graph_node: block."""
    gn = entity.graph_node
    assert gn is not None

    if gn.edge_entity not in entity_map:
        errors.append(f"graph_node edges '{gn.edge_entity}' is not a defined entity")
    else:
        edge_ent = entity_map[gn.edge_entity]
        if edge_ent.graph_edge is None:
            errors.append(f"graph_node edges '{gn.edge_entity}' does not declare graph_edge:")

    field_map = {f.name: f for f in entity.fields}
    if gn.display is not None:
        if gn.display not in field_map:
            errors.append(f"graph_node display '{gn.display}' is not a field on {entity.name}")
    else:
        warnings.append("graph_node has no display field — labels use default fallback")

    # parent_field must reference a real ref field (#781)
    if gn.parent_field is not None:
        parent_spec = field_map.get(gn.parent_field)
        if parent_spec is None:
            errors.append(f"graph_node parent '{gn.parent_field}' is not a field on {entity.name}")
        elif (
            parent_spec.type.kind.value not in ("ref", "belongs_to")
            or not parent_spec.type.ref_entity
        ):
            errors.append(
                f"graph_node parent '{gn.parent_field}' on {entity.name} must be a ref field"
            )


def validate_lifecycles(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Validate entity lifecycle: declarations (ADR-0020).

    Checks:
    - status_field references a real field on the entity
    - status_field is an enum-typed field
    - Every state name matches one of the enum's declared values
    - Order values are unique across states
    - Every transition from_state/to_state references a declared state
    - Evidence predicates, when present, are non-empty strings

    Note: The evidence predicate's internal syntax is NOT validated here
    (deferred to v1.1). This check only guards the structural invariants
    of the lifecycle block itself. The lifecycle: block is treated as
    orthogonal to the existing state_machine: block — both may coexist.

    Returns:
        Tuple of (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []

    for entity in appspec.domain.entities:
        lc = entity.lifecycle
        if lc is None:
            continue

        prefix = f"Entity '{entity.name}' lifecycle:"
        field_map = {f.name: f for f in entity.fields}

        # 1. status_field must reference a real field
        status_field = field_map.get(lc.status_field)
        if status_field is None:
            errors.append(
                f"{prefix} status_field '{lc.status_field}' is not a field on "
                f"entity '{entity.name}'"
            )
            enum_values: set[str] = set()
        elif status_field.type.kind != ir.FieldTypeKind.ENUM:
            errors.append(
                f"{prefix} status_field '{lc.status_field}' must be an enum field, "
                f"got '{status_field.type.kind.value}'"
            )
            enum_values = set()
        else:
            enum_values = set(status_field.type.enum_values or [])

        # 2. State names must match the enum's declared values
        #    (only when we were able to resolve the enum)
        if enum_values:
            for state in lc.states:
                if state.name not in enum_values:
                    errors.append(
                        f"{prefix} state '{state.name}' is not a declared value of "
                        f"enum field '{lc.status_field}' "
                        f"(expected one of: {sorted(enum_values)})"
                    )

        # 3. Order values must be unique across states
        orders_seen: dict[int, str] = {}
        for state in lc.states:
            if state.order in orders_seen:
                errors.append(
                    f"{prefix} duplicate order {state.order} on states "
                    f"'{orders_seen[state.order]}' and '{state.name}' — "
                    f"order values must be unique"
                )
            else:
                orders_seen[state.order] = state.name

        # 4. Transition from/to must reference declared states
        declared_states = {s.name for s in lc.states}
        for idx, tr in enumerate(lc.transitions):
            if tr.from_state not in declared_states:
                errors.append(
                    f"{prefix} transition #{idx} from_state '{tr.from_state}' "
                    f"is not a declared state"
                )
            if tr.to_state not in declared_states:
                errors.append(
                    f"{prefix} transition #{idx} to_state '{tr.to_state}' is not a declared state"
                )

            # 5. Evidence, when present, must be a non-empty string
            if tr.evidence is not None and not tr.evidence.strip():
                errors.append(
                    f"{prefix} transition {tr.from_state} -> {tr.to_state} "
                    f"has empty evidence predicate — omit the evidence clause "
                    f"if none is required"
                )

        # Optional: warn if both state_machine and lifecycle are present
        # with mismatched state lists. Treated as orthogonal, so this is
        # advisory only.
        if entity.state_machine is not None:
            sm_states = {state_name(s) for s in entity.state_machine.states}
            if sm_states and sm_states != declared_states:
                warnings.append(
                    f"{prefix} state_machine states {sorted(sm_states)} "
                    f"differ from lifecycle states {sorted(declared_states)} — "
                    f"these blocks are orthogonal but the mismatch may indicate "
                    f"they are out of sync"
                )

    return errors, warnings


def validate_fitness_repr_fields(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Warn if any entity lacks fitness.repr_fields.

    Part of the Agent-Led Fitness v1 methodology. v1 ships as a warning;
    v1.1 will promote this to an error. Entities without repr_fields are
    skipped by the fitness evaluator.

    Framework-synthetic entities (``domain == "platform"``, e.g. SystemHealth,
    AIJob, FeedbackReport) are exempt — they are code-generated and cannot
    carry a user-authored fitness block.
    """
    errors: list[str] = []
    warnings: list[str] = []
    for entity in appspec.domain.entities:
        # Skip framework-synthetic platform entities (generated from code)
        if entity.domain == "platform":
            continue
        if entity.fitness is None or not entity.fitness.repr_fields:
            warnings.append(
                f"Entity {entity.name!r}: no fitness.repr_fields declared — "
                f"fitness evaluation will skip this entity. Add a "
                f"`fitness:\n  repr_fields: [...]` block with domain-essential "
                f"fields."
            )
    return errors, warnings


def validate_storage_refs(
    appspec: ir.AppSpec,
    storage_defs: Mapping[str, object],
) -> tuple[list[str], list[str]]:
    """Validate that every `field foo: file storage=<name>` reference
    resolves to a `[storage.<name>]` block declared in dazzle.toml (#932).

    Also warns when `storage=<name>` is set on a non-`file` field —
    the binding is ignored everywhere else but it's a clear authoring
    mistake.

    Takes ``storage_defs`` separately because the AppSpec is built
    from DSL alone — the manifest is loaded by a different layer.
    Runtime call site is `dazzle_back.runtime.server` startup, where
    both surfaces are available.

    Returns:
        Tuple of (errors, warnings).
    """
    errors: list[str] = []
    warnings: list[str] = []
    declared = set(storage_defs)
    for entity in appspec.domain.entities:
        for field_spec in entity.fields:
            refs: tuple[str, ...] = getattr(field_spec, "storage", ()) or ()
            if not refs:
                continue
            for ref in refs:
                if ref not in declared:
                    hint = (
                        f" Available: {sorted(declared)}"
                        if declared
                        else " (no [storage.*] blocks declared in dazzle.toml)"
                    )
                    errors.append(
                        f"Entity {entity.name!r} field {field_spec.name!r}: "
                        f"storage={ref!r} does not resolve to a declared "
                        f"[storage.{ref}] block.{hint}"
                    )
            if field_spec.type.kind != ir.FieldTypeKind.FILE:
                rendered = "|".join(refs)
                warnings.append(
                    f"Entity {entity.name!r} field {field_spec.name!r}: "
                    f"storage={rendered!r} only applies to `file` typed fields; "
                    f"got type={field_spec.type.kind.value}. The binding "
                    f"will be ignored at runtime."
                )
    return errors, warnings
