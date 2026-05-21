module acme_billing.entities

# =============================================================================
# ORGANIZATION — tenant root, exercises direct-equality scope + all (admin)
# =============================================================================

entity Organization "Organization":
  intent: "Tenant root — exercises direct-equality scope (id = current_user.org)"

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

  id: uuid pk
  email: email required
  name: str(120) required
  org: ref Organization required

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
  intent: "Billing record — FK-path scope (project.org) + negation (not (sensitive = true))"

  id: uuid pk
  number: str(40) required
  amount: int required
  project: ref Project required
  sensitive: bool=false
  created_at: datetime auto_add

  permit:
    create: role(admin) or role(org_owner)
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
    create: all
      as: org_owner
    update: project.org = current_user.org
      as: org_owner
    list: project.org = current_user.org
      as: org_owner, auditor
    read: project.org = current_user.org
      as: org_owner, auditor
    list: not (sensitive = true)
      as: project_member, external_contractor
    read: not (sensitive = true)
      as: project_member, external_contractor

  audit: all

# =============================================================================
# MEMBERSHIP — junction table assigning users to projects
# =============================================================================

entity Membership "Membership":
  intent: "Junction — assigns users to projects; FK-path scope for org_owner"

  id: uuid pk
  user: ref User required
  project: ref Project required

  permit:
    create: role(admin) or role(org_owner)
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
    create: all
      as: org_owner
    update: project.org = current_user.org
      as: org_owner
    delete: project.org = current_user.org
      as: org_owner
    list: project.org = current_user.org
      as: org_owner
    read: project.org = current_user.org
      as: org_owner

  audit: all
