module invoice_ops.services

# External payment provider, modelled as an integration service. The stub is
# driven by `dazzle mock` scenarios (success / insufficient-funds / timeout).
service payment_provider "Payment Provider":
  kind: integration

  input:
    invoice_id: uuid required
    amount: decimal(15,2) required
    currency: str(3) required

  output:
    succeeded: bool
    provider_reference: str
    failure_reason: text

  guarantees:
    - "Idempotent for the same invoice_id"
    - "Returns a failure_reason on every non-success outcome"

  stub: python

# Settlement saga: triggered when an invoice reaches `approved`.
process settle_invoice "Settle Approved Invoice":
  trigger:
    when: entity Invoice status -> approved

  input:
    invoice_id: uuid required

  steps:
    - step charge:
        service: payment_provider
        timeout: 30s
        retry:
          max_attempts: 3
          backoff: exponential

  timeout: 5m
