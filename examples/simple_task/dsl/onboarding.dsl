module simple_task.guides

use simple_task.core

# First-run onboarding guide for the simple_task example app.
# Demonstrates the v0.71.0 guided-onboarding primitive — concordance
# with the DSL is enforced at `dazzle validate` time.
#
# Workflow:
#   1. Land on /tasks empty list -> popover invites user to create the first task
#   2. Fire the `entity.Task.created` event -> step completes
#   3. Land on the create form -> inline_card prompts to fill in a title
#   4. Title field fills in -> step completes
#   5. Optional: visit team-member list -> dismissable closing card
#
# All targets/events/cta surfaces are real DSL nodes; the linker
# refuses to compile this block if any of them drifts.

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
