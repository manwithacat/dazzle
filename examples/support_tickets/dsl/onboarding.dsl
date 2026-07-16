module support_tickets.guides

use support_tickets.core

# Three onboarding guides — one per primary job persona:
#
#   1. customer_onboarding: customer lands on my_tickets, walks them
#      through filing their first ticket.
#   2. agent_onboarding: agent lands on ticket_queue, walks them through
#      claiming + commenting on a ticket.
#   3. manager_onboarding: manager lands on manager_ops, walks them through
#      metrics + critical queue.
#
# Admin personas are deliberately not targeted — admins know what
# they're doing and overlays would just be friction.

# ─── Customer journey ─────────────────────────────────────────────

guide customer_onboarding "Filing your first ticket":
  audience: persona = customer

  step welcome_empty:
    kind: empty_state
    target: surface.ticket_list
    title: "Need help? File a ticket"
    body: "Describe your issue and a support agent will pick it up. You'll see all your tickets here once they're filed."
    cta_label: "New Ticket"
    cta_target: surface.ticket_create
    complete_on: event entity.Ticket.created

  step write_title:
    kind: popover
    target: surface.ticket_create
    title: "Write a clear subject"
    body: "Keep the title short and specific — that's the first thing the agent sees in the queue."
    placement: bottom
    complete_on: field_filled surface.ticket_create.field.title

  step add_details:
    kind: inline_card
    target: surface.ticket_create
    title: "Add as much detail as you can"
    body: "Steps to reproduce, error messages, what you expected vs what happened — anything that helps the agent fix it without a follow-up."
    complete_on: field_filled surface.ticket_create.field.description

  step await_agent:
    kind: banner
    target: surface.ticket_list
    title: "Ticket filed — we'll be in touch"
    body: "An agent will pick this up shortly. You'll get a notification when there's an update."
    complete_on: dismiss

  step_order: [welcome_empty, write_title, add_details, await_agent]

  on_complete:
    redirect: surface.ticket_list

# ─── Agent journey ────────────────────────────────────────────────

guide agent_onboarding "Working the support queue":
  audience: persona = agent

  step welcome_queue:
    kind: spotlight
    target: surface.ticket_list
    title: "Welcome to the queue"
    body: "Metrics show open pressure; the queue below is every open team ticket. Claim one to start working it."
    placement: center
    complete_on: dismiss

  step claim_first:
    kind: popover
    target: surface.ticket_list
    title: "Pick a ticket to claim"
    body: "Open the ticket and assign it to yourself. Customers see the assignee on their ticket page."
    placement: bottom
    complete_on: dismiss

  step write_comment:
    kind: inline_card
    target: surface.comment_create
    title: "Reply to the customer"
    body: "Use the comment thread for back-and-forth. Stay concise — the customer can see everything you write."
    complete_on: event entity.Comment.created

  step_order: [welcome_queue, claim_first, write_comment]

  on_complete:
    redirect: surface.ticket_list

# ─── Manager journey ──────────────────────────────────────────────

guide manager_onboarding "Running the support team":
  audience: persona = manager

  step welcome_ops:
    kind: spotlight
    target: surface.ticket_list
    title: "Team ops at a glance"
    body: "Start with metrics and the SLA strip, then work the critical and unassigned queues. The agent ticket queue stays available for full triage."
    placement: center
    complete_on: dismiss

  step critical_first:
    kind: popover
    target: surface.ticket_list
    title: "Critical and unassigned first"
    body: "Reassign or escalate from the focused queues — do not hunt through a personal assigned list."
    placement: bottom
    complete_on: dismiss

  step_order: [welcome_ops, critical_first]

  on_complete:
    redirect: surface.ticket_list
