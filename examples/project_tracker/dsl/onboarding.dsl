module project_tracker.guides

use project_tracker.core

# Per-persona first-run onboarding for Project Tracker.
#   - manager: plan projects, break them into tasks, track milestones
#   - member:  pick up assigned work, move it forward, collaborate
# Admins are out of scope (power users). Targets are surfaces; the
# concordance linker validates every target / event / cta at
# `dazzle validate` time.

# ─── Project Manager journey ──────────────────────────────────────

guide manager_onboarding "Plan and run your projects":
  audience: persona = manager

  step new_project:
    kind: empty_state
    target: surface.project_list
    title: "Start with a project"
    body: "Every initiative is a project. Create one, set its owner and dates, then fill it with the work."
    cta_label: "New Project"
    cta_target: surface.project_create
    complete_on: event entity.Project.created

  step break_it_down:
    kind: inline_card
    target: surface.task_list
    title: "Break it into tasks"
    body: "Create tasks under the project and assign each to a team member, so every piece of work is clearly owned."
    cta_label: "New Task"
    cta_target: surface.task_create
    complete_on: event entity.Task.created

  step track_milestones:
    kind: banner
    target: surface.milestone_list
    title: "Mark the milestones"
    body: "Group tasks under milestones to track progress against the dates that matter to the client."
    complete_on: dismiss

  step_order: [new_project, break_it_down, track_milestones]

  on_complete:
    redirect: surface.project_list

# ─── Team Member journey ──────────────────────────────────────────

guide member_onboarding "Working your tasks":
  audience: persona = member

  step your_board:
    kind: spotlight
    target: surface.task_list
    title: "Your assigned work"
    body: "These are the tasks assigned to you. Start with what's next and open one to see the detail."
    placement: center
    complete_on: dismiss

  step move_forward:
    kind: popover
    target: surface.task_detail
    title: "Move work forward"
    body: "Set a task to In Progress when you start it, and to Review when it's ready for a second pair of eyes."
    placement: bottom
    complete_on: dismiss

  step collaborate:
    kind: inline_card
    target: surface.task_detail
    title: "Keep the thread updated"
    body: "Use the comment thread on a task to share progress, and attach files when they help explain the work."
    complete_on: dismiss

  step_order: [your_board, move_forward, collaborate]

  on_complete:
    redirect: surface.task_list
