story ST-001 "User creates a new User":
  actor: User
  trigger: form_submitted
  scope: [User]
  given:
    - "User has permission to create User"
  then:
    - "New User is saved to database"
    - "User sees confirmation message"

story ST-002 "User creates a new Support Ticket":
  actor: User
  trigger: form_submitted
  scope: [Ticket]
  given:
    - "User has permission to create Ticket"
  then:
    - "New Ticket is saved to database"
    - "User sees confirmation message"

story ST-003 "User changes Ticket from open to in_progress":
  actor: User
  trigger: status_changed
  scope: [Ticket]
  given:
    - "Ticket.status is 'open'"
  then:
    - "Ticket.status becomes 'in_progress'"
    - "Timestamp is recorded"

story ST-004 "User changes Ticket from in_progress to resolved":
  actor: User
  trigger: status_changed
  scope: [Ticket]
  given:
    - "Ticket.status is 'in_progress'"
  then:
    - "Ticket.status becomes 'resolved'"
    - "Timestamp is recorded"

story ST-005 "User changes Ticket from in_progress to open":
  actor: User
  trigger: status_changed
  scope: [Ticket]
  given:
    - "Ticket.status is 'in_progress'"
  then:
    - "Ticket.status becomes 'open'"
    - "Timestamp is recorded"

story ST-006 "User creates a new Comment":
  actor: User
  trigger: form_submitted
  scope: [Comment]
  given:
    - "User has permission to create Comment"
  then:
    - "New Comment is saved to database"
    - "User sees confirmation message"

story ST-007 "User creates a new User":
  actor: User
  trigger: form_submitted
  scope: [User]
  given:
    - "User has permission to create User"
  then:
    - "New User is saved to database"
    - "User sees confirmation message"

story ST-008 "User creates a new Support Ticket":
  actor: User
  trigger: form_submitted
  scope: [Ticket]
  given:
    - "User has permission to create Ticket"
  then:
    - "New Ticket is saved to database"
    - "User sees confirmation message"

story ST-009 "User changes Ticket from open to in_progress":
  actor: User
  trigger: status_changed
  scope: [Ticket]
  given:
    - "Ticket.status is 'open'"
  then:
    - "Ticket.status becomes 'in_progress'"
    - "Timestamp is recorded"

story ST-010 "User changes Ticket from in_progress to resolved":
  actor: User
  trigger: status_changed
  scope: [Ticket]
  given:
    - "Ticket.status is 'in_progress'"
  then:
    - "Ticket.status becomes 'resolved'"
    - "Timestamp is recorded"

story ST-011 "User changes Ticket from in_progress to open":
  actor: User
  trigger: status_changed
  scope: [Ticket]
  given:
    - "Ticket.status is 'in_progress'"
  then:
    - "Ticket.status becomes 'open'"
    - "Timestamp is recorded"

story ST-012 "User creates a new Comment":
  actor: User
  trigger: form_submitted
  scope: [Comment]
  given:
    - "User has permission to create Comment"
  then:
    - "New Comment is saved to database"
    - "User sees confirmation message"

story ST-013 "User creates a new User":
  status: accepted
  actor: User
  trigger: form_submitted
  scope: [User]
  given:
    - "User has permission to create User"
  then:
    - "New User is saved to database"
    - "User sees confirmation message"

story ST-014 "User creates a new Support Ticket":
  status: accepted
  actor: User
  trigger: form_submitted
  scope: [Ticket]
  given:
    - "User has permission to create Ticket"
  then:
    - "New Ticket is saved to database"
    - "User sees confirmation message"

story ST-015 "User changes Ticket from open to in_progress":
  status: accepted
  actor: User
  trigger: status_changed
  scope: [Ticket]
  given:
    - "Ticket.status is 'open'"
  then:
    - "Ticket.status becomes 'in_progress'"

story ST-016 "User changes Ticket from in_progress to resolved":
  status: accepted
  actor: User
  trigger: status_changed
  scope: [Ticket]
  given:
    - "Ticket.status is 'in_progress'"
  then:
    - "Ticket.status becomes 'resolved'"

story ST-017 "User changes Ticket from in_progress to open":
  status: accepted
  actor: User
  trigger: status_changed
  scope: [Ticket]
  given:
    - "Ticket.status is 'in_progress'"
  then:
    - "Ticket.status becomes 'open'"

story ST-018 "User creates a new Comment":
  status: accepted
  actor: User
  trigger: form_submitted
  scope: [Comment]
  given:
    - "User has permission to create Comment"
  then:
    - "New Comment is saved to database"
    - "User sees confirmation message"
