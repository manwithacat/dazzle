# DERIVATION stream with lineage
module corpus.stream.derivation
app derivation_app "Derivation Streams"

stream ledger_entries:
  kind: FACT
  description: "Immutable ledger entries"

  schema LedgerCredited:
    entry_id: uuid required
    account_id: uuid required
    amount_minor: int required
    currency: str(3) required
    reference_type: str(50) required
    reference_id: uuid required
    credited_at: datetime required
    causation_id: uuid required

  schema LedgerDebited:
    entry_id: uuid required
    account_id: uuid required
    amount_minor: int required
    currency: str(3) required
    reference_type: str(50) required
    reference_id: uuid required
    debited_at: datetime required
    causation_id: uuid required

  partition_key: account_id
  ordering_scope: per_account
  t_event: credited_at

stream account_balances:
  kind: DERIVATION
  description: "Computed account balances"

  schema AccountBalanceCalculated:
    calculation_id: uuid required
    account_id: uuid required
    balance_minor: int required
    currency: str(3) required
    as_of_sequence: int required
    calculated_at: datetime required

  partition_key: account_id
  ordering_scope: per_account
  t_event: calculated_at
  t_process: calculated_at

  derives_from:
    streams: [ledger_entries]
    type: aggregate
    rebuild: incremental
    function: "sum(credits) - sum(debits) grouped by account_id"

  invariant: "Balance is always rebuildable from ledger entries"
  note: "DERIVATION streams carry lineage to source records"

stream daily_revenue:
  kind: DERIVATION
  description: "Daily revenue aggregations"

  schema DailyRevenueAggregated:
    calculation_id: uuid required
    revenue_date: date required
    total_revenue_minor: int required
    currency: str(3) required
    order_count: int required
    calculated_at: datetime required

  partition_key: revenue_date
  ordering_scope: per_day
  t_event: revenue_date
  t_process: calculated_at

  derives_from:
    streams: [ledger_entries]
    type: aggregate
    rebuild: windowed
    window: "1 day tumbling"
    function: "sum(amount_minor) where reference_type = 'order' grouped by date(credited_at)"

  invariant: "Revenue is always rebuildable from ledger entries"
