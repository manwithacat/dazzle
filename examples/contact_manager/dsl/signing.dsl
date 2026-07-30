module contact_manager.signing

use contact_manager.core

entity EngagementLetter "Engagement Letter":
  intent: "Signed engagement letter / NDA between the firm and a contact"
  domain: crm
  patterns: signing, lifecycle

  id: uuid pk
  contact: ref Contact required
  party: str(200) required
  scope_summary: text required
  effective_date: date required
  signatory_name: str(200) required pii(category=identity)
  signatory_email: email required pii(category=contact)
  # Domain residual lifecycle densify (cycle 1475): letters are not
  # eternally "done" — draft → out for signature → signed, with void.
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
