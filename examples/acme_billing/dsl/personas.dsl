module acme_billing.personas

persona admin "Administrator":
  description: "Platform administrator — full cross-org access (break-glass)"
  goals: "Manage organizations", "Audit access"
  proficiency: expert
  default_workspace: billing

persona org_owner "Organization Owner":
  description: "Owns one organization — full access within that org only"
  goals: "Manage projects", "Review invoices"
  proficiency: expert
  default_workspace: billing
  # WI N: job desks first — not auto entity-list soup
  uses nav owner_nav

persona auditor "Auditor":
  description: "Read-only reviewer scoped to one organization"
  goals: "Review invoices and projects", "Verify compliance"
  proficiency: intermediate
  default_workspace: billing
  uses nav auditor_nav

persona project_member "Project Member":
  description: "Works on assigned projects only"
  goals: "View assigned projects", "View project invoices"
  proficiency: intermediate
  # Answer-first landing (product maturity): job surface, not bare entity list
  default_workspace: my_work
  uses nav member_nav

persona external_contractor "External Contractor":
  description: "Limited outside collaborator — non-sensitive data on assigned projects"
  goals: "View assigned non-sensitive project data"
  proficiency: novice
  default_workspace: my_work
  uses nav contractor_nav

# Curated sidebars: workspace destinations only (WI primary N).
# Auto-discover still lists every entity; explicit nav keeps the shell job-first.

nav owner_nav:
  group "Work":
    billing
    projects_home
    invoices_home
    team_home
    orgs_home
    membership_ops
    sensitive_review
    collections_ops

nav auditor_nav:
  group "Review":
    billing
    invoices_home
    projects_home
    team_home
    orgs_home
    membership_ops
    sensitive_review
    collections_ops

nav member_nav:
  group "My desk":
    my_work
    projects_home
    invoices_home
    collections_ops

nav contractor_nav:
  group "Assigned":
    my_work
    projects_home
