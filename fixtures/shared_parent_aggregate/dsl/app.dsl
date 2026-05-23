module shared_parent_aggregate
app spa "Shared-Parent Aggregate"

# ── Personas ────────────────────────────────────────────────────────
# Single open persona keeps the fixture focused on the diamond shape;
# RBAC composition with `share:` is exercised by tests/, not the
# fixture surface itself.

persona admin "Admin":
  description: "Open access — fixture exists to validate the share: JOIN, not RBAC"
  default_workspace: project_dashboard

# ── Entities ────────────────────────────────────────────────────────
# Diamond shape:
#
#     Person       ← pivot
#      ▲ ▲
#      │ │
#      │ └── Contribution.person
#      └─── ProjectMember.person
#
# ProjectMember (cohort source) and Contribution (aggregated entity)
# both `ref Person`. They do NOT ref each other directly. The
# `share:` keyword names `Person` as the bridge.

entity Person "Person":
  id: uuid pk
  name: str(200) required
  email: email required unique

  permit:
    list: role(admin)
    read: role(admin)
    create: role(admin)
    update: role(admin)
    delete: role(admin)

entity Project "Project":
  id: uuid pk
  name: str(200) required

  permit:
    list: role(admin)
    read: role(admin)
    create: role(admin)
    update: role(admin)
    delete: role(admin)

entity ProjectMember "Project Member":
  id: uuid pk
  project: ref Project required
  person: ref Person required
  role: enum[contributor,maintainer,reviewer]=contributor

  permit:
    list: role(admin)
    read: role(admin)
    create: role(admin)
    update: role(admin)
    delete: role(admin)

entity Contribution "Contribution":
  id: uuid pk
  person: ref Person required
  weight: int required=1

  permit:
    list: role(admin)
    read: role(admin)
    create: role(admin)
    update: role(admin)
    delete: role(admin)

# ── Surface ─────────────────────────────────────────────────────────

surface project_member_list "Project Members":
  uses entity ProjectMember
  mode: list
  section main:
    field role "Role"

# ── Workspace ───────────────────────────────────────────────────────

workspace project_dashboard "Project Dashboard":
  access: persona(admin)
  purpose: "Per-member contribution roll-up via shared-parent JOIN"

  contributions_strip:
    source: ProjectMember
    display: cohort_strip
    cohort_strip_config:
      member_via: id
      default_lens: contribution_count
      lenses:
        - id: contribution_count
          label: "Contributions"
          primary_aggregate:
            aggregate: count(Contribution)
            share: Person
        - id: contribution_weight
          label: "Weight"
          primary_aggregate:
            aggregate: sum(Contribution.weight)
            share: Person
