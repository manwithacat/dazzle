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

nav admin_nav:
  group "Workspace":
    home
    announce
    publish_desk

nav member_nav:
  group "Team":
    announce
    home

# ── Tenant root (resolved by host; members + their role declared here) ─────────

entity Workspace "Workspace":
  intent: "Root tenant kind — the verified-domain workspace a company joins under. Members and their role are declared here (ADR-0037: membership on the root kind)."
  id: uuid pk
  slug: slug required
  name: str(120) required
  role: str(40)
  display_field: name
  tenant_host:
    domain: domainjoin.example
    slug_field: slug
    canonical_hosts: [localhost]   # apex / dev / health-check host → no tenant bound
    order: 1
  membership:
    roles: role            # ADR-0037: membership ONLY on the root kind
  fitness:
    repr_fields: [name, slug, role]

# ── Tenant-scoped data the join grants access to ──────────────────────────────

entity Announcement "Announcement":
  intent: "Tenant-scoped team post — readable by any joined member, authored by the admin. Exercises the current_tenant scope a verified-domain join unlocks."
  id: uuid pk
  title: str(200) required
  body: text required
  workspace: ref Workspace required
  # Domain residual lifecycle (cycle 1477): posts are not eternally live.
  status: enum[draft,published,archived]=draft
  display_field: title
  transitions:
    draft -> published: role(admin)
    published -> archived: role(admin)
    published -> draft: role(admin)
    archived -> published: role(admin)
    draft -> archived: role(admin)
  fitness:
    repr_fields: [title, status, workspace]
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

# Goal B conversation: peer workplace tools (Slack/Workplace/Teams) show
# discussion on the team board — not only announcement title queues.
entity AnnouncementNote "Announcement Note":
  intent: "Team discussion on an Announcement — the conversation that turns a post into action"
  domain: workplace
  patterns: messaging, audit_trail
  display_field: body
  id: uuid pk
  announcement: ref Announcement required
  author: str(120) required
  body: text required
  created_at: datetime auto_add

  permit:
    create: role(admin) or role(member)
    read: role(admin) or role(member)
    update: role(admin)
    list: role(admin) or role(member)

  scope:
    # Notes inherit announcement visibility via parent workspace fence on list
    # through announcement FK; row scope uses announcement's workspace.
    list: announcement.workspace = current_tenant
      as: admin, member
    read: announcement.workspace = current_tenant
      as: admin, member
    create: announcement.workspace = current_tenant
      as: admin, member
    update: announcement.workspace = current_tenant
      as: admin

  fitness:
    repr_fields: [announcement, author, body]

# ── Surfaces (the guide overlays target these) ────────────────────────────────

surface announcement_list "Announcements":
  uses entity Announcement
  mode: list
  # Pipe dual hop (cycle 1529) — prefer one pipe line (parser also merges
  # multiple open: lines since cycle 1530 / AUD-007).
  open: Announcement via id | Workspace via workspace
  section main:
    field title "Title"
    field status "Status"
    field workspace "Workspace"
  ux:
    purpose: "Team board — open a row for the announcement hub or its workspace"
    filter: status
    sort: title asc
    search: title
    empty: "No announcements yet — post one from Publish"

surface announcement_detail "Announcement":
  uses entity Announcement
  mode: view
  section summary "Summary":
    layout: strip
    field title "Title"
    field status "Status"
    field workspace "Workspace"
  section body "Body":
    field body "Body"
  # Goal B conversation: team discussion on the announcement hub.
  related discussion "Discussion":
    display: queue
    show: AnnouncementNote
    columns: body, author, created_at
  ux:
    purpose: "Announcement hub — lifecycle strip, body, and team discussion"

surface announcement_note_list "Announcement Notes":
  uses entity AnnouncementNote
  mode: list
  open: AnnouncementNote via id | Announcement via announcement
  section main:
    field body "Note"
    field author "Author"
    field announcement "Announcement"
    field created_at "When"
  ux:
    purpose: "Team discussion — open a note or its parent announcement"
    sort: created_at desc
    search: body, author
    empty: "No discussion yet"

surface announcement_note_detail "Announcement Note":
  uses entity AnnouncementNote
  mode: view
  section summary "Note":
    field body "Note"
    field author "Author"
    field announcement "Announcement"
    field created_at "When"
  ux:
    purpose: "Read a team note in context of its parent announcement"

surface announcement_note_create "Add Announcement Note":
  uses entity AnnouncementNote
  mode: create
  section main:
    field announcement "Announcement"
    field author "Author"
    field body "Note"

surface announcement_create "Post Announcement":
  uses entity Announcement
  mode: create
  section main:
    field title "Title"
    field body "Body"

# Workspace hub — related announcements reverse hop (journey related + strip).
surface workspace_list "Workspaces":
  uses entity Workspace
  mode: list
  open: Workspace via id
  section main:
    field name "Name"
    field slug "Slug"
    field role "Role"
  ux:
    purpose: "Tenant roots — open a workspace hub for join context and posts"

surface workspace_detail "Workspace":
  uses entity Workspace
  mode: view
  section identity "Identity":
    layout: strip
    field name "Name"
    field slug "Slug"
    field role "Role"
  # Pull-next post queue (not warehouse table) — ST-005 / journey hub deepen.
  related posts "Announcements":
    display: queue
    show: Announcement
    columns: title, status
  ux:
    purpose: "Workspace hub — identity strip and tenant-scoped announcement queue"

# Story-driven home: metrics + readiness strip before the announcement feed.
# Join-request approval lives in runtime admin console (not DSL) — see
# docs/reference/verified-domain-join.md.
workspace home "Workspace Home":
  # Goal B command_density (cycle 1831): peer Slack/Notion team homes put
  # announcement pressure + join readiness above the discussion trail — not
  # conversation alone owning the fold. Caps keep dual attention + notes sharing.
  # Also holds conversation + empty_region_honesty (no twin board dumps/charts).
  purpose: "Multi-panel team home — pulse, announcement queue, join readiness, then discussion"
  access: persona(admin, member)

  # Metrics honesty: count Announcement only (nested AnnouncementNote metrics
  # were ship-lying as 0 while the conversation queue was populated).
  team_pulse:
    source: Announcement
    display: metrics
    aggregate:
      announcements: count(Announcement)
    tones:
      announcements: accent

  # Dual attention A — posts to act on / skim (cap 4 for fold share).
  announcement_queue:
    source: Announcement
    sort: title asc
    limit: 4
    display: queue
    action: announcement_detail
    empty: "No announcements yet — post one to keep the team informed"

  # Dual attention B — always-filled join readiness (not seed-dependent chart).
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

  # Goal B conversation spine AFTER dual attention — newest team notes.
  # display: conversation → MessageScroller / Message + Bubble (not queue meta).
  live_conversation:
    source: AnnouncementNote
    sort: created_at desc
    limit: 4
    display: conversation
    action: announcement_note_detail
    empty: "No conversation yet — team notes on announcements appear here"

  # Awareness stream — one timeline, not a second identical queue dump.
  board_preview:
    source: Announcement
    sort: title asc
    limit: 10
    display: timeline
    action: announcement_detail
    empty: "Board is empty"

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

  tenant_roots:
    source: Workspace
    sort: name asc
    limit: 10
    # Workspace picker is pull-to-enter (queue), not a dense catalogue table.
    display: queue
    action: workspace_detail
    empty: "No workspaces yet"

  ux:
    as admin:
      purpose: "Multi-panel team home — pulse, posts, join readiness, then discussion"
      focus: team_pulse, announcement_queue, join_readiness, live_conversation
    as member:
      purpose: "Multi-panel catch-up — posts and readiness before discussion trail"
      focus: team_pulse, announcement_queue, join_readiness, live_conversation

# Second product workspace lowers warehouse density (3 lists / 1 ws → deepen).
# Admin publish desk vs member reading feed (same entity, different job).
workspace announce "Team Board":
  # Goal B command_density: pulse + feed queue + join context before conversation.
  # empty_region_honesty: no duplicate queues / empty bar / workspace voids.
  purpose: "Multi-panel board — pulse, post feed, join context, then discussion trail"
  access: persona(admin, member)

  board_pulse:
    source: Announcement
    display: metrics
    aggregate:
      posts: count(Announcement)
    tones:
      posts: accent

  # Dual attention A — post feed (cap 4 for fold share with conversation).
  feed_queue:
    source: Announcement
    sort: title asc
    limit: 4
    display: queue
    action: announcement_detail
    empty: "No announcements yet — post one to keep the team informed"

  # Dual attention B — always-filled status strip (not a seed-dependent void).
  join_context:
    display: status_list
    entries:
      - title: "Verified domain join"
        caption: "You are reading posts scoped to your company workspace"
        icon: "globe"
        state: accent
      - title: "Stay informed"
        caption: "Open any post for the full announcement hub and discussion"
        icon: "megaphone"
        state: positive
      - title: "Reply in-thread"
        caption: "Notes on a post keep join and wifi cutover decisions in one place"
        icon: "message-square"
        state: positive

  # Conversation AFTER dual attention so Message chrome shares the fold.
  live_conversation:
    source: AnnouncementNote
    sort: created_at desc
    limit: 4
    display: conversation
    action: announcement_note_detail
    empty: "No conversation yet — notes on published posts appear here"

  post_trail:
    source: Announcement
    sort: title asc
    limit: 12
    display: timeline
    action: announcement_detail
    empty: "No announcements yet"

  ux:
    as admin:
      purpose: "Multi-panel board — feed and join context before discussion"
      focus: board_pulse, feed_queue, join_context, live_conversation
    as member:
      purpose: "Catch up — posts and context before conversation trail"
      focus: board_pulse, feed_queue, join_context, live_conversation

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
    filter: status = draft
    sort: title asc
    limit: 20
    display: queue
    action: announcement_detail
    empty: "No drafts — create one to brief the team"

  live_cards:
    source: Announcement
    filter: status = published
    sort: title asc
    limit: 15
    display: queue
    action: announcement_detail
    empty: "Board empty — publish a draft to go live"

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

  publish_trail:
    source: Announcement
    sort: title asc
    limit: 12
    display: timeline
    action: announcement_detail
    empty: "No posts yet"

  ux:
    as admin:
      purpose: "Drafts and live posts before trail — no empty chart theater"
      focus: publish_pulse, draft_queue, live_cards, readiness
