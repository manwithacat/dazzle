-- benchmarks/indexes.sql — scope-predicate and FK indexes for invoice_ops (SP6)
--
-- WHAT THIS IS
-- ---------------------
-- The Dazzle schema builder (src/dazzle/back/runtime/sa_schema.py) emits only
-- PK constraints and unique constraints (i.e. the "id" column index and any
-- "unique" field indexes from the DSL).  It does NOT create indexes on:
--   • tenant_id columns  — every list/read scope predicate filters on this
--   • FK columns used in JOIN paths  — Invoice.supplier, LineItem.invoice, etc.
--
-- This file adds single-column b-tree indexes on those columns so the
-- benchmark's `indexed` config can quantify their impact against `default`.
--
-- MEASURED RESULT — these indexes do NOT help
-- ---------------------
-- The SP6 benchmark ran every probe against both configs at scales up to
-- 1,000,000 invoices/tenant (3,000,000 Invoice rows).  The `indexed` config
-- (these indexes) is within measurement noise of `default` at every scale:
-- list/read/search/aggregate latency does NOT materially change.  In short:
-- a sorted list path needs a composite index (a single-column tenant_id index
-- cannot satisfy ORDER BY created_at), search's leading-wildcard LIKE cannot
-- use a b-tree, aggregate is a full scan, and at 3 tenants the tenant_id
-- predicate is only ~1/3 selective.  The real lever is a COMPOSITE
-- (tenant_id, created_at) index plus full-text (tsvector/GIN) for search.
-- See docs/reference/performance-envelope.md ("Where it degrades") for the
-- full mechanism + caveats, and issue #1202.  These
-- single-column indexes are kept only as the benchmark's negative-result
-- comparison config — do not treat them as a production fix.
--
-- Apply with:
--   psql $DB_URL -f benchmarks/indexes.sql

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
