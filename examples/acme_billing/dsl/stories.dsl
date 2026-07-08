module acme_billing.stories

# =============================================================================
# ACME BILLING — RBAC Behaviour Stories
# =============================================================================
# 5 stories documenting expected access behaviour for the key personas.
# =============================================================================

story ST-001 "Org owner manages projects within their organization":
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
