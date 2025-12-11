# DAZZLE Contact Manager
# Demonstrates v0.7.1+ LLM Cognition Features:
# - Intent declarations for semantic clarity
# - Domain/pattern tags for classification
# - Invariants for data integrity
# - Workspace with dual_pane_flow stage

module contact_manager.core

app contact_manager "Contact Manager"

# Entity for contact information with LLM cognition metadata
entity Contact "Contact":
  intent: "Store professional and personal contact information for relationship management"
  domain: crm
  patterns: profile, searchable

  id: uuid pk
  first_name: str(100) required
  last_name: str(100) required
  email: email unique required
  phone: str(20)
  company: str(200)
  job_title: str(150)
  notes: text
  is_favorite: bool=false
  created_at: datetime auto_add
  updated_at: datetime auto_update

  # Invariant: contacts must have either email or phone
  invariant: email != null or phone != null

  index email
  index last_name,first_name

# List view - browsable contact directory
surface contact_list "Contact List":
  uses entity Contact
  mode: list

  section main "Contacts":
    field first_name "First Name"
    field last_name "Last Name"
    field email "Email"
    field company "Company"
    field is_favorite "Favorite"

  ux:
    purpose: "Browse and search contacts"
    sort: last_name asc, first_name asc
    filter: is_favorite
    search: first_name, last_name, email, company
    empty: "No contacts yet. Add your first contact!"

# Detail view - full contact information
surface contact_detail "Contact Detail":
  uses entity Contact
  mode: view

  section main "Contact Details":
    field first_name "First Name"
    field last_name "Last Name"
    field email "Email"
    field phone "Phone"
    field company "Company"
    field job_title "Job Title"
    field notes "Notes"
    field is_favorite "Favorite"
    field created_at "Created"
    field updated_at "Updated"

  ux:
    purpose: "View complete contact information"

# Create form
surface contact_create "Create Contact":
  uses entity Contact
  mode: create

  section main "New Contact":
    field first_name "First Name"
    field last_name "Last Name"
    field email "Email"
    field phone "Phone"
    field company "Company"
    field job_title "Job Title"
    field notes "Notes"

  ux:
    purpose: "Add a new contact"

# Edit form
surface contact_edit "Edit Contact":
  uses entity Contact
  mode: edit

  section main "Edit Contact":
    field first_name "First Name"
    field last_name "Last Name"
    field email "Email"
    field phone "Phone"
    field company "Company"
    field job_title "Job Title"
    field notes "Notes"
    field is_favorite "Favorite"

  ux:
    purpose: "Update contact information"

# Workspace with list + detail pattern
workspace contacts "Contacts":
  purpose: "Browse contacts and view details"
  stage: "dual_pane_flow"

  # List signal - browsable contact list
  contact_list:
    source: Contact
    sort: last_name asc, first_name asc
    limit: 20
    display: list
    action: contact_detail
    # Weight: 0.5 (base) + 0.1 (limit) = 0.6 (ITEM_LIST)

  # Detail signal - selected contact details
  contact_detail:
    source: Contact
    display: detail
    action: contact_edit
    # Weight: 0.5 (base) + 0.2 (detail) = 0.7 (DETAIL_VIEW)

# Stage Selection:
# - list_weight = 0.6 >= 0.3 ✓
# - detail_weight = 0.7 >= 0.3 ✓
# → DUAL_PANE_FLOW stage selected
#
# Layout:
# Desktop: Side-by-side list and detail panes
# Mobile: Stacked, detail slides over list on selection
