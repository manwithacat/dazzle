# Stem: Story-driven job workspaces (acme_billing)

## Claim

Billing workspace is portfolio metrics + invoice queue before entity lists.

## Reconstruct

- admin/org_owner/auditor default: billing = metrics + invoice queue + org/project/membership lists.
- project_member/contractor stay on scoped surfaces, not full billing.
- Organization hub related projects and project hub related invoices/memberships
  are **pull queues**, not warehouse tables (ST-006/008/011).
- Invoice list dual open `Invoice via id | Project via project` (cycle 1544
  story_walk) — inspect the invoice or hop to the project hub.
- Project list dual open `Project via id | Organization via org` (cycle 1574
  journey_dogfood) — project hub first; secondary org hub for tenant context
  (ST-001/003/006).
- User list dual open `User via id | Organization via org` (cycle 1574
  journey_dogfood) — user hub first; secondary org hub for roster context.
- Membership list triple open `Membership via id | User via user | Project via
  project` (cycle 1585 journey_dogfood) — membership hub, member context,
  parent project hub.

## Not this

- Persona lands on a bare entity list when the job is triage, review, or oversight.
- Story `given:` workspace names that disagree with `default_workspace`.
- Hub related rosters as dense tables when the job is pull-next review.

## Expressions

- `dsl/` workspaces + personas; `docs/guides/story-to-composition.md`
