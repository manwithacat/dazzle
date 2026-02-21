"""
SLA parser mixin for DAZZLE DSL.

Parses SLA/deadline escalation definitions.

DSL Syntax (v0.25.0):

    sla TicketResponse "Ticket Response SLA":
      entity: SupportTicket
      starts_when: status -> open
      pauses_when: status = on_hold
      completes_when: status -> resolved
      tiers:
        warning: 4 hours
        breach: 8 hours
        critical: 24 hours
      business_hours:
        schedule: "Mon-Fri 09:00-17:00"
        timezone: "Europe/London"
      on_breach:
        notify: support_lead
        set: escalated = true
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import ir
from ..lexer import TokenType


class SLAParserMixin:
    """Parser mixin for SLA blocks."""

    if TYPE_CHECKING:
        expect: Any
        advance: Any
        match: Any
        skip_newlines: Any
        expect_identifier_or_keyword: Any
        current_token: Any
        file: Any
        _parse_construct_header: Any

    def parse_sla(self) -> ir.SLASpec:
        """Parse an SLA block."""
        name, title, _ = self._parse_construct_header(TokenType.SLA, allow_keyword_name=True)

        entity = ""
        starts_when = None
        pauses_when = None
        completes_when = None
        tiers: list[ir.SLATierSpec] = []
        business_hours = None
        on_breach = None

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

            elif tok.value == "starts_when":
                self.advance()
                self.expect(TokenType.COLON)
                starts_when = self._parse_sla_condition()
                self.skip_newlines()

            elif tok.value == "pauses_when":
                self.advance()
                self.expect(TokenType.COLON)
                pauses_when = self._parse_sla_condition()
                self.skip_newlines()

            elif tok.value == "completes_when":
                self.advance()
                self.expect(TokenType.COLON)
                completes_when = self._parse_sla_condition()
                self.skip_newlines()

            elif tok.value == "tiers":
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                tiers = self._parse_sla_tiers()
                self.skip_newlines()

            elif tok.value == "business_hours":
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                business_hours = self._parse_sla_business_hours()
                self.skip_newlines()

            elif tok.value == "on_breach":
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                on_breach = self._parse_sla_breach_action()
                self.skip_newlines()

            else:
                self.advance()
                self.skip_newlines()

        if self.match(TokenType.DEDENT):
            self.advance()

        return ir.SLASpec(
            name=name,
            title=title,
            entity=entity,
            starts_when=starts_when,
            pauses_when=pauses_when,
            completes_when=completes_when,
            tiers=tiers,
            business_hours=business_hours,
            on_breach=on_breach,
        )

    def _parse_sla_condition(self) -> ir.SLAConditionSpec:
        """Parse an SLA condition: field -> value or field = value."""
        field = self.expect_identifier_or_keyword().value

        if self.match(TokenType.ARROW):
            self.advance()
            operator = "->"
        elif self.match(TokenType.EQUALS):
            self.advance()
            operator = "="
        else:
            operator = "->"
            value = self.expect_identifier_or_keyword().value
            return ir.SLAConditionSpec(field=field, operator=operator, value=value)

        value = self.expect_identifier_or_keyword().value
        return ir.SLAConditionSpec(field=field, operator=operator, value=value)

    def _parse_sla_tiers(self) -> list[ir.SLATierSpec]:
        """Parse SLA tier definitions."""
        tiers: list[ir.SLATierSpec] = []

        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break

            tier_name = self.expect_identifier_or_keyword().value
            self.expect(TokenType.COLON)
            duration_value = int(self.expect(TokenType.NUMBER).value)
            duration_unit = self.expect_identifier_or_keyword().value

            tiers.append(
                ir.SLATierSpec(
                    name=tier_name,
                    duration_value=duration_value,
                    duration_unit=duration_unit,
                )
            )
            self.skip_newlines()

        if self.match(TokenType.DEDENT):
            self.advance()

        return tiers

    def _parse_sla_business_hours(self) -> ir.BusinessHoursSpec:
        """Parse business hours block."""
        schedule = ""
        timezone = "UTC"

        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break

            tok = self.current_token()
            if tok.value == "schedule":
                self.advance()
                self.expect(TokenType.COLON)
                schedule = str(self.expect(TokenType.STRING).value)
                self.skip_newlines()
            elif tok.value == "timezone":
                self.advance()
                self.expect(TokenType.COLON)
                timezone = str(self.expect(TokenType.STRING).value)
                self.skip_newlines()
            else:
                self.advance()
                self.skip_newlines()

        if self.match(TokenType.DEDENT):
            self.advance()

        return ir.BusinessHoursSpec(schedule=schedule, timezone=timezone)

    def _parse_sla_breach_action(self) -> ir.SLABreachActionSpec:
        """Parse on_breach block."""
        notify_role = None
        field_assignments: list[ir.FieldAssignment] = []

        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break

            tok = self.current_token()
            if tok.value == "notify":
                self.advance()
                self.expect(TokenType.COLON)
                notify_role = self.expect_identifier_or_keyword().value
                self.skip_newlines()
            elif tok.value == "set":
                self.advance()
                self.expect(TokenType.COLON)
                field_name = self.expect_identifier_or_keyword().value
                self.expect(TokenType.EQUALS)
                value = self.expect_identifier_or_keyword().value
                field_assignments.append(ir.FieldAssignment(field_path=field_name, value=value))
                self.skip_newlines()
            else:
                self.advance()
                self.skip_newlines()

        if self.match(TokenType.DEDENT):
            self.advance()

        return ir.SLABreachActionSpec(
            notify_role=notify_role,
            field_assignments=field_assignments,
        )
