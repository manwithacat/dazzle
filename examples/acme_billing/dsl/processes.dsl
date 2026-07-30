# Process densify from domain process_candidates (improve domain_lifecycle_priors).
# Candidate: approval_flow — Invoice submit/approve handoff across personas.
# Gold Invoice has no status enum yet; trigger on created (grammar: created|status)
# so org_owner review is durable, not an informal chat after admin create.

module acme_billing.processes

use acme_billing.entities

# Org owner reviews a newly created invoice so multi-persona billing is an
# explicit handoff (admin creates; org_owner owns the commercial review).
# Domain process_candidate `approval_flow` (requester/approver) maps to
# admin create → org_owner approve; `assignment` is the same ownership claim.
process invoice_owner_review "Org owner reviews new invoice":
  trigger:
    when: entity Invoice created

  input:
    invoice_id: uuid required

  steps:
    - step owner_review:
        human_task:
          title: "Review newly created invoice"
          assignee_role: org_owner
          form:
            review_ok: bool required
            notes: text
          timeout: 4h

  timeout: 48h
