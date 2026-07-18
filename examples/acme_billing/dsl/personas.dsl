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

persona auditor "Auditor":
  description: "Read-only reviewer scoped to one organization"
  goals: "Review invoices and projects", "Verify compliance"
  proficiency: intermediate
  default_workspace: billing

persona project_member "Project Member":
  description: "Works on assigned projects only"
  goals: "View assigned projects", "View project invoices"
  proficiency: intermediate
  # Answer-first landing (product maturity): job surface, not bare entity list
  default_workspace: my_work

persona external_contractor "External Contractor":
  description: "Limited outside collaborator — non-sensitive data on assigned projects"
  goals: "View assigned non-sensitive project data"
  proficiency: novice
  default_workspace: my_work
