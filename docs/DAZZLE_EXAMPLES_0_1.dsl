# DAZZLE 0.1 – Example Specs

# Example 1: Simple VAT lookup integration

app vat_tools "VAT Tools"

entity Client "Client":
  id: uuid pk
  name: str(200) required
  email: email unique?
  tax_vrn: str(12) optional
  tax_name: str(200) optional

surface vat_check "VAT Check":
  mode: custom

  section main "Check VAT number":
    field vrn "VAT number"

  action lookup "Check VAT":
    on submit -> integration check_vat_registration action lookup

service hmrc_vat "HMRC VAT API":
  spec: url "https://api.gov.uk/hmrc/vat/openapi.json"
  auth_profile: oauth2_legacy scopes="read:vat"
  owner: "HMRC"

foreign_model VatRegistration from hmrc_vat "VAT Registration":
  key: vrn
  constraint read_only
  constraint batch_import frequency=daily

  field vrn: str(12)
  field name: str(200)
  field effective_date: date

integration check_vat_registration "Check VAT Registration":
  uses service hmrc_vat
  uses foreign_model VatRegistration

  action lookup:
    when surface vat_check submitted
    call hmrc_vat.get_registration with:
      vrn <- form.vrn
    map response VatRegistration -> entity Client:
      tax_vrn <- foreign.vrn
      tax_name <- foreign.name


# Example 2: Nightly bank transaction sync

entity LedgerTransaction "Ledger Transaction":
  id: uuid pk
  bank_id: str(64) required
  amount: decimal(12,2) required
  currency: str(3) required
  booked_at: datetime required
  description: text optional

service bank_feed "Bank Feed Provider":
  spec: url "https://api.bankfeed.example/openapi.json"
  auth_profile: oauth2_pkce scopes="transactions:read"
  owner: "Acme Bank Services"

foreign_model BankTransaction from bank_feed "Bank Transaction":
  key: transaction_id
  constraint read_only
  constraint event_driven

  field transaction_id: str(64)
  field amount: decimal(12,2)
  field currency: str(3)
  field booked_at: datetime
  field description: text

integration nightly_bank_sync "Nightly Bank Sync":
  uses service bank_feed
  uses foreign_model BankTransaction

  sync import_transactions:
    mode: scheduled
    schedule: "0 2 * * *"   # nightly at 02:00
    from bank_feed.list_transactions as BankTransaction
    into entity LedgerTransaction
    match on:
      transaction_id <-> bank_id


# Example 3: Experience flow using a surface and integration

surface bank_reconcile "Bank Reconciliation":
  uses entity LedgerTransaction
  mode: list

  section main "Transactions":
    field bank_id "Bank ID"
    field amount "Amount"
    field booked_at "Booked date"

  action refresh "Refresh from bank":
    on click -> integration nightly_bank_sync action import_transactions

experience reconcile_flow "Reconcile Bank Transactions":
  start at step review

  step review:
    kind: surface
    surface bank_reconcile
