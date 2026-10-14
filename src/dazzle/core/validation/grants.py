"""Grant-schema relation clause validation (flense ship U).

Ship Q made ``/_dazzle/grants`` enforce ``approved_by:``, ``confirmation:``,
``expiry:`` and ``max_duration:``. These lints flag declarations the routes
still cannot honour: clauses that contradict each other, an approver list on a
relation that never goes through approval, and presentation text nothing renders.
"""

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
