module contact_manager.signing

use contact_manager.core

entity EngagementLetter "Engagement Letter":
  intent: "Signed engagement letter / NDA between the firm and a contact"
  domain: crm
  patterns: signing

  id: uuid pk
  contact: ref Contact required
  party: str(200) required
  scope_summary: text required
  effective_date: date required
  signatory_name: str(200) required pii(category=identity)
  signatory_email: email required pii(category=contact)

  signable: true
  signing_validator: app.signing.validator.validate_engagement_letter
