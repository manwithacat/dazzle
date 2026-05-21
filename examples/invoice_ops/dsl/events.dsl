module invoice_ops.events

event_model:
  topic invoice_events:
    retention: 730
    partition_key: invoice_id

  event InvoiceSubmitted:
    topic: invoice_events
    fields:
      invoice_id: uuid required
      tenant_id: uuid required
      submitted_by: uuid
      submitted_at: datetime required

  event InvoiceApproved:
    topic: invoice_events
    fields:
      invoice_id: uuid required
      tenant_id: uuid required
      approved_at: datetime required
      currency: str required

  event InvoiceRejected:
    topic: invoice_events
    fields:
      invoice_id: uuid required
      tenant_id: uuid required
      reason: str
      rejected_at: datetime required

  event InvoiceDisputed:
    topic: invoice_events
    fields:
      invoice_id: uuid required
      tenant_id: uuid required
      reason: str
      disputed_at: datetime required

  event InvoicePaid:
    topic: invoice_events
    fields:
      invoice_id: uuid required
      tenant_id: uuid required
      paid_at: datetime required

  event PaymentAttemptFailed:
    topic: invoice_events
    fields:
      invoice_id: uuid required
      tenant_id: uuid required
      attempt_number: int required
      failure_reason: str required

projection InvoiceStatusView from invoice_events:
  on InvoiceSubmitted:
    upsert with invoice_id, status=submitted
  on InvoiceApproved:
    update status=approved
  on InvoiceRejected:
    update status=rejected
  on InvoiceDisputed:
    update status=disputed
  on InvoicePaid:
    update status=paid
