module support_tickets.signing

use support_tickets.core

entity SlaWaiver "SLA Waiver":
  intent: "Signed acknowledgement of an SLA breach and waiver terms"
  domain: support
  patterns: signing

  id: uuid pk
  ticket: ref Ticket required
  breach_summary: text required
  waiver_terms: text required
  signatory_role: str(120) required
  signatory_name: str(200) required pii(category=identity)
  signatory_email: email required pii(category=contact)

  signable: true
  signing_validator: app.signing.validator.validate_sla_waiver
