story ST-001 "User creates a new Contact":
  status: accepted
  persona: user
  trigger: form_submitted
  entities: [Contact]
  given:
    - "User has permission to create Contact"
  then:
    - "New Contact is saved to database"
    - "User sees confirmation message"

story ST-004 "User browses contacts alphabetically":
  persona: user
  trigger: user_click
  entities: [Contact]
  given:
    - "Contacts exist in the directory"
    - "User is on the contacts workspace"
  then:
    - "User sees all Contacts sorted by last_name, first_name"
    - "Contact list is scrollable"

story ST-005 "User searches contacts by name or company":
  persona: user
  trigger: form_submitted
  entities: [Contact]
  given:
    - "User is on the contact list surface"
    - "Contacts exist matching the query"
  then:
    - "User sees only Contacts whose first_name, last_name, email, or company matches"
    - "Search is case-insensitive"

story ST-006 "User views full contact details":
  persona: user
  trigger: user_click
  entities: [Contact]
  given:
    - "User clicked a contact row in the list"
  then:
    - "User sees all fields on the contact detail surface"
    - "User can return to the list via breadcrumb"

story ST-007 "User favourites a contact":
  persona: user
  trigger: user_click
  entities: [Contact]
  given:
    - "Contact.is_favorite = false"
  then:
    - "Contact.is_favorite becomes true"
    - "Favourite contacts sort to the top of the list"

story ST-008 "User edits an existing contact":
  persona: user
  trigger: form_submitted
  entities: [Contact]
  given:
    - "Contact exists"
    - "User has update permission on Contact"
  then:
    - "Updated fields are saved to database"
    - "updated_at timestamp is set"
