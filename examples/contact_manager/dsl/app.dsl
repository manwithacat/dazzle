# DAZZLE Contact Manager - DUAL_PANE_FLOW Archetype Example
# Demonstrates list + detail pattern with explicit display modes

module contact_manager.core

app contact_manager "Contact Manager"

# Entity for contact information
entity Contact "Contact":
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

  index email
  index last_name,first_name

# Workspace with list + detail signals
# Should trigger DUAL_PANE_FLOW archetype
workspace contacts "Contacts":
  purpose: "Browse contacts and view details"

  # List signal - browsable contact list
  contact_list:
    source: Contact
    limit: 20
    # Weight: 0.5 (base) + 0.1 (limit) = 0.6 (ITEM_LIST)

  # Detail signal - selected contact details
  # NEW in v0.3.0: display: detail creates DETAIL_VIEW signal
  contact_detail:
    source: Contact
    display: detail
    # Weight: 0.5 (base) + 0.2 (detail) = 0.7 (DETAIL_VIEW)

# Archetype Selection:
# - list_weight = 0.6 >= 0.3 ✓
# - detail_weight = 0.7 >= 0.3 ✓
# → DUAL_PANE_FLOW archetype selected
#
# Surfaces Allocated:
# - list (priority 1, capacity 0.6) → contact_list
# - detail (priority 2, capacity 0.8) → contact_detail
#
# Layout:
# Desktop: Side-by-side list and detail panes
# Mobile: Stacked, detail slides over list on selection
