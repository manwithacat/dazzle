"""Surface and experience validation.

Split verbatim from dazzle.core.validator per #1361.
"""

from .. import ir


def validate_surfaces(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """
    Validate all surfaces for semantic correctness.

    Checks:
    - Entity references exist (already done by linker, but check fields)
    - Surface fields match entity fields when entity_ref is set
    - `source=<pack>.<op>` field options resolve to a known API pack
      (#996 — fuzz-sweep caught fieldtest_hub referencing
      `companies_house_lookup.search_companies` with no pack declared;
      runtime silently swallowed the resolution failure and the
      autocomplete just rendered as a plain text input)
    - Actions have valid outcomes
    - Modes are appropriate for the surface structure

    Returns:
        Tuple of (errors, warnings)
    """
    errors = []
    warnings = []

    # Pre-resolve API pack metadata once. The list_packs() discovery
    # walks the api-kb directory, so do it lazily and cache. Empty
    # mapping on ImportError keeps validate functional in slim
    # installs (gate self-disables — typo-detection is best-effort).
    pack_ops_cache: dict[str, set[str]] | None = None

    def _resolve_pack_ops() -> dict[str, set[str]]:
        nonlocal pack_ops_cache
        if pack_ops_cache is None:
            try:
                from dazzle.api_kb import list_packs

                pack_ops_cache = {
                    p.name: {getattr(op, "name", str(op)) for op in p.operations}
                    for p in list_packs()
                }
            except Exception:
                pack_ops_cache = {}
        return pack_ops_cache

    for surface in appspec.surfaces:
        # Validate entity field matching
        if surface.entity_ref:
            entity = appspec.get_entity(surface.entity_ref)
            if entity:
                # Check that fields in surface sections match entity fields
                for section in surface.sections:
                    for element in section.elements:
                        if not entity.get_field(element.field_name):
                            errors.append(
                                f"Surface '{surface.name}' section '{section.name}' "
                                f"references non-existent field '{element.field_name}' "
                                f"from entity '{entity.name}'"
                            )

        # Validate field source= references resolve to a known API pack
        # AND a known operation on that pack. #996 — typos and dropped
        # packs would fail silently at runtime; the autocomplete just
        # rendered as a plain text input.
        for section in surface.sections:
            for element in section.elements:
                source_ref = element.options.get("source") if element.options else None
                if not source_ref or "." not in source_ref:
                    continue
                pack_name, op_name = source_ref.rsplit(".", 1)
                packs = _resolve_pack_ops()
                if not packs:
                    continue  # api_kb unavailable — skip the gate
                if pack_name not in packs:
                    errors.append(
                        f"Surface '{surface.name}' field '{element.field_name}' "
                        f"references source '{source_ref}' but no API pack "
                        f"named '{pack_name}' is declared. "
                        f"Known packs: {sorted(packs)}"
                    )
                elif op_name not in packs[pack_name]:
                    errors.append(
                        f"Surface '{surface.name}' field '{element.field_name}' "
                        f"references source '{source_ref}' but operation "
                        f"'{op_name}' is not defined on pack '{pack_name}'. "
                        f"Known ops: {sorted(packs[pack_name])}"
                    )

        # Validate search fields reference valid entity fields
        if surface.search_fields and surface.entity_ref:
            entity = appspec.get_entity(surface.entity_ref)
            if entity:
                for sf in surface.search_fields:
                    if not entity.get_field(sf):
                        warnings.append(
                            f"Surface '{surface.name}' search field '{sf}' "
                            f"does not exist on entity '{entity.name}'"
                        )

        # Warn if no sections — unless the surface is intentionally headless
        # (e.g. a framework-generated API-only surface whose UI lives in a
        # client-side widget).
        if not surface.sections and not getattr(surface, "headless", False):
            warnings.append(f"Surface '{surface.name}' has no sections defined")

        # Check mode consistency
        if surface.mode == ir.SurfaceMode.CREATE:
            if not surface.entity_ref:
                warnings.append(
                    f"Surface '{surface.name}' has mode 'create' but no entity reference"
                )
        elif surface.mode == ir.SurfaceMode.EDIT:
            if not surface.entity_ref:
                warnings.append(f"Surface '{surface.name}' has mode 'edit' but no entity reference")
        elif surface.mode == ir.SurfaceMode.VIEW:
            if not surface.entity_ref:
                warnings.append(f"Surface '{surface.name}' has mode 'view' but no entity reference")

    return errors, warnings


def validate_experiences(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """
    Validate all experiences for semantic correctness.

    Checks:
    - All steps are reachable from start step
    - No infinite loops without exit
    - Step kinds match targets
    - Transitions are valid

    Returns:
        Tuple of (errors, warnings)
    """
    errors = []
    warnings = []

    for experience in appspec.experiences:
        # Check for empty experiences
        if not experience.steps:
            errors.append(f"Experience '{experience.name}' has no steps")
            continue

        # Build reachability graph
        reachable = set()
        to_visit = {experience.start_step}

        while to_visit:
            step_name = to_visit.pop()
            if step_name in reachable:
                continue
            reachable.add(step_name)

            step = experience.get_step(step_name)
            if step:
                for transition in step.transitions:
                    to_visit.add(transition.next_step)

        # Check for unreachable steps
        all_steps = {step.name for step in experience.steps}
        unreachable = all_steps - reachable
        if unreachable:
            warnings.append(f"Experience '{experience.name}' has unreachable steps: {unreachable}")

        # Check step consistency
        for step in experience.steps:
            # Validate step kind matches target
            if step.kind == ir.StepKind.SURFACE:
                if not step.surface and not step.entity_ref:
                    errors.append(
                        f"Experience '{experience.name}' step '{step.name}' "
                        f"has kind 'surface' but no surface or entity target"
                    )
            elif step.kind == ir.StepKind.INTEGRATION:
                if not step.integration or not step.action:
                    errors.append(
                        f"Experience '{experience.name}' step '{step.name}' "
                        f"has kind 'integration' but missing integration or action"
                    )

            # Warn about steps with no transitions — but only if the step
            # is NOT the last defined step (terminal steps at the end of a
            # flow are expected, e.g. "complete", "done", "success").
            if not step.transitions:
                is_last = step == experience.steps[-1] if experience.steps else False
                if not is_last:
                    warnings.append(
                        f"Experience '{experience.name}' step '{step.name}' "
                        f"has no transitions (terminal step)"
                    )

            # Validate saves_to format
            if step.saves_to:
                st_parts = step.saves_to.split(".", 1)
                if len(st_parts) != 2 or st_parts[0] != "context":
                    errors.append(
                        f"Experience '{experience.name}' step '{step.name}' "
                        f"saves_to must be 'context.<varname>', got '{step.saves_to}'"
                    )
                elif experience.context:
                    ctx_names = {cv.name for cv in experience.context}
                    if st_parts[1] not in ctx_names:
                        errors.append(
                            f"Experience '{experience.name}' step '{step.name}' "
                            f"saves_to references unknown context variable '{st_parts[1]}'"
                        )

            # Validate prefill references
            if step.prefills and experience.context:
                ctx_names = {cv.name for cv in experience.context}
                for pf in step.prefills:
                    if not pf.expression.startswith('"'):
                        pf_parts = pf.expression.split(".")
                        if pf_parts and pf_parts[0] == "context" and len(pf_parts) >= 2:
                            if pf_parts[1] not in ctx_names:
                                warnings.append(
                                    f"Experience '{experience.name}' step '{step.name}' "
                                    f"prefill references unknown context variable "
                                    f"'{pf_parts[1]}'"
                                )

            # Warn about when guard on terminal steps
            if step.when and not step.transitions:
                warnings.append(
                    f"Experience '{experience.name}' step '{step.name}' "
                    f"has a 'when' guard but no transitions to skip to"
                )

        # Validate context variable declarations
        if experience.context:
            seen_names: set[str] = set()
            for cv in experience.context:
                if cv.name in seen_names:
                    errors.append(
                        f"Experience '{experience.name}' has duplicate context variable '{cv.name}'"
                    )
                seen_names.add(cv.name)

    return errors, warnings
