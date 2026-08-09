module support_tickets.signing

use support_tickets.core

# Goal B document depth: peer support tools (Zendesk / Salesforce Service Cloud)
# surface named waiver / breach documents on the ops home — not only ticket queues
# and conversation chrome. breach_summary is the document title buyers scan.
entity SlaWaiver "SLA Waiver":
  intent: "Signed acknowledgement of an SLA breach and waiver terms — breach_summary is the document title buyers scan, not a UUID shell"
  domain: support
  patterns: signing, documentation, audit_trail

  display_field: breach_summary
  id: uuid pk
  ticket: ref Ticket required
  breach_summary: text required
  waiver_terms: text required
  signatory_role: str(120) required
  signatory_name: str(200) required pii(category=identity)
  signatory_email: email required pii(category=contact)
  # Lifecycle: draft → out for signature → signed, with void (EngagementLetter pattern).
  status: enum[draft,sent,signed,void]=draft
  # Demo-window aggregates (documents: count) filter on created_at.
  created_at: datetime auto_add

  transitions:
    draft -> sent: role(agent) or role(manager)
    sent -> signed: role(agent) or role(manager)
    sent -> void: role(manager)
    draft -> void: role(manager)
    signed -> void: role(manager)

  signable: true
  signing_validator: app.signing.validator.validate_sla_waiver

  # Agents/managers own the waiver desk; customers never list breach documents.
  permit:
    list: role(agent) or role(manager)
    read: role(agent) or role(manager)
    create: role(agent) or role(manager)
    update: role(agent) or role(manager)
    delete: role(manager)

  scope:
    list: all
      as: agent, manager
    read: all
      as: agent, manager
    create: all
      as: agent, manager
    update: all
      as: agent, manager
    delete: all
      as: manager

  fitness:
    repr_fields: [ticket, breach_summary, signatory_name, status]

# List surface for dual-open (#1603 open-via is list-only). Composition + related
# queues on ticket_queue / manager_ops / ticket_detail remain the buyer path —
# not a bare warehouse nav destination.
surface sla_waiver_list "SLA Waivers":
  uses entity SlaWaiver
  mode: list
  render: fragment
  open: SlaWaiver via id | Ticket via ticket

  section main "SLA Waivers":
    field breach_summary "Document"
    field ticket "Ticket"
    field status "Status"
    field signatory_name "Signatory"
    field signatory_role "Role"
    field signatory_email "Signatory email"

  ux:
    purpose: "Document composition queue — named SLA waivers; open a waiver hub or hop to the parent ticket"
    filter: status
    sort: breach_summary asc
    search: breach_summary, signatory_name, waiver_terms
    empty: "No SLA waivers yet — draft a waiver from a ticket hub after a response-time breach"

surface sla_waiver_detail "SLA Waiver":
  uses entity SlaWaiver
  mode: view
  render: fragment

  section summary "Summary":
    layout: strip
    field breach_summary "Document"
    field status "Status"
    field ticket "Ticket"

  section parties "Signatory":
    field signatory_name "Name"
    field signatory_role "Role"
    field signatory_email "Email"

  section terms "Terms":
    field breach_summary "Breach summary"
    field waiver_terms "Waiver terms"

  ux:
    purpose: "SLA waiver hub — named document, lifecycle strip, signatory, and terms in one place"

surface sla_waiver_create "Draft SLA Waiver":
  uses entity SlaWaiver
  mode: create
  render: fragment

  section main "New waiver":
    field ticket "Ticket"
    field breach_summary "Breach summary"
    field waiver_terms "Waiver terms"
    field signatory_role "Signatory role"
    field signatory_name "Signatory name"
    field signatory_email "Signatory email"
    field status "Status"

  ux:
    purpose: "Draft a named SLA waiver document on a ticket after a response-time breach"

surface sla_waiver_edit "Edit SLA Waiver":
  uses entity SlaWaiver
  mode: edit
  render: fragment

  section main "Edit waiver":
    field breach_summary "Breach summary"
    field waiver_terms "Waiver terms"
    field signatory_role "Signatory role"
    field signatory_name "Signatory name"
    field signatory_email "Signatory email"
    field status "Status"

  ux:
    purpose: "Update waiver document prose or lifecycle before signature"
