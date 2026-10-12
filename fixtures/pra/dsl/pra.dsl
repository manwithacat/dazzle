# Performance Reference App (PRA)
# Parser-conformance corpus — a kitchen-sink of DSL forms.
#
# This is NOT a tutorial or production example. Its HLESS stream topology and
# the events/messaging modules were removed with the parked event and
# messaging DSL (DD-006, DD-007).

module pra
app pra "Performance Reference App"

# =============================================================================
# ENTITIES (Minimal domain carriers for stress patterns)
# =============================================================================

entity Actor "Actor":
  id: uuid pk
  name: str(100) required
  created_at: datetime required

entity Account "Account":
  id: uuid pk
  actor_id: uuid required
  balance: decimal(19,4)=0
  currency: str(3)="GBP"
  created_at: datetime required

entity TradeOrder "Trade Order":
  id: uuid pk
  actor_id: uuid required
  account_id: uuid required
  amount: decimal(19,4) required
  currency: str(3)="GBP"
  status: enum[pending,placed,rejected,fulfilled]=pending
  placed_at: datetime
  created_at: datetime required

entity PaymentAttempt "Payment Attempt":
  id: uuid pk
  order_id: uuid required
  amount: decimal(19,4) required
  currency: str(3)="GBP"
  status: enum[pending,succeeded,failed]=pending
  gateway_ref: str(100)
  attempted_at: datetime required

entity LedgerEntry "Ledger Entry":
  id: uuid pk
  account_id: uuid required
  amount: decimal(19,4) required
  entry_type: enum[credit,debit] required
  reference_type: str(50) required
  reference_id: uuid required
  recorded_at: datetime required
