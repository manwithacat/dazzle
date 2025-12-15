# Entity with state machine transitions
module corpus.state_machine
app state_machine_app "State Machine App"

entity Ticket "Support Ticket":
  archetype: versioned
  id: uuid pk
  title: str(200) required
  description: text optional
  assignee: str(100) optional
  resolution_note: text optional
  status: enum[open,assigned,in_progress,resolved,closed]=open

  transitions:
    open -> assigned: requires assignee
    assigned -> in_progress
    in_progress -> resolved: requires resolution_note
    resolved -> closed: auto after 7 days
    * -> open: role(admin)

entity Order "Order":
  id: uuid pk
  customer_name: str(200) required
  total: decimal(10,2) required
  status: enum[draft,pending,confirmed,shipped,delivered,cancelled]=draft

  transitions:
    draft -> pending
    pending -> confirmed
    confirmed -> shipped
    shipped -> delivered
    pending -> cancelled
    confirmed -> cancelled: role(manager)

surface ticket_list "Tickets":
  uses entity Ticket
  mode: list
  section main:
    field title "Title"
    field status "Status"
    field assignee "Assignee"

surface order_list "Orders":
  uses entity Order
  mode: list
  section main:
    field customer_name "Customer"
    field total "Total"
    field status "Status"
