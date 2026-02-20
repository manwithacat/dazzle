"""
Approval parser mixin for DAZZLE DSL.

Parses first-class approval gate definitions.

DSL Syntax (v0.25.0):

    approval PurchaseApproval "Purchase Order Approval":
      entity: PurchaseOrder
      trigger: status -> pending_approval
      approver_role: finance_manager
      quorum: 1
      threshold: amount > 1000
      escalation:
        after: 48 hours
        to: finance_director
      auto_approve:
        when: amount <= 100
      outcomes:
        approved -> approved
        rejected -> rejected
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import ir
from ..lexer import TokenType


class ApprovalParserMixin:
    """Parser mixin for approval blocks."""

    if TYPE_CHECKING:
        expect: Any
        advance: Any
        match: Any
        skip_newlines: Any
        expect_identifier_or_keyword: Any
        current_token: Any
        file: Any
        parse_condition_expr: Any

    def parse_approval(self) -> ir.ApprovalSpec:
        """Parse an approval block."""
        name, title, _ = self._parse_construct_header(TokenType.APPROVAL, allow_keyword_name=True)

        entity = ""
        trigger_field = "status"
        trigger_value = ""
        approver_role = ""
        quorum = 1
        threshold = None
        escalation = None
        auto_approve = None
        outcomes: list[ir.ApprovalOutcomeSpec] = []

        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break

            tok = self.current_token()

            if tok.value == "entity":
                self.advance()
                self.expect(TokenType.COLON)
                entity = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            elif tok.value == "trigger":
                self.advance()
                self.expect(TokenType.COLON)
                trigger_field = self.expect_identifier_or_keyword().value
                self.expect(TokenType.ARROW)
                trigger_value = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            elif tok.value == "approver_role":
                self.advance()
                self.expect(TokenType.COLON)
                approver_role = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            elif tok.value == "quorum":
                self.advance()
                self.expect(TokenType.COLON)
                quorum = int(self.expect(TokenType.NUMBER).value)
                self.skip_newlines()

            elif tok.value == "threshold":
                self.advance()
                self.expect(TokenType.COLON)
                threshold = self.parse_condition_expr()
                self.skip_newlines()

            elif tok.value == "escalation":
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                escalation = self._parse_approval_escalation()
                self.skip_newlines()

            elif tok.value == "auto_approve":
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                auto_approve = self._parse_approval_auto()
                self.skip_newlines()

            elif tok.value == "outcomes":
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                outcomes = self._parse_approval_outcomes()
                self.skip_newlines()

            else:
                self.advance()
                self.skip_newlines()

        if self.match(TokenType.DEDENT):
            self.advance()

        return ir.ApprovalSpec(
            name=name,
            title=title,
            entity=entity,
            trigger_field=trigger_field,
            trigger_value=trigger_value,
            approver_role=approver_role,
            quorum=quorum,
            threshold=threshold,
            escalation=escalation,
            auto_approve=auto_approve,
            outcomes=outcomes,
        )

    def _parse_approval_escalation(self) -> ir.ApprovalEscalationSpec:
        """Parse escalation block: after + to."""
        after_value = 0
        after_unit = "hours"
        to_role = ""

        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break

            tok = self.current_token()
            if tok.value == "after":
                self.advance()
                self.expect(TokenType.COLON)
                after_value = int(self.expect(TokenType.NUMBER).value)
                after_unit = self.expect_identifier_or_keyword().value
                self.skip_newlines()
            elif tok.value == "to":
                self.advance()
                self.expect(TokenType.COLON)
                to_role = self.expect_identifier_or_keyword().value
                self.skip_newlines()
            else:
                self.advance()
                self.skip_newlines()

        if self.match(TokenType.DEDENT):
            self.advance()

        return ir.ApprovalEscalationSpec(
            after_value=after_value,
            after_unit=after_unit,
            to_role=to_role,
        )

    def _parse_approval_auto(self) -> ir.ConditionExpr:
        """Parse auto_approve block: when: condition."""
        condition = None

        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break

            tok = self.current_token()
            if tok.value == "when":
                self.advance()
                self.expect(TokenType.COLON)
                condition = self.parse_condition_expr()
                self.skip_newlines()
            else:
                self.advance()
                self.skip_newlines()

        if self.match(TokenType.DEDENT):
            self.advance()

        if condition is None:
            condition = ir.ConditionExpr(
                comparison=ir.Comparison(
                    field="",
                    operator=ir.ComparisonOperator.EQUALS,
                    value=ir.ConditionValue(literal=True),
                )
            )
        return condition

    def _parse_approval_outcomes(self) -> list[ir.ApprovalOutcomeSpec]:
        """Parse outcomes block: decision -> target_status lines."""
        outcomes: list[ir.ApprovalOutcomeSpec] = []

        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break

            decision = self.expect_identifier_or_keyword().value
            self.expect(TokenType.ARROW)
            target_status = self.expect_identifier_or_keyword().value
            outcomes.append(ir.ApprovalOutcomeSpec(decision=decision, target_status=target_status))
            self.skip_newlines()

        if self.match(TokenType.DEDENT):
            self.advance()

        return outcomes
