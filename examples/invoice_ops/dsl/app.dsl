module invoice_ops.core

app invoice_ops "Invoice Ops"

tenancy:
  mode: shared_schema
  partition_key: tenant_id
  admin_personas: [tenant_admin]
  per_tenant_config:
    approval_threshold: int
    base_currency: str
