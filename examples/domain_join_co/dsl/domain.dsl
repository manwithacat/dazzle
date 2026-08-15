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
    team_home
    announce
    publish_desk

nav member_nav:
  group "Team":
    announce
    team_home
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

# Goal B document composition: named workspace briefs/handbooks buyers scan above discussion trail.
entity WorkspaceDocument "Workspace Document":
  intent: "A named workspace document — brief, onboarding guide, join playbook, policy, or decision log buyers scan above the team discussion trail"
  domain: workplace
  patterns: documentation, audit_trail
  display_field: headline
  id: uuid pk
  workspace: ref Workspace required
  headline: str(200) required
  doc_kind: enum[brief, onboarding_guide, join_playbook, policy, decision]=brief
  body: text
  status: enum[draft, published, archived]=draft
  author: str(120)
  # Goal B media (novel vs headshot shelf): handbook cover preview — letter
  # thumbs on the team home, not User photo chrome (peer: Notion/Confluence/Drive).
  preview_url: url
  created_at: datetime auto_add

  # Domain residual status∄transitions (cycle 1845): workspace briefs publish then archive.
  transitions:
    draft -> published: role(admin)
    published -> archived: role(admin)
    draft -> archived: role(admin)
    published -> draft: role(admin)

  permit:
    create: role(admin)
    read: role(admin) or role(member)
    update: role(admin)
    list: role(admin) or role(member)

  scope:
    list: workspace = current_tenant
      as: admin, member
    read: workspace = current_tenant
      as: admin, member
    create: workspace = current_tenant
      as: admin
    update: workspace = current_tenant
      as: admin

  fitness:
    repr_fields: [workspace, headline, doc_kind, status, author, preview_url]

# Goal B org_structure: peer directory tools (Okta / Google Workspace Admin /
# Microsoft Entra / Rippling) show joined staff by title and department so
# admins place people after domain join — not a flat announcement-only roster.
entity WorkspaceMember "Workspace Member":
  intent: "Joined staff row for a workspace — department and job title so the Team desk shows org shape after verified-domain join"
  domain: workplace
  patterns: org_structure, directory
  display_field: name
  id: uuid pk
  workspace: ref Workspace required
  name: str(120) required
  email: email required
  department: str(50)
  job_title: str(80)
  status: enum[active, pending, offboarded]=active
  created_at: datetime auto_add
  # Domain residual status∄transitions (cycle 1871): invite → seat → offboard.
  transitions:
    pending -> active: role(admin)
    active -> offboarded: role(admin)
    pending -> offboarded: role(admin)
    offboarded -> active: role(admin)
    active -> pending: role(admin)

  permit:
    create: role(admin)
    read: role(admin) or role(member)
    update: role(admin)
    list: role(admin) or role(member)

  scope:
    list: workspace = current_tenant
      as: admin, member
    read: workspace = current_tenant
      as: admin, member
    create: workspace = current_tenant
      as: admin
    update: workspace = current_tenant
      as: admin

  fitness:
    repr_fields: [workspace, name, department, job_title, status]

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
  # Goal B conversation (cycle 1899): announcement hub Discussion uses
  # RelatedDisplayMode.conversation → Message/Bubble chrome (not queue meta).
  related discussion "Discussion":
    display: conversation
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

# WorkspaceDocument surfaces (Goal B document composition)
surface workspace_document_list "Workspace Documents":
  uses entity WorkspaceDocument
  mode: list
  open: WorkspaceDocument via id | Workspace via workspace
  section main "Documents":
    field preview_url "Cover"
    field headline "Headline"
    field doc_kind "Kind"
    field workspace "Workspace"
    field status "Status"
    field author "Author"
    field created_at "When"
  ux:
    purpose: "Document composition queue — named briefs and handbooks; open a letter hub or hop to the Workspace"
    sort: created_at desc
    filter: doc_kind, status
    search: headline, body
    empty: "No workspace documents yet — open a workspace hub to attach a brief or handbook"

surface workspace_document_create "Add Workspace Document":
  uses entity WorkspaceDocument
  mode: create
  section main "New document":
    field workspace "Workspace"
    field headline "Headline"
    field doc_kind "Kind"
    field status "Status"
    field body "Body"
    field author "Author"
    field preview_url "Cover URL"
  ux:
    purpose: "Attach a named brief, onboarding guide, join playbook, policy, or decision log to a workspace"

surface workspace_document_detail "Workspace Document":
  uses entity WorkspaceDocument
  mode: view
  section summary "Document":
    field headline "Headline"
    field doc_kind "Kind"
    field status "Status"
    field workspace "Workspace"
    field author "Author"
    field preview_url "Cover"
    field created_at "When"
  section body "Body":
    field body "Body"
  ux:
    purpose: "Workspace document hub — named letter, lifecycle strip, workspace, and body in one place"

surface workspace_document_edit "Edit Workspace Document":
  uses entity WorkspaceDocument
  mode: edit
  section main "Edit document":
    field headline "Headline"
    field doc_kind "Kind"
    field status "Status"
    field body "Body"
    field author "Author"
    field preview_url "Cover URL"
  ux:
    purpose: "Update workspace document headline, kind, or status"

# WorkspaceMember surfaces (Goal B org_structure)
surface workspace_member_list "Team roster":
  uses entity WorkspaceMember
  mode: list
  open: WorkspaceMember via id | Workspace via workspace
  section main "Staff":
    field name "Name"
    field job_title "Job Title"
    field department "Department"
    field email "Email"
    field workspace "Workspace"
    field status "Status"
  ux:
    purpose: "Browse joined staff by title and department — open a member hub or parent workspace"
    sort: department asc, name asc
    filter: department, job_title, status
    search: name, email, department, job_title
    empty: "No joined staff yet — place people after domain join"

surface workspace_member_detail "Workspace Member":
  uses entity WorkspaceMember
  mode: view
  section summary "Member":
    layout: strip
    field name "Name"
    field job_title "Job Title"
    field department "Department"
    field email "Email"
    field workspace "Workspace"
    field status "Status"
    field created_at "Joined"
  ux:
    purpose: "Joined staff hub — title, department, and workspace placement"

surface workspace_member_create "Add Workspace Member":
  uses entity WorkspaceMember
  mode: create
  section main "New member":
    field workspace "Workspace"
    field name "Name"
    field email "Email"
    field job_title "Job Title"
    field department "Department"
    field status "Status"
  ux:
    purpose: "Place a joined employee on the workspace roster with title and department"

surface workspace_member_edit "Edit Workspace Member":
  uses entity WorkspaceMember
  mode: edit
  section main "Edit member":
    field name "Name"
    field email "Email"
    field job_title "Job Title"
    field department "Department"
    field status "Status"
  ux:
    purpose: "Update joined staff title, department, or status"

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
  # Goal B document: named briefs / handbooks on the workspace hub.
  related documents "Documents":
    display: queue
    show: WorkspaceDocument
    columns: preview_url, headline, doc_kind, status, author
  # Goal B org_structure: joined staff placement on the workspace hub.
  related staff "Staff":
    display: queue
    show: WorkspaceMember
    columns: name, job_title, department, status
  ux:
    purpose: "Workspace hub — identity strip, announcements, documents, and joined staff"

# Story-driven home: metrics + readiness strip before the announcement feed.
# Join-request approval lives in runtime admin console (not DSL) — see
# docs/reference/verified-domain-join.md.
workspace home "Workspace Home":
  # Goal B media FIRST (cycle 1887) + command_density + document: peer
  # Notion/Confluence/Drive put handbook cover thumbs above pulse and dual
  # attention — not headshot shelves (portfolio ban headshot_shelf).
  purpose: "Multi-panel team home — handbook covers, pulse, dual attention, docs, then discussion"
  access: persona(admin, member)

  # Goal B media — recipe handbook_cover_wall (novel vs headshot_shelf).
  handbook_covers:
    source: WorkspaceDocument
    filter: preview_url != null
    sort: created_at desc
    limit: 6
    display: grid
    action: workspace_document_detail
    empty: "No handbook covers yet — attach briefs with cover previews"

  # Metrics honesty: count Announcement + documents (notes stay on conversation trail).
  team_pulse:
    source: Announcement
    display: metrics
    aggregate:
      announcements: count(Announcement)
      documents: count(WorkspaceDocument)
    tones:
      announcements: accent
      documents: accent

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

  # Goal B document composition after dual attention — named briefs before notes.
  composition:
    source: WorkspaceDocument
    sort: created_at desc
    limit: 3
    display: queue
    action: workspace_document_detail
    empty: "No workspace documents yet — attach a brief or handbook on a workspace hub"

  # Goal B conversation spine AFTER dual attention + docs — newest team notes.
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
      purpose: "Handbook cover wall first, then pulse, posts, readiness, and discussion"
      focus: handbook_covers, team_pulse, announcement_queue, join_readiness, composition, live_conversation
    as member:
      purpose: "Handbook cover wall first, then posts, readiness, and discussion trail"
      focus: handbook_covers, team_pulse, announcement_queue, join_readiness, composition, live_conversation

# Second product workspace lowers warehouse density (3 lists / 1 ws → deepen).
# Admin publish desk vs member reading feed (same entity, different job).
workspace announce "Team Board":
  # Goal B media FIRST (cycle 1887) + command_density + document: handbook
  # cover wall before pulse/feed — recipe handbook_cover_wall (not headshots).
  # empty_region_honesty: no duplicate queues / empty bar / workspace voids.
  purpose: "Multi-panel board — handbook covers, pulse, dual attention, docs, then discussion trail"
  access: persona(admin, member)

  # Goal B media — recipe handbook_cover_wall (novel vs headshot_shelf).
  handbook_covers:
    source: WorkspaceDocument
    filter: preview_url != null
    sort: created_at desc
    limit: 6
    display: grid
    action: workspace_document_detail
    empty: "No handbook covers yet — attach briefs with cover previews"

  board_pulse:
    source: Announcement
    display: metrics
    aggregate:
      posts: count(Announcement)
      documents: count(WorkspaceDocument)
    tones:
      posts: accent
      documents: accent

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

  # Goal B document composition after dual attention — named briefs before notes.
  composition:
    source: WorkspaceDocument
    sort: created_at desc
    limit: 3
    display: queue
    action: workspace_document_detail
    empty: "No workspace documents yet — attach a brief or handbook on a workspace hub"

  # Conversation AFTER dual attention + docs so Message chrome shares the fold.
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
      purpose: "Handbook cover wall first, then feed, context, and discussion"
      focus: handbook_covers, board_pulse, feed_queue, join_context, composition, live_conversation
    as member:
      purpose: "Handbook cover wall first, then posts, context, and conversation trail"
      focus: handbook_covers, board_pulse, feed_queue, join_context, composition, live_conversation

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

# Goal B org_structure (cycle 1869): peer directory tools (Okta / Google
# Workspace Admin / Microsoft Entra / Rippling) show joined staff by title and
# department after domain join — not a flat announcement dump before placement.
workspace team_home "Team":
  purpose: "Org structure for the joined company — pending join seats then title and department before flat roster"
  access: persona(admin, member)

  team_pulse:
    source: WorkspaceMember
    display: metrics
    aggregate:
      staff: count(WorkspaceMember)
      pending: count(WorkspaceMember where status = pending)
      active: count(WorkspaceMember where status = active)
      announcements: count(Announcement)
      documents: count(WorkspaceDocument)
    tones:
      staff: positive
      pending: warning
      active: accent
      announcements: accent
      documents: accent

  # Goal B org_structure (cycle 2090): recipe pending_join_seat —
  # Entra/Okta/Rippling show who is waiting to join before the title board.
  pending_joins:
    source: WorkspaceMember
    filter: status = pending
    sort: name asc
    limit: 4
    display: queue
    action: workspace_member_detail
    empty: "No pending joiners — everyone on the roster is active"

  # Title board — active seats only (pending stay on the join queue).
  by_title:
    source: WorkspaceMember
    filter: status = active
    display: kanban
    group_by: job_title
    sort: name asc
    limit: 12
    action: workspace_member_detail
    empty: "No titled staff yet"

  # Department placement — IT / People Ops / Security / Facilities.
  by_department:
    source: WorkspaceMember
    filter: status = active
    display: queue
    sort: department asc, name asc
    limit: 12
    action: workspace_member_detail
    empty: "No staff placed in departments yet"

  # Secondary flat roster (after hierarchy).
  people:
    source: WorkspaceMember
    display: queue
    sort: department asc, name asc
    limit: 25
    action: workspace_member_detail
    empty: "No joined staff yet"

  # Board load after org shape — announcements members will read.
  board_load:
    source: Announcement
    display: queue
    sort: title asc
    limit: 12
    action: announcement_detail
    empty: "No announcements yet"

  org_hint:
    display: status_list
    entries:
      - title: "By title board"
        caption: "Admin / IT Lead / People Ops / Security columns show who can act after join"
        icon: "users"
        state: accent
      - title: "Department queue"
        caption: "IT / People Ops / Security / Facilities before flat roster"
        icon: "building-2"
        state: positive
      - title: "Board load last"
        caption: "Announcements after you read org shape"
        icon: "megaphone"
        state: warning

  ux:
    as admin:
      purpose: "Pending join seats then title/department — Entra/Okta grain"
      focus: team_pulse, pending_joins, by_title, by_department
    as member:
      purpose: "See who is waiting to join, then title board"
      focus: team_pulse, pending_joins, by_title, by_department
