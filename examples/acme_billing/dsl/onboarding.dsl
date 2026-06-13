module acme_billing.guides

use acme_billing.core

# Per-persona onboarding for Acme Billing (multi-tenant). Only the
# org_owner creates; auditor / project_member / external_contractor
# are read-only, so their guides orient (dismiss-only, no CTAs to
# create surfaces — RBAC concordance would reject those). Targets are
# surfaces; concordance + audience permit are enforced at validate.

# ─── Organisation Owner journey ───────────────────────────────────

guide org_owner_onboarding "Set up your organisation's billing":
  audience: persona = org_owner

  step create_project:
    kind: empty_state
    target: surface.project_list
    title: "Create a project"
    body: "Projects group the work you bill for. Create one and assign the team who'll deliver it."
    cta_label: "New Project"
    cta_target: surface.project_create
    complete_on: event entity.Project.created

  step track_invoices:
    kind: inline_card
    target: surface.invoice_list
    title: "Track every invoice"
    body: "Invoices for your org's projects land here. Open one to review it or mark it sensitive."
    complete_on: dismiss

  step manage_team:
    kind: banner
    target: surface.user_list
    title: "Manage your team"
    body: "Add the people in your organisation and assign them to the projects they work on."
    complete_on: dismiss

  step_order: [create_project, track_invoices, manage_team]

  on_complete:
    redirect: surface.project_list

# ─── Auditor journey (read-only) ──────────────────────────────────

guide auditor_onboarding "Review for compliance":
  audience: persona = auditor

  step all_projects:
    kind: spotlight
    target: surface.project_list
    title: "Every project in the org"
    body: "Start here to see all projects, then open one to review its invoices and assignments."
    placement: center
    complete_on: dismiss

  step check_invoices:
    kind: inline_card
    target: surface.invoice_list
    title: "Check the invoices"
    body: "You can see every invoice, including sensitive ones — review amounts, status, and the sensitivity flag."
    complete_on: dismiss

  step_order: [all_projects, check_invoices]

  on_complete:
    redirect: surface.project_list

# ─── Project Member journey (read-only) ───────────────────────────

guide project_member_onboarding "Find your project work":
  audience: persona = project_member

  step your_projects:
    kind: spotlight
    target: surface.project_list
    title: "Your assigned projects"
    body: "These are the projects you're a member of. Open one to see its details and related invoices."
    placement: center
    complete_on: dismiss

  step project_invoices:
    kind: inline_card
    target: surface.invoice_list
    title: "See the project invoices"
    body: "You can review the non-sensitive invoices for your projects — handy for tracking what's been billed."
    complete_on: dismiss

  step_order: [your_projects, project_invoices]

  on_complete:
    redirect: surface.project_list

# ─── External Contractor journey (read-only) ──────────────────────

guide external_contractor_onboarding "Review shared invoices":
  audience: persona = external_contractor

  step shared_invoices:
    kind: spotlight
    target: surface.invoice_list
    title: "Invoices shared with you"
    body: "As an external collaborator, you can review the non-sensitive invoices for the org you're working with."
    placement: center
    complete_on: dismiss

  step open_detail:
    kind: inline_card
    target: surface.invoice_detail
    title: "Open an invoice for detail"
    body: "Click any invoice to see its line items and status — everything you need to reconcile your work."
    complete_on: dismiss

  step_order: [shared_invoices, open_detail]

  on_complete:
    redirect: surface.invoice_list
