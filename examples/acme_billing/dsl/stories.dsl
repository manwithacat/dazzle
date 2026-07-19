module acme_billing.stories

# =============================================================================
# ACME BILLING — RBAC narratives + journey-bound portfolio stories
# =============================================================================

story ST-001 "Org owner manages projects within their organization":
  status: accepted
  executed_by: surface.project_create
  persona: org_owner
  trigger: form_submitted
  entities: [Project, Organization]

  given:
    - "Org owner is authenticated and belongs to the Acme organization"
    - "Acme and Globex organizations both exist"

  when:
    - "Org owner creates a project"

  then:
    - "Project is created with org set to Acme"
    - "Org owner can list only projects belonging to Acme"
    - "Org owner cannot see projects belonging to Globex"

story ST-002 "Auditor reviews invoices but cannot modify them":
  status: accepted
  executed_by: surface.invoice_list
  persona: auditor
  trigger: user_click
  entities: [Invoice, Project]

  given:
    - "Auditor is authenticated and scoped to the Acme organization"
    - "Multiple invoices exist for projects under Acme"

  when:
    - "Auditor lists invoices for an Acme project"

  then:
    - "Auditor can read all invoices within Acme (including sensitive ones)"
    - "Auditor cannot create, update, or delete any invoice"

story ST-003 "Project member sees only their assigned projects":
  status: accepted
  executed_by: surface.project_list
  persona: project_member
  trigger: user_click
  entities: [Project, Membership]

  given:
    - "Project member is authenticated"
    - "Project member has a Membership record linking them to Project Alpha"
    - "Project Beta exists but has no Membership for this project member"

  when:
    - "Project member lists available projects"

  then:
    - "Project Alpha is visible to the project member"
    - "Project Beta is not visible to the project member"

story ST-004 "External contractor views non-sensitive invoices within their organization":
  status: accepted
  executed_by: surface.invoice_list
  persona: external_contractor
  trigger: user_click
  entities: [Invoice]

  given:
    - "External contractor is authenticated and belongs to the Acme organization"
    - "Acme has two invoices: one with sensitive = false, one with sensitive = true"
    - "Globex organization also has invoices (both sensitive and non-sensitive)"

  when:
    - "External contractor lists invoices"

  then:
    - "Non-sensitive Acme invoices are visible to the external contractor"
    - "Sensitive Acme invoice is hidden from the external contractor"
    - "All Globex invoices are hidden — scope predicate is project.org = current_user.org, so cross-org rows are excluded regardless of sensitivity"

  unless:
    - "Invoice has sensitive = true":
        then: "Invoice is excluded from the result set"

story ST-005 "Admin has cross-organization access":
  status: accepted
  narrative_only: true
  persona: admin
  trigger: user_click
  entities: [Organization, Project, Invoice, User, Membership]

  given:
    - "Admin is authenticated"
    - "Both Acme and Globex organizations exist with their respective projects and invoices"

  when:
    - "Admin lists organizations, projects, and invoices"

  then:
    - "Admin can see all Acme data"
    - "Admin can see all Globex data"
    - "Admin is not restricted to any single organization scope"

# --- Journey-bound portfolio stories (agent-first dogfood) ---

story ST-006 "Org owner browses projects and opens a project hub":
  status: accepted
  executed_by: surface.project_list
  persona: org_owner
  trigger: user_click
  entities: [Project, Invoice]
  given:
    - "Org owner is on the billing workspace"
    - "Org owner has list permission on Project within their organization"
  then:
    - "Org owner sees projects scoped to their organization"
    - "Row open hops to Project detail with related invoices and memberships"

story ST-007 "Org owner reviews invoices from the portfolio queue into project context":
  status: accepted
  executed_by: surface.invoice_list
  persona: org_owner
  trigger: user_click
  entities: [Invoice, Project]
  given:
    - "Org owner is on the billing workspace"
    - "Invoices exist for projects under the org"
  then:
    - "Portfolio metrics and open_invoices queue surface recent billing work"
    - "Invoice row open hops to the parent Project hub via project FK"

story ST-008 "Auditor opens project hub for read-only invoice review":
  status: accepted
  executed_by: surface.project_detail
  persona: auditor
  trigger: user_click
  entities: [Project, Invoice]
  given:
    - "Auditor is authenticated and scoped to the organization"
  then:
    - "Project hub shows related invoices including sensitive ones"
    - "Auditor cannot create, update, or delete invoices"

story ST-009 "Project member sees only assigned projects and non-sensitive invoices":
  status: accepted
  executed_by: surface.project_list
  persona: project_member
  trigger: user_click
  entities: [Project, Membership, Invoice]
  given:
    - "Project member has Membership on Project Alpha only"
  then:
    - "Project Alpha is visible; unassigned projects are not"
    - "Opening the project hub shows only non-sensitive invoices per scope"

story ST-010 "External contractor reviews non-sensitive invoices via project hub":
  status: accepted
  executed_by: surface.invoice_list
  persona: external_contractor
  trigger: user_click
  entities: [Invoice, Project]
  given:
    - "External contractor is scoped to their organization"
    - "Sensitive and non-sensitive invoices exist"
  then:
    - "Only non-sensitive org invoices appear"
    - "Row open hops to Project hub; sensitive rows stay excluded by scope"

story ST-011 "Admin reviews cross-org portfolio from organization hubs":
  status: accepted
  executed_by: surface.organization_list
  persona: admin
  trigger: user_click
  entities: [Organization, Project, Invoice]
  given:
    - "Admin is on the billing workspace"
    - "Acme and Globex organizations both exist"
  then:
    - "Admin sees all organizations"
    - "Organization hub shows related projects without org scope restriction"
