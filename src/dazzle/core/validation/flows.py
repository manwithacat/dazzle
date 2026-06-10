"""Atomic flow, transition, approval, SLA, and process-step validation.

Split verbatim from dazzle.core.validator per #1361.
"""

from .. import ir


def validate_atomic_flows(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Validate atomic-flow declarations (#1228 Phase 3c).

    Checks that each flow:
      - has at least one create
      - has unique input names
      - has unique entity targets across creates (one create per entity in MVP)
      - every create targets a known entity
      - every assignment field exists on the target entity
      - every ``input.X`` reference names a declared input
      - every ``above.E.F`` reference points at an entity created earlier
        in this flow (no forward refs) and the field is ``id`` (the only
        always-derivable field at this slice)
      - permit_execute is non-empty
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not appspec.atomic_flows:
        return errors, warnings

    warnings.append(
        f"[Preview] {len(appspec.atomic_flows)} atomic flow(s) defined. "
        "`create` + `update` steps execute in a single transaction with per-step "
        "scope enforcement (#1313, ADR-0029). Pending: in-transaction audit + "
        "matrix/conformance/specs visibility."
    )

    entity_map = {e.name: e for e in appspec.domain.entities}

    for flow in appspec.atomic_flows:
        prefix = f"atomic flow '{flow.name}'"

        if not flow.steps:
            errors.append(f"{prefix}: must declare at least one `create` or `update` step.")
        if not flow.permit_execute:
            errors.append(f"{prefix}: must declare `permit: execute: role(...)`.")

        # Input uniqueness
        input_names: set[str] = set()
        for inp in flow.inputs:
            if inp.name in input_names:
                errors.append(f"{prefix}: duplicate input '{inp.name}'.")
            input_names.add(inp.name)

        # Track entities created so far (left-to-right) for above-ref validation.
        seen_entities: set[str] = set()

        def _check_ref(
            value: ir.FlowFieldValue,
            ctx: str,
            _seen: set[str],
            _prefix: str,
            _inputs: set[str],
        ) -> None:
            """Validate an input/above reference inside a step.

            ``_prefix`` / ``_inputs`` are passed explicitly (not closed over)
            so the helper doesn't bind the enclosing loop variables.
            """
            if value.kind == ir.FlowFieldValueKind.INPUT_REF:
                if value.input_name not in _inputs:
                    errors.append(
                        f"{_prefix}: {ctx} references undeclared input '{value.input_name}'."
                    )
            elif value.kind == ir.FlowFieldValueKind.ABOVE_REF:
                if value.above_entity not in _seen:
                    errors.append(
                        f"{_prefix}: {ctx} references above.{value.above_entity}."
                        f"{value.above_field} but '{value.above_entity}' is not "
                        f"created earlier in this flow."
                    )
                if value.above_field != "id":
                    errors.append(
                        f"{_prefix}: {ctx} uses above.{value.above_entity}."
                        f"{value.above_field}; only '.id' is supported in this release."
                    )

        # #1315 — validate `above`-ref resolution against the EXECUTION order
        # (the FK-derived order when set, else declared). A create-DAG the author
        # wrote out-of-order is reordered parent-before-child by the linker, so
        # its forward `above`-refs are legal; a flow with no derived order is
        # checked in declared order (an `above`-ref to a not-yet-created entity
        # is still an error there).
        if flow.derived_step_order is not None:
            ordered_steps = [flow.steps[i] for i in flow.derived_step_order]
        else:
            ordered_steps = list(flow.steps)
        for step in ordered_steps:
            is_update = isinstance(step, ir.FlowUpdate)
            kind = "update" if is_update else "create"

            # One create per entity per flow (MVP). Updates may target an
            # entity freely (incl. one a create also touches), so they are
            # exempt from the uniqueness check.
            if not is_update and step.entity in seen_entities:
                errors.append(
                    f"{prefix}: create target '{step.entity}' appears more than once "
                    f"(one create per entity per flow in this release)."
                )

            target = entity_map.get(step.entity)
            if target is None:
                errors.append(f"{prefix}: {kind} targets unknown entity '{step.entity}'.")
                if not is_update:
                    seen_entities.add(step.entity)
                continue

            # An update's target row-selector must resolve to an existing row.
            # (Direct isinstance so the type-checker narrows `step` to FlowUpdate.)
            if isinstance(step, ir.FlowUpdate):
                _check_ref(
                    step.target, f"update {step.entity} target", seen_entities, prefix, input_names
                )

            target_fields = {f.name for f in target.fields}
            for field_name, value in step.assignments.items():
                if field_name not in target_fields:
                    errors.append(
                        f"{prefix}: {kind} {step.entity} assigns to unknown field '{field_name}'."
                    )
                _check_ref(
                    value, f"{kind} {step.entity}.{field_name}", seen_entities, prefix, input_names
                )

            if not is_update:
                seen_entities.add(step.entity)

        # #1318 / ADR-0031 — flow-level aggregate invariants. Each invariant
        # asserts `<agg_fn>(<entity>.<field> where <filter>) <op> <rhs>` at
        # commit; here we statically check its references resolve and that it
        # names a lockable anchor row.
        _NUMERIC_KINDS = {
            ir.FieldTypeKind.INT,
            ir.FieldTypeKind.FLOAT,
            ir.FieldTypeKind.DECIMAL,
            ir.FieldTypeKind.MONEY,
        }
        for inv in flow.invariants:
            inv_prefix = f"{prefix}: invariant {inv.agg_fn}({inv.entity}...)"

            target = entity_map.get(inv.entity)
            if target is None:
                errors.append(f"{inv_prefix}: unknown entity '{inv.entity}'.")
                continue

            target_field_map = {f.name: f for f in target.fields}

            # sum requires an existing numeric field; count takes no field.
            if inv.agg_fn == ir.FlowAggregateFn.SUM:
                fld = target_field_map.get(inv.field) if inv.field else None
                if fld is None:
                    errors.append(
                        f"{inv_prefix}: sum field '{inv.field}' does not exist on '{inv.entity}'."
                    )
                elif fld.type.kind not in _NUMERIC_KINDS:
                    errors.append(
                        f"{inv_prefix}: sum field '{inv.field}' on '{inv.entity}' is "
                        f"not numeric (got {fld.type.kind})."
                    )

            # The load-bearing rejection: an aggregate with no lockable anchor.
            if inv.anchor_entity is None or inv.anchor_input is None:
                errors.append(
                    f"{inv_prefix}: unanchored aggregate invariant: needs a "
                    f"`<fk> = input.<name>` filter term naming a lockable anchor "
                    f"row (see ADR-0031)."
                )
            elif inv.anchor_input not in input_names:
                errors.append(
                    f"{inv_prefix}: anchor references undeclared input '{inv.anchor_input}'."
                )

            # Filter columns must exist on the target entity (allow the `_id`
            # FK-suffix spelling, matching the column-naming convention).
            for column, _kind, _value in inv.raw_filter:
                if column not in target_field_map and (column + "_id") not in target_field_map:
                    errors.append(
                        f"{inv_prefix}: filter references unknown column '{column}' "
                        f"on '{inv.entity}'."
                    )

            # RHS: literal needs no check; the field form must resolve to a
            # numeric field on the named input's referenced entity.
            rhs = inv.rhs
            if rhs.anchor_input is not None:
                rhs_input = next((i for i in flow.inputs if i.name == rhs.anchor_input), None)
                if rhs_input is None:
                    errors.append(
                        f"{inv_prefix}: RHS references undeclared input '{rhs.anchor_input}'."
                    )
                else:
                    rhs_entity_name = rhs_input.type.ref_entity
                    rhs_entity = entity_map.get(rhs_entity_name) if rhs_entity_name else None
                    if rhs_entity is None:
                        errors.append(
                            f"{inv_prefix}: RHS input '{rhs.anchor_input}' does not "
                            f"reference a known entity."
                        )
                    else:
                        rhs_field_map = {f.name: f for f in rhs_entity.fields}
                        rhs_field = (
                            rhs_field_map.get(rhs.anchor_field) if rhs.anchor_field else None
                        )
                        if rhs_field is None:
                            errors.append(
                                f"{inv_prefix}: RHS field '{rhs.anchor_field}' does not "
                                f"exist on '{rhs_entity.name}'."
                            )
                        elif rhs_field.type.kind not in _NUMERIC_KINDS:
                            errors.append(
                                f"{inv_prefix}: RHS field '{rhs.anchor_field}' on "
                                f"'{rhs_entity.name}' is not numeric "
                                f"(got {rhs_field.type.kind})."
                            )
            elif rhs.literal is None:
                errors.append(f"{inv_prefix}: invariant RHS is empty.")

    return errors, warnings


def validate_transition_invocations(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Validate transition ``invoke <flow>(...)`` cross-references (#1319, ADR-0032).

    Slice A surface checks (the shared-transaction runtime wiring is Slice B):

    - the invoked flow exists in ``appspec.atomic_flows``;
    - every binding names a real input of that flow;
    - every *required* flow input is bound;
    - a ``self`` binding targets a flow input that is a ``ref`` to the entity that
      owns the state machine (a light shape check — the transitioning row is what
      ``self`` resolves to).
    """
    errors: list[str] = []
    warnings: list[str] = []

    flows_by_name = {f.name: f for f in (appspec.atomic_flows or [])}

    for entity in appspec.domain.entities or []:
        sm = entity.state_machine
        if sm is None:
            continue
        for t in sm.transitions:
            inv = t.invoke_flow
            if inv is None:
                continue
            prefix = (
                f"entity '{entity.name}' transition {t.from_state} -> {t.to_state}: "
                f"invoke {inv.flow_name}"
            )
            # v1 limit (ADR-0032 Slice B): the shared-tx path reads the row back on
            # the flow connection with a plain SELECT, which does not reproduce the
            # soft-delete / temporal / subtype-JOIN logic the normal read applies.
            # Reject invoke on those entity types until the shared read handles them.
            if getattr(entity, "soft_delete", None) or getattr(entity, "temporal", None):
                errors.append(
                    f"{prefix} on a soft-delete/temporal entity is not supported in this "
                    "release (transition invoke is v1-limited to plain entities)."
                )
            if getattr(entity, "subtype_of", None) or getattr(entity, "subtypes", None):
                errors.append(
                    f"{prefix} on a subtype-polymorphic entity is not supported in this "
                    "release (transition invoke is v1-limited to plain entities)."
                )
            # A guarded effect needs a principal; an `auto` (scheduled/system)
            # transition has none, so reject `invoke` on it at validate time
            # (ADR-0032 — the service-principal story for system transitions is
            # deferred). A manual (user-triggered) transition carries the PUT caller.
            if t.trigger == ir.TransitionTrigger.AUTO:
                errors.append(
                    f"{prefix} on an `auto` transition: a transition-invoked atomic flow "
                    "needs an authenticated principal, which an auto/scheduled transition "
                    "lacks (ADR-0032 — use a manual transition)."
                )
            flow = flows_by_name.get(inv.flow_name)
            if flow is None:
                errors.append(f"{prefix} references unknown atomic flow '{inv.flow_name}'.")
                continue

            flow_inputs = {fi.name: fi for fi in flow.inputs}
            bound = {b.flow_input for b in inv.bindings}

            for b in inv.bindings:
                if b.flow_input not in flow_inputs:
                    errors.append(
                        f"{prefix} binds unknown input '{b.flow_input}' "
                        f"(flow '{inv.flow_name}' has {sorted(flow_inputs)})."
                    )
                elif b.source_kind == ir.InvokeSourceKind.SELF:
                    # `self` is the transitioning row → the bound input should be a
                    # ref to this entity.
                    fi = flow_inputs[b.flow_input]
                    ref_entity = getattr(fi.type, "ref_entity", None)
                    if ref_entity is not None and ref_entity != entity.name:
                        errors.append(
                            f"{prefix} binds `self` to input '{b.flow_input}', which is a "
                            f"ref {ref_entity}, not ref {entity.name} (the transitioning entity)."
                        )
                elif b.source_kind == ir.InvokeSourceKind.INPUT and not b.source_name:
                    # An `input.<name>` binding must carry the transition input name
                    # (the runtime resolves the value from it in Slice B).
                    errors.append(
                        f"{prefix} binds input '{b.flow_input}' from a transition input "
                        "but names no source (expected `input.<name>`)."
                    )

            for name, fi in flow_inputs.items():
                if fi.required and name not in bound:
                    errors.append(f"{prefix} does not bind required input '{name}'.")

    return errors, warnings


def validate_approvals(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Validate approval definitions and warn about runtime status."""
    errors: list[str] = []
    warnings: list[str] = []

    if not appspec.approvals:
        return errors, warnings

    entity_names = {e.name for e in appspec.domain.entities}

    warnings.append(
        f"[Preview] {len(appspec.approvals)} approval(s) defined. "
        "Approval gates are not yet enforced at runtime."
    )

    for ap in appspec.approvals:
        if ap.entity and ap.entity not in entity_names:
            errors.append(f"Approval '{ap.name}' references unknown entity '{ap.entity}'.")
        if not ap.approver_role:
            warnings.append(f"Approval '{ap.name}' has no approver_role specified.")
        if not ap.outcomes:
            warnings.append(f"Approval '{ap.name}' has no outcomes defined.")

    return errors, warnings


def validate_slas(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Validate SLA definitions and warn about runtime status."""
    errors: list[str] = []
    warnings: list[str] = []

    if not appspec.slas:
        return errors, warnings

    entity_names = {e.name for e in appspec.domain.entities}

    warnings.append(
        f"[Preview] {len(appspec.slas)} SLA(s) defined. "
        "SLA monitoring is not yet enforced at runtime."
    )

    for sla in appspec.slas:
        if sla.entity and sla.entity not in entity_names:
            errors.append(f"SLA '{sla.name}' references unknown entity '{sla.entity}'.")
        if not sla.tiers:
            warnings.append(f"SLA '{sla.name}' has no tiers defined.")

    return errors, warnings


def validate_process_step_service_refs(
    appspec: ir.AppSpec,
) -> tuple[list[str], list[str]]:
    """Warn when a process step references a service that doesn't exist.

    Found in examples/pra during /fuzz: `service: auto_assign_task` on a
    process step where no such domain_service is declared.
    """
    errors: list[str] = []
    warnings: list[str] = []

    domain_service_names = {s.name for s in appspec.domain_services}
    for process in appspec.processes:
        for step in process.steps:
            if step.kind != ir.ProcessStepKind.SERVICE:
                continue
            if step.service and step.service not in domain_service_names:
                warnings.append(
                    f"Process {process.name!r} step {step.name!r}: "
                    f"service {step.service!r} is not declared in "
                    f"`domain_services`. The step will fail at runtime."
                )
    return errors, warnings
