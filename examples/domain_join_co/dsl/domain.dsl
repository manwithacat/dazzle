module domain_join_co.domain

# Domain Join Co — a worked example of verified-domain self-service join (#1424).
#
# The story: a company proves it owns its email domain (DNS-TXT, via a
# provider-less `type="domain"` connection), then an employee whose *verified*
# work email matches that domain self-joins the workspace under a per-tenant
# policy (default: admin_approval). The admin verifies the domain, sets the
# policy, and approves join requests; joined members read the team's
# announcements.
#
# IMPORTANT — what is DSL vs runtime here:
#   * DSL (this file): a `tenant_host:` + `membership:` workspace for the join
#     flow to land members into, plus the tenant-scoped data a join grants.
#   * RUNTIME (admin console / `dazzle auth` CLI): the domain connection, the
#     `domain_join_policy`, the join-request queue, and the
#     `restrict_membership_to_verified_domains` flag. These are NOT DSL keywords.
# The end-to-end CLI loop is in docs/reference/verified-domain-join.md.

persona admin "Workspace Admin":
  description: "Owns one workspace — verifies the company email domain, sets the join policy, approves join requests, and posts announcements."
  goals: "Verify our domain", "Approve the right joiners", "Keep the team informed"
  proficiency: expert
  default_workspace: home

persona member "Team Member":
  description: "An employee who self-joined with a verified company email — reads the team's announcements."
  goals: "Join my company workspace", "Stay up to date"
  proficiency: intermediate
  default_workspace: home

# ── Tenant root (resolved by host; members + their role declared here) ─────────

entity Workspace "Workspace":
  intent: "Root tenant kind — the verified-domain workspace a company joins under. Members and their role are declared here (ADR-0037: membership on the root kind)."
  id: uuid pk
  slug: slug required
  name: str(120) required
  role: str(40)
  tenant_host:
    domain: domainjoin.example
    slug_field: slug
    canonical_hosts: [localhost]   # apex / dev / health-check host → no tenant bound
    order: 1
  membership:
    roles: role            # ADR-0037: membership ONLY on the root kind

# ── Tenant-scoped data the join grants access to ──────────────────────────────

entity Announcement "Announcement":
  intent: "Tenant-scoped team post — readable by any joined member, authored by the admin. Exercises the current_tenant scope a verified-domain join unlocks."
  id: uuid pk
  title: str(200) required
  body: text required
  workspace: ref Workspace required
  permit:
    create: role(admin)
    read: role(admin) or role(member)
    update: role(admin)
    list: role(admin) or role(member)
  scope:
    # The join lands a member into one Workspace; current_tenant fences every
    # read/write to that workspace's rows. Both list AND read are declared: the
    # runtime resolves row scope per operation, so a list endpoint with only a
    # `read:` rule would default-deny.
    list: workspace = current_tenant
      as: admin, member
    read: workspace = current_tenant
      as: admin, member
    create: workspace = current_tenant
      as: admin
    update: workspace = current_tenant
      as: admin

# ── Surfaces (the guide overlays target these) ────────────────────────────────

surface announcement_list "Announcements":
  uses entity Announcement
  mode: list
  open: Announcement via id
  section main:
    field title "Title"
    field workspace "Workspace"
  ux:
    purpose: "Team board — open a row for the announcement hub"

surface announcement_detail "Announcement":
  uses entity Announcement
  mode: view
  section summary "Summary":
    field title "Title"
    field workspace "Workspace"
  section body "Body":
    field body "Body"
  ux:
    purpose: "Announcement hub — title, workspace context, and body in one place"

surface announcement_create "Post Announcement":
  uses entity Announcement
  mode: create
  section main:
    field title "Title"
    field body "Body"

# Story-driven home: metrics + readiness strip before the announcement feed.
# Join-request approval lives in runtime admin console (not DSL) — see
# docs/reference/verified-domain-join.md.
workspace home "Workspace Home":
  access: persona(admin, member)

  team_pulse:
    source: Announcement
    display: metrics
    aggregate:
      announcements: count(Announcement)
    tones:
      announcements: accent

  join_readiness:
    display: status_list
    entries:
      - title: "Verified domain"
        caption: "DNS-TXT domain connection is managed in dazzle auth / admin console"
        icon: "globe"
        state: accent
      - title: "Join policy"
        caption: "Default admin_approval — approve join requests before members land"
        icon: "shield"
        state: warning
      - title: "Announcements"
        caption: "Members read posts scoped to current_tenant after join"
        icon: "megaphone"
        state: positive

  announcements:
    source: Announcement
    sort: title asc
    display: list
    action: announcement_detail
    empty: "No announcements yet — post one to keep the team informed"
