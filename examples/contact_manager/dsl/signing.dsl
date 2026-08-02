module contact_manager.signing

use contact_manager.core

entity EngagementLetter "Engagement Letter":
  intent: "Signed engagement letter / NDA between the firm and a contact"
  domain: crm
  patterns: signing, lifecycle

  # Cycle 1615 story_walk: scan letter queues by party (counterparty), not UUID.
  display_field: party
  id: uuid pk
  contact: ref Contact required
  party: str(200) required
  scope_summary: text required
  effective_date: date required
  signatory_name: str(200) required pii(category=identity)
  signatory_email: email required pii(category=contact)
  # Lifecycle (cycle 1475): letters are not eternally "done" —
  # draft → out for signature → signed, with void.
  status: enum[draft,sent,signed,void]=draft

  transitions:
    draft -> sent: role(admin) or role(user)
    sent -> signed: role(admin) or role(user)
    sent -> void: role(admin)
    draft -> void: role(admin)
    signed -> void: role(admin)

  signable: true
  signing_validator: app.signing.validator.validate_engagement_letter

  fitness:
    repr_fields: [party, effective_date, signatory_name, contact, status]

# Journey open-via (cycle 1517 story_walk; AUD-007 fix 1528): letters are not
# orphan warehouse rows — pipe dual hop (parser last-wins if two open: lines).
surface engagement_letter_list "Engagement letters":
  uses entity EngagementLetter
  mode: list
  open: EngagementLetter via id | Contact via contact
  section main:
    field party "Party"
    field status "Status"
    field effective_date "Effective"
    field contact "Contact"
    field signatory_name "Signatory"
  ux:
    purpose: "Engagement letter queue — open a letter hub or hop to the Contact"
    filter: status
    sort: effective_date desc
    search: party, signatory_name
    empty: "No engagement letters yet — open a contact hub to attach one"

surface engagement_letter_detail "Engagement letter":
  uses entity EngagementLetter
  mode: view
  section summary "Summary":
    layout: strip
    field party "Party"
    field status "Status"
    field effective_date "Effective"
  section parties "Parties":
    field contact "Contact"
    field signatory_name "Signatory"
    field signatory_email "Signatory email"
  section scope "Scope":
    field scope_summary "Scope summary"
  ux:
    purpose: "Engagement letter hub — lifecycle strip, parties, and scope in one place"
