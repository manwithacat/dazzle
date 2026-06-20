"""benchmarks/seed.py — invoice_ops dataset seeder (SP6).

Bulk-loads the invoice_ops schema with deterministic, reproducible data using
PostgreSQL COPY for maximum throughput.  Designed so seeding time does not
dominate the latency measurements in subsequent benchmark phases.

Usage::

    python -m benchmarks.seed --db postgresql://localhost/dazzle_invoice_ops_bench \\
        --tenants 10 --invoices-per-tenant 1000

Public API::

    seed(db_url, tenants, invoices_per_tenant) -> dict[str, int]
"""

from __future__ import annotations

import argparse
import logging
import os
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Fixed namespace for uuid5 — guarantees identical ids across runs.
_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # uuid.NAMESPACE_URL

# Fixed seed timestamp — all created_at / updated_at values are identical
# so seeding latency is irrelevant to the benchmark.
_TS = datetime(2024, 1, 15, 9, 0, 0, tzinfo=UTC)
_TS_STR = _TS.isoformat()

# Roles seeded per tenant (one User row per role).
_ROLES: list[str] = ["requester", "approver", "finance", "auditor", "tenant_admin", "finance_admin"]

# Invoice status values (cycle through for spread).
_INVOICE_STATUSES: list[str] = [
    "draft",
    "submitted",
    "approved",
    "partially_paid",
    "rejected",
    "disputed",
    "paid",
]

# Regions for tenants / suppliers.
_REGIONS: list[str] = ["emea", "amer", "apac"]

# Number of suppliers per tenant.
_SUPPLIERS_PER_TENANT: int = 20

# Average line items per invoice.
_LINE_ITEMS_PER_INVOICE: int = 2

# One PaymentAttempt per N invoices.
_PAYMENT_ATTEMPT_RATIO: int = 10

# Path to the invoice_ops example app (for load_target_metadata CWD).
_INVOICE_OPS_DIR = Path(__file__).resolve().parent.parent / "examples" / "invoice_ops"


# ---------------------------------------------------------------------------
# ID helpers
# ---------------------------------------------------------------------------


def _uid(*parts: str) -> uuid.UUID:
    """Return a deterministic UUID5 from the given string parts."""
    return uuid.uuid5(_NS, ":".join(parts))


# ---------------------------------------------------------------------------
# Row generators
# ---------------------------------------------------------------------------


def _build_tenants(n: int) -> list[tuple[Any, ...]]:
    """Return ``n`` Tenant row tuples.

    Columns: id, name, slug, region, status, created_at
    """
    rows: list[tuple[Any, ...]] = []
    for i in range(n):
        tid = _uid("tenant", str(i))
        name = f"Tenant {i:04d}"
        slug = f"tenant-{i:04d}"
        region = _REGIONS[i % len(_REGIONS)]
        rows.append((str(tid), name, slug, region, "active", _TS_STR))
    return rows


def _build_users(tenant_ids: list[str]) -> list[tuple[Any, ...]]:
    """Return one User row per role per tenant.

    Columns: id, email, name, tenant_id, created_at
    """
    rows: list[tuple[Any, ...]] = []
    for t_idx, tid in enumerate(tenant_ids):
        for role in _ROLES:
            uid = _uid("user", tid, role)
            email = f"{role}.t{t_idx:04d}@bench.invalid"
            name = f"{role.title()} (tenant {t_idx:04d})"
            rows.append((str(uid), email, name, tid, _TS_STR))
    return rows


def _build_suppliers(tenant_ids: list[str]) -> list[tuple[Any, ...]]:
    """Return ``_SUPPLIERS_PER_TENANT`` Supplier rows per tenant.

    Columns: id, tenant_id, name, contact_email, region, created_at, updated_at
    """
    rows: list[tuple[Any, ...]] = []
    for tid in tenant_ids:
        for s_idx in range(_SUPPLIERS_PER_TENANT):
            sid = _uid("supplier", tid, str(s_idx))
            name = f"Supplier {s_idx:03d} / {tid[:8]}"
            contact_email = f"accounts{s_idx:03d}@supplier-{tid[:8]}.invalid"
            region = _REGIONS[s_idx % len(_REGIONS)]
            rows.append((str(sid), tid, name, contact_email, region, _TS_STR, _TS_STR))
    return rows


def _build_supplier_bank_accounts(
    supplier_rows: list[tuple[Any, ...]],
) -> list[tuple[Any, ...]]:
    """One SupplierBankAccount per Supplier.

    Columns: id, tenant_id, supplier, bank_account_ref, account_name, iban, created_at, updated_at

    ``supplier_rows`` column order: id[0], tenant_id[1], name[2], …
    """
    rows: list[tuple[Any, ...]] = []
    for sr in supplier_rows:
        sid = sr[0]  # supplier.id
        tid = sr[1]  # supplier.tenant_id
        name = sr[2]  # supplier.name
        sba_id = _uid("sba", sid)
        bank_ref = f"REF-{sba_id.hex[:12].upper()}"
        iban = f"GB{sba_id.int % 10**18:018d}"[:34]
        rows.append((str(sba_id), tid, sid, bank_ref, name, iban, _TS_STR, _TS_STR))
    return rows


def _build_invoices(
    tenant_ids: list[str],
    supplier_id_map: dict[str, list[str]],
    invoices_per_tenant: int,
) -> list[tuple[Any, ...]]:
    """Return ``invoices_per_tenant`` Invoice rows per tenant.

    Columns: id, tenant_id, invoice_number, supplier, amount, currency,
             po_number, status, submitted_by, rejection_reason, dispute_reason,
             created_at, updated_at
    """
    rows: list[tuple[Any, ...]] = []
    for tid in tenant_ids:
        suppliers = supplier_id_map[tid]
        for i in range(invoices_per_tenant):
            inv_id = _uid("invoice", tid, str(i))
            invoice_number = f"INV-{tid[:6].upper()}-{i:06d}"
            supplier_id = suppliers[i % len(suppliers)]
            amount = round(100.0 + (i % 99_900) + 0.50, 2)
            currency = "GBP"
            po_number = f"PO-{i:06d}" if i % 3 == 0 else None
            status = _INVOICE_STATUSES[i % len(_INVOICE_STATUSES)]
            # submitted_by, rejection_reason, dispute_reason are nullable
            submitted_by = None
            rejection_reason = "Duplicate submission" if status == "rejected" else None
            dispute_reason = "Amount mismatch" if status == "disputed" else None
            rows.append(
                (
                    str(inv_id),
                    tid,
                    invoice_number,
                    supplier_id,
                    amount,
                    currency,
                    po_number,
                    status,
                    submitted_by,
                    rejection_reason,
                    dispute_reason,
                    _TS_STR,
                    _TS_STR,
                )
            )
    return rows


def _build_line_items(
    invoice_rows: list[tuple[Any, ...]],
) -> list[tuple[Any, ...]]:
    """Return approximately ``_LINE_ITEMS_PER_INVOICE`` LineItem rows per invoice.

    Columns: id, tenant_id, invoice, description, quantity, unit_amount, created_at

    ``invoice_rows`` column order: id[0], tenant_id[1], …
    """
    rows: list[tuple[Any, ...]] = []
    for inv in invoice_rows:
        inv_id = inv[0]
        tid = inv[1]
        for li_idx in range(_LINE_ITEMS_PER_INVOICE):
            li_id = _uid("lineitem", inv_id, str(li_idx))
            description = f"Service line {li_idx + 1}"
            quantity = 1 + (li_idx % 5)
            unit_amount = round(50.0 + li_idx * 12.50, 2)
            rows.append((str(li_id), tid, inv_id, description, quantity, unit_amount, _TS_STR))
    return rows


def _build_payment_attempts(
    invoice_rows: list[tuple[Any, ...]],
) -> list[tuple[Any, ...]]:
    """Return one PaymentAttempt per ``_PAYMENT_ATTEMPT_RATIO`` invoices.

    Columns: id, tenant_id, invoice, attempt_number, status, provider_reference,
             failure_reason, created_at

    ``invoice_rows`` column order: id[0], tenant_id[1], …
    """
    rows: list[tuple[Any, ...]] = []
    for idx, inv in enumerate(invoice_rows):
        if idx % _PAYMENT_ATTEMPT_RATIO != 0:
            continue
        inv_id = inv[0]
        tid = inv[1]
        pa_id = _uid("payment", inv_id, "0")
        pa_status = "succeeded" if idx % 20 != 0 else "failed"
        provider_ref = f"TXN-{pa_id.hex[:16].upper()}"
        failure_reason = "Insufficient funds" if pa_status == "failed" else None
        rows.append((str(pa_id), tid, inv_id, 1, pa_status, provider_ref, failure_reason, _TS_STR))
    return rows


# ---------------------------------------------------------------------------
# COPY bulk loader
# ---------------------------------------------------------------------------


def _copy_rows(
    cursor: Any,
    table: str,
    columns: list[str],
    rows: list[tuple[Any, ...]],
) -> None:
    """Bulk-load rows into *table* via ``COPY … FROM STDIN``."""
    if not rows:
        return
    col_list = ", ".join(f'"{c}"' for c in columns)
    sql = f'COPY "{table}" ({col_list}) FROM STDIN'
    with cursor.copy(sql) as copy:
        for row in rows:
            copy.write_row(row)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def ensure_schema(db_url: str) -> None:
    """Ensure the invoice_ops schema exists in *db_url*.

    Changes CWD to ``examples/invoice_ops`` temporarily so that
    ``load_target_metadata()`` can locate ``dazzle.toml``.  CWD is restored
    unconditionally.
    """
    import sqlalchemy

    from dazzle.http.alembic.metadata_loader import load_target_metadata

    original_cwd = os.getcwd()
    try:
        os.chdir(_INVOICE_OPS_DIR)
        metadata = load_target_metadata()
    finally:
        os.chdir(original_cwd)

    # Ensure SQLAlchemy uses the psycopg3 driver (not psycopg2).
    # Rewrite bare "postgresql://" to "postgresql+psycopg://" so the engine
    # does not fall back to the psycopg2 dialect.
    sa_url = db_url
    if sa_url.startswith("postgresql://") and "+psycopg" not in sa_url:
        sa_url = "postgresql+psycopg" + sa_url[len("postgresql") :]
    engine = sqlalchemy.create_engine(sa_url, echo=False)
    with engine.begin():
        metadata.create_all(engine)
    engine.dispose()
    logger.info("Schema ensured for %s (%d tables)", db_url, len(metadata.tables))


def seed(db_url: str, tenants: int, invoices_per_tenant: int) -> dict[str, int]:
    """Seed the invoice_ops benchmark database.

    1. Ensures the schema exists via ``load_target_metadata`` + ``create_all``.
    2. Truncates the seven entity tables (idempotent).
    3. Generates rows deterministically in memory (uuid5, fixed timestamp).
    4. Bulk-loads via PostgreSQL ``COPY`` in FK-dependency order.

    Args:
        db_url: SQLAlchemy-style DB URL, e.g.
            ``postgresql://localhost/dazzle_invoice_ops_bench``.
        tenants: Number of Tenant rows to create.
        invoices_per_tenant: Number of Invoice rows per tenant.

    Returns:
        Per-table row counts keyed by table name.
    """
    import psycopg

    ensure_schema(db_url)

    # Build conninfo from db_url (psycopg3 does not accept SQLAlchemy-style URLs
    # directly for psycopg.connect(), but it does for libpq-style connstrings).
    # We strip the driver prefix if present.
    pg_url = db_url
    for prefix in ("postgresql+psycopg://", "postgresql+psycopg2://", "postgresql://"):
        if pg_url.startswith(prefix):
            pg_url = "postgresql://" + pg_url[len(prefix) :]
            break

    t0 = time.perf_counter()

    # ------------------------------------------------------------------
    # 1. Generate all rows in memory
    # ------------------------------------------------------------------
    tenant_rows = _build_tenants(tenants)
    tenant_ids = [r[0] for r in tenant_rows]

    user_rows = _build_users(tenant_ids)

    supplier_rows = _build_suppliers(tenant_ids)
    # Map tenant_id → list of supplier ids for FK assignment.
    supplier_id_map: dict[str, list[str]] = {}
    for sr in supplier_rows:
        supplier_id_map.setdefault(sr[1], []).append(sr[0])

    sba_rows = _build_supplier_bank_accounts(supplier_rows)

    invoice_rows = _build_invoices(tenant_ids, supplier_id_map, invoices_per_tenant)
    line_item_rows = _build_line_items(invoice_rows)
    payment_attempt_rows = _build_payment_attempts(invoice_rows)

    logger.info(
        "Generated in-memory: %d tenants, %d users, %d suppliers, %d SBAs, "
        "%d invoices, %d line items, %d payment attempts",
        len(tenant_rows),
        len(user_rows),
        len(supplier_rows),
        len(sba_rows),
        len(invoice_rows),
        len(line_item_rows),
        len(payment_attempt_rows),
    )

    # ------------------------------------------------------------------
    # 2. Truncate + COPY in FK-dependency order
    # ------------------------------------------------------------------
    with psycopg.connect(pg_url, autocommit=False) as conn:
        with conn.cursor() as cur:
            # Truncate cascade respects FK ordering automatically.
            cur.execute(
                """
                TRUNCATE
                    "PaymentAttempt",
                    "LineItem",
                    "Invoice",
                    "SupplierBankAccount",
                    "Supplier",
                    "User",
                    "Tenant"
                CASCADE
                """
            )

            # Tenant (no FKs)
            _copy_rows(
                cur,
                "Tenant",
                ["id", "name", "slug", "region", "status", "created_at"],
                tenant_rows,
            )

            # User (FK → Tenant)
            _copy_rows(
                cur,
                "User",
                ["id", "email", "name", "tenant_id", "created_at"],
                user_rows,
            )

            # Supplier (FK → Tenant)
            _copy_rows(
                cur,
                "Supplier",
                ["id", "tenant_id", "name", "contact_email", "region", "created_at", "updated_at"],
                supplier_rows,
            )

            # SupplierBankAccount (FK → Tenant, Supplier)
            _copy_rows(
                cur,
                "SupplierBankAccount",
                [
                    "id",
                    "tenant_id",
                    "supplier",
                    "bank_account_ref",
                    "account_name",
                    "iban",
                    "created_at",
                    "updated_at",
                ],
                sba_rows,
            )

            # Invoice (FK → Tenant, Supplier, User[submitted_by nullable])
            _copy_rows(
                cur,
                "Invoice",
                [
                    "id",
                    "tenant_id",
                    "invoice_number",
                    "supplier",
                    "amount",
                    "currency",
                    "po_number",
                    "status",
                    "submitted_by",
                    "rejection_reason",
                    "dispute_reason",
                    "created_at",
                    "updated_at",
                ],
                invoice_rows,
            )

            # LineItem (FK → Tenant, Invoice)
            _copy_rows(
                cur,
                "LineItem",
                [
                    "id",
                    "tenant_id",
                    "invoice",
                    "description",
                    "quantity",
                    "unit_amount",
                    "created_at",
                ],
                line_item_rows,
            )

            # PaymentAttempt (FK → Tenant, Invoice)
            _copy_rows(
                cur,
                "PaymentAttempt",
                [
                    "id",
                    "tenant_id",
                    "invoice",
                    "attempt_number",
                    "status",
                    "provider_reference",
                    "failure_reason",
                    "created_at",
                ],
                payment_attempt_rows,
            )

        conn.commit()

    elapsed = time.perf_counter() - t0

    counts = {
        "Tenant": len(tenant_rows),
        "User": len(user_rows),
        "Supplier": len(supplier_rows),
        "SupplierBankAccount": len(sba_rows),
        "Invoice": len(invoice_rows),
        "LineItem": len(line_item_rows),
        "PaymentAttempt": len(payment_attempt_rows),
    }

    logger.info(
        "Seeded in %.2fs: %s",
        elapsed,
        ", ".join(f"{k}={v:,}" for k, v in counts.items()),
    )

    return counts


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed the invoice_ops benchmark database via PostgreSQL COPY."
    )
    parser.add_argument(
        "--db",
        required=True,
        metavar="URL",
        help="PostgreSQL connection URL (e.g. postgresql://localhost/dazzle_invoice_ops_bench)",
    )
    parser.add_argument(
        "--tenants",
        type=int,
        default=10,
        metavar="N",
        help="Number of tenants to seed (default: 10)",
    )
    parser.add_argument(
        "--invoices-per-tenant",
        type=int,
        default=1000,
        metavar="M",
        help="Number of invoices per tenant (default: 1000)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable DEBUG logging",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    t_wall = time.perf_counter()
    counts = seed(
        db_url=args.db,
        tenants=args.tenants,
        invoices_per_tenant=args.invoices_per_tenant,
    )
    elapsed = time.perf_counter() - t_wall

    total = sum(counts.values())
    print(f"\nSeeding complete in {elapsed:.2f}s  ({total:,} rows total)")
    for table, count in counts.items():
        print(f"  {table:30s} {count:>10,}")


if __name__ == "__main__":
    main()
