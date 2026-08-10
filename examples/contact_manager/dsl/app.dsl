# DAZZLE Contact Manager
# Demonstrates v0.7.1+ LLM Cognition Features:
# - Intent declarations for semantic clarity
# - Domain/pattern tags for classification
# - Invariants for data integrity
# - Workspace with dual_pane_flow stage

module contact_manager.core

app contact_manager "Contact Manager":
  security_profile: basic

# #1324 FR-4: per-tenant config flag gating a nav group at render time.
# `show_browse` toggles the "Browse" sidebar group per tenant via the
# `when: tenant_config.show_browse = true` clause on `nav contact_nav`.
tenancy:
  per_tenant_config:
    show_browse: bool

persona admin "Administrator":
  # Product home — not framework platform chrome (#1626 P0-3/4).
  default_workspace: home

# #1324: curated per-persona navigation. The `user` persona gets an
# explicit, hand-ordered sidebar via `uses nav contact_nav` (below);
# `admin` is left without a binding so it auto-discovers its sidebar
# from accessible workspaces — exercising both nav paths in one app.
persona user "User":
  # TR-2: land on a welcome/overview workspace, not a bare contact list.
  default_workspace: home
  uses nav contact_nav

# Curated sidebar for the `user` persona (#1324). Each item is a bare
# entity or workspace name (no `item` keyword): an entity resolves to its
# list surface, a workspace to its page. Both targets here are real —
# Contact has a `mode: list` surface and `contacts` is a declared workspace.
nav contact_nav:
  group "Home":
    home
  group "Directory":
    contacts
    companies
  # #1324 FR-4: optional Browse group still exposes the contacts desk when
  # the tenant enables `show_browse` (workspace target, not bare Contact list).
  group "Browse" when: tenant_config.show_browse = true:
    contacts

# Entity for contact information with LLM cognition metadata.
#
# Tutorial-only: permit:/scope: blocks intentionally omitted to keep
# the minimal-demo entity focused on LLM cognition metadata. Production
# DSL would declare permit + scope rules per ADR-0010 — see
# `docs/reference/rbac-scope.md` (#1123) and `examples/simple_task/`
# for the canonical write-op scope pattern.
entity Contact "Contact":
  intent: "Store professional and personal contact information for relationship management"
  domain: crm
  patterns: profile, searchable

  # Panel 1279: email-as-title made favourites unreadable for call lookup;
  # lead with last_name so cards scan like a practice directory (first+phone
  # remain on the card body via surface fields).
  display_field: last_name
  id: uuid pk
  first_name: str(100) required pii(category=identity)
  last_name: str(100) required pii(category=identity)
  # Panel 1745 / trial adoption: name + at least one reachable channel.
  # Email is unique when present, but phone-only prospects must save
  # (invariant below). Create form no longer hard-requires email.
  email: email unique pii(category=contact)
  phone: str(20) pii(category=contact)
  company: str(200)
  job_title: str(150)
  notes: text pii(category=freeform)
  is_favorite: bool=false
  created_at: datetime auto_add
  updated_at: datetime auto_update

  # Invariant: contacts must have either email or phone
  invariant: email != null or phone != null

  index email
  index last_name,first_name

  fitness:
    repr_fields: [first_name, last_name, email, company, is_favorite]

# Goal B conversation: peer CRM tools (HubSpot / Attio / Affinity) show
# relationship notes as the row identity on the home desk — not only
# directory metrics and engagement-letter composition.
entity ContactNote "Contact Note":
  intent: "Relationship note on a Contact — the conversation that moves a letter or call forward"
  domain: crm
  patterns: messaging, audit_trail
  display_field: body
  id: uuid pk
  contact: ref Contact required
  author: str(120) required
  body: text required
  created_at: datetime auto_add

  fitness:
    repr_fields: [contact, author, body]

# List view - browsable contact directory
surface contact_list "Contacts":
  uses entity Contact
  mode: list
  render: fragment
  open: Contact via id

  section main "Contacts":
    field first_name "First Name"
    field last_name "Last Name"
    field email "Email"
    field phone "Phone"
    field company "Company"
    field job_title "Job Title"
    field is_favorite "Favorite"

  ux:
    purpose: "Browse and search contacts — Find by first name, last name, email, or company above the A–Z list; open a row for the contact hub"
    sort: last_name asc, first_name asc
    filter: is_favorite, company, job_title
    search: first_name, last_name, email, company, job_title
    empty: "No contacts yet. Add your first contact!"

# Detail view — contact hub (identity / employment / notes / engagement letters)
surface contact_detail "Contact Detail":
  uses entity Contact
  mode: view
  render: fragment

  section identity "Identity":
    field first_name "First Name"
    field last_name "Last Name"
    field email "Email"
    field phone "Phone"

  section employment "Employment":
    layout: strip
    field company "Company"
    field job_title "Job Title"
    field is_favorite "Favorite"

  section notes "Notes & timeline":
    field notes "Notes"
    field created_at "Created"
    field updated_at "Updated"

  # Journey deepen: reverse-hop engagement letters (SPEC signing flow) — pull
  # roster queue (RelatedDisplayMode.QUEUE), not a warehouse table (cycle 1498).
  # Goal B document: lead with scope_summary (document title) then lifecycle.
  related engagements "Engagement letters":
    display: queue
    show: EngagementLetter
    columns: scope_summary, status, party, effective_date, signatory_name

  # Goal B conversation: relationship notes pull queue on the contact hub.
  related discussion "Discussion":
    display: queue
    show: ContactNote
    columns: body, author, created_at

  ux:
    purpose: "Contact hub — identity, employment, notes, and named engagement documents in one place"

# Create form
surface contact_create "Create Contact":
  uses entity Contact
  mode: create
  render: fragment

  section identity "Identity":
    field first_name "First Name"
    field last_name "Last Name"

  section contact_details "Contact Details":
    field email "Email"
    field phone "Phone"

  section employment "Employment":
    field company "Company"
    field job_title "Job Title"

  section extras "Additional Info":
    field notes "Notes"

  ux:
    purpose: "Add a new contact — name plus email or phone (at least one channel)"

# Edit form
surface contact_edit "Edit Contact":
  uses entity Contact
  mode: edit
  render: fragment

  section identity "Identity":
    field first_name "First Name"
    field last_name "Last Name"

  section contact_details "Contact Details":
    field email "Email"
    field phone "Phone"

  section employment "Employment":
    field company "Company"
    field job_title "Job Title"

  section extras "Additional Info":
    field notes "Notes"
    # HM Switch — boolean settings / favorite on-off (boolean_settings_switch)
    field is_favorite "Favorite" widget=switch

  ux:
    purpose: "Update contact information"

surface contact_note_list "Contact Notes":
  uses entity ContactNote
  mode: list
  render: fragment
  open: ContactNote via id | Contact via contact

  section main "Notes":
    field body "Note"
    field author "Author"
    field contact "Contact"
    field created_at "When"

  ux:
    purpose: "Relationship discussion — open a note or its parent contact"
    sort: created_at desc
    search: body, author
    empty: "No contact notes yet"

surface contact_note_detail "Contact Note":
  uses entity ContactNote
  mode: view
  render: fragment

  section summary "Note":
    field body "Note"
    field author "Author"
    field contact "Contact"
    field created_at "When"

  ux:
    purpose: "Read a relationship note in context of its parent contact"

surface contact_note_create "Add Contact Note":
  uses entity ContactNote
  mode: create
  render: fragment
  section main "New note":
    field contact "Contact"
    field author "Author"
    field body "Note"

# #954 — full-text search over Contact. Indexed via tsvector + GIN
# at startup; powers the search_box region below + the
# /api/fts/Contact endpoint.
search on Contact:
  fields: first_name, last_name, email, company
  ranking:
    last_name: 4
    first_name: 3
    company: 2
    email: 1
  highlight: true
  tokenizer: english

# TR-2: first-run / post-login welcome — overview before the dense list.
# Story-driven (docs/guides/story-to-composition.md): metrics + favourites
# queue first (ST-007), then a short directory sample (ST-004).
# Goal B document depth: named engagement letters above fold (composition),
# not only directory metrics + empty letter chrome.
workspace home "Home":
  # Goal B command_density (cycle 1830): peer CRM homes (HubSpot / Salesforce)
  # put directory pulse + dual attention (who to call + letters in flight) above
  # the note trail — not conversation owning the fold alone. Conversation stays,
  # capped to share fold after dual queues + document composition.
  # Also holds document + empty_region_honesty (no company bar / twin dumps).
  purpose: "Multi-panel CRM — directory pulse, favourites to call, open letters, then relationship notes"
  access: persona(user, admin)

  directory_stats:
    source: Contact
    display: metrics
    aggregate:
      total_contacts: count(Contact)
      favourites: count(Contact where is_favorite = true)
      conversation: count(ContactNote)
    tones:
      favourites: accent
      total_contacts: positive
      conversation: accent

  # Document pulse (Goal B): letters awaiting action, not only people counts.
  engagement_docs:
    source: EngagementLetter
    display: metrics
    aggregate:
      documents: count(EngagementLetter)
      awaiting_signature: count(EngagementLetter where status = sent)
      drafts: count(EngagementLetter where status = draft)
    tones:
      documents: accent
      awaiting_signature: positive

  # Dual attention A — favourites as a work queue (who to call), not buried
  # in the full list sort. Cap at 4 so dual panels + composition + notes share fold.
  favourite_contacts:
    source: Contact
    filter: is_favorite = true
    sort: last_name asc, first_name asc
    limit: 4
    display: queue
    action: contact_detail
    empty: "No favourites yet — star a contact from the directory."

  # Dual attention B + Goal B composition — named document titles (scope_summary).
  composition:
    source: EngagementLetter
    filter: status = draft or status = sent
    sort: effective_date desc
    limit: 4
    display: queue
    action: engagement_letter_detail
    empty: "No open engagement letters — draft an MSA, NDA, or retainer from a contact hub."

  # Goal B conversation spine AFTER dual attention — newest relationship notes
  # so stills show domain-true CRM prose without owning the whole fold.
  # display: conversation → MessageScroller / Message + Bubble (not queue meta rows).
  live_conversation:
    source: ContactNote
    sort: created_at desc
    limit: 4
    display: conversation
    action: contact_note_detail
    empty: "No conversation yet — notes on contacts and letters appear here"

  recent_contacts:
    source: Contact
    sort: last_name asc, first_name asc
    limit: 8
    # Home "who to call" is pull-next, not a photo grid.
    display: queue
    action: contact_detail
    empty: "No contacts yet. Open Contacts or use New Contact to add your first person or company."

  # Always-filled context strip (not seed-dependent chart theater).
  practice_context:
    display: status_list
    entries:
      - title: "Dual attention"
        caption: "Favourites to call and letters in flight share the fold"
        icon: "layout-dashboard"
        state: accent
      - title: "Engagement docs"
        caption: "MSAs, NDAs, and retainers open from composition"
        icon: "file-text"
        state: positive
      - title: "Notes trail"
        caption: "Relationship notes follow pressure queues (Message chrome)"
        icon: "message-square"
        state: positive

  find_contact:
    source: Contact
    display: search_box
    title: "Find a contact — results appear below"
    # Placeholder must say results-panel (not list filter) — panel agents mis-score search
    empty: "Results appear below as you type (name, company, or email). The directory list stays full until you open a hit."

  ux:
    as user:
      purpose: "Multi-panel CRM — directory pulse, dual attention, letters, then notes"
      # Goal B command_density: metrics → dual queues → conversation (no chart voids)
      focus: directory_stats, engagement_docs, favourite_contacts, composition, live_conversation, practice_context
    as admin:
      purpose: "Full practice home — multi-panel attention before conversation trail"
      focus: directory_stats, engagement_docs, favourite_contacts, composition, live_conversation, practice_context

# Workspace with list + detail pattern
workspace contacts "Contacts":
  # #1626 P0-7: dual_pane_flow stage selects list+detail layout when the shell
  # supports it; captures may still show list-primary if selection is empty.
  purpose: "Browse contacts (list + detail hub) — favourites strip and A–Z directory"
  access: persona(user, admin)
  stage: "dual_pane_flow"

  # Find-by-name is the list chrome (?q= via surface ux.search on Contact) —
  # cycle 1386. Do NOT also mount display:search_box here: dual search
  # (FTS panel + unfiltered A–Z) is what agent_acceptance scored as broken
  # (panels type into #dz-search-results-*-input and expect the directory to
  # shrink). Home keeps find_contact FTS for overview lookup; dual_pane uses
  # one mental model — type in the list filter, rows shrink in place.

  # Favourites strip above the A–Z list (ST-007).
  favourites_queue:
    source: Contact
    filter: is_favorite = true
    sort: last_name asc, first_name asc
    limit: 8
    display: queue
    action: contact_detail
    empty: "No favourites pinned"

  # List signal - browsable contact list (dual_pane needs listish)
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

  ux:
    as user:
      purpose: "Favourites strip then A–Z dual-pane — no kanban theater under the list"
      focus: favourites_queue, contact_list, contact_detail
    as admin:
      purpose: "Favourites strip then A–Z dual-pane directory"
      focus: favourites_queue, contact_list, contact_detail

# Third product workspace: org structure for CRM relationships.
workspace companies "Companies":
  # Goal B org_structure (cycle 1861): peer CRM tools (HubSpot / Salesforce /
  # Attio / Affinity) show contacts by job title and company placement before a
  # flat recents dump — users call from org shape, not a warehouse A–Z list.
  # Keeps empty_region_honesty: no bar-chart company_mix theater under the boards.
  purpose: "Org structure buyers can parse — role board and company placement before flat recents"
  access: persona(user, admin)

  company_pulse:
    source: Contact
    display: metrics
    aggregate:
      companies: count(Contact where company != null)
      people: count(Contact)
      favourites: count(Contact where is_favorite = true)
    tones:
      companies: accent
      favourites: positive

  # Title board — functional org (Account Manager / Sales Director / …).
  by_title:
    source: Contact
    filter: job_title != null
    display: kanban
    group_by: job_title
    sort: last_name asc, first_name asc
    limit: 40
    action: contact_detail
    empty: "No titled contacts yet"

  # Company placement queue — multi-person accounts before flat recents.
  by_company:
    source: Contact
    filter: company != null
    sort: company asc, last_name asc
    limit: 30
    # Company roster is a call queue, not a warehouse grid.
    display: queue
    action: contact_detail
    empty: "No company contacts yet"

  # Secondary flat recents (after hierarchy) — still pull-to-open hubs.
  recent_people:
    source: Contact
    sort: updated_at desc
    limit: 12
    display: timeline
    action: contact_detail
    empty: "No contacts yet"

  company_context:
    display: status_list
    entries:
      - title: "By title board"
        caption: "Account Manager / Sales / Engineering columns show who to call by role"
        icon: "users"
        state: accent
      - title: "Company placement"
        caption: "Multi-person accounts sorted before flat recents"
        icon: "building-2"
        state: positive
      - title: "Star favourites"
        caption: "Favourites still surface on Home and Contacts"
        icon: "star"
        state: positive

  ux:
    as user:
      purpose: "See contacts by title and company before flat recents — org structure first"
      focus: company_pulse, by_title, by_company, recent_people
    as admin:
      purpose: "Org structure for the practice directory — role board then company placement"
      focus: company_pulse, by_title, by_company, recent_people
