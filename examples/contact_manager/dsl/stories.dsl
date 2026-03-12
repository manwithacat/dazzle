story ST-001 "User creates a new Contact":
  actor: User
  trigger: form_submitted
  scope: [Contact]
  given:
    - "User has permission to create Contact"
  then:
    - "New Contact is saved to database"
    - "User sees confirmation message"

story ST-002 "User creates a new Contact":
  actor: User
  trigger: form_submitted
  scope: [Contact]
  given:
    - "User has permission to create Contact"
  then:
    - "New Contact is saved to database"
    - "User sees confirmation message"

story ST-003 "User creates a new Contact":
  status: accepted
  actor: User
  trigger: form_submitted
  scope: [Contact]
  given:
    - "User has permission to create Contact"
  then:
    - "New Contact is saved to database"
    - "User sees confirmation message"
