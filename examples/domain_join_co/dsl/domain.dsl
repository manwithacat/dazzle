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
  uses nav admin_nav

persona member "Team Member":
  description: "An employee who self-joined with a verified company email — reads the team's announcements."
  goals: "Join my company workspace", "Stay up to date"
  proficiency: intermediate
  # Answer-first: feed board after join (product maturity)
  default_workspace: announce
  uses nav member_nav

# Curated sidebars: workspace destinations only (WI N).
nav admin_nav:
  group "Workspace":
    home
    announce
    publish_desk
    workspace_ops
    board_ops
    feed_ops
    tenant_ops
    roster_ops

nav member_nav:
  group "Team":
    announce
    home
    workspace_ops
    board_ops
    feed_ops
    tenant_ops
    roster_ops

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
# WI L: denser landing regions (queue/chart/related/strip/activity).
workspace home "Workspace Home":
  purpose: "Admin desk — join readiness, team pulse, and announcement queue"
  access: persona(admin, member)

  team_pulse:
    source: Announcement
    display: metrics
    aggregate:
      announcements: count(Announcement)
      workspaces: count(Workspace)
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

  announcement_queue:
    source: Announcement
    sort: title asc
    limit: 15
    display: queue
    action: announcement_detail
    empty: "No announcements yet — post one to keep the team informed"

  board_preview:
    source: Announcement
    sort: title asc
    limit: 10
    display: list
    action: announcement_detail
    empty: "Board is empty"

  tenant_roots:
    source: Workspace
    sort: name asc
    limit: 10
    display: list
    empty: "No workspaces yet"

  activity_strip:
    display: status_list
    entries:
      - title: "Member feed"
        caption: "Joined members land on the Team Board after domain join"
        icon: "users"
        state: positive
      - title: "Publish desk"
        caption: "Admins draft and post from Publish"
        icon: "pen"
        state: accent

  # WI D: grid family for announcement cards
  board_cards:
    source: Announcement
    sort: title asc
    limit: 12
    display: grid
    action: announcement_detail
    empty: "No announcements yet"

  # WI D: chart family — announcement load by workspace
  post_mix:
    source: Announcement
    display: bar_chart
    group_by: workspace
    aggregate:
      count: count(Announcement)
    empty: "No announcements yet"

# Second product workspace lowers warehouse density (3 lists / 1 ws → deepen).
# Admin publish desk vs member reading feed (same entity, different job).
# WI L: member default landing — aim for ≥5 signal-rich mode×source pairs.
workspace announce "Team Board":
  purpose: "Announcement board — post and browse without warehouse list chrome"
  access: persona(admin, member)

  board_pulse:
    source: Announcement
    display: metrics
    aggregate:
      posts: count(Announcement)
      workspaces: count(Workspace)
    tones:
      posts: accent

  feed_queue:
    source: Announcement
    sort: title asc
    limit: 20
    display: queue
    action: announcement_detail
    empty: "No announcements yet — post one to keep the team informed"

  # WI D: grid family for feed cards (not list pad)
  feed_cards:
    source: Announcement
    sort: title asc
    limit: 15
    display: grid
    action: announcement_detail
    empty: "No announcements yet — post one to keep the team informed"

  join_context:
    display: status_list
    entries:
      - title: "Verified domain join"
        caption: "You are reading posts scoped to your company workspace"
        icon: "globe"
        state: accent
      - title: "Stay informed"
        caption: "Open any post for the full announcement hub"
        icon: "megaphone"
        state: positive

  # WI D: context family — recent posts trail
  post_trail:
    source: Announcement
    sort: title asc
    limit: 12
    display: timeline
    action: announcement_detail
    empty: "No announcements yet"

  # WI D: chart family — posts by workspace
  post_mix:
    source: Announcement
    display: bar_chart
    group_by: workspace
    aggregate:
      count: count(Announcement)
    empty: "No announcements yet"

  # WI D: workspace context grid
  workspace_cards:
    source: Workspace
    sort: name asc
    limit: 8
    display: grid
    empty: "No workspace context"

# Third product workspace (WI D): admin publish desk vs read-only board.
workspace publish_desk "Publish":
  purpose: "Admin publish desk — draft queue and live board pulse before posting"
  access: persona(admin)

  publish_pulse:
    source: Announcement
    display: metrics
    aggregate:
      posts: count(Announcement)
      workspaces: count(Workspace)
    tones:
      posts: accent

  draft_queue:
    source: Announcement
    sort: title asc
    limit: 20
    display: queue
    action: announcement_detail
    empty: "No posts yet — create one to brief the team"

  # WI D: grid family for live board cards
  live_cards:
    source: Announcement
    sort: title asc
    limit: 15
    display: grid
    action: announcement_detail
    empty: "Board empty"

  readiness:
    display: status_list
    entries:
      - title: "Domain verified?"
        caption: "Confirm DNS-TXT in dazzle auth before inviting joiners"
        icon: "globe"
        state: warning
      - title: "Join policy"
        caption: "admin_approval keeps the roster intentional"
        icon: "shield"
        state: accent

  # WI D: context family — publish trail
  publish_trail:
    source: Announcement
    sort: title asc
    limit: 12
    display: timeline
    action: announcement_detail
    empty: "No posts yet"

  # WI D: chart family — posts by workspace
  post_mix:
    source: Announcement
    display: bar_chart
    group_by: workspace
    aggregate:
      count: count(Announcement)
    empty: "No posts yet"

# Fourth product desk (WI D): skip invoice_ops desk-cap; densify domain_join_co.
workspace workspace_ops "Workspace Ops":
  purpose: "Tenant-root pressure — workspace footprint and post load without warehouse CRUD"
  access: persona(admin, member)

  tenant_pulse:
    source: Workspace
    display: metrics
    aggregate:
      workspaces: count(Workspace)
      posts: count(Announcement)
    tones:
      workspaces: accent
      posts: positive

  # WI D: queue family — workspaces first
  workspace_queue:
    source: Workspace
    sort: name asc
    limit: 20
    display: queue
    empty: "No workspaces yet"

  # WI D: grid family — announcement cards
  post_cards:
    source: Announcement
    sort: title asc
    limit: 15
    display: grid
    action: announcement_detail
    empty: "No announcements yet"

  # WI D: context family — post trail
  post_trail:
    source: Announcement
    sort: title asc
    limit: 15
    display: timeline
    action: announcement_detail
    empty: "No announcement activity yet"

  # WI D: chart family — posts by workspace
  post_mix:
    source: Announcement
    display: bar_chart
    group_by: workspace
    aggregate:
      count: count(Announcement)
    empty: "No posts to chart"

# Fifth product desk (WI D): skip invoice/fieldtest/acme soft-cap; densify domain_join_co.
workspace board_ops "Board Ops":
  purpose: "Announcement-board pressure — post load without warehouse CRUD"
  access: persona(admin, member)

  board_pulse:
    source: Announcement
    display: metrics
    aggregate:
      posts: count(Announcement)
      workspaces: count(Workspace)
    tones:
      posts: accent
      workspaces: muted

  # WI D: queue family — posts first
  post_queue:
    source: Announcement
    sort: title asc
    limit: 20
    display: queue
    action: announcement_detail
    empty: "No posts on the board"

  # WI D: grid family — post cards
  post_grid:
    source: Announcement
    sort: title asc
    limit: 15
    display: grid
    action: announcement_detail
    empty: "No posts on the board"

  # WI D: context family — post trail
  post_trail:
    source: Announcement
    sort: title asc
    limit: 15
    display: timeline
    action: announcement_detail
    empty: "No board activity yet"

  # WI D: chart family — posts by workspace
  post_mix:
    source: Announcement
    display: bar_chart
    group_by: workspace
    aggregate:
      count: count(Announcement)
    empty: "No posts to chart"

# Sixth product desk (WI D): skip invoice/fieldtest/acme/hr soft-cap; densify domain_join_co.
workspace feed_ops "Feed Ops":
  purpose: "Member-feed pressure — announcement intake without warehouse CRUD"
  access: persona(admin, member)

  feed_pulse:
    source: Announcement
    display: metrics
    aggregate:
      posts: count(Announcement)
      workspaces: count(Workspace)
    tones:
      posts: accent
      workspaces: muted

  # WI D: queue family — feed first
  feed_queue:
    source: Announcement
    sort: title asc
    limit: 20
    display: queue
    action: announcement_detail
    empty: "Feed is empty"

  # WI D: grid family — feed cards
  feed_grid:
    source: Announcement
    sort: title asc
    limit: 15
    display: grid
    action: announcement_detail
    empty: "Feed is empty"

  # WI D: context family — feed trail
  feed_trail:
    source: Announcement
    sort: title asc
    limit: 15
    display: timeline
    action: announcement_detail
    empty: "No feed activity yet"

  # WI D: chart family — posts by workspace
  feed_mix:
    source: Announcement
    display: bar_chart
    group_by: workspace
    aggregate:
      count: count(Announcement)
    empty: "No posts to chart"

# Seventh product desk (WI D): skip invoice/fieldtest/acme/hr soft-cap; densify domain_join_co.
workspace tenant_ops "Tenant Ops":
  purpose: "Tenant-slug pressure — workspace identity without warehouse CRUD"
  access: persona(admin, member)

  tenant_pulse:
    source: Workspace
    display: metrics
    aggregate:
      workspaces: count(Workspace)
      posts: count(Announcement)
    tones:
      workspaces: accent
      posts: positive

  # WI D: queue family — workspaces by slug/name
  tenant_queue:
    source: Workspace
    sort: slug asc
    limit: 20
    display: queue
    empty: "No workspaces yet"

  # WI D: grid family — workspace cards
  tenant_grid:
    source: Workspace
    sort: name asc
    limit: 15
    display: grid
    empty: "No workspaces yet"

  # WI D: context family — post trail as tenant activity
  tenant_trail:
    source: Announcement
    sort: title asc
    limit: 15
    display: timeline
    action: announcement_detail
    empty: "No tenant activity yet"

  # WI D: chart family — posts by workspace
  post_mix:
    source: Announcement
    display: bar_chart
    group_by: workspace
    aggregate:
      count: count(Announcement)
    empty: "No posts to chart"

# Eighth product desk (WI D): skip invoice/fieldtest/acme/hr soft-cap; densify domain_join_co.
workspace roster_ops "Roster Ops":
  purpose: "Membership-role pressure — workspace roster footprint without warehouse CRUD"
  access: persona(admin, member)

  roster_pulse:
    source: Workspace
    display: metrics
    aggregate:
      workspaces: count(Workspace)
      posts: count(Announcement)
    tones:
      workspaces: accent
      posts: muted

  # WI D: queue family — workspaces by name
  roster_queue:
    source: Workspace
    sort: name asc
    limit: 20
    display: queue
    empty: "No workspaces yet"

  # WI D: grid family — workspace cards
  roster_grid:
    source: Workspace
    sort: slug asc
    limit: 15
    display: grid
    empty: "No workspaces yet"

  # WI D: context family — announcement trail as roster pulse
  roster_trail:
    source: Announcement
    sort: title asc
    limit: 15
    display: timeline
    action: announcement_detail
    empty: "No roster activity yet"

  # WI D: chart family — posts by workspace
  post_mix:
    source: Announcement
    display: bar_chart
    group_by: workspace
    aggregate:
      count: count(Announcement)
    empty: "No posts to chart"
