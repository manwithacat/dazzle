"""SLA and process-step validation.

Split verbatim from dazzle.core.validator per #1361.
"""

from .. import ir


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

    Found in fixtures/pra during /fuzz: `service: auto_assign_task` on a
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
