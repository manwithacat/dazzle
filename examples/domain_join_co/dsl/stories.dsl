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
    - "Row open hops to Announcement via id (detail hub, not a dead warehouse row)"

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
    - "Announcement hub shows summary (title, workspace) and body sections"
    - "Member cannot create or update announcements"
