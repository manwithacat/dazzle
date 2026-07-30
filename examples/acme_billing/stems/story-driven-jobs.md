# Stem: Story-driven job workspaces (acme_billing)

## Claim

Billing workspace is portfolio metrics + invoice queue before entity lists.

## Reconstruct

- admin/org_owner/auditor default: billing = metrics + invoice queue + org/project/membership lists.
- project_member/contractor stay on scoped surfaces, not full billing.
- Organization hub related projects and project hub related invoices/memberships
  are **pull queues**, not warehouse tables (ST-006/008/011).

## Not this

- Persona lands on a bare entity list when the job is triage, review, or oversight.
- Story `given:` workspace names that disagree with `default_workspace`.
- Hub related rosters as dense tables when the job is pull-next review.

## Expressions

- `dsl/` workspaces + personas; `docs/guides/story-to-composition.md`
