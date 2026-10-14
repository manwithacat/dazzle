"""Grant-schema relation clause validation (flense ship U).

Ship Q made ``/_dazzle/grants`` enforce ``approved_by:``, ``confirmation:``,
``expiry:`` and ``max_duration:``. These lints flag declarations the routes
still cannot honour: clauses that contradict each other, an approver list on a
relation that never goes through approval, and presentation text nothing renders.

Flense ship AC adds ``validate_permit_grant_checks``: ``has_grant(...)`` in a
``permit:``/``forbid:`` rule parses, but the permit gate never resolves the
caller's grants, so the term is always false.
"""

from typing import Any

from .. import ir


def validate_grant_relation_clauses(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Warn on grant relation clauses the grant routes ignore.

    - ``expiry: none`` with ``max_duration:`` — the routes reject any
      ``expires_at`` under ``expiry: none``, so the cap is never applied.
    - ``approved_by:`` with ``approval:`` other than ``required`` — only a
      pending grant is approved, and only ``approval: required`` creates one.
    - ``principal_label:`` / ``revoke_verb:`` — presentation text no framework
      grant UI renders yet (see the flense ship Q CHANGELOG entry).

    Returns:
        Tuple of (errors, warnings)
    """
    warnings: list[str] = []
    for schema in appspec.grant_schemas:
        for rel in schema.relations:
            label = f"grant_schema '{schema.name}' relation '{rel.name}'"
            if rel.expiry == ir.GrantExpiryMode.NONE and rel.max_duration is not None:
                warnings.append(
                    f"W_GRANT_EXPIRY_CONTRADICTION: {label}: `expiry: none` with "
                    f"`max_duration:` — no grant carries an expiry, so the cap is never "
                    f"applied; drop `max_duration:` or use `expiry: required`"
                )
            if rel.approved_by is not None and rel.approval != ir.GrantApprovalMode.REQUIRED:
                warnings.append(
                    f"W_GRANT_APPROVER_UNUSED: {label}: `approved_by:` declared with "
                    f"`approval: {rel.approval.value}` — grants are active on creation, so "
                    f"the approvers are never consulted; drop `approved_by:` or use "
                    f"`approval: required`"
                )
            presentation = [
                f"`{clause}`"
                for clause, value in (
                    ("principal_label:", rel.principal_label),
                    ("revoke_verb:", rel.revoke_verb),
                )
                if value is not None
            ]
            if presentation:
                warnings.append(
                    f"W_DECLARED_NOT_READ: {label}: {'/'.join(presentation)} declared but "
                    f"not read by the runtime (presentation text no framework grant UI "
                    f"renders yet); see CHANGELOG, flense ship Q"
                )
    return [], warnings


def _has_grant_relations(expr: Any) -> list[str]:
    """Relations named by ``has_grant(...)`` terms anywhere in a ConditionExpr."""
    if expr is None:
        return []
    grant_check = getattr(expr, "grant_check", None)
    found = [grant_check.relation] if grant_check is not None else []
    return (
        found
        + _has_grant_relations(getattr(expr, "left", None))
        + _has_grant_relations(getattr(expr, "right", None))
    )


def validate_permit_grant_checks(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Warn on ``has_grant(...)`` in an entity's ``permit:``/``forbid:`` rules.

    The permit gate (``render.access_evaluator``) evaluates a ``has_grant`` term
    against grants the runtime never loads into the access context, so the term
    is always false: a permit it guards admits nobody through it, and a forbid it
    guards never fires. ``has_grant`` is honoured in transition guards and in a
    relation's ``granted_by:``/``approved_by:`` (see CHANGELOG, flense ship AC).

    Returns:
        Tuple of (errors, warnings)
    """
    warnings: list[str] = []
    for entity in appspec.domain.entities:
        access = entity.access
        if access is None:
            continue
        for rule in access.permissions:
            relations = _has_grant_relations(rule.condition)
            if not relations:
                continue
            terms = ", ".join(f'`has_grant("{r}", …)`' for r in dict.fromkeys(relations))
            effect = getattr(rule.effect, "value", str(rule.effect))
            warnings.append(
                f"W_DECLARED_NOT_READ: entity '{entity.name}' {effect} "
                f"{rule.operation.value}: {terms} declared but not read by the runtime "
                f"(the permit gate does not resolve the caller's grants, so the term is "
                f"always false); see CHANGELOG, flense ship AC"
            )
    return [], warnings
