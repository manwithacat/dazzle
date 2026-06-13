module simple_task.guides

use simple_task.core

# Per-persona first-run onboarding for Team Task Manager.
#
# One guide per interactive persona, each rooted in the work that
# persona actually does:
#   - admin   (workspace_setup):   set the board up + invite the team
#   - manager (manager_onboarding): triage, review, and assign team work
#   - member  (member_onboarding):  pick up, progress, and submit your tasks
#
# Copy stays terse and speaks as the product. All targets/events/cta
# surfaces are real DSL nodes; the linker refuses to compile this block
# if any of them drifts (concordance is enforced at `dazzle validate`).

guide workspace_setup "First-run setup":
  audience: persona = admin

  step welcome_empty:
    kind: empty_state
    target: surface.task_list
    title: "Welcome — create your first task"
    body: "Tasks let you track work across the team. Click below to get started."
    cta_label: "New Task"
    cta_target: surface.task_create
    complete_on: event entity.Task.created

  step fill_title:
    kind: popover
    target: surface.task_create
    title: "Give your task a title"
    body: "A clear, action-oriented title helps the team scan their list."
    placement: bottom
    complete_on: field_filled surface.task_create.field.title

  step invite_team:
    kind: inline_card
    target: surface.user_list
    title: "Invite your team"
    body: "Other admins and members can co-edit and be assigned tasks."
    cta_label: "Add Team Member"
    cta_target: surface.user_create
    complete_on: dismiss

  step_order: [welcome_empty, fill_title, invite_team]

  on_complete:
    redirect: surface.task_list

# ─── Team Manager journey ─────────────────────────────────────────
# Managers triage the queue: review submitted work and assign what's
# waiting. Rooted on the task list they monitor from Team Overview.

guide manager_onboarding "Keeping the team on track":
  audience: persona = manager

  step pulse:
    kind: spotlight
    target: surface.task_list
    title: "Your team's work, at a glance"
    body: "Every task across the team lives here. Filter by status to spot what's in review, in progress, or still waiting to be picked up."
    placement: center
    complete_on: dismiss

  step review_work:
    kind: popover
    target: surface.task_edit
    title: "Review and move work forward"
    body: "Open a task that's in Review, then mark it Done — or send it back to In Progress if it needs another pass."
    placement: bottom
    complete_on: dismiss

  step assign_work:
    kind: inline_card
    target: surface.task_list
    title: "Hand work to the right person"
    body: "Create a task and choose an assignee, so everyone knows what's theirs and nothing slips through the cracks."
    cta_label: "New Task"
    cta_target: surface.task_create
    complete_on: event entity.Task.created

  step_order: [pulse, review_work, assign_work]

  on_complete:
    redirect: surface.task_list

# ─── Team Member journey ──────────────────────────────────────────
# Members work their own queue: pick up assigned work, mark it in
# progress, and send it for review when it's done.

guide member_onboarding "Working your tasks":
  audience: persona = member

  step your_work:
    kind: spotlight
    target: surface.task_list
    title: "Your tasks, front and centre"
    body: "These are the tasks assigned to you, grouped by status. Start with your backlog and pick what to work on next."
    placement: center
    complete_on: dismiss

  step start_it:
    kind: popover
    target: surface.task_detail
    title: "Open a task to begin"
    body: "Move it to In Progress when you start — that tells your manager the work is underway."
    placement: bottom
    complete_on: dismiss

  step send_review:
    kind: inline_card
    target: surface.task_edit
    title: "Finished? Send it for review"
    body: "Set the status to Review when your work is ready, and your manager takes it from there."
    complete_on: dismiss

  step_order: [your_work, start_it, send_review]

  on_complete:
    redirect: surface.task_list
