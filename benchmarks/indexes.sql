-- benchmarks/indexes.sql — scope-predicate and FK indexes for invoice_ops (SP6)
--
-- WHY THESE ARE NEEDED
-- ---------------------
-- The Dazzle schema builder (src/dazzle/back/runtime/sa_schema.py) emits only
-- PK constraints and unique constraints (i.e. the "id" column index and any
-- "unique" field indexes from the DSL).  It does NOT create indexes on:
--   • tenant_id columns  — every list/read scope predicate filters on this
--   • FK columns used in JOIN paths  — Invoice.supplier, LineItem.invoice, etc.
--
-- At low row counts the sequential scan is cheaper; at benchmark scale
-- (tens of thousands to millions of rows) the planner switches to SeqScan and
-- latency degrades non-linearly.  These indexes let the benchmark isolate
-- *application-level* latency from missing-index overhead.
--
-- Apply with:
--   psql $DB_URL -f benchmarks/indexes.sql
-- or inside a migration if you want them in production too.

-- ---------------------------------------------------------------------------
-- tenant_id indexes — one per entity that carries a tenant scope predicate
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS ix_bench_user_tenant_id
    ON "User" ("tenant_id");

CREATE INDEX IF NOT EXISTS ix_bench_supplier_tenant_id
    ON "Supplier" ("tenant_id");

CREATE INDEX IF NOT EXISTS ix_bench_supplierbankaccount_tenant_id
    ON "SupplierBankAccount" ("tenant_id");

CREATE INDEX IF NOT EXISTS ix_bench_invoice_tenant_id
    ON "Invoice" ("tenant_id");

CREATE INDEX IF NOT EXISTS ix_bench_lineitem_tenant_id
    ON "LineItem" ("tenant_id");

CREATE INDEX IF NOT EXISTS ix_bench_paymentattempt_tenant_id
    ON "PaymentAttempt" ("tenant_id");

-- ---------------------------------------------------------------------------
-- FK join-path indexes
-- ---------------------------------------------------------------------------

-- Invoice.supplier → Supplier.id  (list invoices by supplier, JOIN for display)
CREATE INDEX IF NOT EXISTS ix_bench_invoice_supplier
    ON "Invoice" ("supplier");

-- LineItem.invoice → Invoice.id  (fetch line items for an invoice)
CREATE INDEX IF NOT EXISTS ix_bench_lineitem_invoice
    ON "LineItem" ("invoice");

-- PaymentAttempt.invoice → Invoice.id  (fetch attempts for an invoice)
CREATE INDEX IF NOT EXISTS ix_bench_paymentattempt_invoice
    ON "PaymentAttempt" ("invoice");

-- SupplierBankAccount.supplier → Supplier.id  (lookup bank account for a supplier)
CREATE INDEX IF NOT EXISTS ix_bench_supplierbankaccount_supplier
    ON "SupplierBankAccount" ("supplier");
