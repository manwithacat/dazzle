# Typical payment streams with OBSERVATION
module corpus.stream.payment_flow
app payment_flow "Payment Flow Streams"

stream payment_requests:
  kind: INTENT
  description: "Requests to process payments"

  schema PaymentRequested:
    request_id: uuid required
    payment_id: uuid required
    order_id: uuid required
    amount_minor: int required
    currency: str(3) required
    gateway: str(50) required
    requested_at: datetime required

  partition_key: order_id
  ordering_scope: per_order
  t_event: requested_at

  outcomes:
    success:
      emits PaymentSucceeded from payment_facts
    failure:
      emits PaymentFailed from payment_facts
    timeout:
      emits PaymentTimedOut from payment_facts

stream gateway_observations:
  kind: OBSERVATION
  description: "Observations from payment gateways"

  schema GatewayWebhookReceived:
    observation_id: uuid required
    gateway_ref: str(100) required
    webhook_type: str(50) required
    payload_hash: str(64) required
    received_at: datetime required

  partition_key: gateway_ref
  ordering_scope: per_gateway

  t_event: received_at

  idempotency:
    type: dedupe_window
    field: observation_fingerprint
    derivation: "hash(gateway_ref, webhook_type, payload_hash)"
    window: "5 minutes"

  note: "Observations may arrive late or out of order"
  note: "Truth is 'this was observed', not 'this is correct'"

stream payment_facts:
  kind: FACT
  description: "Immutable facts about payments"

  schema PaymentSucceeded:
    payment_id: uuid required
    order_id: uuid required
    amount_minor: int required
    currency: str(3) required
    gateway_ref: str(100) required
    succeeded_at: datetime required
    causation_id: uuid required

  schema PaymentFailed:
    payment_id: uuid required
    order_id: uuid required
    reason: str(500) required
    error_code: str(50) optional
    failed_at: datetime required
    causation_id: uuid required

  schema PaymentTimedOut:
    payment_id: uuid required
    order_id: uuid required
    timeout_ms: int required
    timed_out_at: datetime required
    causation_id: uuid required

  partition_key: order_id
  ordering_scope: per_order
  t_event: succeeded_at

  side_effects:
    allowed: false
