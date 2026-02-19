"""
View parser mixin for DAZZLE DSL.

Parses read-only view definitions for dashboards and reports.

DSL Syntax (v0.25.0):

    view MonthlySales "Monthly Sales Summary":
      source: Order
      filter: status = completed
      group_by: [customer, month(created_at)]
      fields:
        customer: ref Customer
        month: str
        total_amount: sum(amount)
        order_count: count()
        avg_order: avg(amount)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import ir
from ..lexer import TokenType


class ViewParserMixin:
    """Parser mixin for view blocks."""

    if TYPE_CHECKING:
        expect: Any
        advance: Any
        match: Any
        skip_newlines: Any
        expect_identifier_or_keyword: Any
        current_token: Any
        file: Any
        parse_type_spec: Any
        parse_condition_expr: Any

    def parse_view(self) -> ir.ViewSpec:
        """
        Parse a view block.

        Grammar:
            view IDENTIFIER STRING? COLON NEWLINE INDENT
              source COLON IDENTIFIER NEWLINE
              [filter COLON condition_expr NEWLINE]
              [group_by COLON LBRACKET identifier_list RBRACKET NEWLINE]
              [fields COLON NEWLINE INDENT
                (IDENTIFIER COLON (type | computed_expr) NEWLINE)*
              DEDENT]
            DEDENT

        Returns:
            ViewSpec with parsed values
        """
        self.expect(TokenType.VIEW)
        name = self.expect_identifier_or_keyword().value

        title = None
        if self.match(TokenType.STRING):
            title = str(self.advance().value)

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        source_entity = ""
        filter_condition = None
        group_by: list[str] = []
        fields: list[ir.ViewFieldSpec] = []
        date_field: str | None = None
        time_bucket: ir.TimeBucket | None = None

        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break

            if self.match(TokenType.SOURCE):
                self.advance()
                self.expect(TokenType.COLON)
                source_entity = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            elif self.match(TokenType.FILTER):
                self.advance()
                self.expect(TokenType.COLON)
                filter_condition = self.parse_condition_expr()
                self.skip_newlines()

            elif self.match(TokenType.GROUP_BY):
                self.advance()
                self.expect(TokenType.COLON)
                group_by = self._parse_view_identifier_list()
                self.skip_newlines()

            # date_field: created_at
            elif self.match(TokenType.DATE_FIELD):
                self.advance()
                self.expect(TokenType.COLON)
                date_field = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            # time_bucket: month
            elif self.match(TokenType.TIME_BUCKET):
                self.advance()
                self.expect(TokenType.COLON)
                bucket_token = self.expect_identifier_or_keyword()
                time_bucket = ir.TimeBucket(bucket_token.value)
                self.skip_newlines()

            elif self.match(TokenType.FIELD):
                # fields: block
                self.advance()
                # Check if this is "fields:" block header
                if self.match(TokenType.COLON):
                    self.advance()
                    self.skip_newlines()
                    self.expect(TokenType.INDENT)
                    fields = self._parse_view_fields()
                else:
                    self.skip_newlines()
            elif self.match(TokenType.FIELDS):
                # fields: block (keyword token)
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                fields = self._parse_view_fields()
            else:
                # Try identifier as "fields:" without keyword
                token = self.current_token()
                if token.type == TokenType.IDENTIFIER and token.value == "fields":
                    self.advance()
                    self.expect(TokenType.COLON)
                    self.skip_newlines()
                    self.expect(TokenType.INDENT)
                    fields = self._parse_view_fields()
                else:
                    self.advance()
                    self.skip_newlines()

        if self.match(TokenType.DEDENT):
            self.advance()

        return ir.ViewSpec(
            name=name,
            title=title,
            source_entity=source_entity,
            filter_condition=filter_condition,
            group_by=group_by,
            fields=fields,
            date_field=date_field,
            time_bucket=time_bucket,
        )

    def _parse_view_identifier_list(self) -> list[str]:
        """Parse a bracketed or plain identifier list, supporting function calls like month(x)."""
        items: list[str] = []
        if self.match(TokenType.LBRACKET):
            self.advance()
            while not self.match(TokenType.RBRACKET, TokenType.EOF):
                item = self.expect_identifier_or_keyword().value
                # Handle function call syntax like month(created_at)
                if self.match(TokenType.LPAREN):
                    self.advance()
                    arg = self.expect_identifier_or_keyword().value
                    self.expect(TokenType.RPAREN)
                    item = f"{item}({arg})"
                items.append(item)
                if self.match(TokenType.COMMA):
                    self.advance()
            if self.match(TokenType.RBRACKET):
                self.advance()
        else:
            item = self.expect_identifier_or_keyword().value
            items.append(item)
        return items

    def _parse_view_fields(self) -> list[ir.ViewFieldSpec]:
        """Parse view field definitions within the fields: block."""
        fields: list[ir.ViewFieldSpec] = []
        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break

            field_name = self.expect_identifier_or_keyword().value
            self.expect(TokenType.COLON)

            # Check for aggregate function: sum(x), count(), avg(x), etc.
            expression = None
            field_type = None

            if self.match(
                TokenType.SUM, TokenType.AVG, TokenType.MIN, TokenType.MAX, TokenType.COUNT
            ):
                expression = self._parse_view_computed_expr()
            else:
                # Parse as a type
                field_type = self.parse_type_spec()

            fields.append(
                ir.ViewFieldSpec(
                    name=field_name,
                    expression=expression,
                    field_type=field_type,
                )
            )
            self.skip_newlines()

        if self.match(TokenType.DEDENT):
            self.advance()
        return fields

    def _parse_view_computed_expr(self) -> ir.AggregateCall:
        """Parse an aggregate expression like sum(amount) or count()."""
        func_map = {
            TokenType.SUM: ir.AggregateFunction.SUM,
            TokenType.AVG: ir.AggregateFunction.AVG,
            TokenType.MIN: ir.AggregateFunction.MIN,
            TokenType.MAX: ir.AggregateFunction.MAX,
            TokenType.COUNT: ir.AggregateFunction.COUNT,
        }

        token = self.current_token()
        func = func_map.get(token.type, ir.AggregateFunction.COUNT)
        self.advance()

        self.expect(TokenType.LPAREN)
        path_parts: list[str] = []
        if not self.match(TokenType.RPAREN):
            path_parts.append(self.expect_identifier_or_keyword().value)
            while self.match(TokenType.DOT):
                self.advance()
                path_parts.append(self.expect_identifier_or_keyword().value)
        self.expect(TokenType.RPAREN)

        # count() with no args uses wildcard path
        field_ref = ir.FieldReference(path=path_parts if path_parts else ["*"])

        return ir.AggregateCall(
            function=func,
            field=field_ref,
        )
