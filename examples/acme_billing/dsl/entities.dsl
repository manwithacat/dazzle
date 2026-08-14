module acme_billing.entities

# =============================================================================
# ORGANIZATION — tenant root, exercises direct-equality scope + all (admin)
# =============================================================================

entity Organization "Organization":
  intent: "Tenant root — exercises direct-equality scope (id = current_user.org)"

  display_field: name
  id: uuid pk
  name: str(120) required
  created_at: datetime auto_add

  permit:
    create: role(admin)
    read: role(admin) or role(org_owner) or role(auditor)
    update: role(admin)
    delete: role(admin)
    list: role(admin) or role(org_owner) or role(auditor)

  scope:
    create: all
      as: admin
    read: all
      as: admin
    update: all
      as: admin
    delete: all
      as: admin
    list: all
      as: admin
    read: id = current_user.org
      as: org_owner, auditor
    list: id = current_user.org
      as: org_owner, auditor

  audit: all

# =============================================================================
# USER — domain user belonging to an org, direct-equality org scope
# =============================================================================

entity User "User":
  intent: "Domain user record — belongs to an org; user carries org ref for current_user.org resolution"

  display_field: name
  id: uuid pk
  email: email required pii(category=contact)
  name: str(120) required pii(category=identity)
  org: ref Organization required
  # Goal B org_structure (cycle 1867): department + job title so Team desk shows
  # Finance / Delivery / Platform Ops / Audit shape — not a flat persona roster
  # (peer billing tools: Chargebee / Stripe Billing / NetSuite / Coupa).
  department: str(50)
  job_title: str(80)
  created_at: datetime auto_add

  permit:
    create: role(admin) or role(org_owner)
    read: role(admin) or role(org_owner) or role(auditor)
    update: role(admin) or role(org_owner)
    delete: role(admin)
    list: role(admin) or role(org_owner) or role(auditor)

  scope:
    create: all
      as: admin
    read: all
      as: admin
    update: all
      as: admin
    delete: all
      as: admin
    list: all
      as: admin
    create: org = current_user.org
      as: org_owner
    update: org = current_user.org
      as: org_owner
    list: org = current_user.org
      as: org_owner, auditor
    read: org = current_user.org
      as: org_owner, auditor

  audit: all

# =============================================================================
# PROJECT — org project; exercises EXISTS-via-junction scope for project_member
# =============================================================================

entity Project "Project":
  intent: "Org project — exercises EXISTS-via-junction scope (via Membership)"

  display_field: name
  id: uuid pk
  name: str(120) required
  org: ref Organization required
  created_at: datetime auto_add

  permit:
    create: role(admin) or role(org_owner)
    read: role(admin) or role(org_owner) or role(auditor) or role(project_member)
    update: role(admin) or role(org_owner)
    delete: role(admin) or role(org_owner)
    list: role(admin) or role(org_owner) or role(auditor) or role(project_member)

  scope:
    create: all
      as: admin
    read: all
      as: admin
    update: all
      as: admin
    delete: all
      as: admin
    list: all
      as: admin
    create: org = current_user.org
      as: org_owner
    update: org = current_user.org
      as: org_owner
    delete: org = current_user.org
      as: org_owner
    list: org = current_user.org
      as: org_owner, auditor
    read: org = current_user.org
      as: org_owner, auditor
    list: via Membership(user = current_user, project = id)
      as: project_member
    read: via Membership(user = current_user, project = id)
      as: project_member

  audit: all

# =============================================================================
# INVOICE — billing record; FK-path scope + negation scope for sensitivity
# =============================================================================

entity Invoice "Invoice":
  intent: "Billing record — FK-path scope (project.org) + inequality (sensitive != true); boolean-AND compound predicate tenant-isolates project_member/external_contractor. Amount stored as integer cents (no separate money type)"

  # Goal B document: queue/ref title is the invoice number, not a UUID shell.
  display_field: number
  id: uuid pk
  number: str(40) required
  amount: int required
  project: ref Project required
  sensitive: bool=false
  # Goal B document peer-pack (cycle 1904): Stripe/Chargebee dunning state so
  # operators lean into collections work — not amount shells alone.
  dunning_state: enum[none, reminder_1, reminder_2, final, collections]=none
  # Goal B media (novel vs headshot shelf): invoice packet preview — PDF/page
  # thumbs on the money desk, not User photo chrome (peer: Stripe/Chargebee).
  preview_url: url
  created_at: datetime auto_add

  # create is admin-only: scope: create: does not support FK-path predicates (#1124),
  # so an org_owner-scoped create cannot be expressed — granting org_owner an
  # unrestricted create would open a cross-org write hole. org_owner reviews and
  # updates invoices within its own org via the FK-path scope rules below.
  permit:
    create: role(admin)
    read: role(admin) or role(org_owner) or role(auditor) or role(project_member) or role(external_contractor)
    update: role(admin) or role(org_owner)
    delete: role(admin)
    list: role(admin) or role(org_owner) or role(auditor) or role(project_member) or role(external_contractor)

  scope:
    create: all
      as: admin
    read: all
      as: admin
    update: all
      as: admin
    delete: all
      as: admin
    list: all
      as: admin
    update: project.org = current_user.org
      as: org_owner
    list: project.org = current_user.org
      as: org_owner, auditor
    read: project.org = current_user.org
      as: org_owner, auditor
    list: project.org = current_user.org and sensitive != true
      as: project_member, external_contractor
    read: project.org = current_user.org and sensitive != true
      as: project_member, external_contractor

  audit: all

# =============================================================================
# LINE ITEM — document composition body of an Invoice (Goal B document depth)
# =============================================================================

entity LineItem "Line Item":
  intent: "A single line on an invoice document — description + qty × unit amount (cents). Peer tools (Bill.com / Stripe Invoicing) show named composition lines with tax + plan grain, not header-only amounts."
  # Goal B: queue title is the human line description, not a UUID shell.
  display_field: description

  id: uuid pk
  invoice: ref Invoice required
  description: str(200) required
  quantity: int=1
  unit_amount: int required
  # Goal B document peer-pack (cycle 1904): tax line + plan name — finance
  # operators lean into these (Stripe Billing / Chargebee), not description alone.
  tax_code: str(20) optional
  plan_name: str(80) optional
  # Goal B document (cycle 2069): Stripe/Chargebee line-kind density —
  # subscription vs metered usage vs one-time vs credit composition grain
  # (recipe line_kind_density — not dunning_stage_density re-stack).
  line_kind: enum[subscription, usage, one_time, credit]=one_time
  created_at: datetime auto_add

  # Same role surface as Invoice read/list; create stays admin-only (no
  # FK-path create scope for org_owner — #1124, matches Invoice).
  permit:
    create: role(admin)
    read: role(admin) or role(org_owner) or role(auditor) or role(project_member) or role(external_contractor)
    update: role(admin) or role(org_owner)
    delete: role(admin)
    list: role(admin) or role(org_owner) or role(auditor) or role(project_member) or role(external_contractor)

  scope:
    create: all
      as: admin
    read: all
      as: admin
    update: all
      as: admin
    delete: all
      as: admin
    list: all
      as: admin
    update: invoice.project.org = current_user.org
      as: org_owner
    list: invoice.project.org = current_user.org
      as: org_owner, auditor
    read: invoice.project.org = current_user.org
      as: org_owner, auditor
    # Sensitivity follows parent invoice — members never see lines on
    # sensitive documents (same rule as Invoice list/read).
    list: invoice.project.org = current_user.org and invoice.sensitive != true
      as: project_member, external_contractor
    read: invoice.project.org = current_user.org and invoice.sensitive != true
      as: project_member, external_contractor

  audit: all


# =============================================================================
# INVOICE NOTE — conversation trail on an Invoice (Goal B conversation depth)
# =============================================================================

entity InvoiceNote "Invoice Note":
  # Goal B conversation: peer billing tools (Bill.com / Stripe Invoicing / NetSuite)
  # show approval discussion on the billing desk — not composition lines alone.
  intent: "Discussion on an Invoice — the conversation that drives review, dispute, and pay"
  domain: billing
  patterns: messaging, audit_trail
  display_field: body
  id: uuid pk
  invoice: ref Invoice required
  author: str(120) required
  body: text required
  created_at: datetime auto_add

  permit:
    create: role(admin) or role(org_owner) or role(project_member)
    read: role(admin) or role(org_owner) or role(auditor) or role(project_member) or role(external_contractor)
    update: role(admin) or role(org_owner)
    delete: role(admin)
    list: role(admin) or role(org_owner) or role(auditor) or role(project_member) or role(external_contractor)

  scope:
    create: all
      as: admin
    read: all
      as: admin
    update: all
      as: admin
    delete: all
      as: admin
    list: all
      as: admin
    create: invoice.project.org = current_user.org
      as: org_owner, project_member
    update: invoice.project.org = current_user.org
      as: org_owner
    list: invoice.project.org = current_user.org
      as: org_owner, auditor
    read: invoice.project.org = current_user.org
      as: org_owner, auditor
    list: invoice.project.org = current_user.org and invoice.sensitive != true
      as: project_member, external_contractor
    read: invoice.project.org = current_user.org and invoice.sensitive != true
      as: project_member, external_contractor

  fitness:
    repr_fields: [invoice, author, body]

  audit: all

# =============================================================================
# MEMBERSHIP — junction table assigning users to projects
# =============================================================================

entity Membership "Membership":
  intent: "Junction — assigns users to projects; FK-path scope for org_owner"

  id: uuid pk
  user: ref User required
  project: ref Project required

  # create is admin-only: scope: create: does not support FK-path predicates (#1124),
  # so an org_owner-scoped create cannot be expressed — granting org_owner an
  # unrestricted create would open a cross-org write hole. org_owner reviews and
  # updates memberships within its own org via the FK-path scope rules below.
  permit:
    create: role(admin)
    read: role(admin) or role(org_owner)
    update: role(admin) or role(org_owner)
    delete: role(admin) or role(org_owner)
    list: role(admin) or role(org_owner)

  scope:
    create: all
      as: admin
    read: all
      as: admin
    update: all
      as: admin
    delete: all
      as: admin
    list: all
      as: admin
    update: project.org = current_user.org
      as: org_owner
    delete: project.org = current_user.org
      as: org_owner
    list: project.org = current_user.org
      as: org_owner
    read: project.org = current_user.org
      as: org_owner

  audit: all
