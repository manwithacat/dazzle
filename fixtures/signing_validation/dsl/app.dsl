module signing_validation

app signing_validation "Signing Validation Fixture"

persona admin "Administrator":
  default_workspace: docs_dashboard

entity TestDoc "Test Document":
  id: uuid pk
  party: str(200) required
  body: text required
  signatory_email: email required

  signable: true
  signing_validator: app.signing.validator.validate_test_doc

workspace docs_dashboard "Documents":
  access: persona(admin)
  purpose: "View and sign test documents"

  documents:
    source: TestDoc
    sort: id asc
    display: list
    empty: "No documents"
