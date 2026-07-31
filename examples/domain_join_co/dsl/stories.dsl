module domain_join_co.stories

# Journey-bound stories — tenant-scoped announcement board after domain join.
# Domain verify / join-request approval live in admin console (not DSL).

story ST-001 "Admin posts a team announcement from the workspace home":
  status: accepted
  executed_by: surface.announcement_create
  persona: admin
  trigger: form_submitted
  entities: [Announcement]
  given:
    - "Admin is on the home workspace after domain join is configured"
    - "Admin has create permission on Announcement"
  then:
    - "New Announcement is saved scoped to current_tenant workspace"
    - "Announcement appears in team_pulse metrics and the home feed"

story ST-002 "Admin browses announcements and opens the hub":
  status: accepted
  executed_by: surface.announcement_list
  persona: admin
  trigger: user_click
  entities: [Announcement]
  given:
    - "Admin is on the home workspace"
    - "Announcements exist in the tenant"
  then:
    - "Admin sees join_readiness strip and announcement metrics"
    - "Row open hops to Announcement via id or Workspace via workspace (pipe dual open, not a dead warehouse row)"

story ST-003 "Member reads the team board after self-join":
  status: accepted
  executed_by: surface.announcement_list
  persona: member
  trigger: user_click
  entities: [Announcement]
  given:
    - "Member joined via verified company email"
    - "Member is on the home workspace"
  then:
    - "Member sees only announcements for their current_tenant workspace"
    - "Opening a row lands on the Announcement hub with title and body"

story ST-004 "Member opens an announcement hub for full context":
  status: accepted
  executed_by: surface.announcement_detail
  persona: member
  trigger: user_click
  entities: [Announcement]
  given:
    - "Announcement exists and is readable under current_tenant"
  then:
    - "Announcement hub shows lifecycle strip (title, status, workspace) and body"
    - "Member cannot create or update announcements"

story ST-005 "Admin opens a workspace hub from the board":
  status: accepted
  executed_by: surface.workspace_detail
  persona: admin
  trigger: user_click
  entities: [Workspace, Announcement]
  given:
    - "Admin is on the home or announce workspace"
    - "At least one Workspace tenant root exists"
  then:
    - "Workspace hub shows identity strip (name, slug, role)"
    - "Related announcements appear as a pull queue (title + status), not a warehouse table"

story ST-006 "Admin works the publish desk draft queue into a post hub":
  status: accepted
  executed_by: surface.announcement_detail
  persona: admin
  trigger: user_click
  entities: [Announcement]
  given:
    - "Admin is on the publish_desk workspace"
    - "At least one draft Announcement exists"
  then:
    - "Draft queue lists only status=draft posts"
    - "Opening a draft hops to the Announcement hub with lifecycle strip"
    - "Live cards list only published posts for board pulse"
