module ops_dashboard.guides

use ops_dashboard.core

# Onboarding for ops_dashboard. Two workspaces (command_center for
# live monitoring, incident_review for post-mortem). A new ops
# engineer's first job is to acknowledge an incoming alert to show
# they're working it.
#
# System registration is admin-only (#1123): admins set up the initial
# integrations. The ops_engineer onboarding therefore does NOT offer a
# "register a system" CTA — that surface 403s for this persona, and the
# guide-concordance pass hard-errors on a CTA whose audience can't reach
# it (#1292). Alert-response is what this persona can actually do.

guide ops_first_run "Respond to your first alert":
  audience: persona = ops_engineer

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

  step_order: [explore_alerts, ack_workflow]

  on_complete:
    redirect: surface.alert_list
