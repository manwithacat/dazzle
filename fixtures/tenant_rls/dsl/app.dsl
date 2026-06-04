module tenant_rls.core

app tenant_rls "Tenant RLS fixture"

tenancy:
  mode: shared_schema
  partition_key: tenant_id
