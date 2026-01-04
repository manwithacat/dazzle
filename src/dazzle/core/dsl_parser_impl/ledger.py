"""
Ledger parser mixin for DAZZLE DSL.

Parses ledger and transaction blocks for TigerBeetle double-entry accounting.

DSL Syntax (v0.24.0):

    ledger CustomerWallet "Customer Wallet":
      intent: "Track customer prepaid balances"
      account_code: 1001
      ledger_id: 1
      account_type: asset
      currency: GBP
      flags: debits_must_not_exceed_credits
      sync_to: Customer.balance_cache
      metadata_mapping:
        customer_id: ref Customer.id

    transaction RecordPayment "Record Subscription Payment":
      intent: "Charge customer for monthly subscription with VAT"
      execution: async
      priority: high

      transfer revenue_portion:
        debit: CustomerWallet
        credit: Revenue
        amount: payment.amount * 0.80
        code: 1
        flags: linked

      transfer vat_portion:
        debit: CustomerWallet
        credit: VATLiability
        amount: payment.amount * 0.20
        code: 2

      idempotency_key: payment.id

      validation:
        - payment.amount > 0
        - payment.status == "authorized"
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import ir
from ..lexer import TokenType


class LedgerParserMixin:
    """Parser mixin for ledger and transaction blocks."""

    # Type stubs for methods provided by BaseParser
    if TYPE_CHECKING:
        expect: Any
        advance: Any
        match: Any
        skip_newlines: Any
        expect_identifier_or_keyword: Any
        current_token: Any
        file: Any

    def parse_ledger(self) -> ir.LedgerSpec:
        """
        Parse a ledger block.

        Grammar:
            ledger IDENTIFIER STRING? COLON NEWLINE INDENT
              [intent COLON STRING NEWLINE]
              account_code COLON NUMBER NEWLINE
              ledger_id COLON NUMBER NEWLINE
              account_type COLON IDENTIFIER NEWLINE
              currency COLON IDENTIFIER NEWLINE
              [flags COLON flag_list NEWLINE]
              [sync_to COLON dotted_path NEWLINE]
              [tenant_scoped COLON BOOL NEWLINE]
              [metadata_mapping COLON NEWLINE mapping_block]
            DEDENT

        Returns:
            LedgerSpec with parsed values
        """
        self.expect(TokenType.LEDGER)
        name = self.expect_identifier_or_keyword().value

        # Optional label
        label = None
        if self.match(TokenType.STRING):
            label = str(self.advance().value)

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        # Parse description/intent if present (docstring-style)
        intent = None
        if self.match(TokenType.STRING):
            intent = str(self.advance().value)
            self.skip_newlines()

        # Initialize required fields with defaults
        account_code = 0
        ledger_id = 0
        account_type = ir.AccountType.ASSET
        currency = "USD"
        flags: list[ir.AccountFlag] = []
        sync: ir.LedgerSyncSpec | None = None
        tenant_scoped = True
        metadata_mapping: dict[str, str] = {}

        # Parse ledger fields
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.INTENT):
                self.advance()
                self.expect(TokenType.COLON)
                intent = str(self.expect(TokenType.STRING).value)
                self.skip_newlines()

            elif self.match(TokenType.ACCOUNT_CODE):
                self.advance()
                self.expect(TokenType.COLON)
                account_code = int(self.expect(TokenType.NUMBER).value)
                self.skip_newlines()

            elif self.match(TokenType.LEDGER_ID):
                self.advance()
                self.expect(TokenType.COLON)
                ledger_id = int(self.expect(TokenType.NUMBER).value)
                self.skip_newlines()

            elif self.match(TokenType.ACCOUNT_TYPE):
                self.advance()
                self.expect(TokenType.COLON)
                account_type_str = str(self.expect_identifier_or_keyword().value)
                account_type = self._parse_account_type(account_type_str)
                self.skip_newlines()

            elif self.match(TokenType.CURRENCY):
                self.advance()
                self.expect(TokenType.COLON)
                currency = str(self.expect_identifier_or_keyword().value).upper()
                self.skip_newlines()

            elif self.match(TokenType.FLAGS):
                self.advance()
                self.expect(TokenType.COLON)
                flags = self._parse_account_flags()
                self.skip_newlines()

            elif self.match(TokenType.SYNC_TO):
                self.advance()
                self.expect(TokenType.COLON)
                sync = self._parse_ledger_sync()
                self.skip_newlines()

            elif self.match(TokenType.TENANT_SCOPED):
                self.advance()
                self.expect(TokenType.COLON)
                token = self.advance()
                tenant_scoped = token.type == TokenType.TRUE
                self.skip_newlines()

            elif self.match(TokenType.METADATA_MAPPING):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                metadata_mapping = self._parse_metadata_mapping()

            else:
                # Skip unknown field
                self.advance()
                if self.match(TokenType.COLON):
                    self.advance()
                    self._skip_to_next_ledger_field()

        self.expect(TokenType.DEDENT)

        return ir.LedgerSpec(
            name=str(name),
            label=label,
            intent=intent,
            account_code=account_code,
            ledger_id=ledger_id,
            account_type=account_type,
            currency=currency,
            flags=flags,
            sync=sync,
            tenant_scoped=tenant_scoped,
            metadata_mapping=metadata_mapping,
        )

    def parse_transaction(self) -> ir.TransactionSpec:
        """
        Parse a transaction block.

        Grammar:
            transaction IDENTIFIER STRING? COLON NEWLINE INDENT
              [intent COLON STRING NEWLINE]
              [execution COLON IDENTIFIER NEWLINE]
              [priority COLON IDENTIFIER NEWLINE]
              [timeout COLON NUMBER NEWLINE]
              (transfer IDENTIFIER COLON NEWLINE transfer_block)*
              idempotency_key COLON expression NEWLINE
              [validation COLON NEWLINE validation_block]
            DEDENT

        Returns:
            TransactionSpec with parsed values
        """
        self.expect(TokenType.TRANSACTION)
        name = self.expect_identifier_or_keyword().value

        # Optional label
        label = None
        if self.match(TokenType.STRING):
            label = str(self.advance().value)

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        # Parse description/intent if present
        intent = None
        if self.match(TokenType.STRING):
            intent = str(self.advance().value)
            self.skip_newlines()

        # Initialize fields
        transfers: list[ir.TransferSpec] = []
        idempotency_key = ""
        validation: list[ir.ValidationRule] = []
        execution = ir.TransactionExecution.SYNC
        priority = ir.TransactionPriority.NORMAL
        timeout_ms = 5000

        # Parse transaction fields
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.INTENT):
                self.advance()
                self.expect(TokenType.COLON)
                intent = str(self.expect(TokenType.STRING).value)
                self.skip_newlines()

            elif self.match(TokenType.TRANSFER):
                transfer = self._parse_transfer()
                transfers.append(transfer)

            elif self.match(TokenType.IDEMPOTENCY_KEY):
                self.advance()
                self.expect(TokenType.COLON)
                idempotency_key = self._parse_expression_string()
                self.skip_newlines()

            elif self.match(TokenType.VALIDATION):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                validation = self._parse_validation_rules()

            elif self.match(TokenType.EXECUTION):
                self.advance()
                self.expect(TokenType.COLON)
                exec_str = str(self.expect_identifier_or_keyword().value)
                execution = self._parse_execution_mode(exec_str)
                self.skip_newlines()

            elif self.match(TokenType.PRIORITY):
                self.advance()
                self.expect(TokenType.COLON)
                priority_str = str(self.expect_identifier_or_keyword().value)
                priority = self._parse_priority(priority_str)
                self.skip_newlines()

            elif self.match(TokenType.TIMEOUT):
                self.advance()
                self.expect(TokenType.COLON)
                timeout_ms = int(self.expect(TokenType.NUMBER).value)
                self.skip_newlines()

            else:
                # Skip unknown field
                self.advance()
                if self.match(TokenType.COLON):
                    self.advance()
                    self._skip_to_next_transaction_field()

        self.expect(TokenType.DEDENT)

        return ir.TransactionSpec(
            name=str(name),
            label=label,
            intent=intent,
            transfers=transfers,
            idempotency_key=idempotency_key,
            validation=validation,
            execution=execution,
            priority=priority,
            timeout_ms=timeout_ms,
        )

    def _parse_transfer(self) -> ir.TransferSpec:
        """
        Parse a single transfer block.

        Grammar:
            transfer IDENTIFIER COLON NEWLINE INDENT
              debit COLON IDENTIFIER NEWLINE
              credit COLON IDENTIFIER NEWLINE
              amount COLON expression NEWLINE
              code COLON NUMBER NEWLINE
              [flags COLON flag_list NEWLINE]
              [pending_id COLON STRING NEWLINE]
              [user_data COLON NEWLINE user_data_block]
            DEDENT
        """
        self.expect(TokenType.TRANSFER)
        name = str(self.expect_identifier_or_keyword().value)
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        # Initialize fields
        debit_ledger = ""
        credit_ledger = ""
        amount: ir.AmountExpr = ir.LiteralValue(value=0)
        code = 1
        flags: list[ir.TransferFlag] = []
        pending_id: str | None = None
        user_data: dict[str, str] = {}

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.DEBIT):
                self.advance()
                self.expect(TokenType.COLON)
                debit_ledger = str(self.expect_identifier_or_keyword().value)
                self.skip_newlines()

            elif self.match(TokenType.CREDIT):
                self.advance()
                self.expect(TokenType.COLON)
                credit_ledger = str(self.expect_identifier_or_keyword().value)
                self.skip_newlines()

            elif self.match(TokenType.AMOUNT):
                self.advance()
                self.expect(TokenType.COLON)
                amount = self._parse_amount_expression()
                self.skip_newlines()

            elif self.match(TokenType.CODE):
                self.advance()
                self.expect(TokenType.COLON)
                code = int(self.expect(TokenType.NUMBER).value)
                self.skip_newlines()

            elif self.match(TokenType.FLAGS):
                self.advance()
                self.expect(TokenType.COLON)
                flags = self._parse_transfer_flags()
                self.skip_newlines()

            elif self.match(TokenType.PENDING_ID):
                self.advance()
                self.expect(TokenType.COLON)
                pending_id = str(self.expect(TokenType.STRING).value)
                self.skip_newlines()

            elif self.match(TokenType.USER_DATA):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                user_data = self._parse_user_data()

            else:
                # Skip unknown
                self.advance()

        self.expect(TokenType.DEDENT)

        return ir.TransferSpec(
            name=name,
            debit_ledger=debit_ledger,
            credit_ledger=credit_ledger,
            amount=amount,
            code=code,
            flags=flags,
            pending_id=pending_id,
            user_data=user_data,
        )

    def _parse_account_type(self, type_str: str) -> ir.AccountType:
        """Parse account type string to enum."""
        type_map = {
            "asset": ir.AccountType.ASSET,
            "liability": ir.AccountType.LIABILITY,
            "equity": ir.AccountType.EQUITY,
            "revenue": ir.AccountType.REVENUE,
            "expense": ir.AccountType.EXPENSE,
        }
        return type_map.get(type_str.lower(), ir.AccountType.ASSET)

    def _parse_account_flags(self) -> list[ir.AccountFlag]:
        """Parse account flags (comma-separated or single)."""
        flags: list[ir.AccountFlag] = []
        flag_map = {
            "debits_must_not_exceed_credits": ir.AccountFlag.DEBITS_MUST_NOT_EXCEED_CREDITS,
            "credits_must_not_exceed_debits": ir.AccountFlag.CREDITS_MUST_NOT_EXCEED_DEBITS,
            "linked": ir.AccountFlag.LINKED,
            "history": ir.AccountFlag.HISTORY,
        }

        while not self.match(TokenType.NEWLINE, TokenType.DEDENT, TokenType.EOF):
            token = self.current_token()
            flag_str = str(token.value).lower()
            if flag_str in flag_map:
                flags.append(flag_map[flag_str])
            self.advance()
            if self.match(TokenType.COMMA):
                self.advance()
            else:
                break

        return flags

    def _parse_transfer_flags(self) -> list[ir.TransferFlag]:
        """Parse transfer flags (comma-separated or single)."""
        flags: list[ir.TransferFlag] = []
        flag_map = {
            "linked": ir.TransferFlag.LINKED,
            "pending": ir.TransferFlag.PENDING,
            "post_pending": ir.TransferFlag.POST_PENDING,
            "void_pending": ir.TransferFlag.VOID_PENDING,
            "balancing": ir.TransferFlag.BALANCING,
        }

        while not self.match(TokenType.NEWLINE, TokenType.DEDENT, TokenType.EOF):
            token = self.current_token()
            flag_str = str(token.value).lower()
            if flag_str in flag_map:
                flags.append(flag_map[flag_str])
            self.advance()
            if self.match(TokenType.COMMA):
                self.advance()
            else:
                break

        return flags

    def _parse_execution_mode(self, mode_str: str) -> ir.TransactionExecution:
        """Parse execution mode string."""
        mode_map = {
            "sync": ir.TransactionExecution.SYNC,
            "async": ir.TransactionExecution.ASYNC,
        }
        return mode_map.get(mode_str.lower(), ir.TransactionExecution.SYNC)

    def _parse_priority(self, priority_str: str) -> ir.TransactionPriority:
        """Parse priority string."""
        priority_map = {
            "critical": ir.TransactionPriority.CRITICAL,
            "high": ir.TransactionPriority.HIGH,
            "normal": ir.TransactionPriority.NORMAL,
            "low": ir.TransactionPriority.LOW,
        }
        return priority_map.get(priority_str.lower(), ir.TransactionPriority.NORMAL)

    def _parse_ledger_sync(self) -> ir.LedgerSyncSpec:
        """
        Parse ledger sync specification.

        Format: Entity.field [trigger: after_transfer|scheduled "cron"]
        """
        # Parse target: Entity.field
        target = self._parse_dotted_path_ledger()
        parts = target.split(".")
        target_entity = parts[0]
        target_field = ".".join(parts[1:]) if len(parts) > 1 else "balance"

        trigger = ir.SyncTrigger.AFTER_TRANSFER
        cron: str | None = None
        match_field = "id"

        # Check for inline trigger
        if self.match(TokenType.TRIGGER):
            self.advance()
            self.expect(TokenType.COLON)
            trigger_str = str(self.expect_identifier_or_keyword().value).lower()
            if trigger_str == "after_transfer":
                trigger = ir.SyncTrigger.AFTER_TRANSFER
            elif trigger_str == "scheduled":
                trigger = ir.SyncTrigger.SCHEDULED
                if self.match(TokenType.STRING):
                    cron = str(self.advance().value)
            elif trigger_str == "on_demand":
                trigger = ir.SyncTrigger.ON_DEMAND

        return ir.LedgerSyncSpec(
            target_entity=target_entity,
            target_field=target_field,
            trigger=trigger,
            cron=cron,
            match_field=match_field,
        )

    def _parse_metadata_mapping(self) -> dict[str, str]:
        """Parse metadata mapping block."""
        mapping: dict[str, str] = {}

        if not self.match(TokenType.INDENT):
            return mapping

        self.expect(TokenType.INDENT)

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            key = str(self.expect_identifier_or_keyword().value)
            self.expect(TokenType.COLON)

            # Parse value: "ref Entity.field" or just a string
            if self.match(TokenType.IDENTIFIER) and self.current_token().value == "ref":
                self.advance()  # consume 'ref'
                value = "ref " + self._parse_dotted_path_ledger()
            elif self.match(TokenType.STRING):
                value = str(self.advance().value)
            else:
                value = self._parse_dotted_path_ledger()

            mapping[key] = value
            self.skip_newlines()

        self.expect(TokenType.DEDENT)
        return mapping

    def _parse_validation_rules(self) -> list[ir.ValidationRule]:
        """Parse validation rules block."""
        rules: list[ir.ValidationRule] = []

        if not self.match(TokenType.INDENT):
            return rules

        self.expect(TokenType.INDENT)

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.MINUS):
                self.advance()
                expr = self._parse_expression_string()
                rules.append(ir.ValidationRule(expression=expr))
                self.skip_newlines()
            else:
                self.advance()

        self.expect(TokenType.DEDENT)
        return rules

    def _parse_user_data(self) -> dict[str, str]:
        """Parse user data mapping block."""
        data: dict[str, str] = {}

        if not self.match(TokenType.INDENT):
            return data

        self.expect(TokenType.INDENT)

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            key = str(self.expect_identifier_or_keyword().value)
            self.expect(TokenType.COLON)

            if self.match(TokenType.STRING):
                value = str(self.advance().value)
            else:
                value = str(self.expect_identifier_or_keyword().value)

            data[key] = value
            self.skip_newlines()

        self.expect(TokenType.DEDENT)
        return data

    def _parse_amount_expression(self) -> ir.AmountExpr:
        """
        Parse an amount expression.

        Supports:
        - Literals: 100, 50.5
        - Field references: payment.amount
        - Arithmetic: payment.amount * 0.80
        """
        left = self._parse_amount_term()

        # Check for arithmetic operator
        if self.match(TokenType.STAR, TokenType.SLASH, TokenType.PLUS, TokenType.MINUS):
            op_token = self.advance()
            op_map = {
                TokenType.STAR: ir.ArithmeticOperator.MULTIPLY,
                TokenType.SLASH: ir.ArithmeticOperator.DIVIDE,
                TokenType.PLUS: ir.ArithmeticOperator.ADD,
                TokenType.MINUS: ir.ArithmeticOperator.SUBTRACT,
            }
            operator = op_map[op_token.type]
            right = self._parse_amount_term()
            return ir.ArithmeticExpr(left=left, operator=operator, right=right)

        return left

    def _parse_amount_term(self) -> ir.AmountExpr:
        """Parse a single term in amount expression."""
        if self.match(TokenType.NUMBER):
            value_str = str(self.advance().value)
            if "." in value_str:
                return ir.LiteralValue(value=float(value_str))
            else:
                return ir.LiteralValue(value=int(value_str))

        # Field reference
        path_parts: list[str] = []
        path_parts.append(str(self.expect_identifier_or_keyword().value))

        while self.match(TokenType.DOT):
            self.advance()
            path_parts.append(str(self.expect_identifier_or_keyword().value))

        return ir.FieldReference(path=path_parts)

    def _parse_expression_string(self) -> str:
        """Parse expression until newline (as raw string)."""
        if self.match(TokenType.STRING):
            return str(self.advance().value)

        parts: list[str] = []
        while not self.match(TokenType.NEWLINE, TokenType.DEDENT, TokenType.EOF):
            token = self.current_token()
            parts.append(str(token.value))
            self.advance()

        return " ".join(parts)

    def _parse_dotted_path_ledger(self) -> str:
        """Parse a dotted path like Entity.field."""
        parts: list[str] = []
        parts.append(str(self.expect_identifier_or_keyword().value))

        while self.match(TokenType.DOT):
            self.advance()
            parts.append(str(self.expect_identifier_or_keyword().value))

        return ".".join(parts)

    def _skip_to_next_ledger_field(self) -> None:
        """Skip tokens until we reach the next ledger field or end of block."""
        while not self.match(
            TokenType.INTENT,
            TokenType.ACCOUNT_CODE,
            TokenType.LEDGER_ID,
            TokenType.ACCOUNT_TYPE,
            TokenType.CURRENCY,
            TokenType.FLAGS,
            TokenType.SYNC_TO,
            TokenType.TENANT_SCOPED,
            TokenType.METADATA_MAPPING,
            TokenType.DEDENT,
            TokenType.EOF,
        ):
            self.advance()
            self.skip_newlines()

    def _skip_to_next_transaction_field(self) -> None:
        """Skip tokens until we reach the next transaction field or end of block."""
        while not self.match(
            TokenType.INTENT,
            TokenType.TRANSFER,
            TokenType.IDEMPOTENCY_KEY,
            TokenType.VALIDATION,
            TokenType.EXECUTION,
            TokenType.PRIORITY,
            TokenType.TIMEOUT,
            TokenType.DEDENT,
            TokenType.EOF,
        ):
            self.advance()
            self.skip_newlines()
