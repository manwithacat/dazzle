module ops_dashboard.guides

use ops_dashboard.core

# Onboarding for ops_dashboard. Two workspaces (command_center for
# live monitoring, incident_review for post-mortem). New ops
# engineers need to:
#
#   1. Register at least one System so alerts have something to
#      attach to (without registered systems, alerts can't fire).
#   2. Acknowledge an incoming alert to show they're working it.
#
# Admins set up the initial integrations and don't need overlays.

guide ops_first_run "Set up your operations console":
  audience: persona = ops_engineer

  step register_system:
    kind: empty_state
    target: surface.system_list
    title: "Register your first system"
    body: "Alerts attach to systems. Add the production service or environment you're monitoring before alerts start flowing."
    cta_label: "Register System"
    cta_target: surface.system_create
    complete_on: event entity.System.created

  step name_system:
    kind: popover
    target: surface.system_create
    title: "Name it after the deploy unit"
    body: "Use the same name your CI/CD pipeline uses — that's how alerts will cross-reference."
    placement: bottom
    complete_on: field_filled surface.system_create.field.name

  step explore_alerts:
    kind: inline_card
    target: surface.alert_list
    title: "Alerts flow into the queue automatically"
    body: "When an integrated system reports degraded health, an alert appears here. Click to acknowledge or escalate."
    cta_label: "View Alerts"
    cta_target: surface.alert_list
    complete_on: dismiss

  step ack_workflow:
    kind: nudge
    target: surface.alert_list
    title: "Acknowledge means 'I'm on it'"
    body: "It mutes the page-out cycle so others know not to double up."
    placement: "8000"
    complete_on: dismiss

  step_order: [register_system, name_system, explore_alerts, ack_workflow]

  on_complete:
    redirect: surface.alert_list
