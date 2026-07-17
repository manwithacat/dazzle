# Journey-bound stories for contact_manager agent-first dogfood.
# Warehouse lists alone are not enough — list→hub + favourites queues must prove green.

story ST-001 "User creates a new Contact":
  status: accepted
  narrative_only: true
  persona: user
  trigger: form_submitted
  entities: [Contact]
  given:
    - "User has permission to create Contact"
  then:
    - "New Contact is saved to database"
    - "User sees confirmation message"

story ST-004 "User works Home overview then opens a contact hub":
  status: accepted
  executed_by: surface.contact_list
  persona: user
  trigger: user_click
  entities: [Contact]
  given:
    - "User is on the home workspace"
    - "Contacts exist in the directory"
  then:
    - "User sees directory metrics and the favourites queue before the full list"
    - "Opening a contact row hops to the Contact detail hub"

story ST-005 "User browses the dual-pane directory with favourites strip":
  status: accepted
  executed_by: surface.contact_list
  persona: user
  trigger: user_click
  entities: [Contact]
  given:
    - "User is on the contacts workspace"
    - "Contacts exist matching a search or A–Z sort"
  then:
    - "User sees favourites queue above the A–Z list"
    - "Row open hops to Contact via id (detail hub, not a dead warehouse row)"
    - "Search filters by first_name, last_name, email, or company"

story ST-006 "User opens contact hub for call context":
  status: accepted
  executed_by: surface.contact_detail
  persona: user
  trigger: user_click
  entities: [Contact]
  given:
    - "User selected a contact from the list or favourites queue"
  then:
    - "Contact hub shows identity, employment strip, and notes/timeline sections"
    - "User can return to the dual-pane list without losing browse context"

story ST-007 "User pins a favourite from the directory queue":
  status: accepted
  executed_by: surface.contact_edit
  persona: user
  trigger: user_click
  entities: [Contact]
  given:
    - "Contact.is_favorite = false"
    - "User is on home or contacts workspace"
  then:
    - "Contact.is_favorite becomes true"
    - "Favourite appears in the home and contacts favourites queues"

story ST-008 "User edits an existing contact":
  status: accepted
  narrative_only: true
  persona: user
  trigger: form_submitted
  entities: [Contact]
  given:
    - "Contact exists"
    - "User has update permission on Contact"
  then:
    - "Updated fields are saved to database"
    - "updated_at timestamp is set"
