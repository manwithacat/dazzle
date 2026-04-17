story ST-001 "User creates a new User":
  actor: customer
  trigger: form_submitted
  scope: [User]
  given:
    - "User has permission to create User"
  then:
    - "New User is saved to database"
    - "User sees confirmation message"

story ST-002 "User creates a new Support Ticket":
  actor: customer
  trigger: form_submitted
  scope: [Ticket]
  given:
    - "User has permission to create Ticket"
  then:
    - "New Ticket is saved to database"
    - "User sees confirmation message"

story ST-003 "User changes Ticket from open to in_progress":
  actor: customer
  trigger: status_changed
  scope: [Ticket]
  given:
    - "Ticket.status is 'open'"
  then:
    - "Ticket.status becomes 'in_progress'"
    - "Timestamp is recorded"

story ST-004 "User changes Ticket from in_progress to resolved":
  actor: customer
  trigger: status_changed
  scope: [Ticket]
  given:
    - "Ticket.status is 'in_progress'"
  then:
    - "Ticket.status becomes 'resolved'"
    - "Timestamp is recorded"

story ST-005 "User changes Ticket from in_progress to open":
  actor: customer
  trigger: status_changed
  scope: [Ticket]
  given:
    - "Ticket.status is 'in_progress'"
  then:
    - "Ticket.status becomes 'open'"
    - "Timestamp is recorded"

story ST-006 "User creates a new Comment":
  actor: customer
  trigger: form_submitted
  scope: [Comment]
  given:
    - "User has permission to create Comment"
  then:
    - "New Comment is saved to database"
    - "User sees confirmation message"

story ST-007 "User creates a new User":
  actor: customer
  trigger: form_submitted
  scope: [User]
  given:
    - "User has permission to create User"
  then:
    - "New User is saved to database"
    - "User sees confirmation message"

story ST-008 "User creates a new Support Ticket":
  actor: customer
  trigger: form_submitted
  scope: [Ticket]
  given:
    - "User has permission to create Ticket"
  then:
    - "New Ticket is saved to database"
    - "User sees confirmation message"

story ST-009 "User changes Ticket from open to in_progress":
  actor: customer
  trigger: status_changed
  scope: [Ticket]
  given:
    - "Ticket.status is 'open'"
  then:
    - "Ticket.status becomes 'in_progress'"
    - "Timestamp is recorded"

story ST-010 "User changes Ticket from in_progress to resolved":
  actor: customer
  trigger: status_changed
  scope: [Ticket]
  given:
    - "Ticket.status is 'in_progress'"
  then:
    - "Ticket.status becomes 'resolved'"
    - "Timestamp is recorded"

story ST-011 "User changes Ticket from in_progress to open":
  actor: customer
  trigger: status_changed
  scope: [Ticket]
  given:
    - "Ticket.status is 'in_progress'"
  then:
    - "Ticket.status becomes 'open'"
    - "Timestamp is recorded"

story ST-012 "User creates a new Comment":
  actor: customer
  trigger: form_submitted
  scope: [Comment]
  given:
    - "User has permission to create Comment"
  then:
    - "New Comment is saved to database"
    - "User sees confirmation message"

story ST-013 "User creates a new User":
  status: accepted
  actor: customer
  trigger: form_submitted
  scope: [User]
  given:
    - "User has permission to create User"
  then:
    - "New User is saved to database"
    - "User sees confirmation message"

story ST-014 "User creates a new Support Ticket":
  status: accepted
  actor: customer
  trigger: form_submitted
  scope: [Ticket]
  given:
    - "User has permission to create Ticket"
  then:
    - "New Ticket is saved to database"
    - "User sees confirmation message"

story ST-015 "User changes Ticket from open to in_progress":
  status: accepted
  actor: customer
  trigger: status_changed
  scope: [Ticket]
  given:
    - "Ticket.status is 'open'"
  then:
    - "Ticket.status becomes 'in_progress'"

story ST-016 "User changes Ticket from in_progress to resolved":
  status: accepted
  actor: customer
  trigger: status_changed
  scope: [Ticket]
  given:
    - "Ticket.status is 'in_progress'"
  then:
    - "Ticket.status becomes 'resolved'"

story ST-017 "User changes Ticket from in_progress to open":
  status: accepted
  actor: customer
  trigger: status_changed
  scope: [Ticket]
  given:
    - "Ticket.status is 'in_progress'"
  then:
    - "Ticket.status becomes 'open'"

story ST-018 "User creates a new Comment":
  status: accepted
  actor: customer
  trigger: form_submitted
  scope: [Comment]
  given:
    - "User has permission to create Comment"
  then:
    - "New Comment is saved to database"
    - "User sees confirmation message"

story ST-019 "Support Agent views all open tickets in a filterable list":
  actor: agent
  trigger: user_click
  scope: [Ticket]
  given:
    - "Support Agent is on the ticket_queue workspace"
  then:
    - "Support Agent sees all Tickets where status != closed"
    - "Agent can filter by priority, category, and assigned_to"

story ST-020 "Support Agent picks up a ticket":
  actor: agent
  trigger: form_submitted
  scope: [Ticket]
  given:
    - "Ticket.assigned_to is null"
    - "Ticket.status is 'open'"
  then:
    - "Ticket.assigned_to becomes the current agent"
    - "Ticket.status transitions to 'in_progress'"

story ST-021 "Support Agent views full ticket detail with comment history":
  actor: agent
  trigger: user_click
  scope: [Ticket, Comment]
  given:
    - "Ticket exists"
  then:
    - "Support Agent sees the Ticket detail with all Comments"
    - "Internal comments are visually distinguished from customer-visible comments"

story ST-022 "Support Agent adds an internal note":
  actor: agent
  trigger: form_submitted
  scope: [Comment]
  given:
    - "Support Agent is viewing a Ticket"
  then:
    - "Comment is created with is_internal=true"
    - "Comment is visible only to agents and managers"

story ST-023 "Support Agent resolves a ticket":
  actor: agent
  trigger: status_changed
  scope: [Ticket]
  given:
    - "Ticket.status is 'in_progress'"
    - "Resolution is provided"
  then:
    - "Ticket.status becomes 'resolved'"
    - "Customer is notified"

story ST-024 "Customer creates a support ticket":
  actor: customer
  trigger: form_submitted
  scope: [Ticket]
  given:
    - "Customer is on the my_tickets workspace"
  then:
    - "New Ticket is saved with created_by = current customer"
    - "Ticket.status starts as 'open'"

story ST-025 "Customer views their submitted tickets":
  actor: customer
  trigger: user_click
  scope: [Ticket]
  given:
    - "Customer has submitted at least one Ticket"
  then:
    - "Customer sees only Tickets where created_by = self"
    - "Customer cannot see Tickets from other customers"

story ST-026 "Customer follows up on an existing ticket":
  actor: customer
  trigger: form_submitted
  scope: [Comment]
  given:
    - "Ticket exists created by the customer"
  then:
    - "Comment is created with is_internal=false"
    - "Support Agent is notified of the new comment"

story ST-027 "Support Manager reviews team performance":
  actor: manager
  trigger: user_click
  scope: [Ticket, User]
  given:
    - "Support Manager is on the agent_dashboard"
  then:
    - "Manager sees counts of resolved vs open tickets per Agent"
    - "Manager sees average resolution time across the team"

story ST-028 "Support Manager reassigns a ticket":
  actor: manager
  trigger: form_submitted
  scope: [Ticket]
  given:
    - "Ticket.assigned_to is set"
    - "Support Manager is viewing the Ticket"
  then:
    - "Ticket.assigned_to is updated to the chosen Agent"
    - "Previous assignee is notified of the reassignment"

story ST-029 "Support Manager escalates a critical ticket":
  actor: manager
  trigger: status_changed
  scope: [Ticket]
  given:
    - "Ticket.priority is 'critical'"
  then:
    - "Ticket is flagged for immediate attention"
    - "All online agents are notified"

story ST-030 "Administrator triages the full ticket queue":
  actor: admin
  trigger: user_click
  scope: [Ticket]
  given:
    - "Administrator is on the _platform_admin workspace"
  then:
    - "Administrator sees every Ticket regardless of customer, agent, or status"
    - "Administrator can bulk-update status on selected Tickets"
