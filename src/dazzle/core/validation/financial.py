"""Money-field, account-code, transaction, and ledger validation.

Split verbatim from dazzle.core.validator per #1361.
"""

from .. import ir


def validate_money_fields(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """
    Validate that monetary fields use the correct type in FACT/INTENT streams.

    The Money type (amount_minor: int + currency: str) is REQUIRED for all
    monetary values in event payloads. Using float or decimal for money
    causes precision issues and JSON serialization problems.

    Checks:
    - Fields with money-like names in FACT/INTENT streams must use 'money' type
    - Rejects 'decimal' and warns about 'int' for money-like field names

    Returns:
        Tuple of (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Check HLESS streams
    for stream in appspec.streams:
        # Only check FACT and INTENT streams (not OBSERVATION or DERIVATION)
        if stream.record_kind not in (ir.RecordKind.FACT, ir.RecordKind.INTENT):
            continue

        for schema in stream.schemas:
            for field in schema.fields:
                if not ir.is_money_field_name(field.name):
                    continue

                # Check for forbidden types
                if field.type.kind == ir.FieldTypeKind.DECIMAL:
                    errors.append(
                        f"Stream '{stream.name}' schema '{schema.name}' field '{field.name}' "
                        f"uses 'decimal' type for monetary value. "
                        f"Use 'money' type instead (expands to currency + amount_minor:int). "
                        f"Rationale: decimal causes JSON serialization errors and precision issues."
                    )

                # Warn about raw int (might be intentional minor units, but not explicit)
                elif field.type.kind == ir.FieldTypeKind.INT:
                    # Only warn if it looks like a standalone money field without currency
                    # If there's a corresponding currency field, assume it's intentional
                    field_names = {f.name for f in schema.fields}
                    has_currency = any("currency" in name.lower() for name in field_names)
                    if not has_currency:
                        warnings.append(
                            f"Stream '{stream.name}' schema '{schema.name}' field '{field.name}' "
                            f"uses 'int' for monetary value without a currency field. "
                            f"Consider using 'money' type for explicit currency handling."
                        )

    # Also check entity fields (less strict - warning only)
    for entity in appspec.domain.entities:
        for field in entity.fields:
            if not ir.is_money_field_name(field.name):
                continue

            # For entities, using decimal is okay but money is preferred
            if field.type.kind == ir.FieldTypeKind.DECIMAL:
                # Check if there's a corresponding currency field
                field_names = {f.name for f in entity.fields}
                has_currency = any("currency" in name.lower() for name in field_names)
                if not has_currency:
                    warnings.append(
                        f"Entity '{entity.name}' field '{field.name}' uses 'decimal' "
                        f"for monetary value without a currency field. "
                        f"Consider using 'money' type or adding a currency field."
                    )

    return errors, warnings


def _validate_account_codes(
    appspec: ir.AppSpec,
    errors: list[str],
    warnings: list[str],
) -> tuple[set[str], dict[str, ir.LedgerSpec]]:
    """Validate ledger names, account codes, currency, sync targets, and intent.

    Returns:
        (ledger_names, ledger_by_name) for use by transaction validation.
    """
    ledger_names: set[str] = set()
    ledger_by_name: dict[str, ir.LedgerSpec] = {}
    account_codes_by_ledger_id: dict[int, set[int]] = {}

    for ledger in appspec.ledgers:
        # Check unique names
        if ledger.name in ledger_names:
            errors.append(f"Duplicate ledger name: '{ledger.name}'")
        ledger_names.add(ledger.name)
        ledger_by_name[ledger.name] = ledger

        # Check account_code uniqueness within ledger_id
        if ledger.ledger_id not in account_codes_by_ledger_id:
            account_codes_by_ledger_id[ledger.ledger_id] = set()
        if ledger.account_code in account_codes_by_ledger_id[ledger.ledger_id]:
            errors.append(
                f"Ledger '{ledger.name}': account_code {ledger.account_code} "
                f"is already used in ledger_id {ledger.ledger_id}"
            )
        account_codes_by_ledger_id[ledger.ledger_id].add(ledger.account_code)

        # Validate currency format
        if len(ledger.currency) != 3 or not ledger.currency.isalpha():
            errors.append(
                f"Ledger '{ledger.name}': currency '{ledger.currency}' "
                f"must be a 3-letter ISO 4217 code (e.g., GBP, USD, EUR)"
            )

        # Check sync target if specified
        if ledger.sync:
            entity_name = ledger.sync.target_entity
            entity = appspec.get_entity(entity_name)
            if not entity:
                errors.append(
                    f"Ledger '{ledger.name}': sync target entity '{entity_name}' not found"
                )
            else:
                field = entity.get_field(ledger.sync.target_field)
                if not field:
                    errors.append(
                        f"Ledger '{ledger.name}': sync target field "
                        f"'{entity_name}.{ledger.sync.target_field}' not found"
                    )

        # Warn about missing intent
        if not ledger.intent:
            warnings.append(
                f"Ledger '{ledger.name}': consider adding an 'intent' field "
                f"to document the business purpose"
            )

    return ledger_names, ledger_by_name


def _validate_transaction_transfers(
    txn: ir.TransactionSpec,
    ledger_names: set[str],
    ledger_by_name: dict[str, ir.LedgerSpec],
    errors: list[str],
    warnings: list[str],
) -> None:
    """Validate transfers within a single transaction."""
    transfer_codes: set[int] = set()
    for transfer in txn.transfers:
        # Check ledger references exist
        if transfer.debit_ledger not in ledger_names:
            errors.append(
                f"Transaction '{txn.name}' transfer '{transfer.name}': "
                f"debit ledger '{transfer.debit_ledger}' not found"
            )
        if transfer.credit_ledger not in ledger_names:
            errors.append(
                f"Transaction '{txn.name}' transfer '{transfer.name}': "
                f"credit ledger '{transfer.credit_ledger}' not found"
            )

        # Validate ledgers are in same ledger_id (TigerBeetle requirement)
        if transfer.debit_ledger in ledger_by_name and transfer.credit_ledger in ledger_by_name:
            debit_ledger = ledger_by_name[transfer.debit_ledger]
            credit_ledger = ledger_by_name[transfer.credit_ledger]
            if debit_ledger.ledger_id != credit_ledger.ledger_id:
                errors.append(
                    f"Transaction '{txn.name}' transfer '{transfer.name}': "
                    f"debit ledger '{transfer.debit_ledger}' "
                    f"(ledger_id={debit_ledger.ledger_id}) "
                    f"and credit ledger '{transfer.credit_ledger}' "
                    f"(ledger_id={credit_ledger.ledger_id}) "
                    f"must be in the same ledger_id"
                )

            # Validate currency match
            if debit_ledger.currency != credit_ledger.currency:
                errors.append(
                    f"Transaction '{txn.name}' transfer '{transfer.name}': "
                    f"currency mismatch between '{transfer.debit_ledger}' "
                    f"({debit_ledger.currency}) and '{transfer.credit_ledger}' "
                    f"({credit_ledger.currency})"
                )

        # Check transfer code uniqueness
        if transfer.code in transfer_codes:
            warnings.append(
                f"Transaction '{txn.name}' transfer '{transfer.name}': "
                f"code {transfer.code} is duplicated (consider unique codes for debugging)"
            )
        transfer_codes.add(transfer.code)

    # Multi-leg transaction validation
    if len(txn.transfers) > 1:
        for transfer in txn.transfers[:-1]:
            if not transfer.is_linked:
                warnings.append(
                    f"Transaction '{txn.name}' transfer '{transfer.name}': "
                    f"multi-leg transactions should use 'linked' flag on all "
                    f"but the last transfer "
                    f"to ensure atomic execution"
                )


def validate_ledgers(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """
    Validate TigerBeetle ledger and transaction specifications (v0.24.0).

    Checks:
    - Ledger names are unique
    - Account codes are unique within a ledger_id
    - Currency is valid ISO 4217 format
    - Transaction transfers reference valid ledgers
    - Transaction idempotency_key is defined
    - Transfer codes are unique within a transaction
    - Multi-leg transactions use 'linked' flag correctly

    Returns:
        Tuple of (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not appspec.ledgers:
        return errors, warnings

    ledger_names, ledger_by_name = _validate_account_codes(appspec, errors, warnings)

    for txn in appspec.transactions:
        if not txn.idempotency_key:
            errors.append(
                f"Transaction '{txn.name}': idempotency_key is required "
                f"for TigerBeetle transfer deduplication"
            )

        _validate_transaction_transfers(txn, ledger_names, ledger_by_name, errors, warnings)

        if not txn.intent:
            warnings.append(
                f"Transaction '{txn.name}': consider adding an 'intent' field "
                f"to document the business purpose"
            )

    return errors, warnings
