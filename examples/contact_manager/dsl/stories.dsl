story ST-001 "User creates a new Contact":
  status: accepted
  actor: user
  trigger: form_submitted
  scope: [Contact]
  given:
    - "User has permission to create Contact"
  then:
    - "New Contact is saved to database"
    - "User sees confirmation message"

story ST-004 "User browses contacts alphabetically":
  actor: user
  trigger: user_click
  scope: [Contact]
  given:
    - "Contacts exist in the directory"
    - "User is on the contacts workspace"
  then:
    - "User sees all Contacts sorted by last_name, first_name"
    - "Contact list is scrollable"

story ST-005 "User searches contacts by name or company":
  actor: user
  trigger: form_submitted
  scope: [Contact]
  given:
    - "User is on the contact list surface"
    - "Contacts exist matching the query"
  then:
    - "User sees only Contacts whose first_name, last_name, email, or company matches"
    - "Search is case-insensitive"

story ST-006 "User views full contact details":
  actor: user
  trigger: user_click
  scope: [Contact]
  given:
    - "User clicked a contact row in the list"
  then:
    - "User sees all fields on the contact detail surface"
    - "User can return to the list via breadcrumb"

story ST-007 "User favourites a contact":
  actor: user
  trigger: status_changed
  scope: [Contact]
  given:
    - "Contact.is_favorite = false"
  then:
    - "Contact.is_favorite becomes true"
    - "Favourite contacts sort to the top of the list"

story ST-008 "User edits an existing contact":
  actor: user
  trigger: form_submitted
  scope: [Contact]
  given:
    - "Contact exists"
    - "User has update permission on Contact"
  then:
    - "Updated fields are saved to database"
    - "updated_at timestamp is set"
