story ST-013 "Manager invites a new team User":
  status: accepted
  executed_by: surface.user_create
  persona: manager
  trigger: form_submitted
  entities: [User]
  given:
    - "Manager has permission to create User"
  then:
    - "New User is saved to database"
    - "Manager sees confirmation message"

story ST-014 "User creates a new Support Ticket":
  status: accepted
  executed_by: surface.ticket_create
  persona: customer
  trigger: form_submitted
  entities: [Ticket]
  given:
    - "User has permission to create Ticket"
  then:
    - "New Ticket is saved to database"
    - "User sees confirmation message"

story ST-015 "Agent moves Ticket from open to in_progress":
  status: accepted
  executed_by: surface.ticket_edit
  persona: agent
  trigger: status_changed
  entities: [Ticket]
  given:
    - "Ticket.status is 'open'"
    - "Agent has update permission on Ticket"
  then:
    - "Ticket.status becomes 'in_progress'"

story ST-016 "Agent moves Ticket from in_progress to resolved":
  status: accepted
  executed_by: surface.ticket_edit
  persona: agent
  trigger: status_changed
  entities: [Ticket]
  given:
    - "Ticket.status is 'in_progress'"
    - "Resolution is provided"
  then:
    - "Ticket.status becomes 'resolved'"

story ST-017 "Agent reopens Ticket from in_progress to open":
  status: accepted
  executed_by: surface.ticket_edit
  persona: agent
  trigger: status_changed
  entities: [Ticket]
  given:
    - "Ticket.status is 'in_progress'"
  then:
    - "Ticket.status becomes 'open'"

story ST-018 "User creates a new Comment":
  status: accepted
  executed_by: surface.comment_create
  persona: customer
  trigger: form_submitted
  entities: [Comment]
  given:
    - "User has permission to create Comment"
  then:
    - "New Comment is saved to database"
    - "User sees confirmation message"

story ST-019 "Support Agent works the open ticket queue":
  status: accepted
  executed_by: surface.ticket_list
  persona: agent
  trigger: user_click
  entities: [Ticket]
  given:
    - "Support Agent is on the ticket_queue workspace"
  then:
    - "Support Agent sees open Tickets in a review queue (status != closed)"
    - "Queue metrics show open, in-progress, and critical counts"
    - "Agent can act on a row (claim / transition / open detail hub)"

story ST-020 "Support Agent picks up a ticket":
  status: accepted
  executed_by: surface.ticket_edit
  persona: agent
  trigger: form_submitted
  entities: [Ticket]
  given:
    - "Ticket.assigned_to is null"
    - "Ticket.status is 'open'"
  then:
    - "Ticket.assigned_to becomes the current agent"
    - "Ticket.status transitions to 'in_progress'"

story ST-021 "Support Agent views full ticket detail with comment history":
  status: accepted
  executed_by: surface.ticket_detail
  persona: agent
  trigger: user_click
  entities: [Ticket, Comment]
  given:
    - "Ticket exists"
  then:
    - "Support Agent sees the Ticket hub (status strip + discussion related)"
    - "Internal comments are visually distinguished from customer-visible comments"

story ST-022 "Support Agent adds an internal note":
  status: accepted
  executed_by: surface.comment_create
  persona: agent
  trigger: form_submitted
  entities: [Comment]
  given:
    - "Support Agent is viewing a Ticket"
  then:
    - "Comment is created with is_internal=true"
    - "Comment is visible only to agents and managers"

story ST-023 "Support Agent resolves a ticket":
  status: accepted
  executed_by: surface.ticket_edit
  persona: agent
  trigger: status_changed
  entities: [Ticket]
  given:
    - "Ticket.status is 'in_progress'"
    - "Resolution is provided"
  then:
    - "Ticket.status becomes 'resolved'"
    - "Customer is notified"

story ST-024 "Customer creates a support ticket":
  status: accepted
  executed_by: surface.ticket_create
  persona: customer
  trigger: form_submitted
  entities: [Ticket]
  given:
    - "Customer is on the my_tickets workspace"
  then:
    - "New Ticket is saved with created_by = current customer"
    - "Ticket.status starts as 'open'"

story ST-025 "Customer views their submitted tickets":
  status: accepted
  executed_by: surface.ticket_list
  persona: customer
  trigger: user_click
  entities: [Ticket]
  given:
    - "Customer has submitted at least one Ticket"
  then:
    - "Customer sees only Tickets where created_by = self"
    - "Customer cannot see Tickets from other customers"
    - "Row open hops to the ticket context hub"

story ST-026 "Customer follows up on an existing ticket":
  status: accepted
  executed_by: surface.comment_create
  persona: customer
  trigger: form_submitted
  entities: [Comment]
  given:
    - "Ticket exists created by the customer"
  then:
    - "Comment is created with is_internal=false"
    - "Support Agent is notified of the new comment"

story ST-027 "Support Manager reviews team performance":
  status: accepted
  executed_by: surface.ticket_list
  persona: manager
  trigger: user_click
  entities: [Ticket, User]
  given:
    - "Support Manager is on the manager_ops workspace"
  then:
    - "Manager sees open, in-progress, critical, and resolved ticket counts"
    - "Manager sees the SLA readiness strip and critical / unassigned queues"

story ST-028 "Support Manager reassigns a ticket":
  status: accepted
  executed_by: surface.ticket_edit
  persona: manager
  trigger: form_submitted
  entities: [Ticket]
  given:
    - "Ticket.assigned_to is set"
    - "Support Manager is viewing the Ticket"
  then:
    - "Ticket.assigned_to is updated to the chosen Agent"
    - "Previous assignee is notified of the reassignment"

story ST-029 "Support Manager escalates a critical ticket":
  status: accepted
  executed_by: surface.ticket_edit
  persona: manager
  trigger: status_changed
  entities: [Ticket]
  given:
    - "Ticket.priority is 'critical'"
  then:
    - "Ticket is flagged for immediate attention"
    - "All online agents are notified"

story ST-030 "Administrator triages the full ticket queue":
  status: accepted
  executed_by: surface.ticket_list
  persona: admin
  trigger: user_click
  entities: [Ticket]
  given:
    - "Administrator is on the _platform_admin workspace"
  then:
    - "Administrator sees every Ticket regardless of customer, agent, or status"
    - "Administrator can bulk-update status on selected Tickets"
