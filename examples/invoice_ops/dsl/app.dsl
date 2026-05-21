module invoice_ops.core

app invoice_ops "Invoice Ops"

tenancy:
  mode: shared_schema
  partition_key: tenant_id
  per_tenant_config:
    approval_threshold: int
    base_currency: str
