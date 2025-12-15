# Performance Reference App (PRA)
# Dazzle Event-First Architecture - Stress Reference
#
# This is NOT a tutorial or production example.
# It is a stress reference for surfacing performance pathologies.
#
# See: dev_docs/architecture/event_first/performance_reference_app.md

module pra
app pra "Performance Reference App"

# Enforce HLESS strict mode - no "event" terminology allowed
hless:
  mode strict

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

entity Order "Order":
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


# =============================================================================
# INTENT STREAMS
# Records of what actors *requested* - does NOT imply success
# =============================================================================

stream orders_intent:
  kind: INTENT
  description: "Order placement requests from actors"

  schema OrderPlacementRequested:
    request_id: uuid required
    actor_id: uuid required
    account_id: uuid required
    amount: decimal(19,4) required
    currency: str(3) required
    occurred_at: datetime required

  schema OrderPlacementRequestedV2:
    request_id: uuid required
    actor_id: uuid required
    account_id: uuid required
    amount: decimal(19,4) required
    currency: str(3) required
    idempotency_key: str(64) required
    occurred_at: datetime required

  partition_key: actor_id
  ordering_scope: per_actor
  t_event: occurred_at

  outcomes:
    success:
      emits OrderPlaced from orders_fact
    failure:
      emits OrderPlacementRejected from orders_fact

  idempotency:
    strategy: deterministic_id
    field: request_id

stream payments_intent:
  kind: INTENT
  description: "Payment attempt requests"

  schema PaymentRequested:
    request_id: uuid required
    order_id: uuid required
    amount: decimal(19,4) required
    currency: str(3) required
    gateway: str(50) required
    occurred_at: datetime required

  partition_key: order_id
  ordering_scope: per_order
  t_event: occurred_at

  outcomes:
    success:
      emits PaymentSucceeded from payments_fact
    failure:
      emits PaymentFailed from payments_fact
    timeout:
      emits PaymentTimedOut from payments_fact

  idempotency:
    strategy: deterministic_id
    field: request_id


# =============================================================================
# FACT STREAMS
# Irreversible domain facts - must remain true forever
# =============================================================================

stream orders_fact:
  kind: FACT
  description: "Irreversible order facts"

  schema OrderPlaced:
    order_id: uuid required
    actor_id: uuid required
    account_id: uuid required
    amount: decimal(19,4) required
    currency: str(3) required
    causation_id: uuid required
    occurred_at: datetime required

  schema OrderPlacementRejected:
    order_id: uuid required
    actor_id: uuid required
    account_id: uuid required
    reason: str(500) required
    causation_id: uuid required
    occurred_at: datetime required

  schema OrderFulfilled:
    order_id: uuid required
    fulfilled_at: datetime required
    causation_id: uuid required
    occurred_at: datetime required

  partition_key: order_id
  ordering_scope: per_order
  t_event: occurred_at

  idempotency:
    strategy: deterministic_id
    field: order_id

  invariant: "OrderPlaced represents a completed and irreversible action"
  invariant: "order_id is immutable within this stream"
  invariant: "An order can only be placed once"

stream payments_fact:
  kind: FACT
  description: "Irreversible payment facts"

  schema PaymentSucceeded:
    payment_id: uuid required
    order_id: uuid required
    amount: decimal(19,4) required
    currency: str(3) required
    gateway_ref: str(100) required
    causation_id: uuid required
    occurred_at: datetime required

  schema PaymentFailed:
    payment_id: uuid required
    order_id: uuid required
    reason: str(500) required
    gateway_error_code: str(50)
    causation_id: uuid required
    occurred_at: datetime required

  schema PaymentTimedOut:
    payment_id: uuid required
    order_id: uuid required
    timeout_ms: int required
    causation_id: uuid required
    occurred_at: datetime required

  partition_key: payment_id
  ordering_scope: per_payment
  t_event: occurred_at

  idempotency:
    strategy: deterministic_id
    field: payment_id

stream ledger_fact:
  kind: FACT
  description: "Append-only financial ledger"

  schema LedgerCredited:
    entry_id: uuid required
    account_id: uuid required
    amount: decimal(19,4) required
    reference_type: str(50) required
    reference_id: uuid required
    causation_id: uuid required
    occurred_at: datetime required

  schema LedgerDebited:
    entry_id: uuid required
    account_id: uuid required
    amount: decimal(19,4) required
    reference_type: str(50) required
    reference_id: uuid required
    causation_id: uuid required
    occurred_at: datetime required

  partition_key: account_id
  ordering_scope: per_account
  t_event: occurred_at

  idempotency:
    strategy: deterministic_id
    field: entry_id

  invariant: "Ledger entries are append-only and immutable"
  invariant: "Each entry references exactly one external action"
  invariant: "Balance is never stored - always derived"


# =============================================================================
# OBSERVATION STREAMS
# Facts about what was observed - may be duplicated, late, or out-of-order
# =============================================================================

stream gateway_observation:
  kind: OBSERVATION
  description: "Observations from external payment gateway webhooks"

  schema GatewayWebhookReceived:
    observation_id: uuid required
    gateway_ref: str(100) required
    webhook_type: str(50) required
    received_at: datetime required
    occurred_at: datetime required

  schema GatewayWebhookReceivedV2:
    observation_id: uuid required
    gateway_ref: str(100) required
    webhook_type: str(50) required
    signature_valid: bool required
    idempotency_key: str(64)
    received_at: datetime required
    occurred_at: datetime required

  partition_key: gateway_ref
  ordering_scope: per_gateway
  t_event: occurred_at

  idempotency:
    strategy: dedupe_window
    field: observation_id
    window: 5 minutes

  invariant: "Observations report what was received, not what is true"
  invariant: "Duplicate webhooks are expected and tolerated"
  invariant: "Out-of-order arrival is normal"

stream http_observation:
  kind: OBSERVATION
  description: "HTTP request observations for tracing"

  schema HttpRequestObserved:
    observation_id: uuid required
    trace_id: uuid required
    span_id: uuid required
    http_method: str(10) required
    request_path: str(500) required
    response_status: int required
    duration_ms: int required
    occurred_at: datetime required

  partition_key: trace_id
  ordering_scope: per_trace
  t_event: occurred_at

  idempotency:
    strategy: dedupe_window
    field: observation_id
    window: 1 minute

  invariant: "Observations may be sampled or incomplete"
  invariant: "duration_ms is measured, not guaranteed accurate"


# =============================================================================
# DERIVATION STREAMS
# Computed values - fully rebuildable from source streams
# =============================================================================

stream account_balance_derived:
  kind: DERIVATION
  description: "Derived account balances - rebuildable from ledger_fact"

  schema AccountBalanceCalculated:
    calculation_id: uuid required
    account_id: uuid required
    balance: decimal(19,4) required
    currency: str(3) required
    as_of_sequence: int required
    occurred_at: datetime required
    processed_at: datetime required

  partition_key: account_id
  ordering_scope: per_account
  t_event: occurred_at
  t_process: processed_at

  derives_from:
    sources: [ledger_fact]
    type: aggregate
    rebuild: full_replay

  idempotency:
    strategy: deterministic_id
    field: calculation_id

  invariant: "Balance is always computed, never asserted"
  invariant: "Full rebuild from ledger_fact must produce identical results"
  invariant: "as_of_sequence provides consistency point"

stream daily_revenue_derived:
  kind: DERIVATION
  description: "Daily revenue aggregation - rebuildable from orders_fact"

  schema DailyRevenueAggregated:
    calculation_id: uuid required
    revenue_date: date required
    total_revenue: decimal(19,4) required
    order_count: int required
    currency: str(3) required
    occurred_at: datetime required
    processed_at: datetime required

  schema DailyRevenueAggregatedV2:
    calculation_id: uuid required
    revenue_date: date required
    total_revenue: decimal(19,4) required
    order_count: int required
    average_order_value: decimal(19,4) required
    currency: str(3) required
    occurred_at: datetime required
    processed_at: datetime required

  partition_key: revenue_date
  ordering_scope: per_date
  t_event: occurred_at
  t_process: processed_at

  derives_from:
    sources: [orders_fact]
    type: aggregate
    rebuild: full_replay

  idempotency:
    strategy: deterministic_id
    field: calculation_id

  invariant: "Revenue is computed from OrderPlaced facts only"
  invariant: "Rejected orders are not included in revenue"
  invariant: "Rebuild must produce identical totals"
